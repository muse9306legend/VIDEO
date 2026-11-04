"""Silence / filler-word detection and the cut timeline."""
from __future__ import annotations

import bisect
import re

import numpy as np

# Always fillers ("um", "uh") - cut even without AI review.
STRONG_FILLERS = {"어", "음", "으", "으음", "음음", "음음음", "어어", "어어어", "흠", "엄", "에", "어음", "으으", "흐음", "으흠", "음냐"}
# Sometimes fillers, sometimes real words - cut only when Claude confirms from context.
WEAK_FILLERS = {"아", "그", "저", "뭐", "이제", "막", "약간", "그니까", "그러니까", "좀", "저기", "있잖아", "그게", "뭐지", "어디", "그래서"}


def norm(word: str) -> str:
    return re.sub(r"[\s.,?!…~\-\"'·]", "", word)


def filler_candidates(segments: list[dict]) -> list[dict]:
    cands = []
    for s in segments:
        words = s["words"]
        for i, w in enumerate(words):
            n = norm(w["word"])
            kind = "strong" if n in STRONG_FILLERS else "weak" if n in WEAK_FILLERS else None
            if not kind:
                continue
            before = "".join(x["word"] for x in words[max(0, i - 6):i]).strip()
            after = "".join(x["word"] for x in words[i + 1:i + 7]).strip()
            cands.append({"id": w["id"], "word": n, "kind": kind, "start": w["start"], "end": w["end"],
                          "segment_id": s["id"], "context": f"{before} [{n}] {after}"})
    return cands


def silence_ranges(mono: np.ndarray, sr: int, thresh_db: float, min_len: float, hop_s: float = 0.02) -> list[tuple[float, float]]:
    hop = int(sr * hop_s)
    n = len(mono) // hop
    if n == 0:
        return []
    frames = mono[: n * hop].reshape(n, hop)
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    quiet = np.concatenate([[False], db < thresh_db, [False]])
    edges = np.flatnonzero(np.diff(quiet.astype(np.int8)))
    out = []
    for a, b in zip(edges[::2], edges[1::2]):
        if (b - a) * hop_s >= min_len:
            out.append((a * hop_s, b * hop_s))
    return out


def silence_removals(silences, pad: float) -> list[tuple[float, float]]:
    """Shrink each long pause to `2*pad` seconds instead of removing it entirely (keeps the rhythm natural)."""
    return [(s + pad, e - pad) for s, e in silences if e - s > 2 * pad + 0.05]


def word_removals(segments: list[dict], ids: set[int]) -> list[tuple[float, float]]:
    words = [w for s in segments for w in s["words"]]
    out = []
    for i, w in enumerate(words):
        if w["id"] not in ids:
            continue
        lo = words[i - 1]["end"] if i > 0 else 0.0
        hi = words[i + 1]["start"] if i + 1 < len(words) else w["end"] + 0.03
        s, e = max(lo, w["start"] - 0.03), min(max(hi, w["end"]), w["end"] + 0.03)
        if e - s > 0.05:
            out.append((s, e))
    return out


def build_keeps(duration: float, removals, min_keep: float = 0.12) -> list[tuple[float, float]]:
    rem = sorted((max(0.0, s), min(duration, e)) for s, e in removals if e > s)
    merged: list[list[float]] = []
    for s, e in rem:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    keeps, cur = [], 0.0
    for s, e in merged:
        if s - cur >= min_keep:
            keeps.append((cur, s))
        cur = max(cur, e)
    if duration - cur >= min_keep:
        keeps.append((cur, duration))
    return keeps


class Timeline:
    """Maps between original-video time and edited-video time."""

    def __init__(self, keeps):
        self.keeps = list(keeps)
        self.offsets, acc = [], 0.0
        for s, e in self.keeps:
            self.offsets.append(acc)
            acc += e - s
        self.total = acc
        self._starts = [s for s, _ in self.keeps]

    def to_new(self, t: float) -> float:
        i = bisect.bisect_right(self._starts, t) - 1
        if i < 0:
            return 0.0
        s, e = self.keeps[i]
        if t <= e:
            return self.offsets[i] + (t - s)
        return self.offsets[i + 1] if i + 1 < len(self.keeps) else self.total

    def to_orig(self, tn: float) -> float:
        i = max(0, bisect.bisect_right(self.offsets, tn) - 1)
        s, e = self.keeps[i]
        return min(e, s + (tn - self.offsets[i]))

    def is_kept(self, t: float) -> bool:
        i = bisect.bisect_right(self._starts, t) - 1
        return i >= 0 and t <= self.keeps[i][1]
