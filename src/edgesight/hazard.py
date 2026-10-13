"""Fast layer: object detection, distance/direction estimates, hazard alerts and object finding.

Everything here is deterministic and runs every frame (~20 ms on a 2017 desktop CPU).
The slower VLM is never in the safety path.
"""
import math
import time
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np
import onnxruntime as ort

COCO = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
]

# Typical real-world (height, width) in metres. None = that dimension varies too much to use.
SIZES = {
    "person": (1.70, 0.45), "bicycle": (1.05, None), "car": (1.50, None), "motorcycle": (1.10, None),
    "bus": (3.00, None), "truck": (3.00, None), "train": (3.80, None), "traffic light": (1.00, 0.35),
    "fire hydrant": (0.75, 0.35), "stop sign": (0.75, 0.75), "parking meter": (1.30, 0.30),
    "bench": (0.85, None), "cat": (0.30, None), "dog": (0.55, None), "horse": (1.60, None),
    "backpack": (0.48, 0.32), "umbrella": (1.00, 1.00), "handbag": (0.30, 0.35), "suitcase": (0.65, 0.42),
    "bottle": (0.25, 0.075), "wine glass": (0.20, 0.08), "cup": (0.10, 0.085), "bowl": (0.08, 0.16),
    "chair": (0.90, 0.48), "couch": (0.85, None), "potted plant": (0.60, 0.40), "bed": (0.60, None),
    "dining table": (0.75, None), "toilet": (0.75, 0.40), "tv": (0.60, 1.00), "laptop": (0.24, 0.34),
    "mouse": (0.04, 0.065), "remote": (0.18, 0.05), "keyboard": (0.03, 0.44), "cell phone": (0.15, 0.072),
    "microwave": (0.30, 0.50), "oven": (0.85, 0.60), "sink": (0.25, 0.55), "refrigerator": (1.75, 0.75),
    "book": (0.23, 0.16), "clock": (0.30, 0.30), "vase": (0.30, 0.15), "scissors": (0.20, 0.08),
    "teddy bear": (0.35, 0.25), "toothbrush": (0.19, 0.02), "banana": (0.04, 0.18), "apple": (0.08, 0.08),
    "orange": (0.08, 0.08),
}

VEHICLES = {"bicycle", "car", "motorcycle", "bus", "truck", "train"}
OBSTACLES = {
    "person", "chair", "bench", "couch", "dining table", "potted plant", "fire hydrant", "dog", "suitcase",
    "bed", "toilet", "refrigerator", "parking meter", "backpack", "umbrella", "horse", "oven", "tv",
}
PATH_HALF_ANGLE = 18.0  # degrees either side of straight ahead that count as "in your path"
LEVELS = {"info": 0, "warn": 1, "danger": 2}


@dataclass
class Detection:
    cls: str
    conf: float
    box: tuple  # x1, y1, x2, y2 in frame pixels
    angle: float = 0.0  # degrees, negative = left
    distance: float | None = None  # metres
    clock: int = 12
    in_path: bool = False
    level: str = "info"
    approaching: bool = False
    track: int = -1

    def to_dict(self):
        return {"cls": self.cls, "conf": round(self.conf, 2), "box": [round(v) for v in self.box],
                "angle": round(self.angle, 1), "distance": self.distance, "clock": self.clock,
                "in_path": self.in_path, "level": self.level, "approaching": self.approaching,
                "track": self.track}


class Detector:
    """YOLO11n ONNX on onnxruntime. Letterbox in, NMS out."""

    def __init__(self, path, size, conf=0.35, iou=0.45, threads=4):
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name
        self.size, self.conf, self.iou = size, conf, iou

    def __call__(self, bgr):
        h, w = bgr.shape[:2]
        r = min(self.size / h, self.size / w)
        nh, nw = round(h * r), round(w * r)
        top, left = (self.size - nh) // 2, (self.size - nw) // 2
        canvas = np.full((self.size, self.size, 3), 114, np.uint8)
        canvas[top:top + nh, left:left + nw] = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0

        out = self.sess.run(None, {self.inp: x})[0][0].T  # (N, 84): cx, cy, w, h, 80 class scores
        scores = out[:, 4:]
        cls = scores.argmax(1)
        conf = scores[np.arange(len(cls)), cls]
        keep = conf > self.conf
        if not keep.any():
            return []
        b, cls, conf = out[keep, :4], cls[keep], conf[keep]
        xywh = np.stack([(b[:, 0] - b[:, 2] / 2 - left) / r, (b[:, 1] - b[:, 3] / 2 - top) / r,
                         b[:, 2] / r, b[:, 3] / r], 1)
        idx = cv2.dnn.NMSBoxesBatched(xywh.tolist(), conf.tolist(), cls.tolist(), self.conf, self.iou)
        dets = []
        for i in np.array(idx).flatten():
            x1, y1, bw, bh = xywh[i]
            box = (float(max(0, x1)), float(max(0, y1)), float(min(w, x1 + bw)), float(min(h, y1 + bh)))
            dets.append(Detection(COCO[cls[i]], float(conf[i]), box))
        return dets


def focal_px(width, hfov_deg):
    return (width / 2) / math.tan(math.radians(hfov_deg / 2))


def estimate_distance(cls, box, w, h, f):
    """Pinhole estimate from known object size. Uses only edges that are not cut off by the frame."""
    size = SIZES.get(cls)
    if not size:
        return None
    x1, y1, x2, y2 = box
    bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
    cut_v = y1 <= 0.01 * h or y2 >= 0.99 * h
    cut_h = x1 <= 0.01 * w or x2 >= 0.99 * w
    est = []
    if size[0] and not cut_v:
        est.append(size[0] * f / bh)
    if size[1] and not cut_h:
        est.append(size[1] * f / bw)
    if not est:  # cut off on every usable side: it fills the view, so it is at most this far
        est = [d * f / px for d, px in ((size[0], bh), (size[1], bw)) if d]
    return round(float(min(est)), 1) if est else None


def clock_of(angle):
    if angle < -45: return 10
    if angle < -15: return 11
    if angle <= 15: return 12
    if angle <= 45: return 1
    return 2


def side_words(angle):
    if abs(angle) <= 8: return "straight ahead"
    if abs(angle) <= 20: return "slightly " + ("left" if angle < 0 else "right")
    return "on your " + ("left" if angle < 0 else "right")


def fmt_distance(d):
    if d is None: return ""
    if d < 1.0: return f"{max(10, round(d * 10) * 10)} centimetres"
    v = round(d * 2) / 2
    return f"{v:g} metre" + ("" if v == 1 else "s")


def classify(det, w):
    """Danger / warn / info from class, distance and whether it is in the walking path."""
    x1, _, x2, _ = det.box
    det.in_path = abs(det.angle) <= PATH_HALF_ANGLE or (x1 < w / 2 < x2)
    if det.cls not in OBSTACLES and det.cls not in VEHICLES:
        return "info"
    near, warn = (4.0, 8.0) if det.cls in VEHICLES else (1.0, 2.5)
    d = det.distance if det.distance is not None else 99
    if det.in_path and d <= near: return "danger"
    if det.approaching and d <= warn: return "danger" if det.in_path else "warn"
    if det.in_path and d <= warn: return "warn"
    if d <= near * 0.8: return "warn"
    return "info"


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-6)


@dataclass
class Track:
    id: int
    cls: str
    box: tuple
    seen: float
    hist: deque = field(default_factory=lambda: deque(maxlen=12))  # (t, distance)


class Tracker:
    """Greedy IoU tracker: gives each object a stable id and a smoothed distance trend."""

    def __init__(self):
        self.tracks, self.next_id = [], 1

    def update(self, dets, now):
        free = list(self.tracks)
        for d in sorted(dets, key=lambda d: -d.conf):
            best = max((t for t in free if t.cls == d.cls), key=lambda t: iou(t.box, d.box), default=None)
            if best is None or iou(best.box, d.box) < 0.2:
                best = Track(self.next_id, d.cls, d.box, now)
                self.next_id += 1
                self.tracks.append(best)
            else:
                free.remove(best)
            best.box, best.seen = d.box, now
            d.track = best.id
            if d.distance is not None:
                best.hist.append((now, d.distance))
                pts = [p for p in best.hist if now - p[0] <= 1.5]
                if len(pts) >= 4:
                    # median-of-halves trend is robust to single noisy boxes
                    half = len(pts) // 2
                    a = sorted(p[1] for p in pts[:half])[half // 2]
                    b = sorted(p[1] for p in pts[half:])[(len(pts) - half) // 2]
                    dt = pts[-1][0] - pts[0][0]
                    d.approaching = dt > 0.4 and (a - b) / dt > 0.5 and b < 6
        self.tracks = [t for t in self.tracks if now - t.seen < 2.0]


class HazardMonitor:
    """Turns per-frame detections into rare, prioritised spoken alerts.

    An object is announced once, then again only if it escalates (warn -> danger), gets clearly
    closer, or is still a hazard after a long gap. A static scene therefore stays quiet.
    """

    REPEAT_AFTER = {"danger": 15.0, "warn": 60.0}

    def __init__(self):
        self.said, self.last_any = {}, float("-inf")  # track id -> (time, level, distance)

    def _worth_saying(self, d, now):
        prev = self.said.get(d.track)
        if prev is None:
            return True
        t, level, dist = prev
        if LEVELS[d.level] > LEVELS[level]:
            return True
        if d.distance is not None and dist is not None and d.distance < dist * 0.7 and now - t > 1.5:
            return True
        return now - t > self.REPEAT_AFTER[d.level]

    def update(self, dets, now):
        # Only real danger is spoken. Warnings stay on screen (amber box) so the user is not nagged.
        cands = [d for d in dets if d.level == "danger"]
        if not cands:
            return None
        d = max(cands, key=lambda d: (d.in_path, -(d.distance or 99)))
        if not self._worth_saying(d, now):
            return None
        if d.level == "warn" and now - self.last_any < 2.0:
            return None
        self.said[d.track], self.last_any = (now, d.level, d.distance), now
        if len(self.said) > 200:
            self.said = {k: v for k, v in self.said.items() if now - v[0] < 60}
        name = d.cls if d.cls != "dining table" else "table"
        what = f"{name} approaching" if d.approaching else name
        text = f"{what.capitalize()} {side_words(d.angle)}."
        return {"text": text, "level": d.level, "angle": round(d.angle, 1), "cls": d.cls}


class FindGuide:
    """'Find my cup': locks onto one class and gives spoken cues; the browser adds a sonar tone."""

    def __init__(self):
        self.target, self.locked, self.lost_at = None, False, 0.0
        self.centered_said = self.last_said = float("-inf")

    def set(self, cls):
        self.target, self.locked = cls, False
        self.centered_said = self.last_said = float("-inf")

    def update(self, dets, now):
        if not self.target:
            return None, None
        hits = [d for d in dets if d.cls == self.target]
        if not hits:
            if self.locked and now - self.lost_at > 2.0:
                self.locked = False
                return None, f"Lost the {self.target}. Pan slowly."
            return None, None
        d = max(hits, key=lambda d: d.conf)
        self.lost_at = now
        msg = None
        if not self.locked:
            self.locked = True
            msg = f"{self.target.capitalize()} found at {d.clock} o'clock."
            self.last_said = now
        elif abs(d.angle) <= 6 and now - self.centered_said > 6 and now - self.last_said > 1.5:
            self.centered_said = self.last_said = now
            msg = "Straight ahead."
        return d, msg


class FastLayer:
    """Detector + geometry + tracker + alert policy, called once per frame."""

    def __init__(self, cfg):
        self.det = Detector(cfg.DETECTOR, cfg.DET_SIZE, cfg.DET_CONF, cfg.DET_IOU, cfg.CPU_THREADS)
        self.hfov = cfg.CAMERA_HFOV_DEG
        self.tracker, self.monitor, self.finder = Tracker(), HazardMonitor(), FindGuide()

    def measure(self, bgr):
        """Detect and attach direction + distance. Stateless, so it is safe for one-off frames."""
        h, w = bgr.shape[:2]
        f = focal_px(w, self.hfov)
        dets = self.det(bgr)
        for d in dets:
            cx = (d.box[0] + d.box[2]) / 2
            d.angle = math.degrees(math.atan((cx - w / 2) / f))
            d.clock = clock_of(d.angle)
            d.distance = estimate_distance(d.cls, d.box, w, h, f)
            d.level = classify(d, w)
        return dets

    def analyse(self, bgr, hazards=True, now=None):
        """Per-frame path for the live stream: measure, track, then decide alerts and find cues."""
        now = now or time.time()
        w = bgr.shape[1]
        dets = self.measure(bgr)
        self.tracker.update(dets, now)
        for d in dets:
            d.level = classify(d, w)
        alert = self.monitor.update(dets, now) if hazards else None
        target, guide = self.finder.update(dets, now)
        return dets, alert, target, guide

    @staticmethod
    def hazard_sentence(dets, levels=("danger", "warn")):
        """Deterministic safety line that goes in front of any VLM answer. The VLM never decides safety."""
        cands = [d for d in dets if d.level in levels]
        if not cands:
            return ""
        d = max(cands, key=lambda d: (LEVELS[d.level], d.in_path, -(d.distance or 99)))
        name = "table" if d.cls == "dining table" else d.cls
        return f"Careful: {name} {side_words(d.angle)}."

    @staticmethod
    def summary(dets, limit=8):
        """Plain-text scene facts handed to the VLM so its answer is grounded in measured positions."""
        parts = []
        for d in sorted(dets, key=lambda d: d.distance or 99)[:limit]:
            parts.append(f"{d.cls} at {d.clock} o'clock")
        return "; ".join(parts)
