"""决定哪些内容不该被记录。宁可漏记，也不能把密码存进去。"""

from __future__ import annotations

import re
import struct

from core import win32

# 程序主动声明的「别记录我」标记，必须全部认。
# 前两个是老牌密码管理器和旧式剪贴板查看器用的，
# 后两个是 Win10 1809 之后系统剪贴板历史读的。
IGNORE_FORMATS = (
    "ExcludeClipboardContentFromMonitorProcessing",
    "Clipboard Viewer Ignore",
)
HISTORY_FLAG_FORMAT = "CanIncludeInClipboardHistory"

DEFAULT_BLOCKED_APPS = (
    "keepass.exe",
    "keepassxc.exe",
    "1password.exe",
    "bitwarden.exe",
    "keeper.exe",
    "lastpass.exe",
    "dashlane.exe",
)

_SECRET_PATTERNS = (
    re.compile(r"^[A-Za-z0-9+/=]{40,}$"),
    re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)\S{12,64}$"),
)


_fmt_cache: dict[str, int] = {}


def _fmt(name: str) -> int:
    if name not in _fmt_cache:
        _fmt_cache[name] = win32.user32.RegisterClipboardFormatW(name)
    return _fmt_cache[name]


def has_ignore_marker() -> bool:
    """必须在剪贴板打开的状态下调用。"""
    for name in IGNORE_FORMATS:
        if win32.user32.IsClipboardFormatAvailable(_fmt(name)):
            return True

    flag_id = _fmt(HISTORY_FLAG_FORMAT)
    if flag_id and win32.user32.IsClipboardFormatAvailable(flag_id):
        raw = win32.global_bytes(win32.user32.GetClipboardData(flag_id))
        if len(raw) >= 4:
            if struct.unpack_from("<I", raw, 0)[0] == 0:
                return True
    return False


def is_blocked_app(app_name: str, extra: tuple[str, ...] = ()) -> bool:
    if not app_name:
        return False
    name = app_name.lower()
    return name in DEFAULT_BLOCKED_APPS or name in {a.lower() for a in extra}


def looks_like_secret(text: str) -> bool:
    """保守的启发式判断，只在用户主动开启严格模式时使用。"""
    candidate = text.strip()
    if len(candidate) < 12 or " " in candidate or "\n" in candidate:
        return False
    return any(pattern.match(candidate) for pattern in _SECRET_PATTERNS)
