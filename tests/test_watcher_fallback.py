"""消息丢失兜底：只有序号变了且超过宽限期没消息时才补读。"""

from __future__ import annotations

import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.clipboard import MESSAGE_GRACE, ClipboardWatcher, message_lost  # noqa: E402


class WatcherFallbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _watcher(self) -> ClipboardWatcher:
        watcher = ClipboardWatcher(0)
        watcher._active = True  # 不真的挂系统监听，只验证轮询逻辑
        watcher._last_sequence = 1
        return watcher

    def test_message_lost_boundary(self) -> None:
        self.assertTrue(message_lost(0.0, MESSAGE_GRACE + 0.1))
        self.assertFalse(message_lost(0.0, MESSAGE_GRACE - 0.1))
        self.assertFalse(message_lost(10.0, 10.0))

    def test_recovers_when_message_missing(self) -> None:
        watcher = self._watcher()
        watcher._last_message_at = time.monotonic() - 5
        with (
            patch.object(watcher, "_sequence", return_value=2),
            patch.object(watcher, "_on_update") as on_update,
        ):
            watcher._poll_once()
        on_update.assert_called_once()

    def test_skips_when_message_arrived(self) -> None:
        watcher = self._watcher()
        watcher._last_message_at = time.monotonic()
        with (
            patch.object(watcher, "_sequence", return_value=2),
            patch.object(watcher, "_on_update") as on_update,
        ):
            watcher._poll_once()
        on_update.assert_not_called()

    def test_skips_when_sequence_unchanged(self) -> None:
        watcher = self._watcher()
        watcher._last_message_at = time.monotonic() - 5
        with (
            patch.object(watcher, "_sequence", return_value=1),
            patch.object(watcher, "_on_update") as on_update,
        ):
            watcher._poll_once()
        on_update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
