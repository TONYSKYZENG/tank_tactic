import logging
from typing import Optional, Callable
from PyQt5.QtCore import QObject
from .controller import GameAPIController
from .tcp_server import RawTCPIPServer
from .ws_server import WebSocketAPIServer
from .udp_beacon import UDPBeaconServer

logger = logging.getLogger("APIServerManager")

class APIServerManager(QObject):
    """
    统一网络 API 管理中枢：
    管理并运行：
    - WebSocket API (默认端口 8090)
    - 原始 TCP/IP API (默认端口 8091)
    - UDP 探针广播与 API (默认端口 8092)
    """

    def __init__(self, game_context, host: str = "0.0.0.0",
                 ws_port: int = 8090, tcp_port: int = 8091, udp_port: int = 8092,
                 termination_handler: Optional[Callable] = None, parent=None):
        super().__init__(parent)
        self.game_context = game_context
        self.host = host
        self.ws_port = ws_port
        self.tcp_port = tcp_port
        self.udp_port = udp_port

        # 核心控制器
        self.controller = GameAPIController(
            game_context=self.game_context,
            termination_handler=termination_handler or self.stop
        )

        # 三大协议服务器
        self.ws_server = WebSocketAPIServer(self.controller, host=self.host, port=self.ws_port, parent=self)
        self.tcp_server = RawTCPIPServer(self.controller, host=self.host, port=self.tcp_port, parent=self)
        self.udp_beacon = UDPBeaconServer(
            self.controller,
            host=self.host,
            port=self.udp_port,
            tcp_port=self.tcp_port,
            ws_port=self.ws_port,
            parent=self
        )

    def start(self) -> bool:
        ws_ok = self.ws_server.start()
        tcp_ok = self.tcp_server.start()
        udp_ok = self.udp_beacon.start()

        print("=" * 64)
        print("🚀  【Tanks Network API】三合一控制接口服务已启动")
        print(f"📡  WebSocket API: ws://{self.host}:{self.ws_port}")
        print(f"🔌  Raw TCP/IP API: tcp://{self.host}:{self.tcp_port}")
        print(f"📢  UDP Beacon/API: udp://{self.host}:{self.udp_port} (广播: '我在这里')")
        print("=" * 64)

        return ws_ok and tcp_ok and udp_ok

    def stop(self):
        self.ws_server.stop()
        self.tcp_server.stop()
        self.udp_beacon.stop()
