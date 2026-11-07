"""Claude reads the transcript and plans explainer pictures and twin-character reactions."""
from __future__ import annotations

import json
import os

from .characters import POSES

_client = None
_client_key: str | None = None


def model() -> str:
    return os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")


def available() -> bool:
    """True when a key is configured. Rebuilds the client when the key in .env changed."""
    global _client, _client_key
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if not key:
        _client = _client_key = None
        return False
    if _client is not None and key == _client_key:
        return True
    try:
        import anthropic

        _client, _client_key = anthropic.Anthropic(), key
        return True
    except Exception:
        _client = _client_key = None
        return False


def _call(system: str, user: str, *, effort: str, schema: dict, max_tokens: int = 16000) -> str:
    if not available():
        raise RuntimeError("Claude API 키가 설정되지 않았습니다 (.env 의 ANTHROPIC_API_KEY).")
    resp = _client.beta.messages.create(
        model=model(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude가 요청을 거절했습니다.")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Claude 응답이 길이 제한에 걸렸습니다.")
    return "".join(b.text for b in resp.content if b.type == "text")


SYSTEM = f"""You are the editor of a Korean family kids YouTube channel.
You receive the timestamped Korean transcript of one video and plan two kinds of overlays.

1. cards - explainer pictures that help young viewers picture what is being talked about.
   Good: a food, animal, place, object, process or comparison that a child may not picture,
   or a fun moment that a picture makes clearer (e.g. how ramen noodles are made, where penguins live).
   Bad: greetings, "subscribe", chit-chat with nothing to show.
   Start just after the idea is first said, 4-7 seconds long, at least 25 seconds apart.
   visual_brief: one concrete English description of a single simple scene for an illustrator
   (3-8 objects, no text or letters in the picture, no real people's likeness).
   label: at most one very short Korean word (max 8 characters) shown under the picture, or "".

2. reactions - the twins appear as cute cartoon characters in a corner and react to the moment with a
   short speech bubble, like friendly co-hosts. Show their chemistry: one teases, the other answers,
   they cheer, are surprised, or get hungry together. Use both twins about equally.
   twin: "A" or "B" (see the twin descriptions). pose: one of {", ".join(POSES)}.
   text: natural spoken Korean a child would say, max 18 characters. emoji: exactly one emoji that fits.
   2-4 seconds long. The other twin may answer right after (a short exchange of 2-3 bubbles); between
   exchanges leave about 8 seconds or more. Reactions never overlap each other. Never mock anyone; keep everything kind and safe for kids.

Times are seconds in the original video. Return fewer items rather than weak ones."""

SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {"type": "array", "items": {
            "type": "object",
            "properties": {"start": {"type": "number"}, "duration": {"type": "number"}, "concept": {"type": "string"},
                           "visual_brief": {"type": "string"}, "label": {"type": "string"}},
            "required": ["start", "duration", "concept", "visual_brief", "label"], "additionalProperties": False}},
        "reactions": {"type": "array", "items": {
            "type": "object",
            "properties": {"start": {"type": "number"}, "duration": {"type": "number"}, "twin": {"type": "string", "enum": ["A", "B"]},
                           "pose": {"type": "string", "enum": list(POSES)}, "text": {"type": "string"}, "emoji": {"type": "string"}},
            "required": ["start", "duration", "twin", "pose", "text", "emoji"], "additionalProperties": False}},
    },
    "required": ["cards", "reactions"],
    "additionalProperties": False,
}


def plan(segments: list[dict], duration: float, twins: dict, *, max_cards: int, max_reactions: int, topic: str = "") -> dict:
    lines = [f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments]
    user = (
        (f"영상 주제: {topic}\n" if topic else "") + f"영상 길이: {duration:.1f}초\n"
        f"쌍둥이 A: {twins['A']['name']} - {twins['A']['desc'] or '설명 없음'}\n"
        f"쌍둥이 B: {twins['B']['name']} - {twins['B']['desc'] or '설명 없음'}\n\n"
        "## 대본 (초)\n" + "\n".join(lines) +
        f"\n\n## 요청\n- cards: 최대 {max_cards}개\n- reactions: 최대 {max_reactions}개"
    )
    data = json.loads(_call(SYSTEM, user, effort="medium", schema=SCHEMA))
    return clean(data, duration, max_cards, max_reactions)


def clean(data: dict, duration: float, max_cards: int, max_reactions: int, card_gap: float = 10.0) -> dict:
    """Clamp times into the video, drop overlaps and keep cards apart even if the model slips."""
    def keep(items, gap, limit, lo, hi):
        out, last_end = [], -1e9
        for it in sorted(items, key=lambda x: x["start"]):
            it["duration"] = min(max(float(it["duration"]), lo), hi)
            it["start"] = max(0.0, float(it["start"]))
            if it["start"] >= duration - 1.0 or it["start"] < last_end + gap:
                continue
            it["duration"] = min(it["duration"], duration - it["start"])
            out.append(it)
            last_end = it["start"] + it["duration"]
            if len(out) >= limit:
                break
        return out

    reactions = [r for r in data.get("reactions", []) if r.get("pose") in POSES and r.get("twin") in ("A", "B")]
    for r in reactions:
        r["text"] = r["text"].strip()[:24]
    return {"cards": keep(data.get("cards", []), card_gap, max_cards, 3.0, 8.0),
            "reactions": keep(reactions, 0.2, max_reactions, 1.5, 5.0)}
