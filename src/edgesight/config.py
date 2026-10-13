"""Paths, model choices and tunables. Override anything with environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
WEB = ROOT / "web"
RESULTS = ROOT / "results"

HOST = os.environ.get("EDGESIGHT_HOST", "127.0.0.1")
PORT = int(os.environ.get("EDGESIGHT_PORT", "8800"))

# Vision-language model served by Ollama. "edge" is sized for the UGen300's 8 GB;
# "quality" is a bigger model for comparison on the stand-in PC.
OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
VLM_MODELS = {
    "edge": os.environ.get("EDGESIGHT_VLM_EDGE", "qwen3.5:2b"),
    "quality": os.environ.get("EDGESIGHT_VLM_QUALITY", "qwen3.5:9b"),
}

# Object detector (YOLO11n exported to ONNX; the same file is the input to Hailo's compiler).
DET_SIZE = int(os.environ.get("EDGESIGHT_DET_SIZE", "416"))
DETECTOR = MODELS / f"yolo11n-{DET_SIZE}.onnx"
DET_CONF = 0.35
DET_IOU = 0.45

# Horizontal field of view of the camera, used to turn pixels into angles and metres.
# Logitech C920 is about 70 degrees; phone main cameras are usually 65-75.
CAMERA_HFOV_DEG = float(os.environ.get("EDGESIGHT_HFOV", "70"))

STT_MODEL = os.environ.get("EDGESIGHT_STT", "small.en")
VOICE_DIR = MODELS / "voices"
DEFAULT_VOICE = os.environ.get("EDGESIGHT_VOICE", "en_US-lessac-medium")

CPU_THREADS = int(os.environ.get("EDGESIGHT_THREADS", "4"))
