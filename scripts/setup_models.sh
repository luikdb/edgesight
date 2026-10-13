#!/usr/bin/env bash
# One-time setup: Python environment, the object detector (exported to ONNX), a Piper voice and the Ollama models.
# Large model files are not stored in the repository; this script fetches or builds them.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v uv >/dev/null || { echo "Install uv first: https://github.com/astral-sh/uv"; exit 1; }
command -v ollama >/dev/null || { echo "Install Ollama first: https://ollama.com"; exit 1; }

echo "== Python environment"
[ -d .venv ] || uv venv .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt

echo "== Text-to-speech voice"
mkdir -p models/voices
.venv/bin/python -m piper.download_voices en_US-lessac-medium --download-dir models/voices

echo "== Object detector: YOLO11n exported to ONNX (needs a one-off PyTorch install in a temporary environment)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
uv venv -q "$TMP/venv"
uv pip install -q --python "$TMP/venv/bin/python" ultralytics onnx onnxslim
for SIZE in 416 640; do
  (cd "$TMP" && ./venv/bin/yolo export model=yolo11n.pt format=onnx imgsz="$SIZE" simplify=True opset=17)
  mv "$TMP/yolo11n.onnx" "models/yolo11n-$SIZE.onnx"
done

echo "== Vision-language models (Ollama)"
ollama pull qwen3.5:2b
echo "Optional larger model:  ollama pull qwen3.5:9b"

echo "Done. Start the app with ./run.sh"
