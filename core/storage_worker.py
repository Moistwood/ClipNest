"""把落盘和数据库写入放到独立线程。

复制一张 4K 截图时，PNG 写文件加上 SQLite 事务可能要几十毫秒，
放在主线程会让呼出的面板掉帧。这里让工作线程持有自己的 SQLite
连接，主线程那个连接只做查询；WAL 模式下两者互不阻塞。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.models import KIND_IMAGE, ClipItem
from core.repository import Repository


class _Worker(QObject):
    """实际干活的对象，活在 QThread 里。"""

    stored = Signal(object)
    failed = Signal(str)

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self._db_path = db_path
        self._repo: Repository | None = None

    @Slot()
    def initialize(self) -> None:
        try:
            self._repo = Repository(self._db_path, setup_index=False)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"打开数据库失败：{exc}")

    @Slot(object)
    def save(self, item: ClipItem) -> None:
        if self._repo is None:
            return
        try:
            if item.kind == KIND_IMAGE and item.image_bytes:
                # 延迟导入，避免 core 在顶层依赖 app
                from app import paths

                item.image_path = str(paths.save_blob(item.image_bytes, item.content_hash))
                item.image_bytes = None
            item.id = self._repo.add(item)
            self.stored.emit(item)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"写入失败：{exc}")

    def close_repository(self) -> None:
        if self._repo is not None:
            self._repo.close()
            self._repo = None


class StorageService(QObject):
    """主线程唯一需要打交道的入口。"""

    saved = Signal(object)
    failed = Signal(str)
    _request = Signal(object)

    def __init__(self, db_path: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread = QThread(self)
        self._worker = _Worker(db_path)
        self._worker.moveToThread(self._thread)

        self._request.connect(self._worker.save)
        self._worker.stored.connect(self.saved)
        self._worker.failed.connect(self.failed)
        self._thread.started.connect(self._worker.initialize)
        self._thread.start()

    def save(self, item: ClipItem) -> None:
        """异步投递，调用方立刻返回。"""
        self._request.emit(item)

    def shutdown(self) -> None:
        # 先停事件循环，确认没有写入在进行，再关连接
        self._thread.quit()
        self._thread.wait(3000)
        self._worker.close_repository()
