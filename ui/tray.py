"""托盘。图标状态要能一眼看出「在记」还是「暂停了」。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from app import paths
from ui import theme


class TrayIcon(QSystemTrayIcon):
    show_requested = Signal()
    settings_requested = Signal()
    pause_toggled = Signal(bool)
    clear_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(theme.make_icon(True), parent)
        self.setToolTip(f"{paths.APP_NAME} · 正在记录")

        self._menu = QMenu()
        self._open_action = QAction("显示历史", self._menu)
        self._settings_action = QAction("设置…", self._menu)
        self._pause_action = QAction("暂停记录", self._menu)
        self._pause_action.setCheckable(True)
        self._clear_action = QAction("清空历史", self._menu)
        self._quit_action = QAction("退出", self._menu)

        self._menu.addAction(self._open_action)
        self._menu.addAction(self._settings_action)
        self._menu.addSeparator()
        self._menu.addAction(self._pause_action)
        self._menu.addAction(self._clear_action)
        self._menu.addSeparator()
        self._menu.addAction(self._quit_action)
        self.setContextMenu(self._menu)

        self._open_action.triggered.connect(self.show_requested.emit)
        self._settings_action.triggered.connect(self.settings_requested.emit)
        self._pause_action.toggled.connect(self.pause_toggled.emit)
        self._clear_action.triggered.connect(self.clear_requested.emit)
        self._quit_action.triggered.connect(self.quit_requested.emit)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_requested.emit()

    def set_paused(self, paused: bool) -> None:
        self._pause_action.blockSignals(True)
        self._pause_action.setChecked(paused)
        self._pause_action.blockSignals(False)
        self.setIcon(theme.make_icon(not paused))
        self.setToolTip(f"{paths.APP_NAME} · " + ("已暂停" if paused else "正在记录"))
