"""Pictures from ChatGPT's image model (OpenAI Images API).

Generation is the slowest step, so every picture is requested in parallel (OPENAI_IMAGE_CONCURRENCY,
default 6) while the rest of the pipeline keeps working, slow requests fall back to faster settings,
and finished pictures are cached in jobs/_image_cache so re-renders cost nothing.
"""
from __future__ import annotations

import base64
import hashlib
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from . import JOBS

CACHE_DIR = JOBS / "_image_cache"

CARD_STYLE = (
    "Flat vector illustration combined with a hand-drawn cartoon look for a kids YouTube channel: thick, slightly "
    "wobbly dark outlines (#2E2A26) with round line ends, flat bright fills, small white highlight strokes, no "
    "gradients, no photorealism. Cheerful pastel palette: coral #FFB4A2, yellow #FFD166, sky blue #8ECAE6, mint "
    "#95D5B2, lavender #CDB4DB, orange #F4A261. One clear idea, 3-8 objects, cute rounded shapes, generous empty "
    "space. Plain solid cream background (#FFF8EC), no border or frame. Absolutely no text, letters or numbers."
)


def available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def concurrency() -> int:
    try:
        return max(1, int(os.environ.get("OPENAI_IMAGE_CONCURRENCY", "6")))
    except ValueError:
        return 6


def _model() -> str:
    return os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2")


def card_prompt(brief: str) -> str:
    return f"{CARD_STYLE}\n\nScene: {brief}"


def make(prompt: str, *, refs: list[bytes] | None = None, size: str = "1536x1024",
         transparent: bool = False, slow_after: float = 90.0) -> bytes:
    """One picture. Attempts: configured model at medium quality, then low quality, then gpt-image-1.
    With `refs`, the reference images (e.g. photos of the twins) guide the drawing through images.edit."""
    from openai import OpenAI

    refs = refs or []
    key = hashlib.sha256(f"{_model()}|{size}|{transparent}|{prompt}".encode()
                         + b"".join(hashlib.sha256(r).digest() for r in refs)).hexdigest()[:24]
    cached = CACHE_DIR / f"{key}.png"
    if cached.exists():
        return cached.read_bytes()

    attempts = [(_model(), "medium", slow_after), (_model(), "low", slow_after), ("gpt-image-1", "low", slow_after * 1.5)]
    last = None
    for mdl, quality, timeout in dict.fromkeys(attempts):
        extra = {"background": "transparent"} if transparent else {}
        if refs:
            extra["input_fidelity"] = "high"
        while True:
            try:
                client = OpenAI(timeout=timeout, max_retries=2)
                if refs:
                    files = [(f"ref{i}.png", r, "image/png") for i, r in enumerate(refs)]
                    r = client.images.edit(model=mdl, image=files, prompt=prompt, size=size, quality=quality, **extra)
                else:
                    r = client.images.generate(model=mdl, prompt=prompt, size=size, quality=quality, n=1, **extra)
                data = base64.b64decode(r.data[0].b64_json)
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(data)
                return data
            except Exception as e:
                last = e
                bad = next((k for k in extra if k in str(e)), None)
                if bad:  # this model does not take an optional parameter: drop it and retry
                    extra.pop(bad)
                    continue
                break
    raise RuntimeError(f"이미지 생성 실패: {last}")


class Batch:
    """Runs jobs (name, fn) in the background at once; collect the results later with `results()`."""

    def __init__(self, jobs: list[tuple[str, callable]], log=print, what: str = "그림"):
        self.log, self.what, self.t0 = log, what, time.time()
        n = max(1, min(len(jobs), concurrency()))
        self.pool = ThreadPoolExecutor(max_workers=n)
        self.futures: list[Future] = [self.pool.submit(self._one, name, fn) for name, fn in jobs]
        if jobs:
            log(f"{what} {len(jobs)}개 동시 생성 시작 (동시 {n}개)")

    def _one(self, name, fn):
        start = time.time()
        try:
            data = fn()
            self.log(f"{self.what} 완료: {name} ({time.time() - start:.0f}초)")
            return data
        except Exception as e:
            self.log(f"{self.what} 생성 실패 ({name}): {e}")
            return None

    def results(self) -> list:
        out = [f.result() for f in self.futures]
        self.pool.shutdown(wait=False)
        if self.futures:
            self.log(f"{self.what} 전체 {time.time() - self.t0:.0f}초 만에 준비 완료")
        return out
