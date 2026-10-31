import logging
from typing import List
from PyQt5.QtCore import QObject
from PyQt5.QtWebSockets import QWebSocketServer, QWebSocket
from PyQt5.QtNetwork import QHostAddress

logger = logging.getLogger("WebSocketAPIServer")

class WebSocketAPIServer(QObject):
    """
    WebSocket 网络 API 服务：
    - 基于 RFC 6455 协议
    - 纯文本 JSON 协议交互
    - 支持多客户端连接与实时请求/响应
    """

    def __init__(self, api_controller, host: str = "0.0.0.0", port: int = 8090, parent=None):
        super().__init__(parent)
        self.api_controller = api_controller
        self.host = host
        self.port = port
        self.server = QWebSocketServer("TanksAPIWebSocket", QWebSocketServer.NonSecureMode, self)
        self.clients: List[QWebSocket] = []

    def start(self) -> bool:
        addr = QHostAddress(self.host) if self.host != "0.0.0.0" else QHostAddress.Any
        if not self.server.listen(addr, self.port):
            logger.error("WebSocket Server failed to listen on %s:%d: %s", self.host, self.port, self.server.errorString())
            return False
        self.server.newConnection.connect(self._on_new_connection)
        logger.info("WebSocket API Server listening on ws://%s:%d", self.host, self.port)
        return True

    def stop(self):
        for client in list(self.clients):
            try:
                client.close()
            except Exception:
                pass
        self.clients.clear()
        self.server.close()

    def _on_new_connection(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            self.clients.append(client)
            client.textMessageReceived.connect(lambda msg, c=client: self._on_message_received(c, msg))
            client.disconnected.connect(lambda c=client: self._on_disconnected(c))

    def _on_disconnected(self, client: QWebSocket):
        if client in self.clients:
            self.clients.remove(client)
        client.deleteLater()

    def _on_message_received(self, client: QWebSocket, message: str):
        response_str = self.api_controller.handle_request(message)
        client.sendTextMessage(response_str)
