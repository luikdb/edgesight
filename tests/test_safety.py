import pytest

from edgesight.router import route
from edgesight.vlm import REFUSAL, first_sentences, makes_safety_claim, scrub_safety


@pytest.mark.parametrize("text", [
    "Is it safe to cross?", "can I cross the road", "is the road clear", "should I go now", "am I okay to walk",
    "are there cars coming", "is it clear to proceed", "when can I cross",
])
def test_safety_questions_are_routed_to_the_refusal(text):
    assert route(text)["intent"] == "safety"


@pytest.mark.parametrize("text", [
    "Yes, it is safe to cross.", "It looks clear to cross.", "You can safely cross now.", "No cars are coming.",
    "The road seems safe.", "It's okay to go.", "The road ahead is clear.", "The crossing looks free.",
])
def test_claims_of_safety_are_caught(text):
    assert makes_safety_claim(text)


@pytest.mark.parametrize("text", [
    "A black car is approaching from the left.", "People are walking on the crosswalk.", "The stairs are ahead.",
    "The Tylenol is on the second shelf.",
])
def test_plain_descriptions_pass(text):
    assert not makes_safety_claim(text)


def test_find_beats_label_for_medicine_requests():
    assert route("find the cough medicine")["intent"] == "find"
    assert route("where is my medicine")["intent"] == "find"
    assert route("read the medicine label")["intent"] == "read_label"
    assert route("how many pills do I take")["intent"] == "read_label"


def test_sentence_limit():
    assert first_sentences("One. Two. Three.", 2) == "One. Two."
    assert first_sentences("One. Two. Three.", None) == "One. Two. Three."


def test_scrub_keeps_useful_sentences_and_drops_the_claim():
    out = scrub_safety("The road ahead is clear. A black car is approaching from the left.")
    assert out == "A black car is approaching from the left."
    assert scrub_safety("It is safe to cross.") == REFUSAL
    assert scrub_safety("Two people stand by the bus.") == "Two people stand by the bus."
