"""环境与依赖自检。

不修改剪贴板内容，不写入历史库，只做只读探测。
用法：.venv\\Scripts\\python.exe tools\\selftest.py
"""

import ctypes
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

results: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        detail = fn()
        results.append((name, True, str(detail)))
    except Exception as exc:  # noqa: BLE001
        results.append((name, False, f"{type(exc).__name__}: {exc}"))


def check_python() -> str:
    if sys.version_info < (3, 10):
        raise RuntimeError("需要 Python 3.10 及以上")
    return f"{sys.version.split()[0]} ({sys.executable})"


def check_pyside() -> str:
    import PySide6

    from PySide6 import QtCore

    return f"PySide6 {PySide6.__version__} / Qt {QtCore.qVersion()}"


def check_platform() -> str:
    if os.name != "nt":
        raise RuntimeError("本程序依赖 Win32 API，只能在 Windows 上运行")
    return f"Windows {sys.getwindowsversion().major}.{sys.getwindowsversion().build}"


def check_win32_structs() -> str:
    from core import win32

    sizes = {
        "INPUT": (ctypes.sizeof(win32.INPUT), 40),
        "BITMAPFILEHEADER": (ctypes.sizeof(win32.BITMAPFILEHEADER), 14),
        "KEYBDINPUT": (ctypes.sizeof(win32.KEYBDINPUT), 24),
    }
    bad = [f"{k}={v[0]} 应为 {v[1]}" for k, v in sizes.items() if v[0] != v[1]]
    if bad:
        raise RuntimeError("结构体尺寸不对: " + ", ".join(bad))
    return "INPUT 40 / BITMAPFILEHEADER 14，与 x64 对齐一致"


def check_clipboard_formats() -> str:
    from core import win32

    ids = {
        name: win32.user32.RegisterClipboardFormatW(name)
        for name in (
            "PNG",
            "ExcludeClipboardContentFromMonitorProcessing",
            "CanIncludeInClipboardHistory",
        )
    }
    missing = [k for k, v in ids.items() if not v]
    if missing:
        raise RuntimeError("注册剪贴板格式失败: " + ", ".join(missing))
    return "PNG / 忽略标记 / 历史开关 三种私有格式均可用"


def check_clipboard_read() -> str:
    from core.clipboard import read_clipboard

    item = read_clipboard()
    if item is None:
        return "当前剪贴板为空或不含可识别格式（正常）"
    return f"读到 {item.kind}，{item.size} 字节，来源 {item.source_app or '未知'}"


def check_data_dir() -> str:
    from app import paths

    directory = paths.data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    probe = directory / ".write_probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    return str(directory)


def check_sqlite() -> str:
    from app import paths

    if sqlite3.sqlite_version_info < (3, 35, 0):
        raise RuntimeError(f"SQLite {sqlite3.sqlite_version} 过旧，需要 3.35 以上支持 RETURNING")
    conn = sqlite3.connect(str(paths.db_path()))
    mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    conn.close()
    return f"SQLite {sqlite3.sqlite_version}，journal_mode={mode}"


def check_repository() -> str:
    from core.models import KIND_TEXT, ClipItem
    from core.repository import Repository

    tmp = Path(tempfile.mkdtemp()) / "selftest.db"
    repo = Repository(tmp)
    mark = "clipnest-selftest-" + str(os.getpid())
    repo.add(ClipItem(kind=KIND_TEXT, content_hash=mark, preview=mark, text=mark))
    repo.add(ClipItem(kind=KIND_TEXT, content_hash=mark, preview=mark, text=mark))
    if repo.count() != 1:
        raise RuntimeError("重复内容没有被去重")
    hits = repo.list(query="selftest")
    if not hits:
        raise RuntimeError("关键字搜索没有命中")
    return "写入 / 去重 / 搜索 三项通过"


def check_hotkey() -> str:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget

    app = QApplication.instance() or QApplication([])
    from core import win32
    from core.hotkey import parse_combo

    host = QWidget()
    host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    host.show()
    hwnd = int(host.winId())

    modifiers, vk = parse_combo("Ctrl+Alt+V")
    ok = win32.user32.RegisterHotKey(hwnd, 9901, modifiers | win32.MOD_NOREPEAT, vk)
    if ok:
        win32.user32.UnregisterHotKey(hwnd, 9901)
        host.close()
        app.processEvents()
        return "Ctrl+Alt+V 可以注册（已立即注销）"

    host.close()
    app.processEvents()
    raise RuntimeError("Ctrl+Alt+V 已被其他程序占用，需要换一个热键")


def check_native_clipboard() -> str:
    from app import system_probe

    state = system_probe.native_history_enabled()
    if state is True:
        return "系统自带剪贴板历史已开启（Win+V 可用）"
    if state is False:
        return "系统自带剪贴板历史未开启（Win+V 不可用，不影响本工具）"
    return "读取失败，程序按未开启处理"


def check_clipboard_fallback() -> str:
    from core.clipboard import MESSAGE_GRACE, message_lost

    if not message_lost(0.0, MESSAGE_GRACE + 0.1):
        raise RuntimeError("消息丢失时没有触发补读")
    if message_lost(0.0, MESSAGE_GRACE - 0.1):
        raise RuntimeError("宽限期内误触发了补读")
    return f"序号兜底判定阈值 {MESSAGE_GRACE}s"


def check_fts() -> str:
    from core.repository import Repository

    tmp = Path(tempfile.mkdtemp()) / "fts_probe.db"
    repo = Repository(tmp)
    ready = repo._fts_ready
    repo.close()
    if not ready:
        return "当前 SQLite 不支持 trigram，检索自动降级成模糊匹配"
    return "trigram 索引可用，短查询会降级成模糊匹配"


def check_theme() -> str:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from ui import theme

    palette = theme.current()
    icon = theme.make_icon(True)
    if icon.isNull():
        raise RuntimeError("托盘图标生成失败")
    sizes = icon.availableSizes()
    app.processEvents()
    return f"配色令牌 OK，图标 {sizes[0].width()}px"


def main() -> int:
    checks = [
        ("Python 解释器", check_python),
        ("运行平台", check_platform),
        ("PySide6 / Qt", check_pyside),
        ("Win32 结构体对齐", check_win32_structs),
        ("剪贴板私有格式", check_clipboard_formats),
        ("剪贴板读取", check_clipboard_read),
        ("数据目录可写", check_data_dir),
        ("SQLite 能力", check_sqlite),
        ("存储层读写", check_repository),
        ("全文检索能力", check_fts),
        ("全局热键", check_hotkey),
        ("剪贴板消息兜底", check_clipboard_fallback),
        ("系统剪贴板状态", check_native_clipboard),
        ("主题与图标", check_theme),
    ]

    print("=" * 62)
    print(" ClipNest 环境自检")
    print("=" * 62)
    for name, fn in checks:
        check(name, fn)

    width = max(len(n) for n, _, _ in results)
    failed = 0
    for name, ok, detail in results:
        mark = "通过" if ok else "失败"
        print(f"[{mark}] {name.ljust(width)}  {detail}")
        if not ok:
            failed += 1

    print("-" * 62)
    if failed:
        print(f"共 {len(results)} 项，{failed} 项失败。把上面带「失败」的行发给我。")
    else:
        print(f"共 {len(results)} 项，全部通过。可以双击 run_dev.bat 开始手动测试。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
