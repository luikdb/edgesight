"""Turns a spoken sentence into an intent. Rule-based on purpose: instant, predictable and testable."""
import re

from .hazard import COCO

# spoken word -> detector class
SYNONYMS = {
    "mug": "cup", "glass": "cup", "coffee": "cup", "phone": "cell phone", "mobile": "cell phone",
    "smartphone": "cell phone", "seat": "chair", "sofa": "couch", "table": "dining table", "desk": "dining table",
    "bag": "backpack", "purse": "handbag", "luggage": "suitcase", "tv": "tv", "television": "tv",
    "computer": "laptop", "notebook": "laptop", "remote control": "remote", "plant": "potted plant",
    "water": "bottle", "people": "person", "someone": "person", "somebody": "person", "man": "person",
    "woman": "person", "fridge": "refrigerator", "puppy": "dog", "kitty": "cat", "bike": "bicycle",
    "toilet": "toilet", "door": None, "keys": None, "key": None, "wallet": None, "glasses": None,
}

# questions asking the device to certify safety: it must never answer yes
SAFETY_Q = re.compile(
    r"\b(is it|am i|are we|is this|is that) (safe|ok|okay|clear|fine)\b"
    r"|\b(safe|okay|ok|clear) to (cross|go|walk|proceed|step|move)\b"
    r"|\b(can|should|may|could) i (safely )?(cross|go|walk|proceed|step|move)\b"
    r"|\bis the (road|street|path|crossing|way) (clear|safe|free)\b"
    r"|\b(any|are there) (cars|traffic|vehicles|bikes|cyclists) (coming|approaching|near)\b"
    r"|\bwhen (can|should) i (cross|go)\b")

HELP = ("You can say: what's in front of me, read this, read the label, find my cup, "
        "where is the chair, describe the room, hazards on or off, repeat, or stop.")


def to_class(phrase):
    phrase = phrase.lower().strip(" .?!")
    phrase = re.sub(r"^(my|the|a|an|some)\s+", "", phrase)
    for cand in (phrase, phrase.rstrip("s"), phrase.split()[-1] if phrase else "", phrase.split()[-1].rstrip("s") if phrase else ""):
        if cand in SYNONYMS:
            return SYNONYMS[cand]
        if cand in COCO:
            return cand
    return None


def route(text):
    t = text.lower().strip()
    t = re.sub(r"[^\w\s']", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return {"intent": "none"}
    if re.fullmatch(r"(stop|cancel|never ?mind|quiet|shut up|be quiet|stop finding|stop looking)( it| please| now)?", t):
        return {"intent": "stop"}
    if re.search(r"\b(help|what can you do|commands)\b", t):
        return {"intent": "help"}
    if re.search(r"\b(repeat|say (that|it) again|what did you say)\b", t):
        return {"intent": "repeat"}
    m = re.search(r"\b(hazard|hazards|navigation|walking mode|obstacle alerts?)\b.*\b(on|off|start|stop|enable|disable)\b", t) \
        or re.search(r"\b(on|off|start|stop|enable|disable)\b.*\b(hazard|hazards|navigation|walking mode)\b", t)
    if m:
        on = any(w in t.split() for w in ("on", "start", "enable"))
        return {"intent": "hazards", "on": on}
    if SAFETY_Q.search(t):
        return {"intent": "safety"}
    m = re.search(r"\b(?:find|locate|look for|search for|where(?:'s| is| are)|where did i put)\s+(?:my |the |a |an |some )?([a-z ]{2,30}?)(?:\s+(?:is|at|please|for me|go|now))?$", t)
    if m:
        what = m.group(1).strip()
        return {"intent": "find", "object": what, "cls": to_class(what)}
    if re.search(r"\b(medicine|medication|pill|pills|tablet|tablets|dose|dosage|prescription|label|expiry|expiration|ingredients)\b", t):
        return {"intent": "read_label"}
    if re.search(r"\b(read|what does (it|this|that) say|what's written|what is written|text|sign|menu)\b", t):
        return {"intent": "read"}
    if re.search(r"\b(describe|what's (in front|around|here|there)|what is (in front|around|here|there)|what do you see|where am i|look around|what's ahead|what is ahead|surroundings|scene)\b", t):
        return {"intent": "describe"}
    return {"intent": "ask"}
