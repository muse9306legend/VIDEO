"""키즈 유튜브 AI 편집기: 영상 위에 AI 설명 그림과 쌍둥이 캐릭터를 얹는다."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
JOBS = ROOT / "jobs"
FONTS = ROOT / "assets" / "fonts"
_from_file: set[str] = set()  # keys this loader put into the environment


def load_env() -> None:
    """(Re)read .env. Called at start-up and before every preview / render, so a key added or
    changed in .env applies without restarting. Variables set outside .env are left alone."""
    seen: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                seen[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in seen.items():
        if v and (k in _from_file or k not in os.environ):
            os.environ[k] = v
            _from_file.add(k)
        elif not v and k in _from_file:
            os.environ.pop(k, None)
            _from_file.discard(k)
    for k in list(_from_file - seen.keys()):
        os.environ.pop(k, None)
        _from_file.discard(k)


load_env()
