"""Understanding layer: a small vision-language model served locally by Ollama.

The VLM gets the camera frame plus facts measured by the fast layer (objects, clock
directions, distances) and any OCR text, so answers stay grounded and short.
"""
import json
import re
import urllib.request

SYSTEM = (
    "You are EdgeSight, a calm assistant for a blind or low-vision person. You see through their camera. "
    "Your reply is read aloud, so be brief: one short sentence, under 20 words, with no markdown, lists or emoji. "
    "Only give more, at most three short sentences, when the user asks for detail or to describe the scene. "
    "Answer exactly what was asked and nothing more. Give positions as clock directions (12 o'clock is straight ahead). "
    "Do not say whether there are or are not hazards or obstacles; the device's detector gives safety warnings separately. "
    "Never state distances or sizes in metres, centimetres, feet or inches. "
    "If you cannot see the thing that was asked about, say so briefly instead of guessing. "
    "Never identify a real person by name, even if you think you recognise them; say what they look like or are doing instead. "
    "Never tell the user that it is safe to cross a road or to walk somewhere."
)

READ_PROMPT = (
    "The user wants to know what this label or document says. OCR text from the image is below; it may contain "
    "errors. Using the image and the OCR text, give the key facts in plain speech: what it is, the name, any dose, "
    "strength or amount, directions, warnings and expiry date if present. Do not invent anything that is not "
    "visible. If it is unreadable, say so and suggest moving closer or adding light.\n\nOCR text:\n{ocr}"
)


SAFETY_CLAIM = re.compile(
    r"\b(it'?s|it is|this is|that is|that's|looks|seems|appears) (completely |totally |perfectly |pretty |quite )?(safe|clear|okay|ok)\b"
    r"|\b(safe|okay|ok|clear) to (cross|walk|go|proceed|step|move)\b"
    r"|\byou (can|may|could) (safely )?(cross|go|walk|proceed|step)\b"
    r"|\b(no|not any) (cars|traffic|vehicles) (are )?(coming|approaching)\b"
    r"|\b(road|street|path|crossing|crosswalk|way|area|intersection|sidewalk)( ahead| in front| in front of (you|me|us))? (is|looks|seems|appears) (completely |totally |perfectly |pretty |quite |all )?(safe|clear|free)\b", re.I)
REFUSAL = "I can't tell you it's safe. Please listen for traffic and use your cane or guide dog."


def makes_safety_claim(text):
    return bool(SAFETY_CLAIM.search(text or ""))


def scrub_safety(text):
    """Drop any sentence that certifies safety; keep the rest. If nothing is left, fall back to the refusal."""
    keep = [s for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s and not SAFETY_CLAIM.search(s)]
    return " ".join(keep) if keep else REFUSAL


def first_sentences(text, n):
    """Small models do not always obey 'one sentence'; enforce the spoken-answer length in code."""
    if not n:
        return text
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:n])


class VLM:
    def __init__(self, host, models):
        self.host, self.models = host, models

    def available(self):
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=2) as r:
                names = {m["name"] for m in json.load(r)["models"]}
            return {k: v in names for k, v in self.models.items()}
        except Exception:
            return {k: False for k in self.models}

    def chat(self, prompt, image_b64, history=(), facts="", mode="edge", max_tokens=60, max_sentences=2):
        user = prompt if not facts else f"{prompt}\n\n[Detector: {facts}]"
        messages = [{"role": "system", "content": SYSTEM}, *list(history)[-8:],
                    {"role": "user", "content": user, "images": [image_b64]}]
        body = {"model": self.models.get(mode, self.models["edge"]), "stream": False, "think": False,
                "keep_alive": "30m", "messages": messages, "options": {"temperature": 0.2, "num_predict": max_tokens}}
        req = urllib.request.Request(f"{self.host}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            text = json.load(r)["message"]["content"].strip()
        if text and text[-1] not in ".!?" and max(text.rfind(c) for c in ".!?") > 0:
            text = text[:max(text.rfind(c) for c in ".!?") + 1]  # drop a sentence cut off by the token cap
        return first_sentences(text, max_sentences)

    def warm_up(self, mode="edge"):
        """Load the model into memory at startup so the first real question is fast."""
        tiny = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
        try:
            self.chat("Say OK.", tiny, mode=mode)
        except Exception:
            pass

    def read_label(self, ocr_text, image_b64, mode="edge"):
        return self.chat(READ_PROMPT.format(ocr=ocr_text or "(no text found)"), image_b64, mode=mode, max_tokens=110, max_sentences=None)
