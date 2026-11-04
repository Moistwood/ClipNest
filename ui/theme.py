"""配色与字体。深色跟随系统，两套色值都按中性灰调过，不刺眼。"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap


@dataclass(frozen=True)
class Palette:
    window: str
    panel: str
    panel_border: str
    row_hover: str
    row_selected: str
    text: str
    text_muted: str
    text_faint: str
    accent: str
    search_bg: str
    divider: str
    kind_text: str
    kind_image: str
    kind_files: str


LIGHT = Palette(
    window="#00000000",
    panel="#FBFBFB",
    panel_border="#1A000000",
    row_hover="#0F000000",
    row_selected="#1F2B6CB0",
    text="#1A1A1A",
    text_muted="#5C5C5C",
    text_faint="#8A8A8A",
    accent="#2B6CB0",
    search_bg="#F1F1F1",
    divider="#14000000",
    kind_text="#2B6CB0",
    kind_image="#7B4FBF",
    kind_files="#A8620F",
)

DARK = Palette(
    window="#00000000",
    panel="#2A2A2A",
    panel_border="#22FFFFFF",
    row_hover="#12FFFFFF",
    row_selected="#332F7FD8",
    text="#F2F2F2",
    text_muted="#A8A8A8",
    text_faint="#7A7A7A",
    accent="#4C9AFF",
    search_bg="#1F1F1F",
    divider="#1AFFFFFF",
    kind_text="#6BA9F0",
    kind_image="#B18BEA",
    kind_files="#D9A05B",
)


def current() -> Palette:
    try:
        dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        dark = False
    return DARK if dark else LIGHT


def font(size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    result = QFont("Microsoft YaHei UI")
    result.setStyleHint(QFont.StyleHint.SansSerif)
    result.setPointSize(size)
    result.setWeight(weight)
    return result


def kind_color(pal: Palette, kind: str) -> str:
    return {"text": pal.kind_text, "image": pal.kind_image, "files": pal.kind_files}.get(
        kind, pal.text_muted
    )


def make_icon(active: bool = True) -> QIcon:
    """运行时画图标，仓库里不放二进制资源，改样式只需要改代码。"""
    palette_now = current()
    base = palette_now.accent if active else "#8A8A8A"

    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(base))
        painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.24, size * 0.24)

        painter.setBrush(QColor("#FFFFFF"))
        body = QRectF(size * 0.28, size * 0.22, size * 0.44, size * 0.56)
        painter.drawRoundedRect(body, size * 0.09, size * 0.09)

        painter.setBrush(QColor(base))
        clip = QRectF(size * 0.38, size * 0.16, size * 0.24, size * 0.14)
        painter.drawRoundedRect(clip, size * 0.05, size * 0.05)

        painter.end()
        icon.addPixmap(pixmap)
    return icon
