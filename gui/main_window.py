from pathlib import Path
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt5.QtGui import QFont, QColor, QPalette
from PyQt5.QtCore import Qt

from map_loader.models import GameMap
from mission_loader.models import Mission
from .game_widget import GameCanvasWidget

class MainWindow(QMainWindow):
    """游戏主窗口"""

    def __init__(self, mission: Mission, game_map: GameMap, base_dir: Path):
        super().__init__()
        self.mission = mission
        self.game_map = game_map
        self.base_dir = base_dir

        self.setWindowTitle(f"小霸王坦克大战 - {self.mission.name}")
        self._init_ui()

    def _init_ui(self):
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#1C1C1C"))
        palette.setColor(QPalette.WindowText, QColor("#EEEEEE"))
        self.setPalette(palette)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        # 顶部复古标题栏与操作说明
        header_layout = QHBoxLayout()

        title_label = QLabel("★ BATTLE CITY PIXEL ★")
        title_label.setFont(QFont("Courier New", 15, QFont.Bold))
        title_label.setStyleSheet("color: #E69C24;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        help_label = QLabel("控制: [方向键/WASD] 移动 | [空格键] 开火")
        help_label.setFont(QFont("Courier New", 11))
        help_label.setStyleSheet("color: #AAAAAA;")
        header_layout.addWidget(help_label)

        main_layout.addLayout(header_layout)

        # 游戏画布容器（加复古像素外边框）
        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setStyleSheet("border: 2px solid #444444; background-color: #000000;")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = GameCanvasWidget(self.mission, self.game_map, self.base_dir, self)
        frame_layout.addWidget(self.canvas, alignment=Qt.AlignCenter)

        main_layout.addWidget(frame, alignment=Qt.AlignCenter)

        # 底部状态栏 HUD
        status_layout = QHBoxLayout()

        self.hud_label = QLabel("正在初始化任务战局...")
        self.hud_label.setFont(QFont("Courier New", 12, QFont.Bold))
        self.hud_label.setStyleSheet("color: #4AF626;")
        status_layout.addWidget(self.hud_label)

        status_layout.addStretch()

        self.mission_label = QLabel(f"任务: {self.mission.name}")
        self.mission_label.setFont(QFont("Courier New", 11))
        self.mission_label.setStyleSheet("color: #888888;")
        status_layout.addWidget(self.mission_label)

        main_layout.addLayout(status_layout)

        self.canvas.status_updated.connect(self._on_status_updated)
        self.setFixedSize(self.sizeHint())

    def _on_status_updated(self, status: dict):
        hp = status.get("player_hp", 0)
        enemies_left = status.get("enemies_left", 0)
        base_alive = status.get("base_alive", True)

        hp_str = "♥ " * hp
        base_str = "基地安全" if base_alive else "基地失守!"

        hud_text = f"生命: {hp_str:<6} | 敌军残余: {enemies_left} | 鹰巢: {base_str}"
        self.hud_label.setText(hud_text)

        if not base_alive or hp <= 0:
            self.hud_label.setStyleSheet("color: #E74C3C;")
        elif enemies_left == 0:
            self.hud_label.setStyleSheet("color: #F1C40F;")
            self.hud_label.setText(f"★ 任务达成！敌军全歼！ | 鹰巢: {base_str}")
        else:
            self.hud_label.setStyleSheet("color: #4AF626;")
