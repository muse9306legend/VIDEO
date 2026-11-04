"""Paper-card template (cream paper, ink outline, hand-drawn wobble, Gaegu font) rendered in headless Chromium.

Used for: explainer cards (an AI image placed on the card, optional short label) and
the sermon title / preacher name badges.
"""
from __future__ import annotations

import base64
import html
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
CARD_W, CARD_H = 880, 660
INK, PAPER, CORAL = "#2E2A26", "#FFF8EC", "#FFB4A2"


def _font_css() -> str:
    css = []
    for file, weight in (("Gaegu-Regular.ttf", 400), ("Gaegu-Bold.ttf", 700)):
        p = FONT_DIR / file
        if p.exists():
            b64 = base64.b64encode(p.read_bytes()).decode()
            css.append(f"@font-face{{font-family:'Gaegu';src:url(data:font/ttf;base64,{b64}) format('truetype');font-weight:{weight};}}")
    return "".join(css)


def _filters(seed: int) -> str:
    return f"""<svg width="0" height="0" style="position:absolute"><defs>
 <filter id="rough" x="-5%" y="-5%" width="110%" height="110%">
  <feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves="2" seed="{seed}" result="n"/>
  <feDisplacementMap in="SourceGraphic" in2="n" scale="5" xChannelSelector="R" yChannelSelector="G"/>
 </filter>
 <filter id="rough2" x="-5%" y="-5%" width="110%" height="110%">
  <feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="1" seed="{seed + 7}" result="n"/>
  <feDisplacementMap in="SourceGraphic" in2="n" scale="3" xChannelSelector="R" yChannelSelector="G"/>
 </filter></defs></svg>"""


def _page(body: str, font_css: str, seed: int) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{font_css}
html,body{{margin:0;padding:24px;background:transparent;font-family:'Gaegu','Malgun Gothic',sans-serif;color:{INK}}}
</style></head><body>{_filters(seed)}{body}</body></html>"""


def _card_body(png: bytes, label: str) -> str:
    b64 = base64.b64encode(png).decode()
    img_h = 470 if label else 580
    lab = (f'<div style="position:absolute;left:0;right:0;bottom:34px;text-align:center;font-weight:700;'
           f'font-size:76px;line-height:1;filter:url(#rough2)">{html.escape(label)}</div>') if label else ""
    return f"""<div id="target" style="position:relative;width:{CARD_W}px;height:{CARD_H}px">
 <div style="position:absolute;left:28px;top:28px;width:836px;height:620px;border-radius:40px;background:{INK};opacity:.22;filter:url(#rough)"></div>
 <div style="position:absolute;left:16px;top:14px;width:824px;height:608px;border-radius:40px;background:{PAPER};border:6px solid {INK};filter:url(#rough)"></div>
 <div style="position:absolute;left:58px;top:46px;width:764px;height:{img_h}px;border-radius:22px;overflow:hidden;filter:url(#rough2)">
  <img src="data:image/png;base64,{b64}" style="width:100%;height:100%;object-fit:contain"></div>{lab}
</div>"""


def _badge_body(text: str, kind: str, font_px: int) -> str:
    """kind: 'title' (cream paper) or 'name' (cream paper with a coral tab)."""
    pad_v, pad_h = int(font_px * 0.32), int(font_px * 0.6)
    tab = (f'<span style="display:inline-block;width:{int(font_px * 0.28)}px;height:{int(font_px * 0.9)}px;'
           f'background:{CORAL};border:4px solid {INK};border-radius:8px;margin-right:{int(font_px * 0.35)}px;vertical-align:middle"></span>'
           if kind == "name" else "")
    border = max(4, font_px // 14)
    return f"""<div id="target" style="display:inline-block;position:relative;padding:0 {border * 2}px {border * 2}px 0">
 <div style="position:absolute;left:{border * 2}px;top:{border * 2}px;right:0;bottom:0;border-radius:{font_px // 2}px;background:{INK};opacity:.22;filter:url(#rough)"></div>
 <div style="position:relative;background:{PAPER};border:{border}px solid {INK};border-radius:{font_px // 2}px;padding:{pad_v}px {pad_h}px;filter:url(#rough)">
  <span style="font-weight:700;font-size:{font_px}px;line-height:1.15;white-space:nowrap;vertical-align:middle">{tab}{html.escape(text)}</span>
 </div></div>"""


def render(jobs: list[dict], scale: float = 1.5) -> list[Path]:
    """jobs: {"out": Path, "kind": "card"|"title"|"name", "image": bytes (card), "label"/"text": str, "font_px": int}."""
    if not jobs:
        return []
    from playwright.sync_api import sync_playwright

    font_css = _font_css()
    done = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=scale, viewport={"width": 1900, "height": 1000})
        page.route("**/*", lambda route: route.abort() if route.request.url.startswith("http") else route.continue_())
        for i, j in enumerate(jobs):
            if j["kind"] == "card":
                body = _card_body(j["image"], j.get("label", ""))
            else:
                body = _badge_body(j["text"], j["kind"], j.get("font_px", 64))
            page.set_content(_page(body, font_css, seed=3 + i * 11))
            page.evaluate("document.fonts.ready.then(() => true)")
            page.locator("#target").screenshot(path=str(j["out"]), omit_background=True)
            done.append(j["out"])
        browser.close()
    return done
