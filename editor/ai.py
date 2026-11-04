"""Claude: reads the sermon transcript, decides which fillers to cut and where an explainer picture helps."""
from __future__ import annotations

import json
import os

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
_client: anthropic.Anthropic | None = None


def available() -> bool:
    global _client
    if _client is not None:
        return True
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return False
    try:
        _client = anthropic.Anthropic()
        return True
    except Exception:
        return False


def _call(system: str, user: str, *, effort: str, schema: dict | None = None, max_tokens: int = 16000) -> str:
    if not available():
        raise RuntimeError("Claude API 키가 설정되지 않았습니다 (.env 의 ANTHROPIC_API_KEY).")
    output_config: dict = {"effort": effort}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    resp = _client.beta.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config=output_config,
        # If a request is declined by a safety classifier, retry it on a fallback model automatically.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude가 요청을 거절했습니다.")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Claude 응답이 길이 제한에 걸렸습니다.")
    return "".join(b.text for b in resp.content if b.type == "text")


ANALYSIS_SYSTEM = """You are the assistant editor for a Korean church's sermon videos.
You receive a timestamped Korean transcript of one sermon and make two editing decisions.

1. filler_cut_ids - which filler-word candidates can be cut.
   Cut hesitation sounds and empty fillers ("어", "음", a meaningless "그", "뭐", "이제", "막" ...).
   Keep a candidate when removing it would change meaning or break the sentence, when it is part of a
   Bible quotation or prayer, or when it is a deliberate rhetorical "아!" / "자," that the preacher uses for emphasis.
   When unsure, keep it.

2. cards - moments where a short explainer illustration helps the congregation understand what is being said.
   Good: a Bible place, object, custom or historical background the audience may not picture
   (e.g. a threshing floor, a Roman denarius, the route of the Exodus), a parable or illustration story,
   a comparison, a sequence of steps, a number or proportion.
   Bad: prayers, Bible verses read aloud, emotional appeals, greetings, announcements, invitations to respond.
   Space cards at least 60 seconds apart, duration 4-7 seconds, start just after the idea is first mentioned.
   visual_brief: one concrete English description of a single, simple, symbolic scene for an illustrator
   (3-8 objects; no text in the picture). Keep it reverent; never ask for a depiction of God's face.
   label: at most one very short Korean word (max 8 characters) shown under the picture, or "" -
   prefer "" whenever the picture alone is clear.
   Return fewer cards (or none) rather than weak ones."""

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "filler_cut_ids": {"type": "array", "items": {"type": "integer"}},
        "cards": {"type": "array", "items": {
            "type": "object",
            "properties": {"start_sec": {"type": "number"}, "duration_sec": {"type": "number"}, "concept": {"type": "string"},
                           "visual_brief": {"type": "string"}, "label": {"type": "string"}},
            "required": ["start_sec", "duration_sec", "concept", "visual_brief", "label"], "additionalProperties": False}},
    },
    "required": ["filler_cut_ids", "cards"],
    "additionalProperties": False,
}


def analyze(segments: list[dict], candidates: list[dict], duration: float, max_cards: int, title: str = "") -> dict:
    lines = [f"[S{s['id']} {s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments]
    cands = [f"F{c['id']} \"{c['word']}\" @{c['start']:.2f}s  문맥: {c['context']}" for c in candidates]
    user = (
        (f"설교 제목: {title}\n" if title else "") + f"영상 길이: {duration:.1f}초\n\n## 대본 (원본 시간, 초)\n" + "\n".join(lines)
        + "\n\n## 필러워드 후보 (id 는 F 뒤 숫자)\n" + ("\n".join(cands) or "(없음)")
        + "\n\n## 요청\n- filler_cut_ids: 잘라도 되는 후보 id (숫자만)\n"
        + f"- cards: 설명 그림 최대 {max_cards}개" + (" (이번에는 0개, 빈 배열로)" if max_cards == 0 else "")
    )
    data = json.loads(_call(ANALYSIS_SYSTEM, user, effort="medium", schema=ANALYSIS_SCHEMA))
    data["cards"] = data["cards"][:max_cards]
    return data
