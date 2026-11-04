"""全局热键。注册失败必须让用户知道，静默失败是最讨厌的行为。"""

from __future__ import annotations

from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtWidgets import QApplication

from core import win32

HOTKEY_ID = 0xC11

_MODIFIERS = {
    "ctrl": win32.MOD_CONTROL,
    "control": win32.MOD_CONTROL,
    "alt": win32.MOD_ALT,
    "shift": win32.MOD_SHIFT,
    "win": win32.MOD_WIN,
    "meta": win32.MOD_WIN,
}

_NAMED_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "tab": 0x09,
    "`": 0xC0,
    "~": 0xC0,
    "-": 0xBD,
    "=": 0xBB,
    "[": 0xDB,
    "]": 0xDD,
    "\\": 0xDC,
    ";": 0xBA,
    "'": 0xDE,
    ",": 0xBC,
    ".": 0xBE,
    "/": 0xBF,
}


def parse_combo(combo: str) -> tuple[int, int]:
    """把 "Ctrl+Alt+V" 解析成 (修饰键掩码, 虚拟键码)。"""
    parts = [part.strip() for part in combo.split("+") if part.strip()]
    if not parts:
        raise ValueError("热键为空")

    modifiers = 0
    key_token = None
    for index, part in enumerate(parts):
        lowered = part.lower()
        if lowered in _MODIFIERS:
            if index == len(parts) - 1:
                raise ValueError(f"「{part}」是修饰键，不能作为主键")
            modifiers |= _MODIFIERS[lowered]
        else:
            key_token = lowered
    if key_token is None or not modifiers:
        raise ValueError("热键必须包含至少一个修饰键和一个主键")

    virtual_key = _virtual_key(key_token)
    if virtual_key is None:
        raise ValueError(f"无法识别的按键：{key_token}")
    return modifiers, virtual_key


def _virtual_key(token: str) -> int | None:
    if token in _NAMED_KEYS:
        return _NAMED_KEYS[token]
    if len(token) == 1 and token.isascii() and token.isalnum():
        return ord(token.upper())
    if token.startswith("f") and token[1:].isdigit():
        number = int(token[1:])
        if 1 <= number <= 12:
            return 0x70 + number - 1
    return None


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, manager: HotkeyManager) -> None:
        super().__init__()
        self._manager = manager

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt 接口)
        return self._manager.handle_native(event_type, message)


class HotkeyManager(QObject):
    activated = Signal()

    def __init__(self, host_hwnd: int, combo: str = "Ctrl+Alt+V", parent: QObject | None = None):
        super().__init__(parent)
        self._hwnd = host_hwnd
        self._combo = combo
        self._registered = False
        self._filter_installed = False
        self._filter = _HotkeyFilter(self)

    @property
    def combo(self) -> str:
        return self._combo

    def register(self, combo: str | None = None) -> bool:
        target = combo or self._combo
        self.unregister()
        modifiers, virtual_key = parse_combo(target)

        if not self._filter_installed:
            app = QApplication.instance()
            if app is not None:
                app.installNativeEventFilter(self._filter)
                self._filter_installed = True

        ok = win32.user32.RegisterHotKey(
            self._hwnd, HOTKEY_ID, modifiers | win32.MOD_NOREPEAT, virtual_key
        )
        self._registered = bool(ok)
        if ok:
            self._combo = target
        return self._registered

    def unregister(self) -> None:
        if self._registered:
            win32.user32.UnregisterHotKey(self._hwnd, HOTKEY_ID)
            self._registered = False

    def handle_native(self, event_type, message):
        if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            try:
                msg = wintypes.MSG.from_address(int(message))
            except (TypeError, ValueError):
                return False, 0
            if msg.message == win32.WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.activated.emit()
        return False, 0
