"""系统剪贴板开关探测的单元测试，用打桩代替真实注册表。"""

from __future__ import annotations

import unittest
import winreg
from unittest import mock

from app import system_probe


class NativeHistoryProbeTest(unittest.TestCase):
    def test_missing_key_counts_as_off(self) -> None:
        with mock.patch.object(winreg, "OpenKey", side_effect=FileNotFoundError):
            self.assertIs(system_probe.native_history_enabled(), False)

    def test_access_denied_returns_unknown(self) -> None:
        with mock.patch.object(winreg, "OpenKey", side_effect=PermissionError("拒绝")):
            self.assertIsNone(system_probe.native_history_enabled())

    def test_zero_value_counts_as_off(self) -> None:
        key = mock.MagicMock()
        key.__enter__.return_value = key
        with mock.patch.object(winreg, "OpenKey", return_value=key), mock.patch.object(
            winreg, "QueryValueEx", return_value=(0, winreg.REG_DWORD)
        ):
            self.assertIs(system_probe.native_history_enabled(), False)

    def test_one_value_counts_as_on(self) -> None:
        key = mock.MagicMock()
        key.__enter__.return_value = key
        with mock.patch.object(winreg, "OpenKey", return_value=key), mock.patch.object(
            winreg, "QueryValueEx", return_value=(1, winreg.REG_DWORD)
        ):
            self.assertIs(system_probe.native_history_enabled(), True)


if __name__ == "__main__":
    unittest.main()
