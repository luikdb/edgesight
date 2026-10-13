"""EdgeSight HTTP server: serves the web app and the on-device AI pipeline as a small JSON API.

    browser (camera, mic, speakers)  <->  this server  <->  detector / OCR / VLM / STT / TTS
"""
import base64
import json
import mimetypes
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

from . import config as cfg
from .camera import Focus
from .hazard import PATH_HALF_ANGLE, FastLayer
from .metrics import Metrics, timer
from .ocr import Reader
from .router import HELP, route
from .vlm import REFUSAL, VLM, scrub_safety
from .voice import STT, TTS


def log(msg):
    print(f"[edgesight] {msg}", flush=True)


log("loading detector...")
fast = FastLayer(cfg)
log("loading OCR...")
reader = Reader()
log("loading speech-to-text...")
stt = STT(cfg.STT_MODEL, cfg.CPU_THREADS)
log("loading text-to-speech...")
tts = TTS(cfg.VOICE_DIR, cfg.DEFAULT_VOICE)
vlm = VLM(cfg.OLLAMA, cfg.VLM_MODELS)
metrics = Metrics(cfg.RESULTS / "latency.csv")
focus = Focus()
fast_lock = threading.Lock()  # tracker/alert state is per-stream

_net = {"t": 0.0, "online": None}


def internet_reachable():
    """Cached check used only for the 'offline' badge: proves nothing leaves the machine during the demo."""
    if time.time() - _net["t"] > 15:
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=0.6).close()
            _net["online"] = True
        except OSError:
            _net["online"] = False
        _net["t"] = time.time()
    return _net["online"]


def decode(jpeg: bytes):
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode image")
    return img


def handle_command(req):
    """Spoken (or typed) command + current frame -> what to say and any mode changes."""
    text, mode = req.get("text", ""), req.get("model", "edge")
    image_b64 = req.get("image", "")
    r = route(text)
    intent = r["intent"]
    out = {"intent": intent, "heard": text}

    if intent == "none":
        return {**out, "say": "I didn't catch that."}
    if intent == "stop":
        with fast_lock:
            fast.finder.set(None)
        return {**out, "say": "Stopped.", "find": None}
    if intent == "help":
        return {**out, "say": HELP}
    if intent == "repeat":
        return out
    if intent == "hazards":
        return {**out, "hazards": r["on"], "say": f"Hazard alerts {'on' if r['on'] else 'off'}."}

    img = decode(base64.b64decode(image_b64)) if image_b64 else None
    if img is None:
        return {**out, "say": "I can't see anything yet. Check the camera."}

    if intent in ("read", "read_label"):
        with timer(metrics, "ocr") as t:
            res = reader.read(img)
        out.update(ocr=res["lines"], ocr_ms=round(t.ms))
        if intent == "read":
            if not res["text"]:
                return {**out, "say": "I can't find any text. Try moving closer or adding more light."}
            return {**out, "say": res["text"].replace("\n", ". ")}
        with timer(metrics, "vlm", vlm.models.get(mode, "")) as t:
            say = vlm.read_label(res["text"], image_b64, mode)
        return {**out, "say": say, "vlm_ms": round(t.ms), "source": "OCR + VLM"}

    if intent == "safety":
        # never certify safety: refuse, then say what is visible so the user can decide
        with timer(metrics, "vlm", vlm.models.get(mode, "")) as t:
            seen = vlm.chat("Describe the road or path ahead in one short sentence: vehicles, people, crossings.", image_b64, [], "", mode)
        seen = scrub_safety(seen)
        if seen == REFUSAL:
            seen = ""
        return {**out, "say": f"{REFUSAL} {seen}".strip(), "vlm_ms": round(t.ms), "source": "rule + VLM"}

    if intent == "find" and r.get("cls"):
        with fast_lock:
            fast.finder.set(r["cls"])
        return {**out, "find": r["cls"], "say": f"Looking for the {r['cls']}. Move the camera slowly."}

    # describe / ask / find-for-something-the-detector-doesn't-know: VLM grounded on detector facts
    dets = fast.measure(img)
    facts = FastLayer.summary(dets)
    # describe always leads with any nearby hazard; other questions only for real danger
    safety = FastLayer.hazard_sentence(dets, ("danger", "warn") if intent == "describe" else ("danger",)) if req.get("hazards") else ""
    prompt = text
    if intent == "describe":
        prompt = f"{text}\nDescribe the scene in one short sentence of under 25 words: the main people or objects and where they are."
    history = req.get("history", [])
    if intent == "find":
        prompt = (f"Where is the {r['object']} in this image? Reply in one short sentence that says where it is "
                  "(for example which shelf or surface, and a clock direction), or say you can't see it.")
        history = []  # a lookup question should not drift into the previous conversation
    with timer(metrics, "vlm", vlm.models.get(mode, "")) as t:
        say = vlm.chat(prompt, image_b64, history, facts, mode)
    say = scrub_safety(say)  # the model must never certify safety, whatever the prompt says
    if safety:
        say = f"{safety} {say}"
    return {**out, "say": say, "facts": facts, "safety": safety, "vlm_ms": round(t.ms), "source": "VLM + detector"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self._send(200, {
                "detector": cfg.DETECTOR.name, "ocr": "RapidOCR (PP-OCR ONNX)", "stt": f"faster-whisper {cfg.STT_MODEL}",
                "tts": "Piper", "vlm": cfg.VLM_MODELS, "vlm_available": vlm.available(),
                "internet": internet_reachable(), "voices": tts.names(), "default_voice": tts.default,
                "hfov": cfg.CAMERA_HFOV_DEG, "path_half_angle": PATH_HALF_ANGLE,
                "uptime_s": round(time.time() - metrics.started)})
        if path == "/api/focus":
            return self._send(200, focus.state())
        if path == "/api/metrics":
            return self._send(200, metrics.summary())
        base = cfg.ROOT / "demo" if path.startswith("/demo/") else cfg.WEB
        rel = path.removeprefix("/demo/") if base != cfg.WEB else (path.lstrip("/") or "index.html")
        f = (base / rel).resolve()
        if base.resolve() not in f.parents or not f.is_file():
            return self._send(404, {"error": "not found"})
        self._send(200, f.read_bytes(), (mimetypes.guess_type(f.name)[0] or "application/octet-stream")
                   + ("; charset=utf-8" if f.suffix in (".html", ".js", ".css") else ""))

    def do_POST(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            if u.path == "/api/detect":
                img = decode(raw)
                with fast_lock, timer(metrics, "detector") as t:
                    dets, alert, target, guide = fast.analyse(img, hazards=q.get("hazards", "1") == "1")
                return self._send(200, {"dets": [d.to_dict() for d in dets], "alert": alert, "guide": guide,
                                        "target": target.to_dict() if target else None,
                                        "find": fast.finder.target, "ms": round(t.ms, 1),
                                        "frame": [img.shape[1], img.shape[0]]})
            if u.path == "/api/ocr":
                with timer(metrics, "ocr") as t:
                    res = reader.read(decode(raw))
                return self._send(200, {**res, "ms": round(t.ms)})
            if u.path == "/api/stt":
                with timer(metrics, "stt") as t:
                    res = stt.transcribe(raw)
                return self._send(200, {**res, "ms": round(t.ms)})
            if u.path == "/api/tts":
                req = json.loads(raw)
                with timer(metrics, "tts") as t:
                    wav = tts.synthesize(req["text"], req.get("voice"))
                return self._send(200, wav, "audio/wav")
            if u.path == "/api/focus":
                req = json.loads(raw or b"{}")
                return self._send(200, focus.apply(req.get("auto"), req.get("value")))
            if u.path == "/api/command":
                t0 = time.perf_counter()
                res = handle_command(json.loads(raw))
                res["total_ms"] = round((time.perf_counter() - t0) * 1000)
                return self._send(200, res)
            self._send(404, {"error": "not found"})
        except Exception as e:
            log(f"error on {u.path}: {e!r}")
            self._send(500, {"error": str(e)})

    def log_message(self, *args):
        pass


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return  # the tab was closed or reloaded mid-request; nothing to report
        super().handle_error(request, client_address)


def open_browser(url):
    import subprocess
    try:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        webbrowser.open(url)


def main():
    url = f"http://localhost:{cfg.PORT}"
    log(f"ready on {url}  detector={cfg.DETECTOR.name} stt={cfg.STT_MODEL} vlm={cfg.VLM_MODELS} "
        f"voices={len(tts.names())}")
    threading.Thread(target=vlm.warm_up, daemon=True).start()
    if "--no-browser" not in sys.argv:
        open_browser(url)
    Server((cfg.HOST, cfg.PORT), Handler).serve_forever()
