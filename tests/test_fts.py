"""全文检索：trigram 索引、短查询降级、触发器同步。"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.models import KIND_TEXT, ClipItem
from core.repository import SCHEMA, Repository

FTS_AVAILABLE = sqlite3.sqlite_version_info >= (3, 34, 0)


def text_item(body: str, key: str | None = None) -> ClipItem:
    return ClipItem(
        kind=KIND_TEXT,
        content_hash=key or body,
        text=body,
        preview=body,
        size=len(body.encode("utf-16-le")),
    )


class FtsSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self._dir.name) / "search.db")
        for body in (
            "复制配置项的内容",
            "服务器配置文件路径",
            "hello world 配置",
            "完成度 100%",
        ):
            self.repo.add(text_item(body))

    def tearDown(self) -> None:
        self.repo.close()
        self._dir.cleanup()

    @unittest.skipUnless(FTS_AVAILABLE, "SQLite 版本低于 3.34，没有 trigram")
    def test_fts_ready(self) -> None:
        self.assertTrue(self.repo._fts_ready)

    def test_two_chars_still_findable(self) -> None:
        # trigram 对两字查询必然返回 0 条，这里必须靠 LIKE 兜住
        hits = self.repo.list(query="配置")
        self.assertEqual(len(hits), 3)

    def test_three_chars_findable(self) -> None:
        hits = self.repo.list(query="配置项")
        self.assertEqual(len(hits), 1)
        self.assertIn("配置项", hits[0].text)

    def test_latin_query(self) -> None:
        self.assertEqual(len(self.repo.list(query="hello")), 1)

    def test_wildcard_is_literal(self) -> None:
        hits = self.repo.list(query="100%")
        self.assertEqual(len(hits), 1)
        self.assertIn("100%", hits[0].text)

    def test_fts_syntax_chars_do_not_raise(self) -> None:
        for term in ('OR', '配置项 OR 文件', '"', '---', 'a"b', "100%"):
            with self.subTest(term=term):
                self.repo.list(query=term)

    def test_kind_filter_still_applies(self) -> None:
        self.assertEqual(len(self.repo.list(query="配置项", kind="image")), 0)

    def test_delete_removes_from_index(self) -> None:
        target = self.repo.list(query="配置项")[0]
        self.repo.delete(target.id)
        self.assertEqual(len(self.repo.list(query="配置项")), 0)

    def test_imported_row_is_searchable(self) -> None:
        self.repo.insert_if_absent(text_item("导入的新配置项目", key="imported-1"))
        self.assertEqual(len(self.repo.list(query="配置项目")), 1)

    def test_like_only_mode(self) -> None:
        # 模拟老版本 SQLite：建不起 trigram 表时一切照旧
        self.repo._fts_ready = False
        self.assertEqual(len(self.repo.list(query="配置项")), 1)
        self.assertEqual(len(self.repo.list(query="配置")), 3)

    @unittest.skipUnless(FTS_AVAILABLE, "SQLite 版本低于 3.34，没有 trigram")
    def test_existing_database_is_backfilled(self) -> None:
        """旧版数据库只有 items 表，升级后老记录也必须能搜到。"""
        holder = tempfile.TemporaryDirectory()
        path = Path(holder.name) / "legacy.db"
        legacy = sqlite3.connect(str(path))
        legacy.executescript(SCHEMA)
        legacy.execute(
            "INSERT INTO items (kind, content_hash, preview, text_body, "
            "created_at, last_used_at) VALUES ('text', 'old-1', '旧数据', '旧数据', 1, 1)"
        )
        legacy.commit()
        legacy.close()

        upgraded = Repository(path)
        try:
            self.assertTrue(upgraded._fts_ready)
            self.assertEqual(len(upgraded.list(query="旧数据")), 1)
        finally:
            upgraded.close()
            holder.cleanup()


if __name__ == "__main__":
    unittest.main()
