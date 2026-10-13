"""Camera focus control through Video4Linux, so it works in any browser (Firefox exposes no focus API).

Talks to the same /dev/video* device the browser is streaming from; changing a control does not interrupt the stream.
Linux only. Everything degrades to "not available" on other systems or cameras without a focus control.
"""
import fcntl
import glob
import os
import struct
import threading

VIDIOC_QUERYCTRL = 0xC0445624
VIDIOC_G_CTRL = 0xC008561B
VIDIOC_S_CTRL = 0xC008561C
VIDIOC_QUERYCAP = 0x80685600
CID_FOCUS_ABSOLUTE = 0x009A090A
CID_FOCUS_AUTO = 0x009A090C


class Focus:
    def __init__(self):
        self.lock = threading.Lock()
        self.path = None
        self.range = None  # (min, max, step, default)
        self.card = ""
        self._find()

    def _open(self):
        return os.open(self.path, os.O_RDWR | os.O_NONBLOCK)

    def _find(self):
        for path in sorted(glob.glob("/dev/video*")):
            try:
                fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
            except OSError:
                continue
            try:
                buf = bytearray(68)
                struct.pack_into("=I", buf, 0, CID_FOCUS_ABSOLUTE)
                fcntl.ioctl(fd, VIDIOC_QUERYCTRL, buf)
                _id, _typ, _name, mn, mx, st, df, flags = struct.unpack_from("=II32siiiiI", buf, 0)
                if flags & 0x1:  # disabled
                    continue
                cap = bytearray(104)
                fcntl.ioctl(fd, VIDIOC_QUERYCAP, cap)
                self.card = bytes(cap[16:48]).split(b"\0")[0].decode(errors="replace")
                self.path, self.range = path, (mn, mx, max(1, st), df)
                return
            except OSError:
                continue
            finally:
                os.close(fd)

    def _get(self, fd, cid):
        b = bytearray(8)
        struct.pack_into("=Ii", b, 0, cid, 0)
        fcntl.ioctl(fd, VIDIOC_G_CTRL, b)
        return struct.unpack_from("=Ii", b, 0)[1]

    def _set(self, fd, cid, value):
        b = bytearray(8)
        struct.pack_into("=Ii", b, 0, cid, int(value))
        fcntl.ioctl(fd, VIDIOC_S_CTRL, b)

    def state(self):
        if not self.path:
            return {"available": False}
        mn, mx, st, df = self.range
        with self.lock:
            fd = self._open()
            try:
                return {"available": True, "device": self.path, "camera": self.card, "auto": bool(self._get(fd, CID_FOCUS_AUTO)),
                        "value": self._get(fd, CID_FOCUS_ABSOLUTE), "min": mn, "max": mx, "step": st, "default": df}
            finally:
                os.close(fd)

    def apply(self, auto=None, value=None):
        if not self.path:
            raise ValueError("this camera has no focus control")
        mn, mx, st, _ = self.range
        with self.lock:
            fd = self._open()
            try:
                if value is not None:
                    value = max(mn, min(mx, round((int(value) - mn) / st) * st + mn))
                    self._set(fd, CID_FOCUS_AUTO, 0)  # a manual value only sticks with autofocus off
                    self._set(fd, CID_FOCUS_ABSOLUTE, value)
                elif auto is not None:
                    self._set(fd, CID_FOCUS_AUTO, 1 if auto else 0)
            finally:
                os.close(fd)
        return self.state()
