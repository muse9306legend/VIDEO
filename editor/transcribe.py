"""Korean speech-to-text with word timestamps (faster-whisper)."""
from __future__ import annotations

import gc
import os

import numpy as np

# Whisper tends to drop "어/음" from transcripts. Seeding the prompt with
# disfluent speech makes it write them out, so we can find and cut them.
FILLER_PROMPT = "음, 어, 그러니까, 어... 음... 아 이거 진짜 맛있다. 음 그 뭐지, 어 이거 먹어볼게요."


def _enable_cuda_dlls() -> bool:
    """faster-whisper needs cuBLAS/cuDNN; the CUDA build of torch ships them in torch/lib."""
    try:
        import torch
    except Exception:
        return False
    lib = os.path.join(os.path.dirname(torch.__file__), "lib")
    if os.path.isdir(lib):
        os.environ["PATH"] = lib + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(lib)
    return torch.cuda.is_available()


def transcribe(audio16k: np.ndarray, model_size: str = "large-v3", log=print) -> list[dict]:
    cuda = _enable_cuda_dlls()
    from faster_whisper import WhisperModel

    attempts = [("cuda", "int8_float16", model_size)] if cuda else []
    attempts.append(("cpu", "int8", "medium" if model_size.startswith("large") else model_size))

    last_err = None
    for device, compute_type, size in attempts:
        model = None
        try:
            log(f"Whisper {size} 로딩 ({device})")
            model = WhisperModel(size, device=device, compute_type=compute_type)
            segs, _ = model.transcribe(
                audio16k, language="ko", word_timestamps=True, initial_prompt=FILLER_PROMPT,
                condition_on_previous_text=False, vad_filter=False, beam_size=5,
            )
            segments, wid = [], 0
            for s in segs:
                words = []
                for w in s.words or []:
                    words.append({"id": wid, "start": float(w.start), "end": float(w.end),
                                  "word": w.word, "prob": float(w.probability)})
                    wid += 1
                if words:
                    segments.append({"id": len(segments), "start": float(s.start), "end": float(s.end),
                                     "text": s.text.strip(), "words": words})
            return segments
        except Exception as e:  # CUDA libs missing, out of memory, ...
            last_err = e
            log(f"Whisper {device} 실패: {e}")
        finally:
            del model
            gc.collect()
    raise RuntimeError(f"음성 인식 실패: {last_err}")
