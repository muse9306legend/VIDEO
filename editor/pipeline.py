"""Whole edit: speech → Claude plan → pictures & characters (parallel) → overlay layout → render.

`prepare()` does everything except the frame loop and returns a Job. `render()` streams the frames and
`frame_at()` draws one preview frame through the same `overlay.compose()`, so the preview always
matches the final video.
"""
from __future__ import annotations

import html
import json
import time
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import JOBS, ai, characters, images, load_env, media, overlay


BUSY_DIR = JOBS / "_busy"


@contextmanager
def busy():
    """Marks a running job so the auto-updater (자동업데이트.bat) does not pull new code mid-job:
    a code update would reload the app and interrupt it."""
    BUSY_DIR.mkdir(parents=True, exist_ok=True)
    mark = BUSY_DIR / f"{uuid.uuid4().hex}.lock"
    mark.write_text(datetime.now().isoformat(), encoding="utf-8")
    try:
        yield
    finally:
        mark.unlink(missing_ok=True)


@dataclass
class Settings:
    twin_a: str = "첫째"
    twin_b: str = "둘째"
    desc_a: str = ""
    desc_b: str = ""
    photos_a: list[bytes] = field(default_factory=list)
    photos_b: list[bytes] = field(default_factory=list)
    topic: str = ""
    max_cards: int = 6
    max_reactions: int = 12
    max_side: int = 1920

    def twins(self) -> dict:
        return {"A": {"name": self.twin_a, "desc": self.desc_a, "photos": self.photos_a},
                "B": {"name": self.twin_b, "desc": self.desc_b, "photos": self.photos_b}}


@dataclass
class Job:
    src: Path
    out: Path
    w: int
    h: int
    fps: float
    duration: float
    has_audio: bool
    plan: dict
    els: list = field(default_factory=list)


class Logger:
    def __init__(self, path: Path | None = None, sink=print):
        self.path, self.sink, self.t0 = path, sink, time.time()

    def __call__(self, msg: str):
        line = f"[{time.time() - self.t0:6.1f}s] {msg}"
        if self.sink:
            self.sink(line)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


def plan_video(src: Path, info: dict, s: Settings, out: Path, log) -> dict:
    """Transcribe and ask Claude for cards and reactions. Any failure → an empty plan, the edit continues."""
    empty = {"cards": [], "reactions": []}
    try:
        from .transcribe import transcribe

        wav = out / "audio16k.wav"
        media.extract_wav(src, wav)
        segments = transcribe(str(wav), log)
        wav.unlink(missing_ok=True)
        (out / "transcript.json").write_text(json.dumps(segments, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        log(f"음성 인식 실패: {e}")
        return empty
    if not segments:
        log("말소리를 찾지 못해 그림과 캐릭터를 넣지 않습니다.")
        return empty
    if not ai.available():
        log("ANTHROPIC_API_KEY 가 없어 그림·캐릭터 위치를 정할 수 없습니다. .env 에 키를 넣어 주세요.")
        return empty
    try:
        log(f"Claude({ai.model()})가 설명 그림과 쌍둥이 반응을 계획하는 중...")
        p = ai.plan(segments, info["duration"], s.twins(), max_cards=s.max_cards, max_reactions=s.max_reactions, topic=s.topic)
        log(f"계획: 설명 그림 {len(p['cards'])}개, 쌍둥이 반응 {len(p['reactions'])}개")
        return p
    except Exception as e:
        log(f"Claude 분석 실패: {e}")
        return empty


def layout(plan: dict, pictures: list, sprites: dict, s: Settings, w: int, h: int, out: Path | None = None) -> list[overlay.El]:
    landscape = w >= h
    margin = int(min(w, h) * 0.04)
    names = {"A": s.twin_a or "A", "B": s.twin_b or "B"}
    els: list[overlay.El] = []

    for r in plan["reactions"]:
        spr = sprites.get((r["twin"], r["pose"]))
        if spr is None:
            continue
        side = "left" if r["twin"] == "A" else "right"
        img, _ = overlay.character(spr, r["text"], r["emoji"], names[r["twin"]], r["twin"], side,
                                   int(h * (0.44 if landscape else 0.24)),
                                   int(w * (0.34 if landscape else 0.62)))
        x = margin if side == "left" else w - img.width - margin
        els.append(overlay.El(r["start"], r["start"] + r["duration"], img, x, h - img.height - margin // 2,
                              enter="rise", bob=h * 0.006))

    for i, (c, pic) in enumerate(zip(plan["cards"], pictures)):
        if pic is None:
            continue
        if landscape:
            img = overlay.card(pic, c["label"], int(w * 0.40), int(h * 0.62), seed=i)
            busy = {r["twin"] for r in plan["reactions"] if r["start"] < c["start"] + c["duration"] and c["start"] < r["start"] + r["duration"]}
            right = "B" not in busy or "A" in busy and "B" in busy
            x = w - img.width - margin if right else margin
            y = int(h * 0.06)
        else:
            img = overlay.card(pic, c["label"], int(w * 0.82), int(h * 0.42), seed=i)
            x, y = (w - img.width) // 2, int(h * 0.10)
        if out:
            img.save(out / f"card_{i + 1:02d}.png")
        els.append(overlay.El(c["start"], c["start"] + c["duration"], img, x, y, enter="pop"))
    return sorted(els, key=lambda e: e.start)


def prepare(src: str | Path, s: Settings, *, plan: dict | None = None, out: Path | None = None, log=print) -> Job:
    with busy():
        return _prepare(src, s, plan=plan, out=out, log=log)


def _prepare(src, s: Settings, *, plan: dict | None, out: Path | None, log) -> Job:
    load_env()
    src = Path(src)
    out = out or JOBS / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    info = media.probe(src)
    w, h = media.out_size(info["width"], info["height"], s.max_side)
    fps = media.out_fps(info["fps"])
    log(f"입력: {src.name} {info['width']}x{info['height']} {info['fps']:.2f}fps {info['duration']:.1f}초 → 출력 {w}x{h} {fps}fps")

    if plan is None:
        plan = plan_video(src, info, s, out, log)
    else:
        plan = ai.clean(plan, info["duration"], 999, 999, card_gap=0.0)
        log(f"저장된 계획 사용: 설명 그림 {len(plan['cards'])}개, 쌍둥이 반응 {len(plan['reactions'])}개")
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")

    # Cards and characters are generated at the same time.
    if plan["cards"] and not images.available():
        log("OPENAI_API_KEY 가 없어 설명 그림은 넣지 않습니다.")
    card_batch = images.Batch([(c["concept"], lambda c=c: images.make(images.card_prompt(c["visual_brief"])))
                               for c in plan["cards"]] if images.available() else [], log, "설명 그림")
    needed = {(r["twin"], r["pose"]) for r in plan["reactions"]}
    with ThreadPoolExecutor(1) as ex:
        spr_future = ex.submit(characters.sprites, s.twins(), needed, out / "characters", log)
        pictures = card_batch.results() or [None] * len(plan["cards"])
        sprites = spr_future.result()

    job = Job(src, out, w, h, fps, info["duration"], info["has_audio"], plan)
    job.els = layout(plan, pictures, sprites, s, w, h, out)
    return job


def frame_at(job: Job, t: float):
    frame = media.grab_frame(job.src, t, job.w, job.h)
    if frame is None:
        return None
    return overlay.compose(frame, t, job.els)


def render(job: Job, log=print, progress=None) -> Path:
    with busy():
        return _render(job, log, progress)


def _render(job: Job, log, progress) -> Path:
    dst = job.out / "결과영상.mp4"
    total = max(1, int(job.duration * job.fps))
    reader = media.FrameReader(job.src, job.w, job.h, job.fps)
    writer = media.VideoWriter(dst, job.w, job.h, job.fps, job.src if job.has_audio else None)
    log(f"렌더링 시작 ({' '.join(media.video_encoder()[:2])})")
    t0, step = time.time(), max(1, total // 10)
    try:
        for i, frame in enumerate(reader):
            writer.write(overlay.compose(frame, i / job.fps, job.els))
            if i % step == 0 and i:
                log(f"렌더링 {min(100, i * 100 // total)}% ({time.time() - t0:.0f}초)")
                if progress:
                    progress(i / total)
    finally:
        reader.close()
        writer.close()
    log(f"완료: {dst} ({time.time() - t0:.0f}초)")
    report(job)
    return dst


def report(job: Job) -> None:
    def ts(t):
        return f"{int(t // 60)}:{t % 60:04.1f}"

    rows = []
    for i, c in enumerate(job.plan["cards"]):
        img = f"card_{i + 1:02d}.png"
        pic = f'<img src="{img}">' if (job.out / img).exists() else "(그림 없음)"
        rows.append((c["start"], f"<tr><td>{ts(c['start'])}</td><td>설명 그림</td><td>{html.escape(c['concept'])}<br>"
                    f"<small>{html.escape(c['visual_brief'])}</small></td><td>{pic}</td></tr>"))
    for r in job.plan["reactions"]:
        rows.append((r["start"], f"<tr><td>{ts(r['start'])}</td><td>쌍둥이 {r['twin']}</td><td>{html.escape(r['emoji'])} "
                    f"{html.escape(r['text'])}<br><small>{r['pose']}</small></td><td></td></tr>"))
    rows = [row for _, row in sorted(rows, key=lambda x: x[0])]
    page = ("<!doctype html><meta charset=utf-8><title>편집 리포트</title><style>body{font-family:sans-serif;"
            "background:#FFF8EC;color:#2E2A26;max-width:1000px;margin:auto;padding:16px}td{border-bottom:1px solid #ddd;"
            "padding:8px;vertical-align:top}img{max-width:320px}</style><h1>편집 리포트</h1>"
            f"<p>{html.escape(job.src.name)} · {ts(job.duration)} · 그림 {len(job.plan['cards'])}개 · "
            f"쌍둥이 반응 {len(job.plan['reactions'])}개</p><table>{''.join(rows)}</table>")
    (job.out / "편집리포트.html").write_text(page, encoding="utf-8")


def run(src: str | Path, s: Settings, *, plan: dict | None = None, out: Path | None = None, sink=print, progress=None) -> Path:
    out = out or JOBS / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    log = Logger(out / "log.txt", sink)
    job = prepare(src, s, plan=plan, out=out, log=log)
    return render(job, log, progress)
