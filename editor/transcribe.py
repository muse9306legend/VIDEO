"""Speech to text with faster-whisper (GPU when available)."""
from __future__ import annotations

import os


def transcribe(wav: str, log=print) -> list[dict]:
    from faster_whisper import WhisperModel

    size = os.environ.get("WHISPER_MODEL", "large-v3")
    try:
        model = WhisperModel(size, device="cuda", compute_type="float16")
        log(f"음성 인식: {size} (GPU)")
    except Exception:
        model = WhisperModel(size, device="cpu", compute_type="int8")
        log(f"음성 인식: {size} (CPU, 느릴 수 있어요)")
    segs, _ = model.transcribe(wav, language="ko", vad_filter=True, beam_size=5)
    out = []
    for s in segs:
        text = s.text.strip()
        if text:
            out.append({"id": len(out), "start": round(s.start, 2), "end": round(s.end, 2), "text": text})
    log(f"문장 {len(out)}개 인식")
    return out
