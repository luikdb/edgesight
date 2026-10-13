from edgesight.hazard import (Detection, FindGuide, HazardMonitor, classify, clock_of, estimate_distance,
                              fmt_distance, focal_px)

W, H = 640, 480
F = focal_px(W, 70)


def person_at(distance, cx=W / 2):
    """Synthetic full-body person box whose height matches the given distance."""
    h = 1.70 * F / distance
    top = H / 2 - h / 2
    return (cx - h * 0.13, top, cx + h * 0.13, top + h)


def test_distance_roundtrip():
    assert abs(estimate_distance("person", person_at(3.0), W, H, F) - 3.0) < 0.15


def test_truncated_box_falls_back_to_width():
    # feet cut off by the bottom edge: height is unreliable, width (shoulders) still works
    d = estimate_distance("person", (300, 100, 300 + 0.45 * F / 1.5, H), W, H, F)
    assert 1.3 < d < 1.7


def test_unknown_class_has_no_distance():
    assert estimate_distance("kite", (0, 0, 10, 10), W, H, F) is None


def test_clock_and_formatting():
    assert clock_of(0) == 12 and clock_of(-30) == 11 and clock_of(30) == 1
    assert fmt_distance(0.43) == "40 centimetres"
    assert fmt_distance(1.0) == "1 metre"
    assert fmt_distance(2.26) == "2.5 metres"


def make(cls, distance, angle=0.0, cx=W / 2):
    d = Detection(cls, 0.9, person_at(distance, cx), angle=angle, distance=distance, track=1)
    d.level = classify(d, W)
    return d


def test_levels():
    assert make("person", 0.8).level == "danger"
    assert make("person", 1.2).level == "warn"
    assert make("person", 2.0).level == "warn"
    assert make("person", 6.0).level == "info"
    assert make("cup", 0.3).level == "info"  # not an obstacle
    assert make("car", 3.0).level == "danger"  # vehicles get a larger margin


def test_monitor_speaks_once_then_only_on_change():
    m = HazardMonitor()
    assert m.update([make("person", 2.0)], now=0.0) is None  # a warning is shown on screen, never spoken
    first = m.update([make("person", 0.8)], now=3.0)
    assert first and first["level"] == "danger" and first["text"] == "Person straight ahead."
    assert m.update([make("person", 0.8)], now=5.0) is None  # same object, same state: quiet
    assert m.update([make("person", 0.8)], now=12.0) is None  # still quiet inside the 15 s repeat window
    assert m.update([make("person", 0.8)], now=20.0)  # long gap: remind once


def test_find_guide_lock_and_centre():
    g = FindGuide()
    g.set("cup")
    cup = Detection("cup", 0.8, (300, 200, 340, 240), angle=20.0, distance=0.6, clock=1)
    _, msg = g.update([cup], now=0.0)
    assert msg.startswith("Cup found at 1 o'clock")
    cup.angle = 2.0
    _, msg = g.update([cup], now=2.0)
    assert msg.startswith("Straight ahead")
