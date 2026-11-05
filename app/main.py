"""进程装配：单实例、托盘、热键、剪贴板监听之间只有这里连线。"""

from __future__ import annotations

import faulthandler
import sys
import time
from dataclasses import fields

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QSystemTrayIcon, QWidget

from app import autostart, paths, system_probe
from app.config import Config
from app.help_text import help_text
from app.single_instance import SingleInstance
from core import db_guard, filters, thumbnails
from core.clipboard import ClipboardWatcher
from core.hotkey import HotkeyManager
from core.models import KIND_TEXT, ClipItem
from core.repository import Repository
from core.stats import collect as collect_stats
from core.storage_worker import StorageService
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
        # 坏库先隔离再建连接，否则初始化阶段就会抛异常，托盘都出不来
        self._startup_notice = db_guard.ensure_healthy(paths.db_path())
        self.repo = Repository(paths.db_path())
        # 两个独立连接：主线程只读，工作线程负责落盘和写入
        self.storage = StorageService(paths.db_path())

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
        self.storage.saved.connect(self._on_stored)
        self.storage.failed.connect(self._on_storage_failed)
        self.hotkey.activated.connect(self.palette.popup)
        self.palette.size_changed.connect(self._on_size_changed)

        self.tray.show_requested.connect(self.palette.popup)
        self.tray.settings_requested.connect(self._open_settings)
        self.tray.stats_requested.connect(self._open_stats)
        self.tray.help_requested.connect(self._open_help)
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

        if self._startup_notice:
            self._notify(
                "历史库已重置", self._startup_notice, QSystemTrayIcon.MessageIcon.Information
            )
            self._log(self._startup_notice)

        self.watcher.set_enabled(not self.config.paused)

        if not self.hotkey.register(self.config.hotkey):
            self._warn_hotkey(self.config.hotkey)
        else:
            self.tray.setToolTip(f"{paths.APP_NAME} · 正在记录 · {self.config.hotkey}")

        self._prune()
        # 换过安装目录之后注册表里的旧路径会失效，启动时顺手校正
        autostart.repair()
        thumbnails.prune(paths.thumbs_dir(), 30)

        # 托盘刚挂上去时还没准备好接通知，延后一点再说
        QTimer.singleShot(1500, self._hint_on_first_run)

    # ---------- 事件 ----------

    def _on_capture(self, item: ClipItem) -> None:
        if self.config.paused:
            return
        if filters.is_blocked_app(item.source_app, self.config.blocked_apps):
            return
        if (
            self.config.strict_secret_filter
            and item.kind == KIND_TEXT
            and filters.looks_like_secret(item.text)
        ):
            return
        # 大图的落盘和 SQLite 事务都交给工作线程，这里立刻回到事件循环
        self.storage.save(item)

    def _on_size_changed(self, width: int, height: int) -> None:
        self.config.window_width = width
        self.config.window_height = height
        self.config.save()

    def _on_stored(self, _item: ClipItem) -> None:
        self._prune()
        if self.palette.isVisible():
            self.palette.reload()

    def _on_storage_failed(self, message: str) -> None:
        self._notify("有一条记录没保存下来", message)

    def _prune(self) -> None:
        for blob in self.repo.prune(self.config.max_items, self.config.max_days):
            paths.remove_blob(blob)

    def _on_pause(self, paused: bool) -> None:
        self.config.paused = paused
        self.config.save()
        self.watcher.set_enabled(not paused)
        self.tray.set_paused(paused)

    def _on_clear(self) -> None:
        box = QMessageBox(
            QMessageBox.Icon.Question,
            "清空历史",
            "确定清空历史记录吗？\n已固定的条目会保留，其余记录会被删除，不能撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        box.button(QMessageBox.StandardButton.Yes).setText("清空")
        box.button(QMessageBox.StandardButton.No).setText("取消")
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
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

    def _log(self, message: str) -> None:
        try:
            with open(paths.log_path(), "a", encoding="utf-8") as handle:
                handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except OSError:
            pass

    def _notify(
        self,
        title: str,
        message: str,
        level: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Warning,
    ) -> None:
        if QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(title, message, level, 6000)

    def _hint_on_first_run(self) -> None:
        """第一次运行说明热键和入口；看过一次就写进配置，不再打扰。"""
        if self.config.hinted_first_run:
            return
        self.config.hinted_first_run = True
        self.config.save()

        lines = [
            f"已开始记录。按 {self.config.hotkey} 呼出历史面板，"
            "托盘菜单里有「使用说明…」和设置。"
        ]
        if system_probe.native_history_enabled() is False:
            lines.append("系统 Win+V 历史当前是关闭的，两者互不影响。")
        self._notify(
            f"{paths.APP_NAME} 已就绪",
            "\n".join(lines),
            QSystemTrayIcon.MessageIcon.Information,
        )

    def _open_help(self) -> None:
        QMessageBox.information(
            None,
            f"{paths.APP_NAME} 使用说明",
            help_text(self.config.hotkey, str(paths.data_dir()), paths.APP_VERSION),
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
        self.storage.shutdown()
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
