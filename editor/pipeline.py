"""Orchestrates the whole sermon edit and writes the report."""
from __future__ import annotations

import html
import json
import re
import threading
import time
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from . import ai, cuts, framing, illustrate, images, load_env, media, render, transcribe

ROOT = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT / "jobs"
SR = 48000


@dataclass
class Options:
    # trim
    trim_start: float = 0.0
    trim_end: float | None = None      # None = to the end
    # first cut
    remove_silence: bool = True
    silence_db: float = -40.0
    min_silence: float = 1.0           # sermons use deliberate pauses: only shorten long ones
    keep_pad: float = 0.25
    remove_fillers: bool = True
    # preacher framing
    follow: bool = False               # False = one fixed frame centred on the preacher, True = slowly follow
    zoom: float = 1.0                  # minimum zoom; more is added automatically when needed to centre
    pos_x: float = 0.0                 # -0.3..0.3 fraction of width  (+ = preacher further right)
    pos_y: float = 0.0                 # -0.3..0.3 fraction of height (+ = preacher lower)
    # title / name
    title_on: bool = True
    title: str = ""
    title_align: str = "center"        # left | center | right
    title_x: float = 0.0
    title_y: float = 0.0
    title_secs: float = 0.0            # 0 = whole video
    name_on: bool = True
    name: str = ""
    name_secs: float = 15.0
    # explainer pictures
    cards: bool = True
    max_cards: int = 6
    card_mode: str = "overlay"         # overlay | fullscreen
    # misc
    max_side: int = 1920
    whisper_model: str = "large-v3"


def parse_time(s) -> float | None:
    """'1:30' / '01:02:03' / '95' / '' -> seconds or None."""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    parts = [float(p) for p in re.split(r"[:：]", s)]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def _fmt(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t // 60 % 60):02d}:{t % 60:04.1f}" if t >= 3600 else f"{int(t // 60):02d}:{t % 60:04.1f}"


def _srt_time(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def trim_range(opts: Options, duration: float) -> tuple[float, float]:
    t0 = min(max(0.0, opts.trim_start or 0.0), duration)
    t1 = duration if opts.trim_end is None else min(max(opts.trim_end, 0.0), duration)
    if t1 - t0 < 1.0:
        raise ValueError(f"자를 구간이 잘못됐어요 (시작 {_fmt(t0)}, 끝 {_fmt(t1)}).")
    return t0, t1


# ---------------------------------------------------------------- title / name badges

def make_overlays(opts: Options, W: int, H: int, out_dir: Path) -> dict:
    jobs, keys = [], []
    if opts.title_on and opts.title.strip():
        jobs.append({"out": out_dir / "title.png", "kind": "title", "text": opts.title.strip(), "font_px": max(24, int(H * 0.055))})
        keys.append("title")
    if opts.name_on and opts.name.strip():
        jobs.append({"out": out_dir / "name.png", "kind": "name", "text": opts.name.strip(), "font_px": max(20, int(H * 0.042))})
        keys.append("name")
    illustrate.render(jobs, scale=1.0)
    overlays = {}
    for key, j in zip(keys, jobs):
        img = render.fit(render.load_rgba(j["out"]), W * 0.9, H * 0.3)
        secs = opts.title_secs if key == "title" else opts.name_secs
        ov = {"img": img, "until": secs if secs and secs > 0 else 1e9}
        if key == "title":
            ov["x"], ov["y"] = render.title_pos(img, W, H, opts.title_align, opts.title_x, opts.title_y)
        overlays[key] = ov
    return overlays


# ---------------------------------------------------------------- preview (one frame, fast)

_face_cache: dict = {}


def preview(input_path: str, opts: Options, at: float | None = None) -> np.ndarray:
    load_env()
    info = media.probe(input_path)
    W, H = media.target_size(info["width"], info["height"], min(opts.max_side, 1280))
    t0, t1 = trim_range(opts, info["duration"])
    t = t0 + min(30.0, (t1 - t0) / 2) if at is None else min(max(at, t0), t1 - 0.1)
    key = (input_path, round(t0, 1), round(t1, 1))
    if key not in _face_cache:
        _face_cache[key] = framing.sample_static(input_path, W, H, t0, t1, n=20)
    samples = _face_cache[key]
    frame = media.grab_frame(input_path, t, W, H)
    if frame is None:
        raise ValueError("미리보기 프레임을 읽지 못했어요.")
    if opts.follow and (face := framing.face_at_frame(frame)):
        samples = [(t, *face)]
    fr = framing.build(samples, W, H, False, opts.zoom, opts.pos_x, opts.pos_y, t0, t1)
    out_dir = JOBS_DIR / "_preview"
    out_dir.mkdir(parents=True, exist_ok=True)
    overlays = make_overlays(opts, W, H, out_dir)
    img = render.compose(frame, t, 1.0, fr, overlays, [])
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


# ---------------------------------------------------------------- full run

def run(input_path: str, opts: Options, progress=lambda frac, msg: None) -> dict:
    load_env()  # pick up keys added to .env while the program is running
    job = JOBS_DIR / time.strftime("%Y%m%d_%H%M%S")
    (job / "cards").mkdir(parents=True, exist_ok=True)
    log_lines: list[str] = []
    log_lock = threading.Lock()  # image threads log too

    def log(msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        with log_lock:
            log_lines.append(line)
            print(line, flush=True)
            (job / "log.txt").write_text("\n".join(log_lines), encoding="utf-8")

    log(f"입력: {input_path}")
    log(f"옵션: {asdict(opts)}")
    use_ai = ai.available()
    if not use_ai:
        log("Claude API 키 없음 → 필러는 '어/음'만 자르고 설명 그림은 넣지 않습니다.")
    if opts.cards and not images.available():
        log("OpenAI(ChatGPT) API 키 없음 → 설명 그림을 넣지 않습니다.")

    # 1. media + speech (only the trimmed range is transcribed)
    progress(0.01, "영상 정보 확인")
    info = media.probe(input_path)
    W, H = media.target_size(info["width"], info["height"], opts.max_side)
    fps = media.target_fps(info["fps"])
    wav_in = job / "source_audio.wav"
    if info["has_audio"]:
        media.extract_wav(input_path, wav_in, SR, 2)
        with wave.open(str(wav_in)) as wf:
            duration = min(info["duration"] or 1e9, wf.getnframes() / SR)
    else:
        duration = info["duration"]
    t0, t1 = trim_range(opts, duration)
    log(f"원본 {W}x{H} {fps}fps, {_fmt(duration)} → 사용 구간 {_fmt(t0)} ~ {_fmt(t1)}")

    segments: list[dict] = []
    mono16 = np.zeros(0, np.float32)
    if info["has_audio"]:
        mono16 = media.read_audio(input_path, 16000, 1)[:, 0]
        part = mono16[int(t0 * 16000):int(t1 * 16000)]
        progress(0.04, "음성 인식 중 (Whisper)")
        segments = transcribe.transcribe(part, opts.whisper_model, log)
        for s in segments:  # back to original-video time
            s["start"] += t0
            s["end"] += t0
            for w in s["words"]:
                w["start"] += t0
                w["end"] += t0
    (job / "transcript.json").write_text(json.dumps(segments, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"문장 {len(segments)}개 인식")

    # 2. Claude: fillers + where pictures help
    candidates = cuts.filler_candidates(segments)
    want_cards = opts.cards and images.available()
    analysis = {"filler_cut_ids": [], "cards": []}
    ai_ok = False
    if use_ai and segments and (opts.remove_fillers or want_cards):
        progress(0.22, "Claude가 설교 대본 분석 중")
        try:
            analysis = ai.analyze(segments, candidates, t1 - t0, opts.max_cards if want_cards else 0, opts.title)
            ai_ok = True
        except Exception as e:
            log(f"대본 분석 실패 (기본 규칙으로 진행): {e}")
    (job / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=1), encoding="utf-8")

    # 2b. Start every picture now, in parallel, and keep working: cuts, face detection and badges
    #     run while ChatGPT draws. Results are collected just before they are needed.
    planned = []
    if want_cards and ai_ok:
        for c in sorted(analysis["cards"], key=lambda c: c["start_sec"]):
            if t0 <= c["start_sec"] < t1:
                ctx = " ".join(s["text"] for s in segments if s["end"] >= c["start_sec"] - 5 and s["start"] <= c["start_sec"] + 8)
                planned.append(dict(c, context=ctx))
    batch = images.Batch(planned, log) if planned else None

    # 3. cut plan: trim + silence + fillers
    progress(0.28, "컷 편집 계획")
    removals = [(0.0, t0), (t1, duration)]
    silences, filler_ids = [], set()
    if opts.remove_silence and len(mono16):
        found = cuts.silence_ranges(mono16[int(t0 * 16000):int(t1 * 16000)], 16000, opts.silence_db, opts.min_silence)
        silences = cuts.silence_removals([(a + t0, b + t0) for a, b in found], opts.keep_pad)
        removals += silences
    if opts.remove_fillers:
        cand_ids = {c["id"] for c in candidates}
        filler_ids = set(analysis["filler_cut_ids"]) & cand_ids if ai_ok else {c["id"] for c in candidates if c["kind"] == "strong"}
        removals += cuts.word_removals(segments, filler_ids)
    keeps = cuts.build_keeps(duration, removals)
    if not keeps:
        raise RuntimeError("잘라낸 뒤 남는 구간이 없습니다. 무음 기준(dB)을 낮추거나 트림 구간을 확인해 주세요.")
    tl = cuts.Timeline(keeps)
    log(f"무음 {len(silences)}곳, 필러 {len(filler_ids)}개 제거 → 결과 {_fmt(tl.total)}")

    # 4. preacher framing
    progress(0.30, "설교자 위치 찾는 중")
    if opts.follow:
        samples = framing.sample_track(input_path, W, H, 1.0, duration=duration,
                                       progress=lambda f: progress(0.30 + 0.08 * f, "설교자 위치 찾는 중"))
    else:
        samples = framing.sample_static(input_path, W, H, t0, t1, n=30)
    fr = framing.build(samples, W, H, opts.follow, opts.zoom, opts.pos_x, opts.pos_y, t0, t1)
    log(f"설교자 얼굴 {len(samples)}회 검출, 확대 {fr.zoom:.2f}배" + ("" if samples else " (얼굴을 못 찾아 수동 위치만 적용)"))

    # 5. title / name badges
    overlays = make_overlays(opts, W, H, job)

    # 6. explainer cards (Claude plans, ChatGPT draws, paper-card template wraps)
    cards: list[dict] = []
    if batch:
        progress(0.40, "설명 그림 마무리 중 (ChatGPT, 병렬 생성)")
        pics = batch.results()
        plan, plan_pics, last_end = [], [], -1e9
        for c, pic in zip(planned, pics):
            ts = tl.to_new(c["start_sec"])
            dur = float(np.clip(c["duration_sec"], 3.0, 8.0))
            if not pic or ts < last_end + 1.0 or ts + dur > tl.total:
                continue
            plan.append(dict(c, t0=ts, t1=ts + dur))
            plan_pics.append(pic)
            last_end = ts + dur
        jobs = []
        for i, (c, pic) in enumerate(zip(plan, plan_pics)):
            if pic:
                (job / "cards" / f"art_{i + 1:02d}.png").write_bytes(pic)
                c["png"] = job / "cards" / f"card_{i + 1:02d}.png"
                jobs.append({"out": c["png"], "kind": "card", "image": pic, "label": c["label"]})
        try:
            illustrate.render(jobs)
        except Exception as e:
            log(f"그림 카드 렌더링 실패: {e}")
        for c in plan:
            if c.get("png") and c["png"].exists():
                cards.append(dict(c, **render.prepare_card(c["png"], W, H, opts.card_mode), mode=opts.card_mode))
        log(f"설명 그림 {len(cards)}개")

    # 7. audio: kept parts with tiny fades, streamed to disk
    progress(0.50, "오디오 편집")
    wav_out = job / "edited_audio.wav"
    aw = media.AudioWriter(wav_out, SR, 2)
    fade = int(0.006 * SR)
    ramp = np.linspace(0, 1, fade, dtype=np.float32)[:, None]
    if info["has_audio"]:
        with wave.open(str(wav_in)) as wf:
            for s, e in keeps:
                a0, a1 = int(s * SR), min(int(e * SR), wf.getnframes())
                wf.setpos(a0)
                a = np.frombuffer(wf.readframes(max(0, a1 - a0)), "<i2").reshape(-1, 2).astype(np.float32) / 32768
                if len(a) > 2 * fade:
                    a[:fade] *= ramp
                    a[-fade:] *= ramp[::-1]
                aw.write(a)
    else:
        aw.write(np.zeros((int(tl.total * SR), 2), np.float32))
    aw.close()
    wav_in.unlink(missing_ok=True)

    # 8. render
    out = job / "결과영상.mp4"
    progress(0.52, "영상 렌더링")
    render.render(input_path, out, W, H, fps, tl, fr, overlays, cards, wav_out,
                  progress=lambda f: progress(0.52 + 0.47 * f, "영상 렌더링"))
    wav_out.unlink(missing_ok=True)

    # 9. subtitles + report
    srt = job / "자막.srt"
    srt.write_text(_build_srt(segments, tl, filler_ids, t0, t1), encoding="utf-8")
    summary = {
        "original_sec": round(float(duration), 1), "trim": [_fmt(t0), _fmt(t1)], "edited_sec": round(float(tl.total), 1),
        "silence_cuts": len(silences), "filler_cuts": len(filler_ids), "ai_used": ai_ok,
        "zoom": round(fr.zoom, 2), "faces_found": len(samples),
        "cards": [{"time": _fmt(c["t0"]), "concept": c["concept"], "label": c["label"], "png": f"cards/{c['png'].name}"} for c in cards],
    }
    (job / "report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    report = job / "편집리포트.html"
    report.write_text(_report_html(summary), encoding="utf-8")
    log("완료")
    progress(1.0, "완료")
    return {"job": job, "output": out, "srt": srt, "report": report, "summary": summary}


def _build_srt(segments, tl, removed_ids, t0, t1) -> str:
    out, n = [], 0
    for s in segments:
        words = [w for w in s["words"] if w["id"] not in removed_ids and t0 <= w["start"] < t1]
        text = "".join(w["word"] for w in words).strip()
        if not text:
            continue
        n += 1
        a, b = tl.to_new(words[0]["start"]), tl.to_new(words[-1]["end"])
        out.append(f"{n}\n{_srt_time(a)} --> {_srt_time(max(b, a + 0.5))}\n{text}\n")
    return "\n".join(out)


def _report_html(s: dict) -> str:
    e = html.escape
    cards = "".join(f'<figure><img src="{e(c["png"])}"><figcaption><b>{e(c["time"])}</b> {e(c["concept"])}</figcaption></figure>'
                    for c in s["cards"]) or "<p>없음</p>"
    mins = lambda sec: f"{int(sec // 60)}분 {int(sec % 60)}초"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>편집 리포트</title><style>
body{{font-family:'Malgun Gothic',sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#2E2A26;background:#FFFDF8}}
.stats{{display:flex;gap:12px;flex-wrap:wrap}} .stat{{background:#fff;border:2px solid #2E2A26;border-radius:14px;padding:10px 16px}}
.stat b{{font-size:22px;display:block}} figure{{display:inline-block;width:280px;margin:8px;vertical-align:top}} img{{width:100%;border-radius:10px}}
</style></head><body><h1>편집 리포트</h1>
<div class="stats"><div class="stat"><b>{mins(s['original_sec'])} → {mins(s['edited_sec'])}</b>길이</div>
<div class="stat"><b>{e(s['trim'][0])} ~ {e(s['trim'][1])}</b>사용 구간(트림)</div>
<div class="stat"><b>{s['silence_cuts']}곳</b>무음 단축</div><div class="stat"><b>{s['filler_cuts']}개</b>필러 제거</div>
<div class="stat"><b>{s['zoom']}배</b>설교자 맞춤 확대</div><div class="stat"><b>{len(s['cards'])}개</b>설명 그림</div></div>
{'' if s['ai_used'] else '<p>이번 작업은 Claude API 없이 기본 규칙으로만 처리했습니다.</p>'}
{'' if s['faces_found'] else '<p>설교자 얼굴을 찾지 못해 자동 맞춤 없이 수동 위치만 적용했습니다.</p>'}
<h2>설명 그림</h2>{cards}</body></html>"""
