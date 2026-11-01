import json
import logging
from typing import Dict, List
from PyQt5.QtCore import QObject
from PyQt5.QtNetwork import QTcpServer, QTcpSocket, QHostAddress

logger = logging.getLogger("RawTCPIPServer")

class RawTCPIPServer(QObject):
    """
    原始 TCP/IP 网络 API 服务：
    - 支持高并发客户端连接
    - 纯文本 JSON 协议交互（支持换行符分割 `\n` 或单帧完整 JSON 交互）
    - 零拷贝直接回传处理结果
    """

    def __init__(self, api_controller, host: str = "0.0.0.0", port: int = 8091, parent=None):
        super().__init__(parent)
        self.api_controller = api_controller
        self.host = host
        self.port = port
        self.server = QTcpServer(self)
        self.clients: List[QTcpSocket] = []
        self._buffers: Dict[QTcpSocket, bytearray] = {}

    def start(self) -> bool:
        addr = QHostAddress(self.host) if self.host != "0.0.0.0" else QHostAddress.Any
        if not self.server.listen(addr, self.port):
            logger.error("TCP Server failed to listen on %s:%d: %s", self.host, self.port, self.server.errorString())
            return False
        self.server.newConnection.connect(self._on_new_connection)
        logger.info("TCP API Server listening on %s:%d", self.host, self.port)
        return True

    def stop(self):
        for client in list(self.clients):
            try:
                client.disconnectFromHost()
            except Exception:
                pass
        self.clients.clear()
        self._buffers.clear()
        self.server.close()

    def _on_new_connection(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            self.clients.append(client)
            self._buffers[client] = bytearray()
            client.readyRead.connect(lambda c=client: self._on_ready_read(c))
            client.disconnected.connect(lambda c=client: self._on_disconnected(c))

    def _on_disconnected(self, client: QTcpSocket):
        if client in self.clients:
            self.clients.remove(client)
        if client in self._buffers:
            del self._buffers[client]
        client.deleteLater()

    def _on_ready_read(self, client: QTcpSocket):
        data = client.readAll().data()
        if not data:
            return

        buf = self._buffers.get(client, bytearray())
        buf.extend(data)

        # 1. 优先按换行符处理完整的行消息
        while b"\n" in buf:
            line_bytes, buf = buf.split(b"\n", 1)
            line_str = line_bytes.decode("utf-8", errors="ignore").strip()
            if line_str:
                self._process_message(client, line_str)

        # 2. 若缓冲区无换行但构成闭合的 JSON 对象或完整的 func(...) plain 调用，则立即处理
        stripped = buf.strip()
        if stripped.startswith(b"{") and stripped.endswith(b"}"):
            try:
                json_str = stripped.decode("utf-8")
                json.loads(json_str)  # 尝试校验完整性
                self._process_message(client, json_str)
                buf = bytearray()
            except Exception:
                pass
        elif b"(" in stripped and (stripped.endswith(b")") or stripped.endswith(b");")):
            try:
                plain_str = stripped.decode("utf-8")
                if hasattr(self.api_controller, "is_valid_plain_call") and self.api_controller.is_valid_plain_call(plain_str):
                    self._process_message(client, plain_str)
                    buf = bytearray()
            except Exception:
                pass

        self._buffers[client] = buf

    def _process_message(self, client: QTcpSocket, message: str):
        response_str = self.api_controller.handle_request(message)
        payload = (response_str + "\n").encode("utf-8")
        client.write(payload)
        client.flush()
