"""Benchmark every EdgeSight module on this machine and write results/benchmark.md.

    PYTHONPATH=src .venv/bin/python scripts/benchmark.py [--runs 20] [--no-vlm]
"""
import argparse
import base64
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from edgesight import config as cfg  # noqa: E402
from edgesight.hazard import FastLayer  # noqa: E402
from edgesight.ocr import Reader  # noqa: E402
from edgesight.vlm import VLM  # noqa: E402
from edgesight.voice import STT, TTS  # noqa: E402


def bench(fn, runs, warmup=2):
    for _ in range(warmup):
        fn()
    ts = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t) * 1000)
    ts.sort()
    return {"p50": statistics.median(ts), "p95": ts[min(len(ts) - 1, int(len(ts) * 0.95))], "mean": statistics.mean(ts)}


def gpu_name():
    try:
        return subprocess.check_output(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], text=True).strip()
    except Exception:
        return "none"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--no-vlm", action="store_true")
    a = ap.parse_args()

    def load(name):  # the app sends 1280 px wide frames for questions, so benchmark at that size
        im = cv2.imread(str(ROOT / "demo" / name))
        return cv2.resize(im, (1280, round(im.shape[0] * 1280 / im.shape[1])), interpolation=cv2.INTER_AREA)

    street, label = load("street.jpg"), load("label.jpg")
    rows = []

    fl = FastLayer(cfg)
    for size in (416, 640):
        cfg.DET_SIZE, cfg.DETECTOR = size, cfg.MODELS / f"yolo11n-{size}.onnx"
        f = FastLayer(cfg)
        r = bench(lambda: f.analyse(street), a.runs * 2)
        rows.append((f"Fast layer (YOLO11n {size}px + distance + tracker + alerts)", "CPU, ONNX Runtime", r))

    reader = Reader()
    rows.append(("OCR (RapidOCR PP-OCR, medicine box photo)", "CPU, ONNX Runtime", bench(lambda: reader.read(label), max(5, a.runs // 2))))

    tts = TTS(cfg.VOICE_DIR, cfg.DEFAULT_VOICE)
    sentence = "Careful: person straight ahead, one and a half metres."
    rows.append((f"TTS (Piper {cfg.DEFAULT_VOICE}, 1 sentence)", "CPU, ONNX Runtime", bench(lambda: tts.synthesize(sentence), a.runs)))

    wav = tts.synthesize("What is in front of me? Please read the label on this bottle.")
    stt = STT(cfg.STT_MODEL, cfg.CPU_THREADS)
    rows.append((f"STT (faster-whisper {cfg.STT_MODEL}, ~4 s utterance)", "CPU, int8 CTranslate2", bench(lambda: stt.transcribe(wav), max(5, a.runs // 4), 1)))

    if not a.no_vlm:
        vlm = VLM(cfg.OLLAMA, cfg.VLM_MODELS)
        # alternate images and questions so Ollama cannot reuse a cached answer between runs
        frames = []
        for name in ("street.jpg", "room.jpg"):
            im = load(name)
            frames.append((base64.b64encode(cv2.imencode(".jpg", im)[1]).decode(), FastLayer.summary(fl.measure(im))))
        questions = ["What is in front of me?", "How many people can you see?", "Describe what is on my right.",
                     "What are the people wearing?", "Is there any text I should know about?"]
        counter = iter(range(10**6))

        def ask(mode):
            i = next(counter)
            img, facts = frames[i % 2]
            vlm.chat(questions[i % len(questions)], img, facts=facts, mode=mode)

        for mode, name in cfg.VLM_MODELS.items():
            if not vlm.available().get(mode):
                continue
            r = bench(lambda: ask(mode), max(5, a.runs // 2), 1)
            rows.append((f"VLM answer ({name}, Q&A with detector facts)", "GPU via Ollama", r))

    lines = [
        "# EdgeSight benchmark (stand-in PC)", "",
        f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `scripts/benchmark.py --runs {a.runs}`.", "",
        f"- CPU: {platform.processor() or platform.machine()} ({_cpu()})",
        f"- GPU: {gpu_name()} (used only by Ollama for the VLM)",
        f"- Python {platform.python_version()}, {platform.system()} {platform.release()}", "",
        "| Module | Runs on | p50 (ms) | p95 (ms) | mean (ms) |", "|---|---|---:|---:|---:|",
    ]
    for name, where, r in rows:
        lines.append(f"| {name} | {where} | {r['p50']:.0f} | {r['p95']:.0f} | {r['mean']:.0f} |")
    lines += ["", "Stage II target: the same ONNX models compiled to HEF for the Hailo-10H on the ASUS UGen300."]
    out = ROOT / "results/benchmark.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def _cpu():
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


if __name__ == "__main__":
    main()
