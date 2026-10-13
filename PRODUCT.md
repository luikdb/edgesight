# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Existing codebase: plain static HTML, CSS and vanilla JS in `web/`, served by a small Python server (`src/edgesight/server.py`). No framework or build step. Keep it that way: the demo must run from one command on a stand-in PC and later on a laptop with the ASUS UGen300.

## Users

- **End user (the product's reason to exist):** a blind or low-vision person who wants to know what is around them, read labels and text, and be warned about obstacles, hands-free, with audio in and out. They do not rely on the screen. A low-vision user may use it, so a large-type "user view" must stay.
- **Primary audience of this screen, for the competition:** sighted judges (ASUS, Intel and Hailo AI experts) watching a 3-minute demo video of the real device running, and a stage demo if the team goes onsite. Judging weights: business potential and feasibility 35%, innovation 30%, practical value 25%, storytelling and presentation 10%.

## Product Purpose

EdgeSight is a low-cost, fully offline, hands-free assistant that gives blind and low-vision users instant hazard alerts and natural-language answers about their surroundings, with all AI running on the device and nothing in the cloud. It is a complement to a white cane or guide dog, never a replacement. Success for the competition is a Stage I proposal (due Wed 14 Oct 2026, 17:00 Taiwan time) that proves a runnable prototype, then Stage II porting to the ASUS UGen300 (Hailo-10H, 8 GB).

## Positioning

The only one that is fully offline, hazard-first and conversational at once. Seeing AI and Be My AI need the cloud for some or all features. OrCam MyEye is expensive and has no open Q&A. Envision is cloud-based and subscription-priced. Ray-Ban Meta glasses are general-purpose consumer devices. Hazards are detected by a fast on-device detector and never by the slower vision-language model.

## Operating Context

- Demo shape: the real app, running on a stand-in PC with a webcam and mic, screen-recorded for the video; Wi-Fi turned off on camera to prove "offline".
- Three demo moments: read a label aloud, answer a spoken question about a scene, warn about an obstacle. Voice output on all three.
- Layers: a fast layer (YOLO11n object detector, distance and direction, hazard logic, alert) on every frame; an understanding layer on request (faster-whisper speech-to-text, rule-based intent, RapidOCR, Qwen3.5 VLM through Ollama, Piper text-to-speech).
- The screen has two modes in code: Judge view (shows the on-device pipeline and live latency numbers) and User view (large controls, conversation only).

## Capabilities and Constraints

- Works today: live detection with distance estimate and clock direction, tracked objects, spoken hazard alerts with earcons, spoken command routing (describe, read, read label, find an object, hazards on or off, repeat, stop), 21 Piper voices, edge and quality VLM choice, online/offline indicator, live per-module latency, `results/benchmark.md`.
- Measured on the stand-in PC (i7-7700, RTX 2080 Ti), p50: detector 17 ms (416 px), OCR about 400 ms, TTS about 110 ms, speech-to-text about 1.5 s, VLM answer about 0.7 s (2B) and 1.6 s (9B).
- Not yet done: models compiled for the Hailo-10H, real-device UGen300 numbers, depth camera, user testing with blind users. Distance is estimated from known object size with a pinhole model, not measured, and is labelled as an estimate.
- Constraint: the UGen300 has 8 GB, so only small models fit.
- Safety constraint: never imply the device guarantees safe navigation or that it is safe to cross a road.

## Brand Commitments

- The name is **EdgeSight** (user confirmed). No existing logo, colours or typefaces to preserve; the identity is open.
- Language: English for deck and video.

## Evidence on Hand

- Real running prototype and real measured latencies in `results/benchmark.md` and `results/latency.csv`.
- Sample images in `demo/` are public-domain test images from the ultralytics package (a bus scene and a football scene), used only for development.
- No user-testing data, customer quotes, pricing or market numbers exist. Do not fabricate any.

## Product Principles

1. Hazards come from the fast detector, never from the language model, and the screen shows that separation.
2. Offline is the product: every claim on screen about local AI must be provable on screen (network indicator, measured numbers).
3. Audio is the real interface; the screen exists so judges and sighted helpers can see what the system sees and hears.
4. Say what is measured and what is estimated. Honesty about limits is part of the pitch.
5. Fast and unambiguous beats clever: in a 3-minute video every state must read at a glance.

## Accessibility & Inclusion

- Users are blind or low-vision: all feedback is spoken, with a screen-reader live region mirroring it, full keyboard control, visible focus, large touch targets in User view, no information carried by colour alone, and respect for reduced motion.
- Spatial audio cues (stereo pan) support direction without sight.
