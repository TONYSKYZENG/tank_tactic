import json
import time
import logging
from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtNetwork import QUdpSocket, QHostAddress

logger = logging.getLogger("UDPBeaconServer")

class UDPBeaconServer(QObject):
    """
    UDP 探针与发现服务：
    1. 上线后立即广播“我在这里”心跳数据包（包含 UDP/TCP/WS 各服务端口与在线状态）；
    2. 定时向本地子网广播心跳，支持局域网自动发现；
    3. 支持无连接的 UDP 纯文本 JSON API 调用：客户端直接向 UDP 端口发送 JSON 请求，服务器直接原路应答 JSON 响应。
    """

    def __init__(self, api_controller, host: str = "0.0.0.0", port: int = 8092,
                 tcp_port: int = 8091, ws_port: int = 8090, parent=None):
        super().__init__(parent)
        self.api_controller = api_controller
        self.host = host
        self.port = port
        self.tcp_port = tcp_port
        self.ws_port = ws_port

        self.udp_socket = QUdpSocket(self)
        self.beacon_timer = QTimer(self)
        self.beacon_timer.timeout.connect(self.broadcast_beacon)

    def start(self) -> bool:
        addr = QHostAddress(self.host) if self.host != "0.0.0.0" else QHostAddress.Any
        # 允许端口复用与广播
        if not self.udp_socket.bind(addr, self.port, QUdpSocket.ShareAddress | QUdpSocket.ReuseAddressHint):
            logger.error("UDP Beacon failed to bind on %s:%d: %s", self.host, self.port, self.udp_socket.errorString())
            return False

        self.udp_socket.readyRead.connect(self._on_ready_read)
        logger.info("UDP Beacon & API Server listening on %s:%d", self.host, self.port)

        # 立即上线广播“我在这里”
        self.broadcast_beacon()

        # 每 5 秒发送一次周期广播心跳
        self.beacon_timer.start(5000)
        return True

    def stop(self):
        self.beacon_timer.stop()
        self.udp_socket.close()

    def broadcast_beacon(self):
        """向网络广播‘我在这里’上线数据包"""
        beacon_data = {
            "service": "tanks_tactic_api",
            "status": "online",
            "message": "我在这里",
            "udp_port": self.port,
            "tcp_port": self.tcp_port,
            "ws_port": self.ws_port,
            "timestamp": round(time.time(), 3)
        }
        raw_bytes = json.dumps(beacon_data, ensure_ascii=False).encode("utf-8")

        try:
            # 广播至全网与本地回环
            self.udp_socket.writeDatagram(raw_bytes, QHostAddress.Broadcast, self.port)
            self.udp_socket.writeDatagram(raw_bytes, QHostAddress.LocalHost, self.port)
        except Exception as e:
            logger.debug("UDP beacon write failed: %s", e)

    def _on_ready_read(self):
        while self.udp_socket.hasPendingDatagrams():
            size = self.udp_socket.pendingDatagramSize()
            datagram, sender_host, sender_port = self.udp_socket.readDatagram(size)

            if not datagram:
                continue

            try:
                raw_text = datagram.decode("utf-8", errors="ignore").strip()
            except Exception:
                continue

            # 忽略自己发送的心跳广播包
            if '"message": "我在这里"' in raw_text and '"status": "online"' in raw_text:
                continue

            # 处理客户端发送的 JSON 调用请求
            resp_str = self.api_controller.handle_request(raw_text)
            resp_bytes = resp_str.encode("utf-8")

            try:
                self.udp_socket.writeDatagram(resp_bytes, sender_host, sender_port)
            except Exception as e:
                logger.error("Failed to reply UDP datagram to %s:%d: %s", sender_host.toString(), sender_port, e)
