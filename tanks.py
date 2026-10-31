#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QCoreApplication

# 确保项目根目录在 sys.path 中
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from map_loader import MapLoader
from mission_loader import MissionLoader

def parse_args():
    parser = argparse.ArgumentParser(description="小霸王坦克大战 (Battle City Pixel)")
    parser.add_argument("--web", "-w", action="store_true", help="启动无头 WebUI 模式 (不弹出桌面 PyQt 窗口，通过浏览器 VNC 游玩)")
    parser.add_argument("--port", type=int, default=8080, help="WebUI HTTP 服务端口 (默认: 8080)")
    parser.add_argument("--ws-port", type=int, default=8765, help="WebUI WebSocket 串流端口 (默认: 8765)")
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

    # 3. 区分运行模式
    if args.web:
        # ====== WebUI / 浏览器 VNC 模式 (无桌面窗口) ======
        # 使用 QGuiApplication 或带有 offscreen 平台的 QApplication
        import os
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QApplication(sys.argv)

        from webui.server import WebUIServer
        server = WebUIServer(
            mission=mission,
            game_map=game_map,
            base_dir=BASE_DIR,
            http_port=args.port,
            ws_port=args.ws_port
        )

        print("=" * 64)
        print("🕹️  【小霸王坦克大战】后台引擎已启动 (Headless Web VNC 模式)")
        print(f"🌐  请在浏览器中打开: http://localhost:{args.port}")
        print(f"📡  WebSocket 串流端口: {args.ws_port}")
        print("🎮  无需本地桌面显示环境，随时随地在浏览器中畅玩！")
        print("=" * 64)

        return app.exec_()
    else:
        # ====== 本地原生 PyQt5 GUI 窗口模式 ======
        app = QApplication(sys.argv)
        from gui import MainWindow
        window = MainWindow(mission=mission, game_map=game_map, base_dir=BASE_DIR)
        window.show()
        return app.exec_()

if __name__ == "__main__":
    sys.exit(main())
