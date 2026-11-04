"""缩略图缓存。预览区只读小图，避免每次切条目都解码原图。"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader

DEFAULT_SIDE = 480


def thumb_path(cache_dir: Path, key: str, max_side: int = DEFAULT_SIDE) -> Path:
    return Path(cache_dir) / f"{key[:32]}_{max_side}.png"


def is_fresh(target: Path, source: Path) -> bool:
    if not target.exists():
        return False
    try:
        return target.stat().st_mtime >= source.stat().st_mtime
    except OSError:
        return False


def build(source: Path, target: Path, max_side: int = DEFAULT_SIDE) -> bool:
    """按需缩小解码，大图能省掉大部分像素搬运。"""
    reader = QImageReader(str(source))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid():
        scaled = size.scaled(
            QSize(max_side, max_side), Qt.AspectRatioMode.KeepAspectRatio
        )
        reader.setScaledSize(scaled)
    image = reader.read()
    if image.isNull():
        return False
    return image.save(str(target), "PNG")


def ensure(
    image_path: str, key: str, cache_dir: Path, max_side: int = DEFAULT_SIDE
) -> Path | None:
    if not image_path:
        return None
    source = Path(image_path)
    if not source.exists():
        return None

    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    target = thumb_path(cache_dir, key, max_side)
    if is_fresh(target, source):
        return target
    if build(source, target, max_side):
        return target
    # 生成失败就退回原图，预览总比空白强
    return source if source.exists() else None


def clear(cache_dir: Path) -> int:
    removed = 0
    folder = Path(cache_dir)
    if not folder.exists():
        return 0
    for entry in folder.glob("*.png"):
        try:
            entry.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def total_size(cache_dir: Path) -> int:
    folder = Path(cache_dir)
    if not folder.exists():
        return 0
    return sum(p.stat().st_size for p in folder.glob("*.png") if p.is_file())


def prune(cache_dir: Path, keep_days: int = 30) -> int:
    folder = Path(cache_dir)
    if not folder.exists() or keep_days <= 0:
        return 0
    cutoff = time.time() - keep_days * 86400
    removed = 0
    for entry in folder.glob("*.png"):
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
                removed += 1
        except OSError:
            continue
    return removed
