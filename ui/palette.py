"""居中浮层主窗口：搜索框 + 列表 + 预览。"""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPainterPath, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import paths
from app.config import Config
from core import paster, win32
from core.models import ClipItem
from core.repository import Repository
from ui import theme
from ui.item_delegate import ITEM_ROLE, ROW_HEIGHT, ClipDelegate
from ui.preview import PreviewPane

SHADOW_MARGIN = 16


class SearchBox(QLineEdit):
    nav = Signal(str)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt 接口)
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_Escape:
            self.nav.emit("escape")
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
            self.nav.emit("copy" if control else "paste")
            return
        if key == Qt.Key.Key_Down:
            self.nav.emit("down")
            return
        if key == Qt.Key.Key_Up:
            self.nav.emit("up")
            return
        if modifiers & Qt.KeyboardModifier.ControlModifier and Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            self.nav.emit(f"quick:{key - Qt.Key.Key_0}")
            return
        super().keyPressEvent(event)


class Card(QWidget):
    """带圆角和阴影的底板。窗口本身是透明的，圆角靠这里画。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pal = theme.current()

    def refresh_palette(self) -> None:
        self.pal = theme.current()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt 接口)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(0, 0, -1, -1), 12, 12)
        painter.fillPath(path, QColor(self.pal.panel))
        pen_color = QColor(self.pal.panel_border)
        painter.setPen(pen_color)
        painter.drawPath(path)


class PaletteWindow(QWidget):
    pasted = Signal(object)

    def __init__(self, repo: Repository, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._config = config
        self._prev_hwnd = 0
        self._items: list[ClipItem] = []
        self._shown_at = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(config.window_width, config.window_height)

        # 置顶窗口必须自己负责消失。焦点在搜索框这类子控件上，
        # 父窗口收不到失焦事件，所以除了 changeEvent 还要轮询前台进程兜底。
        self._focus_watch = QTimer(self)
        self._focus_watch.setInterval(250)
        self._focus_watch.timeout.connect(self._drop_if_inactive)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(60)
        self._search_timer.timeout.connect(self.reload)

        self._build()

    # ---------- 界面搭建 ----------

    def _build(self) -> None:
        pal = theme.current()
        root = QVBoxLayout(self)
        root.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        root.setSpacing(0)

        self._card = Card(self)
        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 90))
        self._card.setGraphicsEffect(shadow)
        root.addWidget(self._card)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(10)

        self._search = SearchBox(self._card)
        self._search.setPlaceholderText("搜索剪贴板历史")
        self._search.setFont(theme.font(11))
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: {pal.search_bg}; border: none; border-radius: 8px;"
            f" padding: 9px 12px; color: {pal.text}; }}"
        )
        self._search.textChanged.connect(self._search_timer.start)
        self._search.nav.connect(self._on_nav)
        layout.addWidget(self._search)
        layout.addWidget(self._build_filters(pal))

        body = QHBoxLayout()
        body.setSpacing(12)

        self._model = QStandardItemModel(self)
        self._list = QListView(self._card)
        self._list.setModel(self._model)
        self._delegate = ClipDelegate(self._list)
        self._list.setItemDelegate(self._delegate)
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setStyleSheet(
            "QListView { background: transparent; border: none; outline: 0; }"
        )
        self._list.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._list.setMouseTracking(True)
        self._list.selectionModel().currentChanged.connect(self._on_current_changed)
        self._list.clicked.connect(lambda _index: self._commit(only_copy=False))

        self._empty = QLabel("还没有记录。复制点什么试试。", self._card)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setFont(theme.font(10))
        self._empty.setStyleSheet(f"color: {pal.text_faint};")

        self._stack = QStackedWidget(self._card)
        self._stack.addWidget(self._list)
        self._stack.addWidget(self._empty)
        body.addWidget(self._stack, 5)

        divider = QFrame(self._card)
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet(f"color: {pal.divider};")
        body.addWidget(divider)

        self._preview = PreviewPane(self._card)
        body.addWidget(self._preview, 4)

        layout.addLayout(body, 1)

        self._footer = QLabel(
            "↑↓ 选择 · Enter 粘贴 · Ctrl+Enter 仅复制 · Ctrl+P 固定 · Del 删除 · Esc 关闭",
            self._card,
        )
        self._footer.setFont(theme.font(8))
        self._footer.setStyleSheet(f"color: {pal.text_faint};")
        layout.addWidget(self._footer)

    def _build_filters(self, pal) -> QWidget:
        bar = QWidget(self._card)
        row = QHBoxLayout(bar)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(4)

        self._filter_bar = bar
        self._kind_filter = ""
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)

        options = (("全部", ""), ("文本", "text"), ("图片", "image"), ("文件", "files"))
        for index, (label, kind) in enumerate(options):
            button = QPushButton(label, bar)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("kind", kind)
            if index == 0:
                button.setChecked(True)
            self._filter_group.addButton(button, index)
            row.addWidget(button)
        row.addStretch(1)

        bar.setStyleSheet(self._filter_style(pal))
        self._filter_group.idClicked.connect(self._on_filter_changed)
        return bar

    def _filter_style(self, pal) -> str:
        return (
            f"QPushButton {{ background: transparent; color: {pal.text_faint};"
            f" border: none; padding: 3px 11px; border-radius: 9px; font-size: 11px; }}"
            f"QPushButton:hover {{ color: {pal.text}; }}"
            f"QPushButton:checked {{ background: {pal.search_bg}; color: {pal.text}; }}"
        )

    def _on_filter_changed(self, button_id: int) -> None:
        button = self._filter_group.button(button_id)
        self._kind_filter = str(button.property("kind") or "") if button else ""
        self.reload()

    # ---------- 数据 ----------

    def reload(self) -> None:
        query = self._search.text().strip()
        self._items = self._repo.list(
            query=query, kind=self._kind_filter, limit=self._config.max_items
        )
        self._model.clear()
        for item in self._items:
            row = QStandardItem()
            row.setData(item, ITEM_ROLE)
            row.setEditable(False)
            self._model.appendRow(row)

        self._empty.setText(
            "没有匹配的记录。" if (query or self._kind_filter) else "还没有记录。复制点什么试试。"
        )
        self._stack.setCurrentWidget(self._list if self._items else self._empty)
        if self._items:
            self._list.setCurrentIndex(self._model.index(0, 0))
        else:
            self._preview.show_item(None)

    def _on_current_changed(self, current, _previous) -> None:
        if not current.isValid():
            self._preview.show_item(None)
            return
        item = current.data(ITEM_ROLE)
        self._preview.show_item(item)

    def _selected(self) -> ClipItem | None:
        index = self._list.currentIndex()
        if not index.isValid():
            return None
        return index.data(ITEM_ROLE)

    # ---------- 交互 ----------

    def _on_nav(self, action: str) -> None:
        if action == "escape":
            self.hide()
        elif action == "paste":
            self._commit(only_copy=False)
        elif action == "copy":
            self._commit(only_copy=True)
        elif action in ("up", "down"):
            self._move_selection(-1 if action == "up" else 1)
        elif action.startswith("quick:"):
            self._quick_pick(int(action.split(":", 1)[1]))

    def _move_selection(self, delta: int) -> None:
        if not self._items:
            return
        row = self._list.currentIndex().row()
        target = max(0, min(len(self._items) - 1, row + delta))
        self._list.setCurrentIndex(self._model.index(target, 0))
        self._list.scrollTo(self._model.index(target, 0))

    def _quick_pick(self, position: int) -> None:
        if 0 < position <= len(self._items):
            self._list.setCurrentIndex(self._model.index(position - 1, 0))
            self._commit(only_copy=False)

    def _commit(self, only_copy: bool) -> None:
        item = self._selected()
        if item is None:
            return
        target = self._prev_hwnd
        self.hide()
        if target:
            win32.user32.SetForegroundWindow(target)
        QTimer.singleShot(70, lambda: self._deliver(item, only_copy))

    def _deliver(self, item: ClipItem, only_copy: bool) -> None:
        ok = paster.copy_to_clipboard(item) if only_copy else paster.paste(item)
        if ok:
            self._repo.touch(item.id)
            self.pasted.emit(item)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt 接口)
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.hide()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._commit(only_copy=False)
            return
        if key == Qt.Key.Key_Delete:
            item = self._selected()
            if item:
                blob = self._repo.delete(item.id)
                paths.remove_blob(blob)
                self.reload()
            return
        if key == Qt.Key.Key_P and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            item = self._selected()
            if item:
                self._repo.toggle_pin(item.id)
                self.reload()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802 (Qt 接口)
        super().focusOutEvent(event)
        QTimer.singleShot(140, self._maybe_hide)

    def changeEvent(self, event) -> None:  # noqa: N802 (Qt 接口)
        # 窗口从激活变成不激活，说明用户点了别处，这是最直接的信号
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            QTimer.singleShot(140, self._maybe_hide)
        super().changeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt 接口)
        super().showEvent(event)
        self._shown_at = time.monotonic()
        self._focus_watch.start()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt 接口)
        self._focus_watch.stop()
        super().hideEvent(event)

    def _holds_foreground(self) -> bool:
        """前台窗口是不是自己。

        比自己进程 ID 更严格：设置对话框、提示框也属于本进程，
        但那时候面板应该让位。
        """
        return win32.foreground_window() == int(self.winId())

    def _drop_if_inactive(self) -> None:
        """前台换成别的窗口就收起面板。

        刚弹出的前一瞬 activateWindow 还在路上，给 300ms 宽限期，
        否则会在显示的同时把自己关掉。
        """
        if not self.isVisible():
            return
        if time.monotonic() - self._shown_at < 0.3:
            return
        if not self._holds_foreground():
            self.hide()

    def _maybe_hide(self) -> None:
        if not self.isVisible():
            return
        if self._holds_foreground():
            return
        self.hide()

    # ---------- 显示 ----------

    def popup(self) -> None:
        self._prev_hwnd = win32.user32.GetForegroundWindow()
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)
        self.reload()
        self._place()
        self.show()
        self.raise_()
        self.activateWindow()
        self._search.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _place(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = area.center().x() - self.width() // 2
        y = area.top() + int(area.height() * 0.18)
        self.move(QPoint(max(area.left(), x), max(area.top(), y)))

    def refresh_theme(self) -> None:
        self._delegate.refresh_palette()
        self._preview.refresh_palette()
        self._card.refresh_palette()
        pal = theme.current()
        self._search.setStyleSheet(
            f"QLineEdit {{ background: {pal.search_bg}; border: none; border-radius: 8px;"
            f" padding: 9px 12px; color: {pal.text}; }}"
        )
        self._empty.setStyleSheet(f"color: {pal.text_faint};")
        self._footer.setStyleSheet(f"color: {pal.text_faint};")
        self._filter_bar.setStyleSheet(self._filter_style(pal))
        self._list.viewport().update()
