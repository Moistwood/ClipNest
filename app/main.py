"""进程装配：单实例、托盘、热键、剪贴板监听之间只有这里连线。"""

from __future__ import annotations

import faulthandler
import sys
from dataclasses import fields

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication, QDialog, QSystemTrayIcon, QWidget

from app import autostart, paths
from app.config import Config
from app.single_instance import SingleInstance
from core import filters
from core.clipboard import ClipboardWatcher
from core.hotkey import HotkeyManager
from core.models import KIND_IMAGE, KIND_TEXT, ClipItem
from core.repository import Repository
from core.stats import collect as collect_stats
from ui import theme
from ui.palette import PaletteWindow
from ui.settings_dialog import SettingsDialog
from ui.stats_dialog import StatsDialog
from ui.tray import TrayIcon


class Application:
    def __init__(self, config: Config) -> None:
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName(paths.APP_NAME)
        self.app.setApplicationDisplayName(paths.APP_NAME)
        self.app.setWindowIcon(theme.make_icon(True))

        self.config = config
        self.repo = Repository(paths.db_path())

        self.host = QWidget()
        self.host.setWindowFlags(Qt.WindowType.Tool)
        self.host.hide()
        self.hwnd = int(self.host.winId())

        self.palette = PaletteWindow(self.repo, config)
        self.tray = TrayIcon()
        self.watcher = ClipboardWatcher(self.hwnd)
        self.hotkey = HotkeyManager(self.hwnd, config.hotkey)

        self._wire()
        self._start()

    # ---------- 连线 ----------

    def _wire(self) -> None:
        self.watcher.captured.connect(self._on_capture)
        self.hotkey.activated.connect(self.palette.popup)

        self.tray.show_requested.connect(self.palette.popup)
        self.tray.settings_requested.connect(self._open_settings)
        self.tray.stats_requested.connect(self._open_stats)
        self.tray.pause_toggled.connect(self._on_pause)
        self.tray.clear_requested.connect(self._on_clear)
        self.tray.quit_requested.connect(self._on_quit)

        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._on_color_scheme)

        self.app.aboutToQuit.connect(self._shutdown)

    def _start(self) -> None:
        if not self.tray.isSystemTrayAvailable():
            self.app.setQuitOnLastWindowClosed(True)

        self.tray.set_paused(self.config.paused)
        self.tray.show()

        self.watcher.set_enabled(not self.config.paused)

        if not self.hotkey.register(self.config.hotkey):
            self._warn_hotkey(self.config.hotkey)
        else:
            self.tray.setToolTip(f"{paths.APP_NAME} · 正在记录 · {self.config.hotkey}")

        self._prune()
        # 换过安装目录之后注册表里的旧路径会失效，启动时顺手校正
        autostart.repair()

    # ---------- 事件 ----------

    def _on_capture(self, item: ClipItem) -> None:
        if self.config.paused:
            return
        if (
            self.config.strict_secret_filter
            and item.kind == KIND_TEXT
            and filters.looks_like_secret(item.text)
        ):
            return

        if item.kind == KIND_IMAGE and item.image_bytes:
            item.image_path = str(paths.save_blob(item.image_bytes, item.content_hash))
            item.image_bytes = None

        item.id = self.repo.add(item)
        self._prune()

    def _prune(self) -> None:
        for blob in self.repo.prune(self.config.max_items, self.config.max_days):
            paths.remove_blob(blob)

    def _on_pause(self, paused: bool) -> None:
        self.config.paused = paused
        self.config.save()
        self.watcher.set_enabled(not paused)
        self.tray.set_paused(paused)

    def _on_clear(self) -> None:
        for blob in self.repo.clear(keep_pinned=True):
            paths.remove_blob(blob)
        if self.palette.isVisible():
            self.palette.reload()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self.repo)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            # 导入在对话框里就写库了，取消也得让面板看到新数据
            if self.palette.isVisible():
                self.palette.reload()
            return

        changed = dialog.accepted_changes()
        incoming = dialog.result_config()

        if "hotkey" in changed:
            combo = str(changed["hotkey"])
            if not self.hotkey.register(combo):
                self.hotkey.register(self.config.hotkey)
                incoming.hotkey = self.config.hotkey
                self._warn_hotkey(combo)
            else:
                self.tray.setToolTip(f"{paths.APP_NAME} · 正在记录 · {combo}")

        if "autostart" in changed and not autostart.set_enabled(bool(changed["autostart"])):
            self._notify("开机自启设置失败", "写入注册表被拒绝，可以换用安装版再试。")

        # 原地覆盖，浮层和托盘持有的还是同一个 Config 对象
        for field in fields(Config):
            setattr(self.config, field.name, getattr(incoming, field.name))
        self.config.save()

        if changed.get("prune"):
            self._prune()
        if self.palette.isVisible():
            self.palette.reload()

    def _open_stats(self) -> None:
        StatsDialog(collect_stats(self.repo)).exec()

    def _on_color_scheme(self, _scheme) -> None:
        self.palette.refresh_theme()
        self.tray.setIcon(theme.make_icon(not self.config.paused))

    def _notify(self, title: str, message: str) -> None:
        if QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(
                title, message, QSystemTrayIcon.MessageIcon.Warning, 6000
            )

    def _warn_hotkey(self, combo: str) -> None:
        self.tray.setToolTip(f"{paths.APP_NAME} · 热键 {combo} 注册失败")
        self._notify(
            "热键被占用",
            f"{combo} 已被其他程序占用，请修改配置后重启。\n"
            f"配置文件：{paths.config_path()}",
        )

    def _drain_and_show(self, server: QLocalServer) -> None:
        """第二个实例只是来敲门，把管道读干净再弹面板。"""
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()
            if connection is not None:
                connection.disconnected.connect(connection.deleteLater)
        self.palette.popup()

    def _on_quit(self) -> None:
        self.app.quit()

    def _shutdown(self) -> None:
        self.watcher.stop()
        self.hotkey.unregister()
        self.repo.close()

    def run(self) -> int:
        return self.app.exec()


def main() -> int:
    try:
        faulthandler.enable(open(paths.log_path(), "a", encoding="utf-8"))
    except OSError:
        pass

    # QLocalSocket 依赖事件循环，必须先有 QApplication 再判断单实例
    qt_app = QApplication.instance() or QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)

    instance = SingleInstance()
    if instance.is_running():
        return 0
    instance.listen()

    config = Config.load()
    application = Application(config)

    server: QLocalServer | None = instance.take_server()
    if server is not None:
        server.newConnection.connect(lambda: application._drain_and_show(server))

    return application.run()
