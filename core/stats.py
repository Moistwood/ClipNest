"""使用情况统计。只读聚合，不改任何数据。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from core.repository import Repository

KIND_LABELS = {"text": "文本", "image": "图片", "files": "文件"}


@dataclass
class Stats:
    total: int = 0
    bytes_total: int = 0
    uses: int = 0
    pinned: int = 0
    first_at: float = 0.0
    last_at: float = 0.0
    kinds: dict[str, int] = field(default_factory=dict)
    sources: list[tuple[str, int]] = field(default_factory=list)

    @property
    def average_uses(self) -> float:
        return self.uses / self.total if self.total else 0.0

    @property
    def span_days(self) -> int:
        if not self.first_at or not self.last_at:
            return 0
        return max(0, int((self.last_at - self.first_at) // 86400))

    def share(self, kind: str) -> float:
        return self.kinds.get(kind, 0) / self.total if self.total else 0.0


def collect(repo: Repository) -> Stats:
    raw = repo.summary()
    return Stats(
        total=int(raw["total"]),
        bytes_total=int(raw["bytes_total"]),
        uses=int(raw["uses"]),
        pinned=int(raw["pinned"]),
        first_at=float(raw["first_at"]),
        last_at=float(raw["last_at"]),
        kinds={str(k): int(v) for k, v in dict(raw["kinds"]).items()},
        sources=[(str(s), int(n)) for s, n in list(raw["sources"])],
    )


def human_size(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    for unit in ("KB", "MB", "GB"):
        value /= 1024.0
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} TB"


def format_span(stats: Stats) -> str:
    if not stats.total:
        return "暂无记录"
    days = stats.span_days
    if days <= 0:
        return "今天刚开始"
    if days == 1:
        return "已积累 1 天"
    return f"已积累 {days} 天"


def format_timestamp(value: float) -> str:
    if not value:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(value))
