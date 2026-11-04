"""Explainer illustrations generated with ChatGPT's image model (OpenAI Images API)."""
from __future__ import annotations

import base64
import os

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


def generate(brief: str, context: str) -> bytes:
    from openai import OpenAI

    client = OpenAI()
    prompt = f"{STYLE}\n\nScene: {brief}\n(Sermon context, for meaning only - do not write it: {context[:400]})"
    models = [os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2"), "gpt-image-1"]
    last = None
    for model in dict.fromkeys(models):  # try the configured model, then fall back
        try:
            r = client.images.generate(model=model, prompt=prompt, size="1536x1024", quality="medium", n=1)
            return base64.b64decode(r.data[0].b64_json)
        except Exception as e:
            last = e
    raise RuntimeError(f"이미지 생성 실패: {last}")
