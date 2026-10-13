"""Rolling latency stats per module, also appended to results/latency.csv for the performance report."""
import csv
import threading
import time
from collections import defaultdict, deque


class Metrics:
    def __init__(self, csv_path):
        self.samples = defaultdict(lambda: deque(maxlen=300))
        self.counts = defaultdict(int)
        self.lock = threading.Lock()
        self.csv_path = csv_path
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        new = not csv_path.exists()
        self.fh = open(csv_path, "a", newline="")
        self.writer = csv.writer(self.fh)
        if new:
            self.writer.writerow(["timestamp", "module", "ms", "detail"])
        self.started = time.time()

    def record(self, module, ms, detail=""):
        with self.lock:
            self.samples[module].append(ms)
            self.counts[module] += 1
            # per-frame detector rows would flood the file; keep every 10th
            if module != "detector" or self.counts[module] % 10 == 0:
                self.writer.writerow([f"{time.time():.3f}", module, f"{ms:.1f}", detail])
                self.fh.flush()

    def summary(self):
        with self.lock:
            out = {}
            for m, s in self.samples.items():
                v = sorted(s)
                out[m] = {"last": round(s[-1], 1), "p50": round(v[len(v) // 2], 1),
                          "p95": round(v[min(len(v) - 1, int(len(v) * 0.95))], 1), "n": self.counts[m]}
            return out


class timer:
    """with timer(metrics, "ocr") as t: ...   then t.ms holds the elapsed milliseconds."""

    def __init__(self, metrics, module, detail=""):
        self.m, self.module, self.detail, self.ms = metrics, module, detail, 0.0

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = (time.perf_counter() - self.t0) * 1000
        if exc[0] is None:
            self.m.record(self.module, self.ms, self.detail)
