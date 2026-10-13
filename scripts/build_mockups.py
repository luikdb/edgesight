"""Compose product mockups: real app screenshots inside laptop / phone frames.

    .venv/bin/python scripts/mockup_screens.py     # 1. capture screens (server must be running)
    .venv/bin/python scripts/build_mockups.py      # 2. frame them
Output: mockups/*.png (3200 x 2000)
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
M = ROOT / "mockups"
SRC = M / "src"
SRC.mkdir(parents=True, exist_ok=True)

CSS = """
@font-face{font-family:"Hanken Grotesk";src:url(../../web/fonts/HankenGrotesk.woff2) format("woff2");font-weight:300 700}
*{box-sizing:border-box;margin:0}
html,body{width:1600px;height:1000px;overflow:hidden}
body{font-family:"Hanken Grotesk",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.scene{position:relative;width:1600px;height:1000px;background:var(--bg);overflow:hidden}
.dark{--bg:#14161b;--ink:#eceef2;--sub:#9aa1ad}
.light{--bg:#e6e7ea;--ink:#14161b;--sub:#5b616c}
.black{--bg:#0a0b0e;--ink:#eceef2;--sub:#9aa1ad}

/* laptop: space-grey aluminium */
.laptop{position:absolute;filter:drop-shadow(0 38px 44px rgb(0 0 0 / .38))}
.lid{position:relative;background:#0e0f12;border-radius:22px 22px 5px 5px;padding:17px 15px 15px;box-shadow:inset 0 0 0 1px #34363d,inset 0 0 0 2px #121316}
.lid .cam{position:absolute;top:7px;left:50%;width:5px;height:5px;margin-left:-2px;border-radius:50%;background:#1d1f24;box-shadow:0 0 0 1.5px #16171a}
.screen{background:#000;border-radius:6px;overflow:hidden;aspect-ratio:16/10}
.screen img{display:block;width:100%;height:100%;object-fit:cover}
.base{position:relative;height:17px;margin:0 -7.5%;background:#2b2d33;border-radius:0 0 18px 18px;box-shadow:inset 0 1.5px 0 #4a4d55,inset 0 -2px 0 #1b1c20}
.base::before{content:"";position:absolute;left:50%;top:0;width:15%;height:7px;margin-left:-7.5%;background:#1d1e22;border-radius:0 0 10px 10px}

/* phone */
.phone{position:absolute;padding:11px;background:#0c0d0f;border-radius:64px;box-shadow:inset 0 0 0 2px #34363d,inset 0 0 0 3.5px #121316;filter:drop-shadow(0 34px 40px rgb(0 0 0 / .4))}
.phone .pscreen{border-radius:53px;overflow:hidden;background:#0a0b0e;aspect-ratio:1170/2532;display:flex;flex-direction:column}
.phone .pscreen img{display:block;width:100%;flex:1;min-height:0;object-fit:cover;object-position:top}
.phone .status{flex:none;display:flex;align-items:center;justify-content:space-between;padding:0 11%;color:#eceef2;font-weight:600;letter-spacing:-.01em}
.phone .status svg{height:.8em;width:auto}
.phone .island{position:absolute;top:21px;left:50%;width:31%;height:3.6%;margin-left:-15.5%;background:#000;border-radius:999px}
.phone .b{position:absolute;width:4px;background:#26282d;border-radius:2px}
.phone .b1{left:-4px;top:15%;height:4.5%}.phone .b2{left:-4px;top:22%;height:8%}.phone .b3{left:-4px;top:32%;height:8%}.phone .b4{right:-4px;top:26%;height:12%}

/* captions */
.cap h1{font-size:46px;font-weight:600;letter-spacing:-.025em;color:var(--ink)}
.cap p{font-size:24px;color:var(--sub);margin-top:8px;letter-spacing:-.01em}
"""


def laptop(img, w, x, y):
    return (f'<div class="laptop" style="width:{w}px;left:{x}px;top:{y}px"><div class="lid"><i class="cam"></i>'
            f'<div class="screen"><img src="../screens/{img}"></div></div><div class="base"></div></div>')


def phone(img, w, x, y):
    st = round(w * 0.13)
    bat = ('<svg viewBox="0 0 54 22" fill="none"><rect x="1" y="2" width="44" height="18" rx="5" stroke="#eceef2" stroke-opacity=".5" stroke-width="2"/>'
           '<rect x="4" y="5" width="32" height="12" rx="3" fill="#eceef2"/><rect x="47" y="7" width="4" height="8" rx="2" fill="#eceef2" fill-opacity=".5"/></svg>')
    return (f'<div class="phone" style="width:{w}px;left:{x}px;top:{y}px"><i class="b b1"></i><i class="b b2"></i><i class="b b3"></i><i class="b b4"></i>'
            f'<div class="pscreen"><div class="status" style="height:{st}px;font-size:{round(w*0.042)}px"><span>9:41</span>{bat}</div>'
            f'<img src="../screens/{img}"></div><i class="island"></i></div>')


def page(theme, body):
    return f'<!doctype html><meta charset="utf-8"><style>{CSS}</style><body><div class="scene {theme}">{body}</div></body>'


SCENES = {}

# single laptop heroes (laptop 1240 wide, centred)
for name, img, theme in [("hero-dark", "describe.png", "dark"), ("hero-light", "describe.png", "light"),
                         ("read-label", "label.png", "light"), ("find-mode", "find.png", "dark"),
                         ("road-safety", "safety.png", "light"), ("find-medicine", "medicine.png", "dark"),
                         ("pipeline-details", "details.png", "light")]:
    SCENES[name] = page(theme, laptop(img, 1240, 180, 108))

# laptop + phone together
SCENES["laptop-and-phone"] = page("light", laptop("describe.png", 1060, 130, 170) + phone("phone.png", 330, 1205, 128))

# phone-only pair: describe + settings aren't both phone captures, so show one large phone with a caption
SCENES["phone"] = page("black",
    '<div class="cap" style="position:absolute;left:150px;top:380px;width:560px"><h1>Ask. Listen. Go.</h1><p>Know what is ahead, read a label, find a medicine. Offline, on your phone or laptop.</p></div>'
    + phone("phone.png", 430, 830, 70))

# feature board: four screens, short captions
def small(img, title, x, y, w=590):
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px"><div style="border-radius:16px;overflow:hidden;aspect-ratio:16/10;'
            f'box-shadow:0 0 0 1px rgb(255 255 255 / .08),0 18px 30px rgb(0 0 0 / .45)"><img src="../screens/{img}" style="display:block;width:100%;height:100%;object-fit:cover"></div>'
            f'<div style="margin-top:12px;font-size:22px;font-weight:500;color:var(--ink);letter-spacing:-.01em">{title}</div></div>')


SCENES["feature-board"] = page("black",
    '<div class="cap" style="position:absolute;left:165px;top:28px"><h1 style="font-size:40px">EdgeSight</h1><p style="font-size:21px;margin-top:2px">Sees and speaks, entirely on this device.</p></div>'
    + small("describe.png", "Know what is in front of you", 165, 128)
    + small("safety.png", "Honest about safety: it never says \u201csafe to cross\u201d", 845, 128)
    + small("label.png", "Read the label on any medicine", 165, 566)
    + small("medicine.png", "Find the medicine you are looking for", 845, 566))

with sync_playwright() as p:
    browser = p.chromium.launch()
    for name, html in SCENES.items():
        f = SRC / f"{name}.html"
        f.write_text(html)
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
        page_ = ctx.new_page()
        page_.goto(f.as_uri())
        page_.evaluate("document.fonts.ready")
        page_.wait_for_timeout(600)
        page_.screenshot(path=M / f"{name}.png")
        ctx.close()
        print("wrote", name)
    browser.close()
