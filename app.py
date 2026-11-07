"""키즈 유튜브 AI 편집기 - 화면 (Gradio, 이 PC에서만 열림)."""
from __future__ import annotations

import json
import os
import queue
import threading
from datetime import datetime
from pathlib import Path

import gradio as gr

from editor import JOBS, ai, images, load_env
from editor.pipeline import Logger, Settings, frame_at, prepare, render


def _key_status() -> str:
    load_env()
    a = "✅ Claude 연결됨" if ai.available() else "⚠️ Claude 키 없음 (그림·캐릭터 위치를 정할 수 없어요)"
    o = "✅ ChatGPT 그림 연결됨" if images.available() else "⚠️ OpenAI 키 없음 (설명 그림 없음, 캐릭터는 기본 그림)"
    return f"{a} · {o} — 키는 `.env` 파일에 넣으면 바로 반영돼요."


def _read(files) -> list[bytes]:
    return [Path(f if isinstance(f, str) else f.name).read_bytes() for f in (files or [])]


def _settings(a, b, da, db, pa, pb, topic, n_cards, n_react) -> Settings:
    return Settings(a or "첫째", b or "둘째", da or "", db or "", _read(pa), _read(pb), topic or "", int(n_cards), int(n_react))


def _stream(fn):
    """Run fn(log) in a thread and yield the growing log text, then the result."""
    q: queue.Queue = queue.Queue()
    box: dict = {}

    def work():
        try:
            box["result"] = fn(lambda m: q.put(m))
        except Exception as e:
            box["error"] = e
            q.put(f"❌ 오류: {e}")
        q.put(None)

    threading.Thread(target=work, daemon=True).start()
    lines = []
    while (m := q.get()) is not None:
        lines.append(m)
        yield "\n".join(lines[-200:]), None
    yield "\n".join(lines[-200:]), box.get("result")


def analyze(video, a, b, da, db, pa, pb, topic, n_cards, n_react, plan_text=None):
    if not video:
        raise gr.Error("먼저 영상을 올려 주세요.")
    s = _settings(a, b, da, db, pa, pb, topic, n_cards, n_react)
    plan = None
    if plan_text:
        try:
            plan = json.loads(plan_text)
        except json.JSONDecodeError as e:
            raise gr.Error(f"계획(JSON) 형식이 잘못됐어요: {e}")
    out = JOBS / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    for log_text, job in _stream(lambda sink: prepare(video, s, plan=plan, out=out, log=Logger(out / "log.txt", sink))):
        if job is None:
            yield log_text, gr.update(), gr.update(), gr.update(), None
        else:
            first = min([e.start + 0.8 for e in job.els] or [0.0])
            yield (log_text, json.dumps(job.plan, ensure_ascii=False, indent=1),
                   gr.update(maximum=max(1.0, round(job.duration, 1)), value=round(first, 1)),
                   frame_at(job, first), job)


def preview(job, t):
    if job is None:
        return None
    return frame_at(job, float(t))


def make_video(job, progress=gr.Progress()):
    if job is None:
        raise gr.Error("먼저 '1. 분석하기'를 눌러 주세요.")
    log = None
    for log_text, result in _stream(lambda sink: render(job, Logger(job.out / "log.txt", sink), lambda p: progress(p))):
        log = log_text
        yield log, None, None
    yield log, (str(result) if result else None), (str(job.out / "편집리포트.html") if result else None)


with gr.Blocks(title="키즈 유튜브 AI 편집기") as demo:
    gr.Markdown("# 🎬 키즈 유튜브 AI 편집기\n영상에 **AI 설명 그림**과 **쌍둥이 캐릭터**가 나와서 말풍선으로 반응해요.")
    status = gr.Markdown()
    job = gr.State(None)
    with gr.Row():
        with gr.Column(scale=1):
            video = gr.Video(label="영상 올리기", sources=["upload"])
            topic = gr.Textbox(label="영상 주제 (선택)", placeholder="예: 쌍둥이 마라탕 먹방")
            with gr.Row():
                with gr.Column():
                    a = gr.Textbox(label="쌍둥이 A 이름", value="첫째")
                    da = gr.Textbox(label="A 생김새·성격", placeholder="예: 양갈래 머리, 노란 티셔츠, 활발함")
                    pa = gr.File(label="A 사진 (선택, 캐릭터를 닮게 그려요)", file_count="multiple", file_types=["image"])
                with gr.Column():
                    b = gr.Textbox(label="쌍둥이 B 이름", value="둘째")
                    db = gr.Textbox(label="B 생김새·성격", placeholder="예: 짧은 머리, 파란 후드티, 장난꾸러기")
                    pb = gr.File(label="B 사진 (선택)", file_count="multiple", file_types=["image"])
            with gr.Row():
                n_cards = gr.Slider(0, 20, value=6, step=1, label="설명 그림 최대 개수")
                n_react = gr.Slider(0, 40, value=12, step=1, label="쌍둥이 반응 최대 개수")
            btn_analyze = gr.Button("1. 분석하기 (음성 인식 → 계획 → 그림 생성)", variant="primary")
        with gr.Column(scale=1):
            shot = gr.Image(label="미리보기 (최종 영상과 똑같이 그려져요)", type="numpy")
            t = gr.Slider(0, 1, value=0, step=0.1, label="미리보기 시간 (초)")
            with gr.Accordion("계획 직접 고치기 (시간·대사·포즈)", open=False):
                plan = gr.Code(label="plan.json", language="json")
                btn_apply = gr.Button("고친 계획 적용 (AI 다시 안 부름)")
            btn_make = gr.Button("2. 영상 만들기", variant="primary")
            result = gr.Video(label="결과 영상")
            report = gr.File(label="편집 리포트")
            log = gr.Textbox(label="진행 기록", lines=12, max_lines=12, autoscroll=True)

    inputs = [video, a, b, da, db, pa, pb, topic, n_cards, n_react]
    btn_analyze.click(analyze, inputs, [log, plan, t, shot, job])
    btn_apply.click(analyze, inputs + [plan], [log, plan, t, shot, job])
    t.release(preview, [job, t], shot)
    btn_make.click(make_video, [job], [log, result, report])
    demo.load(_key_status, None, status)

if __name__ == "__main__":
    demo.queue().launch(server_name="127.0.0.1", allowed_paths=[str(JOBS)],
                        inbrowser=not os.environ.get("NO_BROWSER"))
