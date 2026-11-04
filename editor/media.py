"""ffmpeg helpers: probing, decoding audio/frames, writing the final video."""
from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import numpy as np

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


def probe(path: str | Path) -> dict:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, check=True, encoding="utf-8",
    )
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
    if abs(rot) % 180 == 90:  # phone videos shot in portrait
        w, h = h, w
    fr = v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1"
    num, den = fr.split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    duration = float(info["format"].get("duration") or v.get("duration") or 0)
    return {"width": w, "height": h, "fps": fps, "duration": duration, "has_audio": a is not None}


def target_size(w: int, h: int, max_side: int) -> tuple[int, int]:
    scale = min(1.0, max_side / max(w, h))
    return int(w * scale) // 2 * 2, int(h * scale) // 2 * 2


def target_fps(fps: float) -> float:
    if fps <= 0 or fps > 30.5:
        return 30.0
    return round(fps, 3)


def read_audio(path: str | Path, sr: int, channels: int) -> np.ndarray:
    cmd = [FFMPEG, "-v", "error", "-i", str(path), "-vn", "-ac", str(channels), "-ar", str(sr), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, channels).copy()


def extract_wav(path: str | Path, out_wav: str | Path, sr: int, channels: int) -> None:
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(path), "-vn", "-ac", str(channels), "-ar", str(sr),
                    "-c:a", "pcm_s16le", str(out_wav)], check=True)


def write_wav(path: str | Path, audio: np.ndarray, sr: int) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(audio.shape[1])
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def grab_frame(path: str | Path, t: float, w: int, h: int) -> np.ndarray | None:
    cmd = [FFMPEG, "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(path), "-frames:v", "1",
           "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    if len(raw) < w * h * 3:
        return None
    return np.frombuffer(raw[: w * h * 3], np.uint8).reshape(h, w, 3).copy()


class AudioWriter:
    """Streams PCM chunks into a 16-bit wav (sermons are long - avoid holding the whole edit in memory)."""

    def __init__(self, path: str | Path, sr: int, channels: int):
        self.wf = wave.open(str(path), "wb")
        self.wf.setnchannels(channels)
        self.wf.setsampwidth(2)
        self.wf.setframerate(sr)

    def write(self, chunk: np.ndarray) -> None:
        self.wf.writeframes((np.clip(chunk, -1.0, 1.0) * 32767).astype("<i2").tobytes())

    def close(self) -> None:
        self.wf.close()


class FrameReader:
    """Decodes a video to constant-frame-rate BGR frames (rotation already applied by ffmpeg)."""

    def __init__(self, path: str | Path, w: int, h: int, fps: float):
        cmd = [FFMPEG, "-v", "error", "-i", str(path), "-an", "-vf", f"fps={fps},scale={w}:{h}",
               "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=w * h * 3 * 4)
        self.w, self.h, self.size = w, h, w * h * 3

    def read(self) -> np.ndarray | None:
        buf = self.p.stdout.read(self.size)
        if len(buf) < self.size:
            return None
        return np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3).copy()

    def close(self) -> None:
        try:
            self.p.stdout.close()
        finally:
            self.p.kill()
            self.p.wait()


_ENCODER: list[str] | None = None


def video_encoder() -> list[str]:
    """Prefer the NVIDIA hardware encoder when it actually works, else x264."""
    global _ENCODER
    if _ENCODER is None:
        test = subprocess.run(
            [FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=size=256x256:d=0.2", "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True,
        )
        if test.returncode == 0:
            _ENCODER = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "20", "-b:v", "0"]
        else:
            _ENCODER = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
    return _ENCODER


class VideoWriter:
    def __init__(self, out_path: str | Path, w: int, h: int, fps: float, wav_path: str | Path):
        cmd = [FFMPEG, "-y", "-v", "error",
               "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
               "-i", str(wav_path), "-map", "0:v", "-map", "1:a",
               *video_encoder(), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart", str(out_path)]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def write(self, frame: np.ndarray) -> None:
        try:
            self.p.stdin.write(frame.tobytes())
        except BrokenPipeError:
            raise RuntimeError("영상 인코딩 실패: " + self.p.stderr.read().decode("utf-8", "replace"))

    def close(self) -> None:
        self.p.stdin.close()
        err = self.p.stderr.read().decode("utf-8", "replace")
        if self.p.wait() != 0:
            raise RuntimeError("영상 인코딩 실패: " + err)
