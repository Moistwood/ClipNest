"""右侧预览区：文本、图片、文件路径三种。"""

from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.models import KIND_FILES, KIND_IMAGE, ClipItem
from ui import theme


class PreviewPane(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pal = theme.current()

        self._stack = QStackedWidget(self)

        self._empty = QLabel("选中一条记录查看内容", self)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setFont(theme.font(9))
        self._empty.setStyleSheet(f"color: {self.pal.text_faint};")

        self._text = QTextBrowser(self)
        self._text.setFrameShape(QTextBrowser.Shape.NoFrame)
        self._text.setFont(theme.font(9))
        self._text.setStyleSheet(
            f"background: transparent; color: {self.pal.text};"
            f" selection-background-color: {self.pal.accent}; border: none;"
        )

        self._image = QLabel(self)
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        self._stack.addWidget(self._empty)
        self._stack.addWidget(self._text)
        self._stack.addWidget(self._image)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._current: ClipItem | None = None
        self._pixmap: QPixmap | None = None

    def refresh_palette(self) -> None:
        self.pal = theme.current()
        self._empty.setStyleSheet(f"color: {self.pal.text_faint};")
        self._text.setStyleSheet(
            f"background: transparent; color: {self.pal.text};"
            f" selection-background-color: {self.pal.accent}; border: none;"
        )
        self.show_item(self._current)

    def show_item(self, item: ClipItem | None) -> None:
        self._current = item
        if item is None:
            self._stack.setCurrentWidget(self._empty)
            return

        if item.kind == KIND_IMAGE:
            self._pixmap = self._load_pixmap(item)
            if self._pixmap is None:
                self._text.setPlainText("图片文件已丢失")
                self._stack.setCurrentWidget(self._text)
            else:
                self._render_pixmap()
                self._stack.setCurrentWidget(self._image)
            return

        if item.kind == KIND_FILES:
            blocks = []
            for path in item.files:
                pure = Path(path)
                blocks.append(
                    f"<p style='margin:0 0 8px 0'>{escape(pure.name)}"
                    f"<br><span style='color:{self.pal.text_faint}'>{escape(str(pure.parent))}</span></p>"
                )
            self._text.setHtml("".join(blocks))
            self._stack.setCurrentWidget(self._text)
            return

        self._text.setPlainText(item.text)
        self._stack.setCurrentWidget(self._text)

    def _load_pixmap(self, item: ClipItem) -> QPixmap | None:
        if not item.image_path:
            return None
        path = Path(item.image_path)
        if not path.exists():
            return None
        pixmap = QPixmap(str(path))
        return pixmap if not pixmap.isNull() else None

    def _render_pixmap(self) -> None:
        if self._pixmap is None:
            return
        area = self._stack.size()
        max_width = max(80, area.width() - 16)
        max_height = max(80, area.height() - 16)
        scaled = self._pixmap.scaled(
            max_width,
            max_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image.setPixmap(scaled)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt 接口)
        super().resizeEvent(event)
        if self._pixmap is not None and self._current is not None:
            self._render_pixmap()
