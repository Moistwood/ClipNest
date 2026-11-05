"""纯文本粘贴：只放 CF_UNICODETEXT，不放 HTML/RTF。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from core import paster
from core.models import KIND_TEXT, ClipItem


def _rich_item() -> ClipItem:
    return ClipItem(
        kind=KIND_TEXT,
        text="<b>标题</b>",
        html="<b>标题</b>",
        rtf=r"{\b 标题}",
        content_hash="rich-1",
    )


class PasteModeTest(unittest.TestCase):
    def test_default_keeps_rich_formats(self) -> None:
        with patch.object(paster.clipboard, "write_text", return_value=True) as write:
            self.assertTrue(paster.copy_to_clipboard(_rich_item()))
        write.assert_called_once_with("<b>标题</b>", "<b>标题</b>", r"{\b 标题}")

    def test_plain_drops_rich_formats(self) -> None:
        with patch.object(paster.clipboard, "write_text", return_value=True) as write:
            self.assertTrue(paster.copy_to_clipboard(_rich_item(), plain=True))
        write.assert_called_once_with("<b>标题</b>")

    def test_paste_forwards_plain_flag(self) -> None:
        with (
            patch.object(paster, "copy_to_clipboard", return_value=True) as copy,
            patch.object(paster, "wait_clipboard_ready", return_value=True),
            patch.object(paster, "send_paste", return_value=True),
        ):
            self.assertTrue(paster.paste(_rich_item(), plain=True))
        copy.assert_called_once()
        self.assertTrue(copy.call_args.kwargs["plain"])


if __name__ == "__main__":
    unittest.main()
