"""The twins as cartoon characters: one sprite per (twin, pose), consistent across the whole video.

How consistency is kept: each twin first gets a base drawing (from reference photos when given),
then every other pose is drawn from that base image with images.edit. Without an OpenAI key,
simple hand-drawn placeholder characters are used so the layout still works.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import images

INK = (46, 42, 38)
CREAM = (255, 248, 236)
COLORS = {"A": (255, 180, 162), "B": (142, 202, 230)}  # coral, sky

POSES = {
    "happy": "standing and smiling happily, hands relaxed",
    "wave": "waving one hand hello with a big smile",
    "point": "pointing excitedly to the side with one finger, mouth open as if saying 'look!'",
    "think": "finger on chin, eyes looking up, thinking",
    "surprised": "both hands on cheeks, eyes wide, mouth a small O, surprised",
    "laugh": "laughing with eyes closed, holding tummy",
    "eat": "holding chopsticks and a bowl, cheeks full, eating happily",
    "thumbs_up": "giving a big thumbs up with a wink",
    "cheer": "jumping with both arms raised, cheering",
    "shy": "hands behind back, blushing, smiling shyly",
}
BASE_POSE = "happy"

STYLE = (
    "Cute chibi cartoon character for a kids YouTube channel: big head, small body, full body visible from head to "
    "shoes, thick slightly wobbly dark outlines (#2E2A26), flat bright colours, small white highlights, rosy cheeks. "
    "Centered, facing the viewer. Transparent background (or plain pure white if transparency is impossible). "
    "No text, no letters, no frame, no shadow on the ground."
)


def _prompt(desc: str, pose: str, mode: str) -> str:
    who = desc or "a cheerful Korean child"
    if mode == "photo":
        lead = ("Turn the child in the reference photo(s) into a cartoon character. Keep their hairstyle, hair colour, "
                "face shape and clothing colours recognisable, but make it a simple cartoon, not a realistic portrait.")
    elif mode == "base":
        lead = ("Redraw exactly this same character (same hair, face, outfit, colours and drawing style) in a new pose. "
                "Only the pose and expression change.")
    else:
        lead = f"Design an original cartoon character: {who}."
    return f"{STYLE}\n\n{lead}\nCharacter: {who}.\nPose: {POSES[pose]}."


def cut_out(png: bytes) -> Image.Image:
    """Keep real transparency; otherwise remove a plain background by flood-filling from the border."""
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    w, h = im.size
    corners = [im.getpixel(p)[3] for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    if max(corners) > 10:
        rgb = im.convert("RGB")
        key = (255, 0, 255)
        for p in [(0, 0), (w // 2, 0), (w - 1, 0), (0, h // 2), (w - 1, h // 2), (0, h - 1), (w // 2, h - 1), (w - 1, h - 1)]:
            if rgb.getpixel(p) != key:
                ImageDraw.floodfill(rgb, p, key, thresh=40)
        a = np.asarray(rgb)
        fg = ~np.all(a == key, axis=2)
        alpha = Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1))
        im.putalpha(alpha)
    box = im.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
    return im.crop(box) if box else im


def placeholder(twin: str, pose: str, size: int = 600) -> Image.Image:
    """A simple drawn chibi kid in the twin's colour, used without an OpenAI key."""
    s = size / 600
    im = Image.new("RGBA", (int(420 * s), size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    col, lw = COLORS[twin], max(3, int(7 * s))
    cx = im.width // 2

    def E(x0, y0, x1, y1, fill):
        d.ellipse([cx + x0 * s, y0 * s, cx + x1 * s, y1 * s], fill=fill, outline=INK, width=lw)

    arms_up = pose in ("cheer", "wave", "surprised")
    # body + legs
    d.rounded_rectangle([cx - 95 * s, 330 * s, cx + 95 * s, 520 * s], radius=int(60 * s), fill=col, outline=INK, width=lw)
    for dx in (-50, 50):
        d.rounded_rectangle([cx + (dx - 28) * s, 500 * s, cx + (dx + 28) * s, 590 * s], radius=int(20 * s), fill=CREAM, outline=INK, width=lw)
    # arms
    for side in (-1, 1):
        up = arms_up and (pose != "wave" or side == 1)
        x0, y0 = cx + side * 90 * s, 370 * s
        x1, y1 = cx + side * 165 * s, (250 if up else 470) * s
        d.line([x0, y0, x1, y1], fill=INK, width=int(34 * s))
        d.line([x0, y0, x1, y1], fill=CREAM, width=int(34 * s) - 2 * lw)
        d.ellipse([x1 - 22 * s, y1 - 22 * s, x1 + 22 * s, y1 + 22 * s], fill=CREAM, outline=INK, width=lw)
    # head + hair
    E(-150, 40, 150, 340, CREAM)
    d.chord([cx - 150 * s, 40 * s, cx + 150 * s, 340 * s], 180, 360, fill=INK)
    if twin == "A":  # side buns
        E(-185, 60, -115, 130, INK)
        E(115, 60, 185, 130, INK)
    else:  # a little sprout
        d.arc([cx - 10 * s, 0, cx + 50 * s, 60 * s], 90, 250, fill=INK, width=lw)
    # face
    ey = 205 * s
    if pose in ("laugh", "happy", "cheer", "thumbs_up"):
        for dx in (-55, 55):
            d.arc([cx + (dx - 22) * s, ey - 15 * s, cx + (dx + 22) * s, ey + 25 * s], 200, 340, fill=INK, width=lw)
    else:
        for dx in (-55, 55):
            r = 20 if pose == "surprised" else 14
            d.ellipse([cx + (dx - r) * s, ey - r * s, cx + (dx + r) * s, ey + r * s], fill=INK)
    for dx in (-90, 90):
        d.ellipse([cx + (dx - 22) * s, 240 * s, cx + (dx + 22) * s, 268 * s], fill=(255, 150, 150, 200))
    my = 270 * s
    if pose in ("surprised", "point"):
        d.ellipse([cx - 18 * s, my - 10 * s, cx + 18 * s, my + 30 * s], fill=(200, 80, 80), outline=INK, width=lw)
    elif pose in ("laugh", "cheer", "eat"):
        d.chord([cx - 40 * s, my - 30 * s, cx + 40 * s, my + 40 * s], 0, 180, fill=(200, 80, 80), outline=INK, width=lw)
    elif pose == "think":
        d.line([cx - 20 * s, my + 5 * s, cx + 20 * s, my], fill=INK, width=lw)
    else:
        d.arc([cx - 35 * s, my - 25 * s, cx + 35 * s, my + 20 * s], 20, 160, fill=INK, width=lw)
    return im


def sprites(twins: dict, needed: set[tuple[str, str]], out_dir: Path, log=print) -> dict[tuple[str, str], Image.Image]:
    """Return a sprite for every (twin, pose) in `needed`. Uses OpenAI when available, else placeholders."""
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[tuple[str, str], Image.Image] = {}
    if not needed:
        return result
    if not images.available():
        log("OPENAI_API_KEY 가 없어 쌍둥이 캐릭터를 기본 그림으로 표시합니다.")
        return {k: placeholder(*k) for k in needed}

    twin_ids = sorted({t for t, _ in needed})

    def base(t):
        refs = twins[t].get("photos") or []
        mode = "photo" if refs else "new"
        return images.make(_prompt(twins[t]["desc"], BASE_POSE, mode), refs=refs, size="1024x1536", transparent=True)

    bases = dict(zip(twin_ids, images.Batch([(f"{twins[t]['name']} 기본", lambda t=t: base(t)) for t in twin_ids],
                                            log, "캐릭터").results()))
    jobs, keys = [], []
    for t, pose in sorted(needed):
        if bases.get(t) is None or pose == BASE_POSE:
            continue
        keys.append((t, pose))
        jobs.append((f"{twins[t]['name']} {pose}", lambda t=t, pose=pose: images.make(
            _prompt(twins[t]["desc"], pose, "base"), refs=[bases[t]], size="1024x1536", transparent=True)))
    posed = dict(zip(keys, images.Batch(jobs, log, "캐릭터 포즈").results()))
    posed.update({(t, BASE_POSE): b for t, b in bases.items()})

    for t, pose in needed:
        png = posed.get((t, pose)) or bases.get(t)
        try:
            im = cut_out(png) if png else placeholder(t, pose)
        except Exception as e:
            log(f"캐릭터 배경 제거 실패 ({t} {pose}): {e}")
            im = placeholder(t, pose)
        im.save(out_dir / f"{t}_{pose}.png")
        result[(t, pose)] = im
    return result
