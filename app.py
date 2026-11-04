"""Local web UI for sermon videos: upload, adjust with a live preview, get it back edited."""
import os

import gradio as gr

from editor import ai, images, load_env
from editor.pipeline import JOBS_DIR, Options, parse_time, preview, run

ALIGN = {"좌측 정렬": "left", "중앙 정렬": "center", "우측 정렬": "right"}


def key_status() -> str:
    """Re-read .env every time the page opens, so the warning reflects keys added while running."""
    load_env()
    missing = [n for n, ok in (("Claude(ANTHROPIC_API_KEY)", ai.available()), ("ChatGPT(OPENAI_API_KEY)", images.available())) if not ok]
    if not missing:
        return ""
    return (f"> ⚠️ `.env` 에 **{', '.join(missing)}** 키가 없어요. 키를 넣으면 다시 실행하지 않아도 다음 작업부터 적용돼요. "
            "Claude 키가 없으면 '어/음'만 자르고, ChatGPT 키가 없으면 설명 그림을 넣지 않아요.")


def make_opts(trim_start, trim_end, remove_silence, silence_db, min_silence, remove_fillers,
              follow, zoom, pos_x, pos_y,
              title_on, title, title_align, title_x, title_y, title_secs,
              name_on, name, name_secs,
              cards, max_cards, card_mode) -> Options:
    try:
        ts, te = parse_time(trim_start) or 0.0, parse_time(trim_end)
    except ValueError:
        raise gr.Error("트림 시간은 '1:30' 또는 '90' 처럼 입력해 주세요.")
    return Options(
        trim_start=ts, trim_end=te,
        remove_silence=remove_silence, silence_db=float(silence_db), min_silence=float(min_silence), remove_fillers=remove_fillers,
        follow=follow, zoom=float(zoom), pos_x=float(pos_x), pos_y=float(pos_y),
        title_on=title_on, title=title or "", title_align=ALIGN[title_align], title_x=float(title_x), title_y=float(title_y),
        title_secs=float(title_secs), name_on=name_on, name=name or "", name_secs=float(name_secs),
        cards=cards, max_cards=int(max_cards), card_mode="fullscreen" if card_mode == "전체 화면" else "overlay",
    )


def do_preview(video, preview_at, *settings):
    if not video:
        return None
    try:
        return preview(video, make_opts(*settings), parse_time(preview_at))
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(f"미리보기 오류: {e}")


def do_run(video, preview_at, *settings, progress=gr.Progress()):
    if not video:
        raise gr.Error("먼저 영상을 올려 주세요.")
    opts = make_opts(*settings)
    try:
        res = run(video, opts, progress=lambda f, m: progress(f, desc=m))
    except Exception as e:
        raise gr.Error(f"처리 중 오류: {e}")
    s = res["summary"]
    m = lambda sec: f"{int(sec // 60)}분 {int(sec % 60)}초"
    md = (f"### 완료\n- 길이: **{m(s['original_sec'])} → {m(s['edited_sec'])}** (사용 구간 {s['trim'][0]} ~ {s['trim'][1]})\n"
          f"- 무음 단축 {s['silence_cuts']}곳 · 필러 제거 {s['filler_cuts']}개 · 설명 그림 {len(s['cards'])}개\n"
          f"- 설교자 맞춤 확대 {s['zoom']}배" + ("" if s["faces_found"] else " (얼굴을 못 찾아 수동 위치만 적용)") + "\n"
          f"- 작업 폴더: `{res['job']}`")
    return str(res["output"]), [str(res["output"]), str(res["report"]), str(res["srt"])], md


with gr.Blocks(title="자동 영상 편집기") as demo:
    gr.Markdown("# 🎬 자동 영상 편집기\n트림 → 무음·필러워드 컷 → 설교자 가운데 맞춤 → 제목·이름 표시 → 설명 그림 삽입")
    keys_md = gr.Markdown(key_status())
    demo.load(key_status, None, keys_md)
    with gr.Row():
        with gr.Column():
            video = gr.Video(label="원본 영상", sources=["upload"])
            with gr.Accordion("영상 트림 (앞뒤 자르기)", open=True):
                with gr.Row():
                    trim_start = gr.Textbox(label="시작점", placeholder="예: 2:15 (비우면 처음부터)")
                    trim_end = gr.Textbox(label="종료점", placeholder="예: 42:30 (비우면 끝까지)")
            with gr.Accordion("1차 컷 편집", open=False):
                remove_silence = gr.Checkbox(True, label="무음 구간 줄이기")
                silence_db = gr.Slider(-60, -20, value=-40, step=1, label="무음 기준 (dB) — 낮출수록 더 조용해야 무음으로 봄")
                min_silence = gr.Slider(0.3, 3.0, value=1.0, step=0.1, label="이 시간(초) 이상 조용하면 줄이기")
                remove_fillers = gr.Checkbox(True, label="필러워드(어, 음 …) 제거")
            with gr.Accordion("설교자 위치", open=True):
                gr.Markdown("기본값은 설교자를 화면 가운데에 자동으로 맞춥니다. 슬라이더로 미세 조절하세요.")
                follow = gr.Checkbox(False, label="설교자가 움직이면 천천히 따라가기")
                zoom = gr.Slider(1.0, 2.0, value=1.0, step=0.05, label="확대 (가운데 맞춤에 필요하면 자동으로 더 확대됨)")
                pos_x = gr.Slider(-0.3, 0.3, value=0.0, step=0.01, label="좌/우 (− 왼쪽 · + 오른쪽)")
                pos_y = gr.Slider(-0.3, 0.3, value=0.0, step=0.01, label="상/하 (− 위 · + 아래)")
            with gr.Accordion("설교 제목 · 설교자 이름", open=True):
                title_on = gr.Checkbox(True, label="설교 제목 표시")
                title = gr.Textbox(label="설교 제목", placeholder="예: 두려워하지 말라")
                title_align = gr.Radio(list(ALIGN), value="중앙 정렬", label="제목 위치")
                with gr.Row():
                    title_x = gr.Slider(-0.3, 0.3, value=0.0, step=0.01, label="제목 X (− 왼쪽 · + 오른쪽)")
                    title_y = gr.Slider(0.0, 0.8, value=0.0, step=0.01, label="제목 Y (+ 아래로)")
                title_secs = gr.Slider(0, 120, value=0, step=5, label="제목 표시 시간(초) — 0이면 영상 내내")
                name_on = gr.Checkbox(True, label="설교자 이름 표시 (항상 설교자 아래에 자동 정렬)")
                name = gr.Textbox(label="설교자 이름", placeholder="예: 홍길동 담임목사")
                name_secs = gr.Slider(0, 120, value=15, step=5, label="이름 표시 시간(초) — 0이면 영상 내내")
            with gr.Accordion("설명 그림 (ChatGPT 이미지)", open=False):
                cards = gr.Checkbox(True, label="이해를 돕는 그림 넣기 (플랫 벡터 + 손그림 카툰)")
                max_cards = gr.Slider(0, 12, value=6, step=1, label="최대 개수")
                card_mode = gr.Radio(["화면 구석 카드", "전체 화면"], value="화면 구석 카드", label="표시 방식")
            with gr.Row():
                preview_at = gr.Textbox(label="미리보기 시점", placeholder="예: 5:00 (비우면 자동)", scale=2)
                preview_btn = gr.Button("미리보기", scale=1)
            go = gr.Button("편집 시작", variant="primary")
        with gr.Column():
            preview_img = gr.Image(label="미리보기 (위치·제목·이름 확인용)", interactive=False)
            result = gr.Video(label="결과 영상")
            files = gr.File(label="다운로드 (영상 · 리포트 · 자막)", file_count="multiple")
            summary = gr.Markdown()

    settings = [trim_start, trim_end, remove_silence, silence_db, min_silence, remove_fillers,
                follow, zoom, pos_x, pos_y,
                title_on, title, title_align, title_x, title_y, title_secs,
                name_on, name, name_secs,
                cards, max_cards, card_mode]
    pv_inputs = [video, preview_at, *settings]
    preview_btn.click(do_preview, pv_inputs, preview_img)
    video.change(do_preview, pv_inputs, preview_img)
    # Live preview while adjusting position / title / name.
    for s in (zoom, pos_x, pos_y, title_x, title_y):
        s.release(do_preview, pv_inputs, preview_img)
    for c in (follow, title_on, title_align, name_on):
        c.change(do_preview, pv_inputs, preview_img)
    for t in (title, name, preview_at, trim_start, trim_end):
        t.submit(do_preview, pv_inputs, preview_img)
    go.click(do_run, pv_inputs, [result, files, summary])

JOBS_DIR.mkdir(exist_ok=True)

if __name__ == "__main__":
    # Plain start (no auto-reload). 실행.bat uses `gradio app.py` instead, which reloads on code changes.
    demo.queue().launch(server_name="127.0.0.1", inbrowser=not os.environ.get("NO_BROWSER"), allowed_paths=[str(JOBS_DIR)])
