"""坏库隔离：正常库不动、垃圾文件只改名不删除、不存在的库直接放行。"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.db_guard import ensure_healthy


class DbGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.db = self.root / "history.db"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_database_is_fine(self) -> None:
        self.assertEqual(ensure_healthy(self.db), "")

    def test_healthy_database_is_untouched(self) -> None:
        connection = sqlite3.connect(self.db)
        connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
        connection.commit()
        connection.close()

        self.assertEqual(ensure_healthy(self.db), "")
        self.assertTrue(self.db.exists())
        self.assertFalse((self.root / "broken").exists())

    def test_corrupt_database_is_isolated_not_deleted(self) -> None:
        garbage = b"this is not a sqlite database" * 200
        self.db.write_bytes(garbage)
        (self.root / "history.db-wal").write_bytes(b"wal-leftover")

        notice = ensure_healthy(self.db)
        self.assertIn("已移到", notice)
        self.assertFalse(self.db.exists())
        self.assertFalse((self.root / "history.db-wal").exists())

        saved = list((self.root / "broken").glob("history-*.db"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_bytes(), garbage)
        # 孤立的 -wal 可能被 SQLite 打开时自己清掉，这里只要求主文件原样保留
        self.assertFalse((self.root / "history.db-wal").exists())


if __name__ == "__main__":
    unittest.main()
