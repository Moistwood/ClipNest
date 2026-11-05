"""托盘「使用说明」里的文案。纯文本，界面和首次启动提示共用。"""

from __future__ import annotations


def help_text(hotkey: str, data_dir: str, version: str = "") -> str:
    text = (
        f"呼出历史：{hotkey}\n"
        "↑↓ 选择，Enter 粘贴（保留原格式），Shift+Enter 只粘纯文本。\n"
        "Ctrl+Enter 只复制不粘贴；Ctrl+1 ~ Ctrl+9 直接粘第 N 条；Ctrl+P 加入/移出收藏。\n"
        "右键条目可以写备注、复制纯文本、打开文件所在位置、删除。\n"
        "Esc 或点到别的窗口，面板会自动收起。\n"
        "托盘菜单里可以暂停记录、改设置、看统计、清空历史、退出。\n"
        f"所有记录只存在本机：{data_dir}"
    )
    if version:
        text += f"\n版本：{version}"
    return text
