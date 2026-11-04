# AGENTS.md — 설교 영상 자동 편집기

Korean sermon videos → trimmed, tightened, preacher-centred video with title/name badges and explainer pictures.
Python 3.13 on Windows, NVIDIA GPU (RTX 2060 6 GB). UI text, logs and user-facing messages are Korean.

## Pipeline (`editor/pipeline.py::run`)

1. **Trim**: `trim_start` / `trim_end` become removals `(0, start)` and `(end, duration)`. Only the trimmed range is transcribed.
2. **Speech**: `transcribe.py` runs faster-whisper large-v3 with word timestamps. Its `initial_prompt` contains disfluencies on purpose so Whisper writes "어/음" out instead of dropping them.
3. **Claude analysis**: `ai.py::analyze` makes one structured-output call that returns which filler candidates to cut and where explainer cards help.
4. **Cuts**: `cuts.py` shortens silences (RMS dB), removes filler words and builds the keep list. `Timeline` maps original time ↔ edited time.
5. **Framing**: `framing.py` finds the largest face (YuNet) and computes one zoom plus a per-time translation that puts the preacher at horizontal centre. It also applies the user offsets.
6. **Badges**: the title and the preacher name are rendered by `illustrate.py`.
7. **Cards**: Claude plans them, `images.py` (OpenAI Images, ChatGPT) draws them, and `illustrate.py` wraps each picture in the paper-card template.
8. **Audio**: kept ranges are streamed from a temporary 16-bit wav with 6 ms fades into `edited_audio.wav`.
9. **Render**: `render.py` decodes CFR frames from ffmpeg, picks frames through `Timeline.to_orig`, then applies `compose()` (reframe → name → title → cards) and pipes to ffmpeg (NVENC if available, else x264).
10. **Outputs**: `jobs/<timestamp>/` receives `결과영상.mp4`, `편집리포트.html`, `자막.srt`, `transcript.json`, `analysis.json`, `cards/` and `log.txt`.

The `pipeline.py::preview()` path renders a single frame through the same `compose()`, so the preview always matches the final render. Keep it that way.

## Files

| File | Role |
|---|---|
| `app.py` | Gradio UI (local, 127.0.0.1). Sliders update the preview on release. |
| `cli.py` | Same options from the command line. |
| `editor/media.py` | ffprobe/ffmpeg helpers: `FrameReader`, `VideoWriter`, `AudioWriter`, `grab_frame`. |
| `editor/cuts.py` | Filler word lists, silence detection, `build_keeps`, `Timeline`. |
| `editor/framing.py` | Face sampling (static or follow), `Framing.apply`, `person_anchor`. |
| `editor/illustrate.py` | Paper-card template rendered in headless Chromium (Playwright). |
| `editor/render.py` | Overlay placement (`title_pos`, `name_pos`, `prepare_card`), `compose`, `render`. |
| `editor/ai.py` | Claude calls. |
| `editor/images.py` | ChatGPT image generation. |
| `assets/fonts` | Gaegu (OFL). |
| `assets/models` | YuNet face detector (opencv_zoo). |

## Rules — do not break

- **Secrets**: API keys live only in `.env`, which is gitignored. `.env.example` must keep empty values. Run a secret scan before every commit, for example `git grep --cached -nE "sk-ant-|sk-proj-|sk-[A-Za-z0-9]{20,}"`.
- **Design template is fixed**:
  - Colours: cream paper `#FFF8EC`, ink `#2E2A26` outlines, coral `#FFB4A2` accent.
  - Hand-drawn wobble from the SVG `feTurbulence`/`feDisplacementMap` filters, Gaegu Bold text, soft offset shadow.
  - New overlays must reuse `illustrate.py`, not draw text with OpenCV.
- **Preacher name** is always anchored below the preacher (`render.name_pos` uses `framing.person_anchor`) and follows them in follow mode. Do not turn it into a free-floating position.
- **Title**: toggle, left/center/right alignment, and X/Y offsets as fractions of the frame.
- **No black bars**: `Framing.at` clamps the translation so the zoomed frame always covers the output, and zoom is a single value for the whole video (no zoom pumping).
- **No text inside AI images**: image models misspell Korean. Short labels are rendered by us under the picture.
- **Sermon-specific editing**: never cut inside Bible readings or prayers, keep deliberate pauses (`min_silence` default 1.0 s), and when unsure keep the word.
- **Graceful degradation**: without `ANTHROPIC_API_KEY`, only strong fillers ("어/음") are cut. Without `OPENAI_API_KEY`, no cards are added. Every AI failure is logged and the edit continues.
- **Long videos (30–60 min)**: never hold full-length audio or video in memory. Stream through `FrameReader` and `AudioWriter`, and read wav ranges with `wave.setpos`.

## Claude API usage

- Model: `claude-opus-5-5` by default, overridable with `CLAUDE_MODEL`.
- Calls go through `client.beta.messages.create`, with:
  - `output_config.effort`
  - `output_config.format` (JSON schema)
  - server-side fallback: `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`
- Check `stop_reason` for `refusal` and `max_tokens` before reading the text.
- Do not add `temperature`/`top_p`, `budget_tokens` or assistant prefill.

## Run / test

```bash
.venv\Scripts\python app.py                     # UI (NO_BROWSER=1 to skip opening a browser)
.venv\Scripts\python cli.py 설교.mp4 --start 0:06 --end 0:45.7 --title "두려워하지 말라" --name "홍길동 담임목사" --follow
```

- There is no automated test suite.
- To verify a change, run `cli.py` on a short clip, then extract frames with ffmpeg and look at them: centring, name under the preacher, title alignment, the card.
- Check `log.txt` and the report.
- First runs download the Whisper model (about 3 GB). Playwright needs `python -m playwright install chromium`.
- Setup from scratch: `실행.bat` (creates `.venv`, installs CUDA torch and `requirements.txt`).
