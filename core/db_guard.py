"""历史库损坏时的兜底：只隔离，不删除。

启动前跑一次 quick_check。真坏了就把原文件连同 WAL/SHM 改名挪到
broken/，让 Repository 从一个干净的空库重建，而不是整个程序起不来。
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path


def ensure_healthy(db_path: Path) -> str:
    """返回给用户的提示；库正常或不存在时返回空串。"""
    if not db_path.exists():
        return ""
    try:
        connection = sqlite3.connect(str(db_path))
        try:
            row = connection.execute("PRAGMA quick_check").fetchone()
        finally:
            connection.close()
        if row and str(row[0]) == "ok":
            return ""
    except sqlite3.Error:
        pass
    return _isolate(db_path)


def _isolate(db_path: Path) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    folder = db_path.parent / "broken"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"历史库读取失败，且无法隔离旧文件（{exc}），请手动检查数据目录。"

    stem = f"history-{stamp}.db"
    moved = 0
    for suffix in ("", "-wal", "-shm"):
        source = Path(str(db_path) + suffix)
        if not source.exists():
            continue
        try:
            shutil.move(str(source), str(folder / (stem + suffix)))
            moved += 1
        except OSError:
            pass

    if not moved:
        return "历史库读取失败，旧文件没能移走，请手动检查数据目录。"
    return (
        f"历史库读取失败，旧文件已移到 {folder / stem}，程序已从空库重新开始。"
        "旧文件没有删除，可以自行取回。"
    )
