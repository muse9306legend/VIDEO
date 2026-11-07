"""Drawing and animating the overlays: paper picture cards and twin characters with speech bubbles.

Design: cream paper #FFF8EC, ink #2E2A26 outlines with a slight hand-drawn wobble, Gaegu Bold text,
soft offset shadow. Every overlay is drawn once as an RGBA image; per frame only its position,
scale and opacity change, so rendering stays fast.
"""
from __future__ import annotations

import io
import math
import random
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import FONTS
from .characters import COLORS, CREAM, INK

SHADOW = (46, 42, 38, 70)
EMOJI_FONTS = ["seguiemj.ttf", "C:/Windows/Fonts/seguiemj.ttf", "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
               "NotoColorEmoji.ttf", "/System/Library/Fonts/Apple Color Emoji.ttc"]


@lru_cache(maxsize=32)
def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / "Gaegu-Bold.ttf"), size)


@lru_cache(maxsize=64)
def emoji(ch: str, size: int) -> Image.Image | None:
    """Colour emoji as RGBA, or None when no emoji font is installed."""
    for path in EMOJI_FONTS:
        for fs in (109, 137, 160, size):  # bitmap emoji fonts only load at fixed sizes
            try:
                f = ImageFont.truetype(path, fs)
            except OSError:
                continue
            im = Image.new("RGBA", (fs * 2, fs * 2), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((fs // 4, fs // 4), ch, font=f, embedded_color=True)
            box = im.getbbox()
            if not box:
                break
            im = im.crop(box)
            k = size / max(im.size)
            return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    return None


def _wobbly(d: ImageDraw.ImageDraw, box, r, width, seed=0):
    """A rounded rectangle outline drawn as a slightly uneven hand-drawn line."""
    rnd = random.Random(seed)
    x0, y0, x1, y1 = box
    pts = []
    corners = [(x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)]
    for cx, cy, a0 in corners:
        for i in range(10):
            a = math.radians(a0 + i * 10)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        # straight edge to next corner, with a few wobble points
        nx, ny, _ = corners[(corners.index((cx, cy, a0)) + 1) % 4]
        ex, ey = cx + r * math.cos(math.radians(a0 + 90)), cy + r * math.sin(math.radians(a0 + 90))
        tx, ty = nx + r * math.cos(math.radians(a0 + 90)), ny + r * math.sin(math.radians(a0 + 90))
        for j in range(1, 6):
            f = j / 6
            pts.append((ex + (tx - ex) * f + rnd.uniform(-1, 1) * width * 0.35,
                        ey + (ty - ey) * f + rnd.uniform(-1, 1) * width * 0.35))
    pts.append(pts[0])
    d.line(pts, fill=INK, width=width, joint="curve")


def _with_shadow(im: Image.Image, off: int, blur: int) -> Image.Image:
    pad = off + blur * 2
    out = Image.new("RGBA", (im.width + pad, im.height + pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, SHADOW)
    sh.putalpha(im.getchannel("A").point(lambda v: v * SHADOW[3] // 255))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)) if blur else sh, (off, off))
    out.alpha_composite(im, (0, 0))
    return out


def card(picture: bytes | Image.Image, label: str, width: int, max_height: int, seed: int = 0) -> Image.Image:
    """A paper card holding the AI picture, with an optional short label underneath."""
    pic = picture if isinstance(picture, Image.Image) else Image.open(io.BytesIO(picture))
    pic = pic.convert("RGB")
    pad, lw = max(10, width // 28), max(3, width // 130)
    label_h = int(width * 0.11) if label else 0
    pw = width - 2 * pad
    ph = int(pw * pic.height / pic.width)
    if ph + 2 * pad + label_h > max_height:  # too tall: shrink the picture, keep the aspect
        ph = max_height - 2 * pad - label_h
        pw = int(ph * pic.width / pic.height)
        width = pw + 2 * pad
    h = ph + 2 * pad + label_h
    im = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = pad * 2
    d.rounded_rectangle([lw, lw, width - lw, h - lw], radius=r, fill=CREAM + (255,))
    mask = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw - 1, ph - 1], radius=r // 2, fill=255)
    im.paste(pic.resize((pw, ph), Image.LANCZOS), (pad, pad), mask)
    _wobbly(d, (lw, lw, width - lw, h - lw), r, lw, seed)
    if label:
        f = font(int(label_h * 0.8))
        d.text((width / 2, pad + ph + label_h * 0.52), label, font=f, fill=INK, anchor="mm")
    return _with_shadow(im, max(4, width // 60), max(2, width // 120))


def bubble(text: str, emo: str, max_w: int, tail: str, color) -> Image.Image:
    """Speech bubble with Gaegu text, one emoji and the twin's colour as a thin stripe."""
    fs = max(20, max_w // 9)
    f = font(fs)
    limit = max_w * 0.78
    lines, cur = [], ""
    for word in text.split():  # wrap at spaces; split a word only if it alone is too wide
        cand = f"{cur} {word}" if cur else word
        if f.getlength(cand) <= limit:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        cur = ""
        for ch in word:
            if f.getlength(cur + ch) > limit and cur:
                lines.append(cur)
                cur = ""
            cur += ch
    lines.append(cur)
    em = emoji(emo, int(fs * 1.25)) if emo else None
    tw = max(f.getlength(line) for line in lines) + (em.width + fs * 0.3 if em else 0)
    pad, lw = int(fs * 0.55), max(3, fs // 12)
    w = int(tw + 2 * pad)
    th = int(len(lines) * fs * 1.12)
    tail_h = int(fs * 0.8)
    h = th + 2 * pad
    im = Image.new("RGBA", (w + 2 * lw, h + tail_h + 2 * lw), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = min(h // 2, pad * 2)
    tx = int(w * (0.25 if tail == "left" else 0.75))
    tail_pts = [(tx - tail_h * 0.6, h - lw * 2), (tx + (-1 if tail == "left" else 1) * tail_h * 0.4, h + tail_h), (tx + tail_h * 0.6, h - lw * 2)]
    d.polygon(tail_pts, fill=CREAM + (255,), outline=INK, width=lw)
    d.rounded_rectangle([lw, lw, w, h], radius=r, fill=CREAM + (255,))
    band = max(4, fs // 7)  # the twin's colour as a thin stripe along the bottom edge
    d.rounded_rectangle([lw + r // 2, h - band - lw * 2, w - r // 2, h - lw * 2], radius=band // 2, fill=tuple(color) + (255,))
    d.polygon(tail_pts[:1] + tail_pts[2:], fill=CREAM + (255,))
    _wobbly(d, (lw, lw, w, h), r, lw, seed=len(text))
    d.line([tail_pts[0], tail_pts[1], tail_pts[2]], fill=INK, width=lw, joint="curve")
    y = pad + lw
    for line in lines:
        d.text((pad + lw, y), line, font=f, fill=INK)
        y += fs * 1.12
    if em:
        im.alpha_composite(em, (int(w - pad - em.width + lw), int(pad + lw + (th - em.height) / 2)))
    return _with_shadow(im, max(3, fs // 10), 2)


def name_tag(name: str, color, height: int) -> Image.Image:
    f = font(int(height * 0.8))
    w = int(f.getlength(name) + height * 0.9)
    lw = max(2, height // 12)
    im = Image.new("RGBA", (w + 2 * lw, height + 2 * lw), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([lw, lw, w, height], radius=height // 2, fill=tuple(color) + (255,), outline=INK, width=lw)
    d.text(((w + lw) / 2, (height + lw) / 2), name, font=f, fill=INK, anchor="mm")
    return im


def character(sprite: Image.Image, text: str, emo: str, name: str, twin: str, side: str, height: int, bubble_w: int) -> tuple[Image.Image, tuple[int, int]]:
    """Sprite + name tag + speech bubble as one RGBA image. Returns (image, sprite foot point in the image)."""
    k = height / sprite.height
    spr = sprite.resize((max(1, int(sprite.width * k)), height), Image.LANCZOS)
    spr = _with_shadow(spr, max(3, height // 90), 3)
    tag = name_tag(name, COLORS[twin], max(16, height // 10))
    bub = bubble(text, emo, max(160, bubble_w), "left" if side == "left" else "right", COLORS[twin])
    w = max(spr.width + bub.width // 2, bub.width, tag.width)
    h = bub.height + int(height * 0.92) + tag.height // 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sx = 0 if side == "left" else w - spr.width
    sy = bub.height - int(height * 0.08)
    im.alpha_composite(spr, (sx, min(sy, h - spr.height)))
    bx = min(w - bub.width, sx + spr.width // 2) if side == "left" else max(0, sx + spr.width // 2 - bub.width)
    im.alpha_composite(bub, (bx, 0))
    im.alpha_composite(tag, (sx + (spr.width - tag.width) // 2, h - tag.height))
    return im, (sx + spr.width // 2, h)


@dataclass
class El:
    """One animated overlay. (x, y) is the top-left corner when fully shown."""
    start: float
    end: float
    img: Image.Image
    x: int
    y: int
    enter: str = "pop"      # pop | rise | slide_left | slide_right
    bob: float = 0.0        # bounce amplitude in pixels while shown
    _cache: dict = field(default_factory=dict, repr=False)

    def active(self, t: float) -> bool:
        return self.start <= t < self.end


def _ease_back(p: float) -> float:
    c = 1.70158
    p -= 1
    return 1 + (c + 1) * p ** 3 + c * p ** 2


def _blend(frame: np.ndarray, im: Image.Image, x: int, y: int, opacity: float) -> None:
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(w, x + im.width), min(h, y + im.height)
    if x0 >= x1 or y0 >= y1:
        return
    ov = np.asarray(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), dtype=np.float32)
    a = ov[..., 3:4] * (opacity / 255.0)
    region = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (region * (1 - a) + ov[..., :3] * a).astype(np.uint8)


def compose(frame: np.ndarray, t: float, els: list[El]) -> np.ndarray:
    """Draw every overlay active at time t onto a copy of the frame."""
    out = None
    for e in els:
        if not e.active(t):
            continue
        if out is None:
            out = frame.copy()
        p_in = min(1.0, (t - e.start) / 0.35)
        p_out = min(1.0, (e.end - t) / 0.3)
        opacity = min(1.0, p_in * 1.6, p_out)
        img, x, y = e.img, e.x, e.y
        if e.enter == "pop" and p_in < 1:
            s = max(0.05, _ease_back(p_in))
            key = round(s, 2)
            img = e._cache.get(key)
            if img is None:
                img = e.img.resize((max(1, int(e.img.width * s)), max(1, int(e.img.height * s))), Image.BILINEAR)
                e._cache[key] = img
            x, y = e.x + (e.img.width - img.width) // 2, e.y + (e.img.height - img.height) // 2
        elif e.enter == "rise":
            y += int((1 - _ease_back(p_in)) * e.img.height * 0.6) + int((1 - p_out) * e.img.height * 0.3)
        elif e.enter in ("slide_left", "slide_right"):
            d = -1 if e.enter == "slide_left" else 1
            x += int(d * (1 - _ease_back(p_in)) * e.img.width)
        if e.bob:
            y += int(e.bob * math.sin((t - e.start) * 2 * math.pi * 2.2))
        _blend(out, img, x, y, opacity)
    return frame if out is None else out
