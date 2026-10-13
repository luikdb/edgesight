"""Reading layer: RapidOCR (PaddleOCR detection + recognition models in ONNX)."""
from rapidocr_onnxruntime import RapidOCR


class Reader:
    def __init__(self, min_conf=0.5):
        self.engine = RapidOCR()
        self.min_conf = min_conf

    def read(self, bgr):
        res, _ = self.engine(bgr)
        lines = []
        for box, text, conf in res or []:
            conf = float(conf)
            if conf < self.min_conf or not text.strip():
                continue
            ys = [p[1] for p in box]
            xs = [p[0] for p in box]
            lines.append({"text": text.strip(), "conf": round(conf, 2),
                          "box": [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))]})
        if not lines:
            return {"lines": [], "text": ""}
        # reading order: group into rows by vertical position, then left to right
        hmed = sorted(l["box"][3] - l["box"][1] for l in lines)[len(lines) // 2] or 1
        lines.sort(key=lambda l: (round(((l["box"][1] + l["box"][3]) / 2) / (hmed * 0.7)), l["box"][0]))
        return {"lines": lines, "text": "\n".join(l["text"] for l in lines)}
