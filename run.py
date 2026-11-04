"""开发期入口。打包时也是从这里进。"""

from __future__ import annotations

import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
