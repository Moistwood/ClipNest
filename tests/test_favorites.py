"""收藏夹：备注、旧库迁移、重复复制不冲掉备注、只导出收藏项。"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.exporter import export_to_file, import_from_file
from core.models import KIND_TEXT, ClipItem
from core.repository import SCHEMA, Repository


class FavoritesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _text(self, mark: str) -> ClipItem:
        return ClipItem(kind=KIND_TEXT, content_hash=mark, preview=mark, text=mark)

    def test_note_survives_repeated_copy(self) -> None:
        repo = Repository(self.root / "a.db")
        item_id = repo.add(self._text("alpha"))
        repo.toggle_pin(item_id)
        repo.set_note(item_id, "合同编号 2026")

        # 再复制一次同样内容，走的是 upsert，不应该把备注清空
        repo.add(self._text("alpha"))
        self.assertEqual(repo.get(item_id).note, "合同编号 2026")
        self.assertEqual([i.id for i in repo.favorites()], [item_id])
        repo.close()

    def test_legacy_database_gets_note_column(self) -> None:
        legacy = SCHEMA.replace("    note          TEXT    NOT NULL DEFAULT '',\n", "")
        path = self.root / "legacy.db"
        conn = sqlite3.connect(path)
        conn.executescript(legacy)
        conn.close()

        repo = Repository(path)
        item_id = repo.add(self._text("beta"))
        repo.set_note(item_id, "旧库也能写")
        self.assertEqual(repo.get(item_id).note, "旧库也能写")
        repo.close()

    def test_note_search_and_favorites_filter(self) -> None:
        repo = Repository(self.root / "search.db")
        item_id = repo.add(self._text("alpha"))
        repo.set_note(item_id, "季度合同编号")
        repo.add(self._text("ordinary"))

        # 长查询走全文索引，两字短查询走 LIKE，两条路径都要能命中备注
        self.assertIn(item_id, [i.id for i in repo.list(query="季度合同编号")])
        self.assertIn(item_id, [i.id for i in repo.list(query="季度")])

        self.assertEqual(repo.list(favorites_only=True), [])
        repo.toggle_pin(item_id)
        self.assertEqual([i.id for i in repo.list(favorites_only=True)], [item_id])
        self.assertEqual(
            [i.id for i in repo.list(query="季度合同编号", favorites_only=True)], [item_id]
        )
        self.assertEqual(repo.list(query="ordinary", favorites_only=True), [])
        repo.close()

    def test_export_only_favorites_and_import_keeps_note(self) -> None:
        repo = Repository(self.root / "source.db")
        fav_id = repo.add(self._text("important"))
        repo.toggle_pin(fav_id)
        repo.set_note(fav_id, "报价单")
        repo.add(self._text("ordinary"))

        target = self.root / "favorites.json"
        self.assertEqual(export_to_file(repo, target, include_images=False, favorites_only=True), 1)
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(payload["scope"], "favorites")
        self.assertEqual(payload["items"][0]["note"], "报价单")

        other = Repository(self.root / "target.db")
        added, skipped = import_from_file(other, target)
        self.assertEqual((added, skipped), (1, 0))
        imported = other.favorites()
        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0].note, "报价单")
        repo.close()
        other.close()


if __name__ == "__main__":
    unittest.main()
