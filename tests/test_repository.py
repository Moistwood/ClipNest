"""存储层单元测试。不需要 Qt，可以直接跑。"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from core.models import KIND_TEXT, ClipItem
from core.repository import Repository


def make_text(text: str, key: str | None = None) -> ClipItem:
    return ClipItem(
        kind=KIND_TEXT,
        text=text,
        preview=text,
        content_hash=key or text,
        size=len(text.encode("utf-16-le")),
    )


class RepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self._tmp.name) / "history.db")

    def tearDown(self) -> None:
        self.repo.close()
        self._tmp.cleanup()

    def test_same_content_is_deduped_and_bumped(self) -> None:
        self.repo.add(make_text("第一条"))
        time.sleep(0.01)
        self.repo.add(make_text("第二条"))
        time.sleep(0.01)
        self.repo.add(make_text("第一条"))

        items = self.repo.list()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].text, "第一条")
        self.assertEqual(items[0].use_count, 2)

    def test_search_escapes_like_wildcards(self) -> None:
        self.repo.add(make_text("完成度 100%"))
        time.sleep(0.01)
        self.repo.add(make_text("完成度 100 分"))

        hits = self.repo.list(query="100%")
        self.assertEqual(len(hits), 1)
        self.assertIn("100%", hits[0].text)

    def test_pinned_items_sort_first(self) -> None:
        self.repo.add(make_text("旧的"))
        time.sleep(0.01)
        self.repo.add(make_text("新的"))
        old = self.repo.list()[-1]
        self.assertTrue(self.repo.toggle_pin(old.id))

        self.assertEqual(self.repo.list()[0].text, "旧的")

    def test_prune_keeps_newest_and_pinned(self) -> None:
        ids = []
        for index in range(5):
            self.repo.add(make_text(f"第 {index} 条"))
            time.sleep(0.01)
            ids.append(self.repo.list()[0].id)

        self.repo.toggle_pin(ids[0])
        removed = self.repo.prune(max_items=2, max_days=0)

        items = self.repo.list()
        self.assertEqual(len(items), 3)
        self.assertIn("第 0 条", [item.text for item in items])
        self.assertEqual(removed, [])

    def test_clear_keeps_pinned(self) -> None:
        self.repo.add(make_text("保留我"))
        pinned_id = self.repo.list()[0].id
        self.repo.toggle_pin(pinned_id)
        self.repo.add(make_text("删掉我"))

        self.repo.clear(keep_pinned=True)
        items = self.repo.list()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].text, "保留我")


if __name__ == "__main__":
    unittest.main()
