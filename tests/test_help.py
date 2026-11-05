"""首次引导与托盘使用说明。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import Config  # noqa: E402
from app.help_text import help_text  # noqa: E402
from ui.tray import TrayIcon  # noqa: E402


class HelpTextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_shortcuts_are_listed(self) -> None:
        text = help_text("Ctrl+Alt+V", "C:/Users/demo/AppData/Roaming/ClipNest", "1.1.0")
        for token in (
            "Ctrl+Alt+V",
            "Shift+Enter",
            "Ctrl+Enter",
            "Ctrl+P",
            "加入/移出收藏",
            "C:/Users/demo/AppData/Roaming/ClipNest",
            "1.1.0",
        ):
            self.assertIn(token, text)

    def test_tray_menu_has_help(self) -> None:
        tray = TrayIcon()
        labels = [action.text() for action in tray.contextMenu().actions()]
        self.assertIn("使用说明…", labels)

    def test_first_run_hint_defaults_to_off(self) -> None:
        self.assertFalse(Config().hinted_first_run)


if __name__ == "__main__":
    unittest.main()
