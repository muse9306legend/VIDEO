# AGENTS.md — 키즈 유튜브 AI 편집기

Korean family kids-YouTube videos → the same video with AI explainer picture cards and the user's twins as
cartoon characters who react in speech bubbles. No cutting: the original video and audio play unchanged.
Python 3.13 on Windows, NVIDIA GPU (RTX 2060 6 GB). UI text, logs and user-facing messages are Korean.

## Pipeline (`editor/pipeline.py`)

1. **Speech**: `transcribe.py` runs faster-whisper (`WHISPER_MODEL`, default large-v3) on a 16 kHz mono wav.
2. **Plan**: `ai.py::plan` makes one structured-output Claude call returning `cards` (start, duration, concept,
   visual_brief, label) and `reactions` (start, duration, twin A/B, pose, text, emoji). `ai.clean` clamps
   times and removes overlaps.
3. **Pictures + characters, in parallel**: `images.Batch` draws every card at once
   (`OPENAI_IMAGE_CONCURRENCY`, default 6) while `characters.sprites` draws the twins:
   - one base drawing per twin (from reference photos via `images.edit` when given),
   - then every needed pose from that base image, so the character stays the same,
   - `cut_out` keeps real transparency or flood-fills a plain background away.
   - Slow pictures fall back to `quality="low"`, then `gpt-image-1`. Results are cached in
     `jobs/_image_cache/` keyed by model, size, prompt and reference images.
4. **Layout**: `pipeline.layout` turns the plan into `overlay.El` items. Twin A is bottom-left, twin B is
   bottom-right. Cards sit top-right in landscape, or top-left when B is talking at the same time; in
   portrait they sit top-centre.
5. **Render**: `media.FrameReader` streams CFR RGB frames, `overlay.compose` draws the active overlays,
   `media.VideoWriter` encodes (NVENC if it really works, else x264) and muxes the original audio.
6. **Outputs** in `jobs/<timestamp>/`: `결과영상.mp4`, `편집리포트.html`, `plan.json`, `transcript.json`,
   `card_XX.png`, `characters/`, `log.txt`.

`prepare()` does steps 1-4 and returns a `Job`; `render()` does step 5; `frame_at()` draws one preview frame
through the same `compose()`. The preview must always match the final render — keep it that way.
Passing a saved `plan` skips speech and Claude (used by "고친 계획 적용" and `cli.py --plan`).

## Files

| File | Role |
|---|---|
| `app.py` | Gradio UI (127.0.0.1): analyse → preview / edit plan → render. |
| `cli.py` | Same from the command line, including `--plan` re-render. |
| `editor/__init__.py` | Paths and `load_env()`. |
| `editor/media.py` | ffprobe/ffmpeg: `probe`, `extract_wav`, `grab_frame`, `FrameReader`, `VideoWriter`. |
| `editor/transcribe.py` | faster-whisper. |
| `editor/ai.py` | Claude plan + `clean`. |
| `editor/images.py` | OpenAI image generation, cache, `Batch`. |
| `editor/characters.py` | Poses, sprite prompts, `cut_out`, placeholder characters, `sprites()`. |
| `editor/overlay.py` | Paper card, speech bubble, name tag, `El` animation, `compose`. |
| `editor/pipeline.py` | `Settings`, `prepare`, `layout`, `render`, `frame_at`, report. |
| `assets/fonts` | Gaegu (OFL). |

## Rules — do not break

- **Secrets**: API keys live only in `.env` (gitignored). `.env.example` keeps empty values. Run a secret
  scan before every commit, e.g. `git grep --cached -nE "sk-ant-|sk-proj-|sk-[A-Za-z0-9]{20,}"`.
- **Design**: cream paper `#FFF8EC`, ink `#2E2A26` outlines with a slight hand-drawn wobble, Gaegu Bold
  text, soft offset shadow; twin colours coral `#FFB4A2` (A) and sky `#8ECAE6` (B). New overlays are drawn
  in `overlay.py` with Pillow in this style.
- **No text inside AI images**: image models misspell Korean. Labels and bubbles are rendered by us.
- **Kids-safe**: everything the twins say is kind; never mock anyone. Characters are cartoons, never a
  realistic likeness.
- **Graceful degradation**: without `ANTHROPIC_API_KEY` there is no plan (a saved plan still works).
  Without `OPENAI_API_KEY` there are no cards and the twins use `characters.placeholder`. Every AI failure
  is logged and the edit continues.
- **Long videos (30-60 min)**: never hold the full video in memory. Stream frames; overlays are drawn once
  as RGBA images and only moved, scaled and faded per frame.

## Claude API usage

- Model: `claude-opus-5-5` by default, overridable with `CLAUDE_MODEL`.
- `client.beta.messages.create` with `output_config.effort`, `output_config.format` (JSON schema) and
  server-side fallback: `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`.
- Check `stop_reason` for `refusal` and `max_tokens` before reading the text.
- Do not add `temperature`/`top_p`, `budget_tokens` or assistant prefill.

## Run / test

- `실행.bat` creates `.venv`, installs CUDA torch and `requirements.txt`, then runs
  `gradio app.py --demo-name demo --watch-dirs editor` (auto-reload: edits apply in about 4 s).
  Server settings come from `GRADIO_SERVER_NAME`, `GRADIO_SERVER_PORT`, `GRADIO_ALLOWED_PATHS` in the bat.
  Do not edit code while the user is rendering a long video: a reload can interrupt the job.
- `실행.bat` also starts `자동업데이트.bat` (minimized): every 60 s it runs `git pull --ff-only`, so code pushed to
  GitHub reaches the running UI without a restart. `pipeline.busy()` writes a lock in `jobs/_busy/` during
  `prepare()` and `render()`; the updater skips pulling while a lock exists (locks older than 6 h are stale).
- `.bat` files must keep CRLF line endings (`.gitattributes`); `goto` labels break with LF.
- `.env` is re-read at page load and at the start of every `prepare()`. Never cache API keys or model names
  at import time.
- There is no automated test suite. To verify a change, render a short clip with a hand-written plan
  (`cli.py clip.mp4 --plan plan.json`), extract frames with ffmpeg and look at them: card position,
  characters at the bottom corners, bubble wrapping, emoji, portrait layout.
