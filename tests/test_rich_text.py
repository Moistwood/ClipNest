"""富文本：CF_HTML 编解码、数据库字段迁移、导出导入往返。"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from core import clipboard
from core.exporter import export_to_file, import_from_file
from core.models import KIND_TEXT, ClipItem
from core.repository import SCHEMA, Repository


def rich_item(text: str, html: str = "", rtf: str = "", key: str | None = None) -> ClipItem:
    return ClipItem(
        kind=KIND_TEXT,
        content_hash=key or text,
        text=text,
        preview=text,
        html=html,
        rtf=rtf,
        size=len(text.encode("utf-16-le")),
    )


class CfHtmlTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        for fragment in (
            "<b>你好</b>",
            '<span style="color:red">a &amp; b</span>',
            "x" * 5000,
            "",
        ):
            with self.subTest(length=len(fragment)):
                payload = clipboard._cf_html_payload(fragment)
                self.assertEqual(clipboard._parse_cf_html(payload), fragment)

    def test_offsets_point_at_the_fragment(self) -> None:
        fragment = "<i>片段</i>"
        payload = clipboard._cf_html_payload(fragment)
        header = payload[:512].decode("ascii", "ignore")
        start = clipboard._offset(header, "StartFragment")
        end = clipboard._offset(header, "EndFragment")
        self.assertEqual(payload[start:end].decode("utf-8"), fragment)
        self.assertEqual(
            payload.index(b"<!--StartFragment-->") + len(b"<!--StartFragment-->"), start
        )
        self.assertEqual(payload[end : end + len(b"<!--EndFragment-->")], b"<!--EndFragment-->")

    def test_broken_payload_returns_empty(self) -> None:
        for raw in (b"", b"not a clipboard payload", b"Version:0.9\r\nEndFragment:9999\r\n"):
            with self.subTest(raw=raw[:20]):
                self.assertEqual(clipboard._parse_cf_html(raw), "")


class RichTextRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "rich.db"
        self.repo = Repository(self.path)

    def tearDown(self) -> None:
        self.repo.close()
        self._dir.cleanup()

    def test_fields_survive_insert_and_read(self) -> None:
        html = "<b>标题</b>"
        rtf = r"{\rtf1\ansi 标题}"
        self.repo.add(rich_item("标题", html, rtf))
        item = self.repo.list()[0]
        self.assertEqual(item.html, html)
        self.assertEqual(item.rtf, rtf)

    def test_repeat_copy_keeps_rich_version(self) -> None:
        """同内容再复制成纯文本时，不该把已有的富文本冲掉。"""
        self.repo.add(rich_item("标题", "<b>标题</b>", ""))
        self.repo.add(rich_item("标题", "", ""))
        item = self.repo.list()[0]
        self.assertEqual(item.html, "<b>标题</b>")
        self.assertEqual(self.repo.count(), 1)

    def test_export_import_round_trip(self) -> None:
        self.repo.add(rich_item("标题", "<b>标题</b>", r"{\rtf1\ansi}"))
        target = Path(self._dir.name) / "dump.json"
        export_to_file(self.repo, target)

        other = Repository(Path(self._dir.name) / "restored.db")
        try:
            added, skipped = import_from_file(other, target)
            self.assertEqual((added, skipped), (1, 0))
            item = other.list()[0]
            self.assertEqual(item.html, "<b>标题</b>")
            self.assertEqual(item.rtf, r"{\rtf1\ansi}")
        finally:
            other.close()

    def test_legacy_database_gets_new_columns(self) -> None:
        """升级前建的数据库没有这两列，打开时应该自动补上。"""
        legacy_path = Path(self._dir.name) / "legacy.db"
        old_schema = SCHEMA.replace("    html_body     TEXT    NOT NULL DEFAULT '',\n", "").replace(
            "    rtf_body      TEXT    NOT NULL DEFAULT '',\n", ""
        )
        conn = sqlite3.connect(str(legacy_path))
        conn.executescript(old_schema)
        conn.execute(
            "INSERT INTO items (kind, content_hash, preview, text_body, "
            "created_at, last_used_at) VALUES ('text', 'old', '旧', '旧', 1, 1)"
        )
        conn.commit()
        conn.close()

        upgraded = Repository(legacy_path)
        try:
            item = upgraded.list()[0]
            self.assertEqual(item.text, "旧")
            self.assertEqual(item.html, "")
            upgraded.add(rich_item("新", "<b>新</b>", ""))
            self.assertEqual(upgraded.list(query="新")[0].html, "<b>新</b>")
        finally:
            upgraded.close()


if __name__ == "__main__":
    unittest.main()
