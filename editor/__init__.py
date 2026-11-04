import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_from_file: set[str] = set()  # keys this loader put into the environment


def load_env() -> None:
    """(Re)read video_auto_editor/.env. Called at start-up and again before every preview / edit,
    so a key added or changed in .env applies without restarting the program.
    Values from .env win over earlier .env values; variables set outside .env are left alone."""
    seen: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip().lstrip("﻿")
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                seen[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in seen.items():
        if v and (k in _from_file or k not in os.environ):
            os.environ[k] = v
            _from_file.add(k)
        elif not v and k in _from_file:  # key was emptied in .env
            os.environ.pop(k, None)
            _from_file.discard(k)
    for k in list(_from_file - seen.keys()):  # key line removed from .env
        os.environ.pop(k, None)
        _from_file.discard(k)


load_env()
