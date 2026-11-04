"""Final render: cut frames, reframe on the preacher, title/name badges, explainer cards, mux audio."""
from __future__ import annotations

import cv2
import numpy as np

from .media import FrameReader, VideoWriter

PAPER_BGR = (236, 248, 255)  # #FFF8EC
ANIM = 0.35  # seconds for overlays to fade/slide in and out
MARGIN = 0.04


def load_rgba(path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img.shape[2] == 3:
        img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
    return img


def fit(img: np.ndarray, max_w: float, max_h: float) -> np.ndarray:
    h, w = img.shape[:2]
    s = min(1.0, max_w / w, max_h / h)
    return img if s >= 1.0 else cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)


def prepare_card(png_path, W: int, H: int, mode: str) -> dict:
    img = load_rgba(png_path)
    ch, cw = img.shape[:2]
    if mode == "fullscreen":
        card = fit(img, W * 0.9, H * 0.9)
        canvas = np.zeros((H, W, 4), np.uint8)
        canvas[..., :3] = PAPER_BGR
        canvas[..., 3] = 255
        y, x = (H - card.shape[0]) // 2, (W - card.shape[1]) // 2
        blend(canvas[..., :3], card, x, y, 1.0)
        return {"img": canvas, "x": 0, "y": 0}
    if W >= H:  # landscape: right side, vertically centred (the preacher stands in the middle)
        card = cv2.resize(img, (int(W * 0.36), int(ch * W * 0.36 / cw)), interpolation=cv2.INTER_AREA)
        return {"img": card, "x": W - card.shape[1] - int(W * 0.03), "y": (H - card.shape[0]) // 2}
    card = cv2.resize(img, (int(W * 0.84), int(ch * W * 0.84 / cw)), interpolation=cv2.INTER_AREA)
    return {"img": card, "x": (W - card.shape[1]) // 2, "y": int(H * 0.55)}


def blend(frame: np.ndarray, img: np.ndarray, x: int, y: int, alpha: float) -> None:
    H, W = frame.shape[:2]
    h, w = img.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0 or alpha <= 0:
        return
    src = img[y0 - y:y1 - y, x0 - x:x1 - x]
    a = src[..., 3:4].astype(np.float32) * (alpha / 255.0)
    dst = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (dst * (1 - a) + src[..., :3].astype(np.float32) * a).astype(np.uint8)


def _fade(t: float, t0: float, t1: float | None) -> float:
    k = min(1.0, (t - t0) / ANIM)
    if t1 is not None:
        k = min(k, (t1 - t) / ANIM)
    k = max(0.0, k)
    return 1 - (1 - k) ** 3


def title_pos(img: np.ndarray, W: int, H: int, align: str, off_x: float, off_y: float) -> tuple[int, int]:
    w = img.shape[1]
    base = {"left": W * MARGIN, "center": (W - w) / 2, "right": W - w - W * MARGIN}[align]
    return int(base + off_x * W), int(H * MARGIN + off_y * H)


def name_pos(img: np.ndarray, W: int, H: int, person_x: float, face_y: float, face_h: float) -> tuple[int, int]:
    """Always under the preacher: centred on them, at chest/waist height, kept inside the frame."""
    h, w = img.shape[:2]
    x = min(max(person_x - w / 2, W * MARGIN), W - w - W * MARGIN)
    y = face_y + face_h * 2.6
    y = min(max(y, face_y + face_h * 1.2), H - h - H * MARGIN)
    return int(x), int(y)


def compose(frame: np.ndarray, t_orig: float, t_new: float, framing, overlays: dict, cards: list[dict]) -> np.ndarray:
    W, H = framing.W, framing.H
    out = framing.apply(frame, t_orig)
    if out is frame:
        out = frame.copy()
    nm = overlays.get("name")
    if nm and t_new < nm["until"]:
        px, fy, fh = framing.person_anchor(t_orig)
        x, y = name_pos(nm["img"], W, H, px, fy, fh)
        a = _fade(t_new, 0, nm["until"] if nm["until"] < 1e9 else None)
        blend(out, nm["img"], x, y + int((1 - a) * H * 0.02), a)
    tt = overlays.get("title")
    if tt and t_new < tt["until"]:
        a = _fade(t_new, 0, tt["until"] if tt["until"] < 1e9 else None)
        blend(out, tt["img"], tt["x"], tt["y"] - int((1 - a) * H * 0.02), a)
    for c in cards:
        if c["t0"] <= t_new < c["t1"]:
            a = _fade(t_new, c["t0"], c["t1"])
            dy = 0 if c["mode"] == "fullscreen" else int((1 - a) * H * 0.03)
            blend(out, c["img"], c["x"], c["y"] + dy, a)
    return out


def render(input_path, out_path, W: int, H: int, fps: float, timeline, framing, overlays: dict, cards: list[dict],
           wav_path, progress=None) -> None:
    reader = FrameReader(input_path, W, H, fps)
    writer = VideoWriter(out_path, W, H, fps, wav_path)
    n_out = int(round(timeline.total * fps))
    cur, frame = -1, None
    try:
        for j in range(n_out):
            tn = j / fps
            to = timeline.to_orig(tn)
            k = int(round(to * fps))
            while cur < k:
                f = reader.read()
                if f is None:
                    break
                frame, cur = f, cur + 1
            if frame is None:
                frame = np.zeros((H, W, 3), np.uint8)
            writer.write(compose(frame, to, tn, framing, overlays, cards))
            if progress and j % 15 == 0:
                progress(j / max(1, n_out))
    finally:
        reader.close()
    writer.close()
