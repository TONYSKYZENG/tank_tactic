#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
from PyQt5.QtWidgets import QApplication

# 确保项目根目录在 sys.path 中
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from map_loader import MapLoader
from mission_loader import MissionLoader
from monitor import MonitorServer, extract_game_state_snapshot

def parse_args():
    parser = argparse.ArgumentParser(description="小霸王坦克大战 (Battle City Pixel) · 装甲集群微操与全知监视系统")
    parser.add_argument("--web", "-w", action="store_true", help="启动无头 WebUI 操作模式 (不弹出桌面 PyQt 窗口，通过浏览器 VNC 操控)")
    parser.add_argument("--port", type=int, default=8080, help="操作端 WebUI HTTP 服务端口 (默认: 8080)")
    parser.add_argument("--ws-port", type=int, default=8765, help="操作端 WebUI WebSocket 串流端口 (默认: 8765)")
    parser.add_argument("--monitor-port", type=int, default=8088, help="辅助只读监视 WebUI 端口 (默认: 8088)")
    parser.add_argument("--monitor-host", type=str, default="0.0.0.0", help="辅助只读监视 WebUI 绑定地址 (默认: 0.0.0.0)")
    parser.add_argument("--mission", type=str, default="missions/mission_01.json", help="指定任务配置文件路径")
    return parser.parse_args()

def main():
    args = parse_args()

    # 1. 加载任务存档 (JSON)
    mission_path = BASE_DIR / args.mission
    if not mission_path.exists():
        print(f"[Error] 任务文件未找到: {mission_path}")
        return 1
    mission = MissionLoader.load_from_file(mission_path)

    # 2. 从纯地图存档 (JSON) 中加载地形
    map_path = BASE_DIR / mission.map_file
    if not map_path.exists():
        print(f"[Error] 地图文件未找到: {map_path}")
        return 1
    game_map = MapLoader.load_from_file(map_path)

    # 3. 准备只读监控状态获取句柄
    active_engine = None
    active_dispatcher = None

    def get_current_state():
        if active_engine and active_dispatcher:
            return extract_game_state_snapshot(active_engine, game_map, active_dispatcher)
        return {"status": "initializing"}

    # 4. 启动【永远在线】的辅助只读全知监控 WebUI (默认 0.0.0.0:8088)
    monitor_server = MonitorServer(
        state_getter=get_current_state,
        host=args.monitor_host,
        port=args.monitor_port
    )
    monitor_server.start()

    # 5. 启动主游戏引擎 (区分 Web VNC 模式与 本地 PyQt 视窗模式)
    if args.web:
        import os
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QApplication(sys.argv)

        from webui.server import WebUIServer
        web_server = WebUIServer(
            mission=mission,
            game_map=game_map,
            base_dir=BASE_DIR,
            http_port=args.port,
            ws_port=args.ws_port
        )
        active_engine = web_server.runner.physics_engine
        active_dispatcher = web_server.runner.command_dispatcher

        print("=" * 64)
        print("🕹️  【操作端 Web VNC】可操控游戏界面已启动")
        print(f"🌐  操控页面: http://localhost:{args.port}")
        print("=" * 64)

        return app.exec_()
    else:
        app = QApplication(sys.argv)
        from gui import MainWindow
        window = MainWindow(mission=mission, game_map=game_map, base_dir=BASE_DIR)
        active_engine = window.canvas.physics_engine
        active_dispatcher = window.canvas.command_dispatcher

        window.show()
        return app.exec_()

if __name__ == "__main__":
    sys.exit(main())
