"""剪贴板条目的数据结构，以及不依赖 Qt 的展示辅助函数。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

KIND_TEXT = "text"
KIND_IMAGE = "image"
KIND_FILES = "files"

MAX_TEXT_BYTES = 256 * 1024
PREVIEW_CHARS = 180


@dataclass(slots=True)
class ClipItem:
    kind: str
    content_hash: str = ""
    preview: str = ""
    text: str = ""
    files: list[str] = field(default_factory=list)
    image_path: str = ""
    image_bytes: bytes | None = None
    width: int = 0
    height: int = 0
    source_app: str = ""
    size: int = 0
    created_at: float = field(default_factory=time.time)
    id: int = 0
    pinned: bool = False
    use_count: int = 0

    @property
    def kind_label(self) -> str:
        return {KIND_TEXT: "文本", KIND_IMAGE: "图片", KIND_FILES: "文件"}.get(self.kind, "未知")

    def display_title(self) -> str:
        if self.kind == KIND_TEXT:
            return self.text.strip().splitlines()[0][:120] if self.text.strip() else "(空白文本)"
        if self.kind == KIND_IMAGE:
            return f"图片 {self.width}×{self.height}"
        if not self.files:
            return "文件"
        first = self.files[0].rsplit("\\", 1)[-1]
        if len(self.files) == 1:
            return first
        return f"{first} 等 {len(self.files)} 个文件"

    def display_detail(self) -> str:
        if self.kind == KIND_TEXT:
            lines = self.text.strip().splitlines()
            if len(lines) > 1:
                second = next((ln.strip() for ln in lines[1:] if ln.strip()), "")
                if second:
                    return second[:120]
        if self.kind == KIND_FILES and self.files:
            return self.files[0][:120]
        return ""

    def size_label(self) -> str:
        n = float(self.size)
        for unit in ("B", "KB", "MB"):
            if n < 1024 or unit == "MB":
                return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} MB"


def format_relative(ts: float) -> str:
    delta = time.time() - ts
    if delta < 60:
        return "刚刚"
    if delta < 3600:
        return f"{int(delta // 60)} 分钟前"
    if delta < 86400:
        return f"{int(delta // 3600)} 小时前"
    if delta < 86400 * 7:
        return f"{int(delta // 86400)} 天前"
    return time.strftime("%m-%d", time.localtime(ts))


def make_preview(kind: str, text: str, files: list[str], width: int, height: int) -> str:
    if kind == KIND_TEXT:
        return " ".join(text.split())[:PREVIEW_CHARS]
    if kind == KIND_IMAGE:
        return f"[图片 {width}×{height}]"
    if not files:
        return "[文件]"
    names = "、".join(f.rsplit("\\", 1)[-1] for f in files[:3])
    return f"[文件] {names}" + (f" 等 {len(files)} 项" if len(files) > 3 else "")
