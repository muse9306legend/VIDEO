"""Explainer illustrations generated with ChatGPT's image model (OpenAI Images API).

Image generation is the slowest step (tens of seconds per picture), so:
- all pictures are requested in parallel (OPENAI_IMAGE_CONCURRENCY, default 6),
- the pipeline starts them right after the transcript analysis and keeps working meanwhile,
- a picture that is too slow is retried once with faster settings,
- finished pictures are cached, so re-rendering the same sermon (e.g. after moving a slider) costs nothing.
"""
from __future__ import annotations

import base64
import hashlib
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "jobs" / "_image_cache"

STYLE = (
    "Flat vector illustration combined with a hand-drawn cartoon look: thick, slightly wobbly dark brown-black "
    "outlines (#2E2A26) with round line ends, flat solid fills, a few small white highlight strokes, no gradients, "
    "no photorealism. Warm pastel palette: coral #FFB4A2, yellow #FFD166, sky blue #8ECAE6, mint #95D5B2, "
    "lavender #CDB4DB, orange #F4A261. Simple, friendly and calm, one clear idea, 3-8 objects, generous empty space. "
    "Plain solid cream background (#FFF8EC) with no border or frame. "
    "Absolutely no text, letters, numbers or captions anywhere in the image. "
    "Respectful and reverent for a church sermon; people are simple generic cartoon figures, never a realistic "
    "likeness of a real person; prefer symbolic objects."
)


def available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def concurrency() -> int:
    try:
        return max(1, int(os.environ.get("OPENAI_IMAGE_CONCURRENCY", "6")))
    except ValueError:
        return 6


def _prompt(brief: str, context: str) -> str:
    return f"{STYLE}\n\nScene: {brief}\n(Sermon context, for meaning only - do not write it: {context[:400]})"


def _model() -> str:
    return os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2")


def _cache_path(prompt: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(f"{_model()}|{prompt}".encode()).hexdigest()[:24] + ".png")


def generate(brief: str, context: str, slow_after: float = 90.0) -> bytes:
    """One picture. Attempts: configured model at medium quality (cut off after `slow_after` s),
    then the same model at low quality (much faster), then gpt-image-1 as a last resort."""
    from openai import OpenAI

    prompt = _prompt(brief, context)
    cached = _cache_path(prompt)
    if cached.exists():
        return cached.read_bytes()

    attempts = [(_model(), "medium", slow_after), (_model(), "low", slow_after), ("gpt-image-1", "low", slow_after * 1.5)]
    last = None
    for model, quality, timeout in dict.fromkeys(attempts):
        try:
            client = OpenAI(timeout=timeout, max_retries=2)  # 429 rate limits are retried by the SDK
            r = client.images.generate(model=model, prompt=prompt, size="1536x1024", quality=quality, n=1)
            data = base64.b64decode(r.data[0].b64_json)
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
            return data
        except Exception as e:
            last = e
    raise RuntimeError(f"이미지 생성 실패: {last}")


class Batch:
    """Starts every picture at once in the background; collect the results later with `results()`."""

    def __init__(self, items: list[dict], log=print):
        self.log = log
        self.t0 = time.time()
        self.pool = ThreadPoolExecutor(max_workers=max(1, min(len(items), concurrency())))
        self.futures: list[Future] = [self.pool.submit(self._one, it) for it in items]
        if items:
            log(f"설명 그림 {len(items)}개 동시 생성 시작 (동시 {min(len(items), concurrency())}개)")

    def _one(self, it: dict) -> bytes | None:
        start = time.time()
        try:
            data = generate(it["visual_brief"], it.get("context", ""))
            self.log(f"그림 완료: {it['concept']} ({time.time() - start:.0f}초)")
            return data
        except Exception as e:
            self.log(f"그림 생성 실패 ({it['concept']}): {e}")
            return None

    def results(self) -> list[bytes | None]:
        out = [f.result() for f in self.futures]
        self.pool.shutdown(wait=False)
        if self.futures:
            self.log(f"설명 그림 전체 {time.time() - self.t0:.0f}초 만에 준비 완료")
        return out
