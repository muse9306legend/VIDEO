"""ffmpeg helpers. Frames are streamed one at a time, so 30-60 minute videos never sit in memory."""
from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


def probe(path: str | Path) -> dict:
    out = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
                         capture_output=True, check=True, encoding="utf-8")
    info = json.loads(out.stdout)
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
    a = next((s for s in info["streams"] if s.get("codec_type") == "audio"), None)
    if v is None:
        raise ValueError("영상 트랙이 없는 파일입니다.")
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list") or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if "rotate" in (v.get("tags") or {}):
        rot = int(v["tags"]["rotate"])
    if abs(rot) % 180 == 90:  # phone video shot in portrait
        w, h = h, w
    num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    duration = float(info["format"].get("duration") or v.get("duration") or 0)
    return {"width": w, "height": h, "fps": fps, "duration": duration, "has_audio": a is not None}


def out_size(w: int, h: int, max_side: int = 1920) -> tuple[int, int]:
    s = min(1.0, max_side / max(w, h))
    return int(w * s) // 2 * 2, int(h * s) // 2 * 2


def out_fps(fps: float) -> float:
    return 30.0 if fps <= 0 or fps > 60.5 else round(fps, 3)


def extract_wav(src: str | Path, dst: str | Path, sr: int = 16000) -> None:
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(sr),
                    "-c:a", "pcm_s16le", str(dst)], check=True)


def grab_frame(src: str | Path, t: float, w: int, h: int) -> np.ndarray | None:
    cmd = [FFMPEG, "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(src), "-frames:v", "1",
           "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    if len(raw) < w * h * 3:
        return None
    return np.frombuffer(raw[: w * h * 3], np.uint8).reshape(h, w, 3).copy()


class FrameReader:
    """Constant-frame-rate RGB frames from ffmpeg, one at a time."""

    def __init__(self, src: str | Path, w: int, h: int, fps: float):
        self.w, self.h, self.size = w, h, w * h * 3
        cmd = [FFMPEG, "-v", "error", "-i", str(src), "-vf", f"fps={fps},scale={w}:{h}",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=self.size * 2)

    def __iter__(self):
        while True:
            raw = self.proc.stdout.read(self.size)
            if len(raw) < self.size:
                break
            yield np.frombuffer(raw, np.uint8).reshape(self.h, self.w, 3)

    def close(self):
        self.proc.stdout.close()
        self.proc.wait()


@lru_cache(maxsize=1)
def video_encoder() -> list[str]:
    """NVENC when the GPU encoder really works, otherwise x264."""
    test = [FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1", "-c:v", "h264_nvenc", "-f", "null", "-"]
    try:
        if subprocess.run(test, capture_output=True, timeout=20).returncode == 0:
            return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "21", "-b:v", "0"]
    except Exception:
        pass
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]


class VideoWriter:
    """Pipes RGB frames to ffmpeg and muxes the original audio track."""

    def __init__(self, dst: str | Path, w: int, h: int, fps: float, audio_src: str | Path | None):
        cmd = [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-"]
        if audio_src:
            cmd += ["-i", str(audio_src), "-map", "0:v", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd += video_encoder() + ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def write(self, frame: np.ndarray):
        self.proc.stdin.write(np.ascontiguousarray(frame).tobytes())

    def close(self):
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError("ffmpeg 인코딩 실패")
