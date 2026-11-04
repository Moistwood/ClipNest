"""界面冒烟测试：用 offscreen 平台把整个浮层渲染一遍，确保没有崩。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import Config  # noqa: E402
from core import hotkey  # noqa: E402
from core.models import KIND_IMAGE, KIND_TEXT, ClipItem  # noqa: E402
from core.repository import Repository  # noqa: E402
from ui.palette import PaletteWindow  # noqa: E402
from ui.theme import make_icon  # noqa: E402


class UiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = Repository(self.root / "history.db")

    def tearDown(self) -> None:
        self.repo.close()
        self._tmp.cleanup()

    def _seed(self, count: int = 20) -> None:
        for index in range(count):
            self.repo.add(
                ClipItem(
                    kind=KIND_TEXT,
                    text=f"第 {index} 条测试内容\n第二行用于预览",
                    preview=f"第 {index} 条测试内容",
                    content_hash=f"hash-{index}",
                )
            )

    def test_window_renders(self) -> None:
        self._seed()
        window = PaletteWindow(self.repo, Config())
        window.reload()
        window.show()
        self.app.processEvents()

        canvas = QPixmap(window.size())
        window.render(canvas)
        self.assertFalse(canvas.isNull())
        self.assertEqual(len(window._items), 20)
        window.close()

    def test_image_preview_renders(self) -> None:
        image = QImage(64, 48, QImage.Format.Format_ARGB32)
        image.fill(0xFF3366CC)
        blob = self.root / "shot.png"
        image.save(str(blob), "PNG")

        self.repo.add(
            ClipItem(
                kind=KIND_IMAGE,
                content_hash="img-1",
                preview="[图片 64×48]",
                image_path=str(blob),
                width=64,
                height=48,
            )
        )

        window = PaletteWindow(self.repo, Config())
        window.reload()
        window.show()
        self.app.processEvents()
        canvas = QPixmap(window.size())
        window.render(canvas)
        self.assertFalse(canvas.isNull())
        window.close()

    def test_icon_is_generated(self) -> None:
        self.assertFalse(make_icon(True).isNull())
        self.assertFalse(make_icon(False).isNull())

    def test_hotkey_parsing(self) -> None:
        modifiers, key = hotkey.parse_combo("Ctrl+Alt+V")
        self.assertEqual(modifiers, 0x0002 | 0x0001)
        self.assertEqual(key, ord("V"))

        with self.assertRaises(ValueError):
            hotkey.parse_combo("Ctrl")
        with self.assertRaises(ValueError):
            hotkey.parse_combo("Ctrl+Alt+NotAKey")


if __name__ == "__main__":
    unittest.main()
