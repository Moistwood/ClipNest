"""所有落盘路径。配置和数据一律在 %APPDATA%，绝不写进安装目录。"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "ClipNest"
APP_VERSION = "1.0.0"
ORG_NAME = "ClipNest"


def data_dir() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "history.db"


def blobs_dir() -> Path:
    path = data_dir() / "blobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return data_dir() / "config.json"


def thumbs_dir() -> Path:
    path = data_dir() / "thumbs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    return data_dir() / "clipnest.log"


def save_blob(png: bytes, content_hash: str) -> Path:
    path = blobs_dir() / f"{content_hash[:32]}.png"
    if not path.exists():
        path.write_bytes(png)
    return path


def remove_blob(path_str: str) -> None:
    if not path_str:
        return
    try:
        Path(path_str).unlink(missing_ok=True)
    except OSError:
        pass
