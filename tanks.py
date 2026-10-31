#!/usr/bin/env python3
import sys
from pathlib import Path
from PyQt5.QtWidgets import QApplication

# 确保项目根目录在 sys.path 中
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from map_loader import MapLoader
from mission_loader import MissionLoader
from gui import MainWindow

def main():
    # 1. 加载任务存档 (JSON)
    mission_path = BASE_DIR / "missions" / "mission_01.json"
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

    # 3. 初始化并运行 PyQt5 游戏
    app = QApplication(sys.argv)
    window = MainWindow(mission=mission, game_map=game_map, base_dir=BASE_DIR)
    window.show()

    return app.exec_()

if __name__ == "__main__":
    sys.exit(main())
