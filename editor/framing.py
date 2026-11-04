"""Find the preacher (largest face) and compute a reframe that puts them in the horizontal centre."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .media import FrameReader, grab_frame

MODEL = Path(__file__).resolve().parent.parent / "assets" / "models" / "face_detection_yunet_2023mar.onnx"
SCAN_W = 640
MAX_AUTO_ZOOM = 1.8


def _detector(w: int, h: int):
    return cv2.FaceDetectorYN.create(str(MODEL), "", (w, h), 0.6, 0.3, 50)


def _largest_face(det, frame) -> tuple[float, float, float] | None:
    """-> (cx, cy, face_h) as fractions of the frame, for the biggest face (the preacher is usually the closest)."""
    _, faces = det.detect(frame)
    if faces is None or len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])[:4]
    H, W = frame.shape[:2]
    return (x + w / 2) / W, (y + h / 2) / H, h / H


def _scan_size(W: int, H: int) -> tuple[int, int]:
    return SCAN_W, int(round(H * SCAN_W / W)) // 2 * 2


def sample_static(path, W: int, H: int, t0: float, t1: float, n: int = 30) -> list[tuple]:
    """Quick estimate from n frames spread over the range (used for the static framing and the preview)."""
    sw, sh = _scan_size(W, H)
    det = _detector(sw, sh)
    out = []
    for t in np.linspace(t0 + 1, max(t0 + 1, t1 - 1), n):
        f = grab_frame(path, float(t), sw, sh)
        if f is not None and (face := _largest_face(det, f)):
            out.append((float(t), *face))
    return out


def sample_track(path, W: int, H: int, step: float = 1.0, progress=None, duration: float = 0) -> list[tuple]:
    """Face position every `step` seconds over the whole video (used when following the preacher)."""
    sw, sh = _scan_size(W, H)
    det = _detector(sw, sh)
    reader = FrameReader(path, sw, sh, 1.0 / step)
    out, i = [], 0
    try:
        while (f := reader.read()) is not None:
            if (face := _largest_face(det, f)):
                out.append((i * step, *face))
            i += 1
            if progress and duration and i % 20 == 0:
                progress(min(1.0, i * step / duration))
    finally:
        reader.close()
    return out


def face_at_frame(frame) -> tuple[float, float, float] | None:
    H, W = frame.shape[:2]
    sw, sh = _scan_size(W, H)
    return _largest_face(_detector(sw, sh), cv2.resize(frame, (sw, sh), interpolation=cv2.INTER_AREA))


@dataclass
class Framing:
    """Maps original time -> affine transform (zoom z, face fx/fy in px, target tx/ty in px)."""
    W: int
    H: int
    ts: np.ndarray
    fx: np.ndarray  # fractions
    fy: np.ndarray
    fh: np.ndarray
    zoom: float
    off_x: float  # user offsets, fraction of frame
    off_y: float

    def at(self, t: float) -> tuple[float, float, float, float, float, float]:
        """-> (z, fx_px, fy_px, tx, ty, face_h_px_out)."""
        fx = float(np.interp(t, self.ts, self.fx)) * self.W
        fy = float(np.interp(t, self.ts, self.fy)) * self.H
        fh = float(np.interp(t, self.ts, self.fh)) * self.H
        z = self.zoom
        tx = self.W / 2 + self.off_x * self.W
        ty = fy + self.off_y * self.H
        # Keep the picture covering the whole frame (no black bars): clamp the target.
        tx = min(max(tx, self.W - (self.W - fx) * z), fx * z)
        ty = min(max(ty, self.H - (self.H - fy) * z), fy * z)
        return z, fx, fy, tx, ty, fh * z

    def matrix(self, t: float) -> np.ndarray | None:
        z, fx, fy, tx, ty, _ = self.at(t)
        if abs(z - 1) < 1e-3 and abs(tx - fx) < 0.5 and abs(ty - fy) < 0.5:
            return None
        return np.float32([[z, 0, tx - fx * z], [0, z, ty - fy * z]])

    def apply(self, frame: np.ndarray, t: float) -> np.ndarray:
        m = self.matrix(t)
        if m is None:
            return frame
        return cv2.warpAffine(frame, m, (self.W, self.H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    def person_anchor(self, t: float) -> tuple[float, float, float]:
        """-> (x centre of the preacher, y of the face centre, face height) in output pixels."""
        _, _, _, tx, ty, fh = self.at(t)
        return tx, ty, fh


def _needed_zoom(fx, fy, tx, ty, W, H) -> float:
    eps = 1e-6
    return max(1.0, tx / max(fx, eps), (W - tx) / max(W - fx, eps), ty / max(fy, eps), (H - ty) / max(H - fy, eps))


def build(samples: list[tuple], W: int, H: int, follow: bool, min_zoom: float, off_x: float, off_y: float,
          t0: float, t1: float) -> Framing:
    """samples: [(t, cx, cy, face_h)] in fractions. Returns a Framing for the whole range."""
    if not samples:  # nobody found: plain frame + manual offsets
        ts, fx, fy, fh = np.array([t0, t1]), np.full(2, 0.5), np.full(2, 0.4), np.full(2, 0.12)
    elif not follow:
        a = np.array(samples)
        ts = np.array([t0, t1])
        fx, fy, fh = (np.full(2, np.median(a[:, k])) for k in (1, 2, 3))
    else:
        a = np.array(samples)
        grid = np.arange(t0, t1 + 1, 1.0)
        cols = [np.interp(grid, a[:, 0], a[:, k]) for k in (1, 2, 3)]
        # Heavy smoothing: a slow, calm camera instead of jittery tracking.
        cols = [_smooth(c, 9, 7) for c in cols]
        ts, (fx, fy, fh) = grid, cols
    # One zoom for the whole video (no zoom pumping): enough to centre the preacher most of the time.
    needs = [_needed_zoom(x * W, y * H, W / 2 + off_x * W, y * H + off_y * H, W, H) for x, y in zip(fx, fy)]
    zoom = float(np.clip(max(min_zoom, np.percentile(needs, 90)), 1.0, max(MAX_AUTO_ZOOM, min_zoom)))
    return Framing(W, H, ts, fx, fy, fh, zoom, off_x, off_y)


def _smooth(x: np.ndarray, med: int, avg: int) -> np.ndarray:
    pad = med // 2
    xp = np.pad(x, pad, mode="edge")
    m = np.array([np.median(xp[i:i + med]) for i in range(len(x))])
    k = np.ones(avg) / avg
    return np.convolve(np.pad(m, avg // 2, mode="edge"), k, mode="valid")[: len(x)]
