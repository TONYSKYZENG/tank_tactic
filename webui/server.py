import sys
import os
import json
import threading
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from PyQt5.QtCore import QObject, pyqtSlot
from PyQt5.QtWebSockets import QWebSocketServer, QWebSocket
from PyQt5.QtNetwork import QHostAddress

from map_loader.models import GameMap
from mission_loader.models import Mission
from .headless_runner import HeadlessGameRunner

class WebUIServer(QObject):
    """
    WebUI 与 VNC 流服务器：
    - 提供 HTTP 静态服务（提供 Web 前端页面）
    - 提供 WebSocket 二进制高速推流与输入按键中继
    """

    def __init__(self, mission: Mission, game_map: GameMap, base_dir: Path,
                 http_port: int = 8080, ws_port: int = 8765, parent=None):
        super().__init__(parent)
        self.mission = mission
        self.game_map = game_map
        self.base_dir = base_dir
        self.http_port = http_port
        self.ws_port = ws_port

        self.static_dir = Path(__file__).resolve().parent / "static"
        self.clients = []
        self.last_status_sent_time = 0

        # 1. 创建后台游戏运行器
        self.runner = HeadlessGameRunner(self.mission, self.game_map, self.base_dir, self)
        self.runner.frame_ready.connect(self._on_frame_ready)

        # 2. 启动 WebSocket 服务
        self.ws_server = QWebSocketServer("TankWebVNC", QWebSocketServer.NonSecureMode, self)
        if not self.ws_server.listen(QHostAddress.Any, self.ws_port):
            raise RuntimeError(f"WebSocket 无法监听端口 {self.ws_port}")
        self.ws_server.newConnection.connect(self._on_new_connection)

        # 3. 启动 HTTP 静态文件服务 (后台守护线程)
        self.httpd = None
        self._start_http_server()

        # 4. 启动无头游戏循环
        self.runner.start()

    def _start_http_server(self):
        static_path = self.static_dir

        class StaticHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(static_path), **kwargs)

            def log_message(self, format, *args):
                pass  # 静音常规静态文件请求日志

        try:
            self.httpd = ThreadingHTTPServer(('0.0.0.0', self.http_port), StaticHandler)
            thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            thread.start()
        except Exception as e:
            print(f"[Warning] HTTP 服务启动失败 (端口 {self.http_port}): {e}")

    @pyqtSlot()
    def _on_new_connection(self):
        client = self.ws_server.nextPendingConnection()
        self.clients.append(client)

        client.textMessageReceived.connect(lambda msg, c=client: self._on_text_message(msg, c))
        client.disconnected.connect(lambda c=client: self._on_disconnected(c))

    def _on_disconnected(self, client: QWebSocket):
        if client in self.clients:
            self.clients.remove(client)

    def _on_text_message(self, message: str, client: QWebSocket):
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type in ("keydown", "keyup"):
                key = data.get("key", "")
                self.runner.handle_key_event(key, is_down=(msg_type == "keydown"))
            elif msg_type == "ping":
                client.sendTextMessage(json.dumps({"type": "pong"}))
        except Exception as e:
            pass

    @pyqtSlot(bytes, dict)
    def _on_frame_ready(self, frame_bytes: bytes, status: dict):
        if not self.clients:
            return

        # 广播二进制 JPEG 帧
        for client in self.clients:
            client.sendBinaryMessage(frame_bytes)

        # 附带推送状态 (每 100ms 一次，避免占用带宽)
        status_msg = json.dumps({"type": "status", **status})
        for client in self.clients:
            client.sendTextMessage(status_msg)

    def stop(self):
        self.runner.stop()
        if self.httpd:
            self.httpd.shutdown()
        self.ws_server.close()
