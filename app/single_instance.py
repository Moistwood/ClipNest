"""单实例。第二次启动不应该再开一个托盘图标，而是把已有窗口叫出来。"""

from __future__ import annotations

from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "ClipNest-SingleInstance"
CONNECT_TIMEOUT_MS = 300


class SingleInstance:
    def __init__(self, name: str = SERVER_NAME) -> None:
        self._name = name
        self._server: QLocalServer | None = None

    def is_running(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if socket.waitForConnected(CONNECT_TIMEOUT_MS):
            socket.write(b"show")
            socket.flush()
            socket.waitForBytesWritten(300)
            socket.disconnectFromServer()
            return True
        return False

    def listen(self) -> bool:
        QLocalServer.removeServer(self._name)
        self._server = QLocalServer()
        return self._server.listen(self._name)

    def take_server(self) -> QLocalServer | None:
        return self._server
