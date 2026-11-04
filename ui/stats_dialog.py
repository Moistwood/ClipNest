"""统计面板。看一眼就知道记录了多少、占多大、都从哪来。"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.stats import KIND_LABELS, Stats, format_span, format_timestamp, human_size
from ui import theme


class DistributionBar(QWidget):
    """按类型堆一条横条，宽度按占比分。"""

    def __init__(self, stats: Stats, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stats = stats
        self.setFixedHeight(28)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt 接口)
        pal = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        rect = QRectF(self.rect())
        painter.setBrush(QColor(pal.search_bg))
        painter.drawRoundedRect(rect, 6, 6)

        if not self._stats.total:
            painter.end()
            return

        x = rect.left()
        kinds = [k for k in ("text", "image", "files") if self._stats.kinds.get(k)]
        for index, kind in enumerate(kinds):
            width = rect.width() * self._stats.share(kind)
            painter.setBrush(QColor(theme.kind_color(pal, kind)))
            if index == 0:
                painter.drawRoundedRect(QRectF(x, rect.top(), width, rect.height()), 6, 6)
            else:
                painter.drawRect(QRectF(x, rect.top(), width, rect.height()))
            x += width
        painter.end()


class StatsDialog(QDialog):
    def __init__(self, stats: Stats, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stats = stats
        self.setWindowTitle("使用统计")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build()
        self._apply_theme()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(14)

        root.addLayout(self._build_numbers())
        root.addWidget(self._build_kinds())
        if self._stats.sources:
            root.addWidget(self._build_sources())

        span = QLabel(
            f"{format_span(self._stats)} · 最早 {format_timestamp(self._stats.first_at)}"
            f" · 最近 {format_timestamp(self._stats.last_at)}"
        )
        span.setObjectName("hint")
        span.setWordWrap(True)
        root.addWidget(span)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_numbers(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._card("记录条数", str(self._stats.total)))
        row.addWidget(self._card("占用空间", human_size(self._stats.bytes_total)))
        row.addWidget(self._card("平均复用", f"{self._stats.average_uses:.1f} 次"))
        return row

    def _card(self, caption: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(2)

        title = QLabel(caption)
        title.setObjectName("hint")
        number = QLabel(value)
        number.setObjectName("value")

        layout.addWidget(title)
        layout.addWidget(number)
        return frame

    def _build_kinds(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(DistributionBar(self._stats))
        layout.addLayout(self._kind_legend())
        return box

    def _kind_legend(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        for column, kind in enumerate(("text", "image", "files")):
            count = self._stats.kinds.get(kind, 0)
            label = QLabel(f"{KIND_LABELS[kind]} {count} 条 · {self._stats.share(kind):.0%}")
            label.setObjectName("legend")
            label.setStyleSheet(f"color: {theme.kind_color(theme.current(), kind)};")
            grid.addWidget(label, 0, column)
        return grid

    def _build_sources(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(6)

        title = QLabel("最常复制的程序")
        title.setObjectName("hint")
        layout.addWidget(title)

        for name, count in self._stats.sources:
            line = QLabel(f"{name}    {count} 条")
            line.setObjectName("legend")
            layout.addWidget(line)
        return frame

    def _apply_theme(self) -> None:
        pal = theme.current()
        self.setStyleSheet(
            f"""
            QDialog {{ background: {pal.panel}; color: {pal.text}; }}
            QFrame#card {{
                background: {pal.search_bg};
                border: 1px solid {pal.divider};
                border-radius: 8px;
            }}
            QLabel {{ color: {pal.text}; }}
            QLabel#hint {{ color: {pal.text_faint}; font-size: 11px; }}
            QLabel#value {{ color: {pal.text}; font-size: 18px; font-weight: 600; }}
            QLabel#legend {{ color: {pal.text_muted}; font-size: 11px; }}
            QPushButton {{
                background: {pal.search_bg};
                border: 1px solid {pal.divider};
                border-radius: 6px;
                padding: 6px 18px;
                color: {pal.text};
            }}
            """
        )
