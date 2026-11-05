"""把选中的条目写回剪贴板，并注入 Ctrl+V。时序是这里唯一重要的事。"""

from __future__ import annotations

import ctypes
import time
from pathlib import Path

from core import clipboard, win32
from core.models import KIND_FILES, KIND_IMAGE, KIND_TEXT, ClipItem


def copy_to_clipboard(item: ClipItem) -> bool:
    if item.kind == KIND_TEXT:
        return clipboard.write_text(item.text, item.html, item.rtf)
    if item.kind == KIND_FILES:
        return clipboard.write_files(item.files)
    if item.kind == KIND_IMAGE:
        if not item.image_path:
            return False
        path = Path(item.image_path)
        if not path.exists():
            return False
        return clipboard.write_image(path.read_bytes())
    return False


def _scan_code(vk: int) -> int:
    return win32.user32.MapVirtualKeyW(vk, 0)


def _key_event(scan: int, key_up: bool) -> win32.INPUT:
    event = win32.INPUT()
    event.type = win32.INPUT_KEYBOARD
    event.ki.wVk = 0
    event.ki.wScan = scan
    event.ki.dwFlags = win32.KEYEVENTF_SCANCODE
    if key_up:
        event.ki.dwFlags |= win32.KEYEVENTF_KEYUP
    event.ki.time = 0
    event.ki.dwExtraInfo = 0
    return event


def send_paste() -> bool:
    """走扫描码而不是虚拟键，兼容性更好。"""
    ctrl = _scan_code(win32.VK_LCONTROL)
    key_v = _scan_code(win32.VK_V)
    events = [
        _key_event(ctrl, False),
        _key_event(key_v, False),
        _key_event(key_v, True),
        _key_event(ctrl, True),
    ]
    array = (win32.INPUT * len(events))(*events)
    sent = win32.user32.SendInput(len(events), array, ctypes.sizeof(win32.INPUT))
    return sent == len(events)


def wait_clipboard_ready(sequence_before: int, timeout: float = 0.25) -> bool:
    """SetClipboardData 是异步生效的，不等序号变化就粘贴会粘到旧内容。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if win32.user32.GetClipboardSequenceNumber() != sequence_before:
            return True
        time.sleep(0.005)
    return False


def paste(item: ClipItem) -> bool:
    sequence_before = win32.user32.GetClipboardSequenceNumber()
    if not copy_to_clipboard(item):
        return False
    wait_clipboard_ready(sequence_before)
    time.sleep(0.015)
    return send_paste()
