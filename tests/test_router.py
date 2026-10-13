import pytest

from edgesight.router import route, to_class


@pytest.mark.parametrize("text,intent", [
    ("What's in front of me?", "describe"),
    ("describe the room", "describe"),
    ("read this", "read"),
    ("what does this sign say", "read"),
    ("read the medicine label", "read_label"),
    ("how many pills should I take", "read_label"),
    ("find my mug", "find"),
    ("where is the chair", "find"),
    ("stop", "stop"),
    ("repeat that", "repeat"),
    ("hazards off", "hazards"),
    ("is the man smiling?", "ask"),
    ("", "none"),
])
def test_intents(text, intent):
    assert route(text)["intent"] == intent


def test_find_maps_spoken_words_to_detector_classes():
    assert route("find my mug")["cls"] == "cup"
    assert route("where is my phone")["cls"] == "cell phone"
    assert route("where are my keys")["cls"] is None  # not a detector class: falls back to the VLM
    assert to_class("the bottles") == "bottle"


def test_hazard_toggle_direction():
    assert route("turn hazard alerts on")["on"] is True
    assert route("stop navigation")["on"] is False
