"""配置读写。JSON 文件，坏了就回默认值，不让用户因为配置损坏打不开软件。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from app import paths


@dataclass
class Config:
    hotkey: str = "Ctrl+Alt+V"
    max_items: int = 500
    max_days: int = 7
    paused: bool = False
    strict_secret_filter: bool = False
    # 用户自定义的「这些程序里复制的东西别记」，存进程名
    blocked_apps: list[str] = field(default_factory=list)
    window_width: int = 800
    window_height: int = 520
    # 系统剪贴板的提示只弹一次，用户看过就不再打扰
    hinted_native_clipboard: bool = False

    @classmethod
    def load(cls) -> Config:
        path = paths.config_path()
        if not path.exists():
            config = cls()
            config.save()
            return config
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()

        config = cls()
        for field_name, default_value in asdict(config).items():
            value = raw.get(field_name)
            if not isinstance(value, type(default_value)):
                continue
            if field_name == "blocked_apps":
                # 坏配置里混进数字或嵌套结构时，只留字符串
                value = [entry for entry in value if isinstance(entry, str)]
            setattr(config, field_name, value)
        return config

    def save(self) -> None:
        try:
            paths.config_path().write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
