# EdgeSight benchmark (stand-in PC)

Generated 2026-10-13 19:57 by `scripts/benchmark.py --runs 20`.

- CPU: x86_64 (Intel(R) Core(TM) i7-7700 CPU @ 3.60GHz)
- GPU: NVIDIA GeForce RTX 2080 Ti (used only by Ollama for the VLM)
- Python 3.12.14, Linux 7.0.0-34-generic

| Module | Runs on | p50 (ms) | p95 (ms) | mean (ms) |
|---|---|---:|---:|---:|
| Fast layer (YOLO11n 416px + distance + tracker + alerts) | CPU, ONNX Runtime | 16 | 17 | 16 |
| Fast layer (YOLO11n 640px + distance + tracker + alerts) | CPU, ONNX Runtime | 41 | 50 | 42 |
| OCR (RapidOCR PP-OCR, medicine box photo) | CPU, ONNX Runtime | 1067 | 1117 | 1067 |
| TTS (Piper en_US-lessac-medium, 1 sentence) | CPU, ONNX Runtime | 106 | 125 | 107 |
| STT (faster-whisper small.en, ~4 s utterance) | CPU, int8 CTranslate2 | 1542 | 1720 | 1541 |
| VLM answer (qwen3.5:2b, Q&A with detector facts) | GPU via Ollama | 726 | 1091 | 800 |
| VLM answer (qwen3.5:9b, Q&A with detector facts) | GPU via Ollama | 1435 | 1814 | 1493 |

Stage II target: the same ONNX models compiled to HEF for the Hailo-10H on the ASUS UGen300.
