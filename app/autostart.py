"""开机自启。只写当前用户的 Run 键，不碰系统级，也不需要管理员权限。"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

from app import paths

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = paths.APP_NAME


def _launch_command() -> str:
    """打包后是 exe 自身；源码运行时是解释器加 run.py。"""
    if "__compiled__" in globals() or getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = Path(__file__).resolve().parent.parent / "run.py"
    return f'"{sys.executable}" "{script}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return False
    except OSError:
        return False
    return bool(value)


def matches_current_build() -> bool:
    """注册表里的路径是否指向当前这份程序，换目录或换打包方式后要重写。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return False
    return value.strip().lower() == _launch_command().strip().lower()


def enable() -> bool:
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
    except OSError:
        return False
    return True


def disable() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def set_enabled(enabled: bool) -> bool:
    return enable() if enabled else disable()


def repair() -> None:
    """启动时校正：用户勾了自启但路径已失效，就按当前路径重写。"""
    if is_enabled() and not matches_current_build():
        enable()
