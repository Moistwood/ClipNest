"""剪贴板监听、读取与写入。所有 Win32 细节收敛在这里。"""

from __future__ import annotations

import ctypes
import hashlib
import re
import struct
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QBuffer, QByteArray, QIODevice, QObject, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from core import filters, win32
from core.models import (
    KIND_FILES,
    KIND_IMAGE,
    KIND_TEXT,
    MAX_TEXT_BYTES,
    MAX_RICH_BYTES,
    ClipItem,
    make_preview,
)

_formats: dict[str, int] = {}

# CF_HTML 的头部是 ASCII，四个数字是相对整块数据的字节偏移
CF_HTML_TEMPLATE = (
    "Version:0.9\r\n"
    "StartHTML:{sh:010d}\r\n"
    "EndHTML:{eh:010d}\r\n"
    "StartFragment:{sf:010d}\r\n"
    "EndFragment:{ef:010d}\r\n"
)
HTML_PREFIX = b"<html><body><!--StartFragment-->"
HTML_SUFFIX = b"<!--EndFragment--></body></html>"


def fmt(name: str) -> int:
    """注册或复用自定义剪贴板格式。"""
    if name not in _formats:
        _formats[name] = win32.user32.RegisterClipboardFormatW(name)
    return _formats[name]


def _open(retries: int = 3) -> bool:
    for _ in range(retries):
        if win32.user32.OpenClipboard(None):
            return True
        time.sleep(0.015)
    return False


def _dib_to_bmp(dib: bytes) -> bytes:
    """CF_DIB 只有信息头和像素，没有文件头，这里补上 14 字节才能交给解码器。"""
    if len(dib) < 40:
        return b""
    header_size = struct.unpack_from("<I", dib, 0)[0]
    bit_count = struct.unpack_from("<H", dib, 14)[0]
    compression = struct.unpack_from("<I", dib, 16)[0]
    colors_used = struct.unpack_from("<I", dib, 32)[0]

    extra = 0
    if bit_count <= 8:
        extra = (colors_used or (1 << bit_count)) * 4
    if compression == 3 and header_size == 40:
        extra += 12

    offset = 14 + header_size + extra
    file_header = b"BM" + struct.pack("<IHHI", 14 + len(dib), 0, 0, offset)
    return file_header + dib


def _read_text() -> str:
    raw = win32.global_bytes(win32.user32.GetClipboardData(win32.CF_UNICODETEXT))
    if not raw:
        return ""
    text = raw.decode("utf-16-le", "replace").rstrip("\x00")
    return text[:MAX_TEXT_BYTES]


def _offset(header: str, name: str) -> int:
    match = re.search(name + r":(\d+)", header)
    return int(match.group(1)) if match else 0


def _parse_cf_html(raw: bytes) -> str:
    """从 CF_HTML 数据块里按头部偏移把片段切出来。"""
    header = raw[:1024].decode("ascii", "ignore")
    start = _offset(header, "StartFragment")
    end = _offset(header, "EndFragment")
    if not end or end < start or end > len(raw):
        start, end = _offset(header, "StartHTML"), _offset(header, "EndHTML")
    if not end or end < start or end > len(raw):
        return ""
    return raw[start:end].decode("utf-8", "replace").strip("\x00")[:MAX_RICH_BYTES]


def _read_html() -> str:
    """读剪贴板上的 CF_HTML。头部四个偏移是字节位置，片段通常是 UTF-8。"""
    format_id = fmt("HTML Format")
    if not format_id or not win32.user32.IsClipboardFormatAvailable(format_id):
        return ""
    raw = win32.global_bytes(win32.user32.GetClipboardData(format_id))
    return _parse_cf_html(raw) if raw else ""


def _read_rtf() -> str:
    """RTF 本身是 ASCII 加 \\uN 转义，用 latin-1 存才能原样写回去。"""
    format_id = fmt("Rich Text Format")
    if not format_id or not win32.user32.IsClipboardFormatAvailable(format_id):
        return ""
    raw = win32.global_bytes(win32.user32.GetClipboardData(format_id))
    if not raw:
        return ""
    return raw.split(b"\x00", 1)[0].decode("latin-1", "replace")[:MAX_RICH_BYTES]


def _read_files() -> list[str]:
    handle = win32.user32.GetClipboardData(win32.CF_HDROP)
    if not handle:
        return []
    count = win32.shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
    paths: list[str] = []
    for index in range(min(count, 500)):
        buf = ctypes.create_unicode_buffer(32768)
        if win32.shell32.DragQueryFileW(handle, index, buf, len(buf)):
            paths.append(buf.value)
    return paths


def _read_image() -> tuple[bytes, int, int] | None:
    png_id = fmt("PNG")
    if png_id and win32.user32.IsClipboardFormatAvailable(png_id):
        data = win32.global_bytes(win32.user32.GetClipboardData(png_id))
        if data:
            image = QImage.fromData(QByteArray(data), "PNG")
            if not image.isNull():
                return data, image.width(), image.height()

    for clip_format in (win32.CF_DIBV5, win32.CF_DIB):
        if not win32.user32.IsClipboardFormatAvailable(clip_format):
            continue
        dib = win32.global_bytes(win32.user32.GetClipboardData(clip_format))
        if not dib:
            continue
        image = QImage.fromData(QByteArray(_dib_to_bmp(dib)), "BMP")
        if image.isNull():
            continue
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(buffer.data()), image.width(), image.height()
    return None


def read_clipboard(hwnd: int = 0) -> ClipItem | None:
    """读当前剪贴板。读不到或者内容为空返回 None。"""
    if not _open():
        return None
    try:
        owner = win32.user32.GetClipboardOwner()
        source = win32.process_name_from_window(owner)

        if filters.has_ignore_marker() or filters.is_blocked_app(source):
            return None

        files = _read_files() if win32.user32.IsClipboardFormatAvailable(win32.CF_HDROP) else []
        if files:
            item = ClipItem(kind=KIND_FILES, files=files, source_app=source)
            item.size = sum(len(f.encode("utf-16-le")) for f in files)
            item.preview = make_preview(KIND_FILES, "", files, 0, 0)
            item.content_hash = _hash(KIND_FILES, "\n".join(files).encode("utf-16-le"))
            return item

        image = _read_image()
        if image:
            data, width, height = image
            item = ClipItem(
                kind=KIND_IMAGE, image_bytes=data, width=width, height=height, source_app=source
            )
            item.size = len(data)
            item.preview = make_preview(KIND_IMAGE, "", [], width, height)
            item.content_hash = _hash(KIND_IMAGE, data)
            return item

        if win32.user32.IsClipboardFormatAvailable(win32.CF_UNICODETEXT):
            text = _read_text()
            if text.strip():
                item = ClipItem(
                    kind=KIND_TEXT,
                    text=text,
                    html=_read_html(),
                    rtf=_read_rtf(),
                    source_app=source,
                )
                item.size = len(text.encode("utf-16-le"))
                item.preview = make_preview(KIND_TEXT, text, [], 0, 0)
                item.content_hash = _hash(KIND_TEXT, text.encode("utf-16-le"))
                return item
        return None
    finally:
        win32.user32.CloseClipboard()


def _hash(kind: str, payload: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(kind.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(payload)
    return digest.hexdigest()


def _push(payloads: dict[int, bytes], hwnd: int = 0) -> bool:
    if not payloads:
        return False
    if not _open():
        return False
    try:
        win32.user32.EmptyClipboard()
        for clip_format, data in payloads.items():
            handle = win32.kernel32.GlobalAlloc(win32.GMEM_MOVEABLE, len(data))
            if not handle:
                continue
            pointer = win32.kernel32.GlobalLock(handle)
            if not pointer:
                win32.kernel32.GlobalFree(handle)
                continue
            ctypes.memmove(pointer, data, len(data))
            win32.kernel32.GlobalUnlock(handle)
            # SetClipboardData 成功后内存所有权归系统，绝不能再 GlobalFree
            if not win32.user32.SetClipboardData(clip_format, handle):
                win32.kernel32.GlobalFree(handle)
        return True
    finally:
        win32.user32.CloseClipboard()


def _cf_html_payload(fragment: str) -> bytes:
    """把片段包成标准的 CF_HTML，填好四个字节偏移。"""
    body = fragment.encode("utf-8")
    blank = len(CF_HTML_TEMPLATE.format(sh=0, eh=0, sf=0, ef=0).encode("ascii"))
    start_fragment = blank + len(HTML_PREFIX)
    end_fragment = start_fragment + len(body)
    end_html = end_fragment + len(HTML_SUFFIX)
    header = CF_HTML_TEMPLATE.format(
        sh=blank, eh=end_html, sf=start_fragment, ef=end_fragment
    ).encode("ascii")
    return header + HTML_PREFIX + body + HTML_SUFFIX


def write_text(text: str, html: str = "", rtf: str = "") -> bool:
    """纯文本打底，带格式的版本一并放上去，目标程序自己挑能认的。"""
    payloads: dict[int, bytes] = {
        win32.CF_UNICODETEXT: text.encode("utf-16-le") + b"\x00\x00"
    }
    if html:
        format_id = fmt("HTML Format")
        if format_id:
            payloads[format_id] = _cf_html_payload(html)
    if rtf:
        format_id = fmt("Rich Text Format")
        if format_id:
            payloads[format_id] = rtf.encode("latin-1", "replace") + b"\x00"
    return _push(payloads)


def write_files(paths: list[str]) -> bool:
    """写 CF_HDROP：DROPFILES 结构 + 双空结尾的路径列表。"""
    if not paths:
        return False
    header = struct.pack("<IiiII", 20, 0, 0, 0, 1)
    body = "".join(p + "\x00" for p in paths) + "\x00"
    return _push({win32.CF_HDROP: header + body.encode("utf-16-le")})


def write_image(png: bytes) -> bool:
    payloads = {win32.CF_DIB: _png_to_dib(png)}
    png_id = fmt("PNG")
    if png_id:
        payloads[png_id] = png
    return _push({k: v for k, v in payloads.items() if v})


def _png_to_dib(png: bytes) -> bytes:
    """把 PNG 转回 DIB，让不支持 image/png 的老程序也能贴。"""
    image = QImage.fromData(QByteArray(png), "PNG")
    if image.isNull():
        return b""
    converted = image.convertToFormat(QImage.Format.Format_ARGB32)
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    converted.save(buffer, "BMP")
    data = bytes(buffer.data())
    return data[14:] if data[:2] == b"BM" else b""


class _WatcherFilter(QAbstractNativeEventFilter):
    """PySide6 只接受真正的 QAbstractNativeEventFilter 子类，鸭子类型不行。"""

    def __init__(self, watcher: ClipboardWatcher) -> None:
        super().__init__()
        self._watcher = watcher

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt 接口)
        return self._watcher.handle_native(event_type, message)


class ClipboardWatcher(QObject):
    """订阅 WM_CLIPBOARDUPDATE，把每次复制读成 ClipItem 发出去。"""

    captured = Signal(object)

    def __init__(self, host_hwnd: int, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._hwnd = host_hwnd
        self._active = False
        self._app = QApplication.instance()
        self._filter_installed = False
        self._filter = _WatcherFilter(self)
        self._last_hash = ""
        self._last_time = 0.0

    def start(self) -> None:
        if not self._filter_installed and self._app is not None:
            self._app.installNativeEventFilter(self._filter)
            self._filter_installed = True
        if win32.user32.AddClipboardFormatListener(self._hwnd):
            self._active = True

    def stop(self) -> None:
        if self._active:
            win32.user32.RemoveClipboardFormatListener(self._hwnd)
            self._active = False

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.start()
        else:
            self.stop()

    def handle_native(self, event_type, message):
        if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            try:
                msg = wintypes.MSG.from_address(int(message))
            except (TypeError, ValueError):
                return False, 0
            if msg.message == win32.WM_CLIPBOARDUPDATE and self._active:
                self._on_update()
        return False, 0

    def _on_update(self) -> None:
        # 自己写回剪贴板也会触发消息，靠所有者句柄判断，比布尔标记可靠
        if win32.user32.GetClipboardOwner() == self._hwnd:
            return
        try:
            item = read_clipboard(self._hwnd)
        except OSError:
            return
        if item is None:
            return

        # 一次复制会被系统连发多次 WM_CLIPBOARDUPDATE（实测抓到 9 次），
        # 同内容短时间内只处理一次，否则会白白写库、把使用次数刷上天。
        now = time.monotonic()
        if item.content_hash == self._last_hash and now - self._last_time < 0.8:
            return
        self._last_hash = item.content_hash
        self._last_time = now
        self.captured.emit(item)
