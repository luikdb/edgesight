"""Drive the real EdgeSight app in headless Chromium and save high-resolution screenshots for mockups.

The server must be running (./run.sh). Answers on screen are real: every question goes through the full local pipeline.
Scenes are everyday situations for a blind or low-vision person: a road, a medicine box, a pharmacy shelf, a room.

    .venv/bin/python scripts/mockup_screens.py
Output: mockups/screens/*.png
"""
import json
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "mockups" / "screens"
BASE = "http://localhost:8800"
OUT.mkdir(parents=True, exist_ok=True)


def seed_speech_timing():
    """The mic is not used in headless runs, so record real speech-to-text timings by transcribing synthesized questions."""
    for q in ("What's in front of me?", "Where is the Tylenol?", "Read the medicine label."):
        wav = urllib.request.urlopen(urllib.request.Request(BASE + "/api/tts", data=json.dumps({"text": q}).encode()), timeout=60).read()
        urllib.request.urlopen(urllib.request.Request(BASE + "/api/stt", data=wav), timeout=60).read()


def shot(page, name):
    page.mouse.move(2, 2)  # park the pointer so no button shows a hover state
    page.wait_for_timeout(400)
    page.screenshot(path=OUT / name)


def wait_answer(page):
    page.wait_for_function("document.querySelectorAll('.card').length > 0 && document.querySelectorAll('.card .ans .thinking').length === 0",
                           timeout=180000)
    page.wait_for_timeout(900)


def open_app(browser, demo, width=1440, height=900, scale=2, mobile=False):
    ctx = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=scale,
                              color_scheme="dark", is_mobile=mobile, has_touch=mobile)
    page = ctx.new_page()
    page.goto(f"{BASE}/?demo={demo}")
    page.wait_for_selector("#splash")
    page.click("#splash")
    page.wait_for_timeout(1200)
    return ctx, page


def command(page, text):
    page.fill("#asktext", text)
    page.press("#asktext", "Enter")
    wait_answer(page)


def warm(browser, demo, text):
    """Ask once off-screen so the model is loaded and the timings on screen are steady-state."""
    ctx, page = open_app(browser, demo)
    command(page, text)
    ctx.close()


with sync_playwright() as p:
    browser = p.chromium.launch()
    for demo, q in (("street.jpg", "What's in front of me?"), ("pharmacy.jpg", "Where is the Tylenol?"), ("label.jpg", "read the medicine label")):
        warm(browser, demo, q)
    seed_speech_timing()

    # 1. the road: what's in front of me (with clock directions)
    ctx, page = open_app(browser, "street.jpg")
    command(page, "What's in front of me?")
    shot(page, "describe.png")
    ctx.close()

    # 2. "Is it safe to cross?": the device refuses to certify safety and says what it sees
    ctx, page = open_app(browser, "street.jpg")
    command(page, "Is it safe to cross?")
    shot(page, "safety.png")
    ctx.close()

    # 3. reading a medicine box
    ctx, page = open_app(browser, "label.jpg")
    page.click('.act[data-cmd="read the medicine label"]')
    wait_answer(page)
    shot(page, "label.png")
    ctx.close()

    # 4. finding a medicine on a pharmacy shelf
    ctx, page = open_app(browser, "pharmacy.jpg")
    command(page, "Where is the Tylenol?")
    shot(page, "medicine.png")
    ctx.close()

    # 5. find mode with detections on (a chair in a room)
    ctx, page = open_app(browser, "room.jpg")
    page.click("#boxbtn")
    page.fill("#asktext", "find the chair")
    page.press("#asktext", "Enter")
    wait_answer(page)
    page.wait_for_timeout(4500)
    shot(page, "find.png")
    ctx.close()

    # 6. technical details panel (pipeline table) after real requests on the road scene
    ctx, page = open_app(browser, "street.jpg")
    page.click("#boxbtn")
    command(page, "What's in front of me?")
    command(page, "Is it safe to cross?")
    page.click("#viewbtn")
    page.wait_for_timeout(2500)
    shot(page, "details.png")
    ctx.close()

    # 7. settings sheet
    ctx, page = open_app(browser, "stairs.jpg")
    page.click("#setbtn")
    page.wait_for_timeout(900)
    shot(page, "settings.png")
    ctx.close()

    # 8. phone layout
    ctx, page = open_app(browser, "street.jpg", width=390, height=844, scale=3, mobile=True)
    command(page, "What's in front of me?")
    page.evaluate("document.scrollingElement.scrollTo({top: 0, behavior: 'instant'})")
    page.wait_for_timeout(500)
    shot(page, "phone.png")
    ctx.close()

    browser.close()
print("saved:", sorted(f.name for f in OUT.glob("*.png")))
