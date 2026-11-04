"""配置读写。JSON 文件，坏了就回默认值，不让用户因为配置损坏打不开软件。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from app import paths


@dataclass
class Config:
    hotkey: str = "Ctrl+Alt+V"
    max_items: int = 500
    max_days: int = 7
    paused: bool = False
    strict_secret_filter: bool = False
    window_width: int = 800
    window_height: int = 520

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
            if field_name in raw and isinstance(raw[field_name], type(default_value)):
                setattr(config, field_name, raw[field_name])
        return config

    def save(self) -> None:
        try:
            paths.config_path().write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
