"""居中浮层主窗口：搜索框 + 列表 + 预览。"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QGuiApplication, QPainter, QPainterPath, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QPushButton,
    QSizeGrip,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import paths
from app.config import Config
from core import paster, win32
from core.models import KIND_FILES, KIND_TEXT, MAX_NOTE_CHARS, ClipItem
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
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                self.nav.emit("copy")
            elif modifiers & Qt.KeyboardModifier.ShiftModifier:
                self.nav.emit("paste_plain")
            else:
                self.nav.emit("paste")
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
    # 面板自己不写配置，尺寸改动交给主进程统一保存
    size_changed = Signal(int, int)

    def __init__(self, repo: Repository, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._config = config
        self._prev_hwnd = 0
        self._items: list[ClipItem] = []
        self._shown_at = 0.0
        self._favorites_only = False
        # 右键菜单和备注输入框会成为新的前台窗口，这段时间内别把自己收起
        self._modal_open = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(560, 380)
        self.resize(config.window_width, config.window_height)

        # 置顶窗口必须自己负责消失。焦点在搜索框这类子控件上，
        # 父窗口收不到失焦事件，所以除了 changeEvent 还要轮询前台进程兜底。
        self._focus_watch = QTimer(self)
        self._focus_watch.setInterval(250)
        self._focus_watch.timeout.connect(self._drop_if_inactive)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(60)
        self._search_timer.timeout.connect(self.reload)

        # 拖拽时会连发一堆 resizeEvent，停手 350ms 再写配置
        self._size_timer = QTimer(self)
        self._size_timer.setSingleShot(True)
        self._size_timer.setInterval(350)
        self._size_timer.timeout.connect(self._emit_size)

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
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)

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
            "↑↓ 选择 · Enter 粘贴 · Shift+Enter 纯文本 · Ctrl+Enter 仅复制 · Ctrl+P 收藏 · Del 删除 · Esc 关闭",
            self._card,
        )
        self._footer.setFont(theme.font(8))
        self._footer.setStyleSheet(f"color: {pal.text_faint};")
        footer_row = QHBoxLayout()
        footer_row.setSpacing(6)
        footer_row.addWidget(self._footer, 1)
        footer_row.addWidget(
            QSizeGrip(self._card), 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight
        )
        layout.addLayout(footer_row)

    def _build_filters(self, pal) -> QWidget:
        bar = QWidget(self._card)
        row = QHBoxLayout(bar)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(4)

        self._filter_bar = bar
        self._kind_filter = ""
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)

        options = (
            ("全部", ""),
            ("★ 收藏", "favorites"),
            ("文本", "text"),
            ("图片", "image"),
            ("文件", "files"),
        )
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
        value = str(button.property("kind") or "") if button else ""
        self._favorites_only = value == "favorites"
        self._kind_filter = "" if self._favorites_only else value
        self.reload()

    # ---------- 数据 ----------

    def reload(self) -> None:
        query = self._search.text().strip()
        self._items = self._repo.list(
            query=query,
            kind=self._kind_filter,
            limit=self._config.max_items,
            favorites_only=self._favorites_only,
        )
        self._model.clear()
        for item in self._items:
            row = QStandardItem()
            row.setData(item, ITEM_ROLE)
            row.setEditable(False)
            self._model.appendRow(row)

        if self._favorites_only:
            empty_text = (
                "没有匹配的收藏项。" if query else "收藏夹还是空的。选中一条按 Ctrl+P 加入。"
            )
        elif query or self._kind_filter:
            empty_text = "没有匹配的记录。"
        else:
            empty_text = "还没有记录。复制点什么试试。"
        self._empty.setText(empty_text)
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

    def _toggle_favorite(self, item: ClipItem) -> None:
        self._repo.toggle_pin(item.id)
        self.reload()

    def _delete_item(self, item: ClipItem) -> None:
        blob = self._repo.delete(item.id)
        paths.remove_blob(blob)
        self.reload()

    def _edit_note(self, item: ClipItem) -> None:
        self._modal_open = True
        try:
            text, accepted = QInputDialog.getText(
                self,
                "备注",
                "给这条内容起个名字或写句备注（留空即清除）：",
                QLineEdit.EchoMode.Normal,
                item.note,
            )
        finally:
            self._modal_open = False
            self._shown_at = time.monotonic()
            self.activateWindow()
            self._search.setFocus()
        if accepted:
            self._repo.set_note(item.id, text.strip()[:MAX_NOTE_CHARS])
            self.reload()

    def _open_path(self, target: Path) -> None:
        if target.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _build_context_menu(self, item: ClipItem) -> QMenu:
        """单独留出来，界面测试可以只检查菜单项，不必真的弹出菜单。"""
        menu = QMenu(self)
        menu.addAction("粘贴", lambda: self._commit(False))
        menu.addAction("粘贴为纯文本", lambda: self._commit(False, True))
        menu.addAction("仅复制", lambda: self._commit(True))
        if item.kind == KIND_TEXT:
            menu.addAction("复制为纯文本", lambda: self._commit(True, True))
        menu.addSeparator()
        menu.addAction(
            "移出收藏" if item.pinned else "加入收藏",
            lambda: self._toggle_favorite(item),
        )
        menu.addAction("编辑备注…", lambda: self._edit_note(item))
        if item.kind == KIND_FILES and item.files:
            first = Path(item.files[0])
            if first.exists():
                menu.addSeparator()
                menu.addAction("打开文件", lambda: self._open_path(first))
                menu.addAction("打开所在文件夹", lambda: self._open_path(first.parent))
        menu.addSeparator()
        menu.addAction("删除", lambda: self._delete_item(item))
        return menu

    def _on_context_menu(self, pos: QPoint) -> None:
        index = self._list.indexAt(pos)
        if not index.isValid():
            return
        self._list.setCurrentIndex(index)
        item = index.data(ITEM_ROLE)
        if item is None:
            return

        menu = self._build_context_menu(item)
        self._modal_open = True
        try:
            menu.exec(self._list.viewport().mapToGlobal(pos))
        finally:
            self._modal_open = False
            self._shown_at = time.monotonic()
            self.activateWindow()
            self._search.setFocus()

    def _on_nav(self, action: str) -> None:
        if action == "escape":
            self.hide()
        elif action == "paste":
            self._commit(only_copy=False)
        elif action == "paste_plain":
            self._commit(only_copy=False, plain=True)
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

    def _commit(self, only_copy: bool, plain: bool = False) -> None:
        item = self._selected()
        if item is None:
            return
        target = self._prev_hwnd
        self.hide()
        if target:
            win32.user32.SetForegroundWindow(target)
        QTimer.singleShot(70, lambda: self._deliver(item, only_copy, plain))

    def _deliver(self, item: ClipItem, only_copy: bool, plain: bool = False) -> None:
        ok = (
            paster.copy_to_clipboard(item, plain=plain)
            if only_copy
            else paster.paste(item, plain=plain)
        )
        if ok:
            self._repo.touch(item.id)
            self.pasted.emit(item)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt 接口)
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.hide()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._commit(only_copy=False, plain=shift)
            return
        if key == Qt.Key.Key_Delete:
            item = self._selected()
            if item:
                self._delete_item(item)
            return
        if key == Qt.Key.Key_P and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            item = self._selected()
            if item:
                self._toggle_favorite(item)
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
        if not self.isVisible() or self._modal_open:
            return
        if time.monotonic() - self._shown_at < 0.3:
            return
        if not self._holds_foreground():
            self.hide()

    def _maybe_hide(self) -> None:
        if not self.isVisible() or self._modal_open:
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
        # 放大过之后别把面板推到屏幕外面去
        width = min(self.width(), area.width() - 24)
        height = min(self.height(), area.height() - 24)
        x = area.center().x() - width // 2
        y = area.top() + int(area.height() * 0.18)
        x = max(area.left() + 8, min(x, area.right() - width - 7))
        y = max(area.top() + 8, min(y, area.bottom() - height - 7))
        self.move(QPoint(x, y))

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

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt 接口)
        super().resizeEvent(event)
        if self.isVisible():
            self._size_timer.start()

    def _emit_size(self) -> None:
        self.size_changed.emit(self.width(), self.height())
