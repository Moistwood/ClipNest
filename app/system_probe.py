"""探测 Windows 自带剪贴板历史的开关状态。

系统把这个开关放在 HKCU\\Software\\Microsoft\\Clipboard 下，
值名 EnableClipboardHistory。键不存在就说明用户从没打开过，
效果等同于关闭，所以这里把它当成 False 处理。
"""

from __future__ import annotations

import sys

REG_PATH = r"Software\Microsoft\Clipboard"
REG_VALUE = "EnableClipboardHistory"


def native_history_enabled() -> bool | None:
    """True 已开启，False 未开启，None 表示读不出来。"""
    if sys.platform != "win32":
        return None

    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
            value, _kind = winreg.QueryValueEx(key, REG_VALUE)
    except FileNotFoundError:
        return False
    except OSError:
        return None
    return bool(value)
