"""自定义来源黑名单：文本解析、匹配、配置读写。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import paths
from app.config import Config
from core.filters import is_blocked_app, parse_blocked_apps


class BlockedAppsTest(unittest.TestCase):
    def test_parse_mixed_separators(self) -> None:
        text = "WeChat.exe, bank.exe; foo.exe，bar.exe\nfoo.exe"
        self.assertEqual(
            parse_blocked_apps(text),
            ["wechat.exe", "bank.exe", "foo.exe", "bar.exe"],
        )
        self.assertEqual(parse_blocked_apps("  , , "), [])

    def test_matching(self) -> None:
        self.assertTrue(is_blocked_app("KeePass.exe"))  # 内置名单
        self.assertTrue(is_blocked_app("WeChat.exe", ["wechat.exe"]))
        self.assertTrue(is_blocked_app(" wechat.EXE ", ["WECHAT.exe"]))
        self.assertFalse(is_blocked_app("chrome.exe", ["wechat.exe"]))
        self.assertFalse(is_blocked_app("", ["wechat.exe"]))

    def test_config_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "config.json"
            with patch.object(paths, "config_path", return_value=target):
                config = Config.load()
                config.blocked_apps = ["wechat.exe", "bank.exe"]
                config.save()
                self.assertEqual(Config.load().blocked_apps, ["wechat.exe", "bank.exe"])

    def test_bad_config_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "config.json"
            target.write_text(
                json.dumps({"blocked_apps": ["a.exe", 3, None], "max_items": "bad"}),
                encoding="utf-8",
            )
            with patch.object(paths, "config_path", return_value=target):
                config = Config.load()
            self.assertEqual(config.blocked_apps, ["a.exe"])
            self.assertEqual(config.max_items, 500)


if __name__ == "__main__":
    unittest.main()
