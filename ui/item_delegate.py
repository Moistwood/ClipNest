"""列表项自绘。QListWidget 的默认样式撑不起这个界面，所以整行自己画。"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from core.models import ClipItem, format_relative
from ui import theme

ITEM_ROLE = Qt.ItemDataRole.UserRole + 1
ROW_HEIGHT = 58


class ClipDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.pal = theme.current()
        self.font_title = theme.font(10, QFont.Weight.Medium)
        self.font_detail = theme.font(9)
        self.font_badge = theme.font(8)
        self.font_time = theme.font(8)

    def refresh_palette(self) -> None:
        self.pal = theme.current()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        item: ClipItem | None = index.data(ITEM_ROLE)
        if item is None:
            super().paint(painter, option, index)
            return

        pal = self.pal
        rect = option.rect.adjusted(6, 2, -6, -2)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            path = QPainterPath()
            path.addRoundedRect(rect, 8, 8)
            painter.fillPath(path, QColor(pal.row_selected if selected else pal.row_hover))

        accent_bar = QRect(rect.left(), rect.top() + 10, 3, rect.height() - 20)
        if selected:
            painter.fillRect(accent_bar, QColor(theme.kind_color(pal, item.kind)))

        badge_rect = QRect(rect.left() + 14, rect.top() + (rect.height() - 20) // 2, 42, 20)
        badge_path = QPainterPath()
        badge_path.addRoundedRect(badge_rect, 10, 10)
        badge_color = QColor(theme.kind_color(pal, item.kind))
        badge_color.setAlpha(38)
        painter.fillPath(badge_path, badge_color)

        painter.setFont(self.font_badge)
        painter.setPen(QColor(theme.kind_color(pal, item.kind)))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, item.kind_label)

        text_left = badge_rect.right() + 12
        text_right = rect.right() - 68

        painter.setFont(self.font_title)
        painter.setPen(QColor(pal.text))
        title = QFontMetrics(self.font_title).elidedText(
            item.display_title(), Qt.TextElideMode.ElideRight, max(40, text_right - text_left)
        )
        painter.drawText(
            QRect(text_left, rect.top() + 10, text_right - text_left, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )

        detail = item.display_detail()
        if detail:
            painter.setFont(self.font_detail)
            painter.setPen(QColor(pal.text_faint))
            elided = QFontMetrics(self.font_detail).elidedText(
                detail, Qt.TextElideMode.ElideRight, max(40, text_right - text_left)
            )
            painter.drawText(
                QRect(text_left, rect.top() + 30, text_right - text_left, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                elided,
            )

        painter.setFont(self.font_time)
        painter.setPen(QColor(pal.text_faint))
        meta = format_relative(item.created_at)
        if item.pinned:
            meta = "已固定 · " + meta
        painter.drawText(
            QRect(rect.right() - 66, rect.top() + 10, 62, 20),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            meta,
        )
        painter.restore()
