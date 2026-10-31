from pathlib import Path
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt5.QtGui import QFont, QColor, QPalette
from PyQt5.QtCore import Qt

from map_loader.models import GameMap
from mission_loader.models import Mission
from .game_widget import GameCanvasWidget

class MainWindow(QMainWindow):
    """游戏主窗口：融合 RTS 框选与微操的坦克战略前线"""

    def __init__(self, mission: Mission, game_map: GameMap, base_dir: Path):
        super().__init__()
        self.mission = mission
        self.game_map = game_map
        self.base_dir = base_dir

        self.setWindowTitle(f"小霸王坦克大战 · 装甲集群指挥 [RTS框选与微操模式]")
        self._init_ui()

    def _init_ui(self):
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#141418"))
        palette.setColor(QPalette.WindowText, QColor("#EEEEEE"))
        self.setPalette(palette)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(8)

        # 1. 顶部操作栏与战术说明
        header_layout = QHBoxLayout()

        title_label = QLabel("★ TANK TACTICS · RTS MODE ★")
        title_label.setFont(QFont("Courier New", 14, QFont.Bold))
        title_label.setStyleSheet("color: #E69C24;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        help_label = QLabel(
            "操作: [左键] 框选 | [右键] 移动/集火/护卫友军 | [Tab] 切换微操 | [3] 护卫单位 | [B] 自动开路 | [1/2] 进攻/防守"
        )
        help_label.setFont(QFont("Courier New", 10))
        help_label.setStyleSheet("color: #9999AA;")
        header_layout.addWidget(help_label)

        main_layout.addLayout(header_layout)

        # 2. 游戏画布容器
        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setStyleSheet("border: 2px solid #333344; background-color: #000000;")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = GameCanvasWidget(self.mission, self.game_map, self.base_dir, self)
        frame_layout.addWidget(self.canvas, alignment=Qt.AlignCenter)

        main_layout.addWidget(frame, alignment=Qt.AlignCenter)

        # 3. 底部状态面板 HUD
        status_layout = QHBoxLayout()

        self.hud_label = QLabel("正在组建装甲集群...")
        self.hud_label.setFont(QFont("Courier New", 11, QFont.Bold))
        self.hud_label.setStyleSheet("color: #4AF626;")
        status_layout.addWidget(self.hud_label)

        status_layout.addStretch()

        self.micro_label = QLabel("微操坦克: --")
        self.micro_label.setFont(QFont("Courier New", 11, QFont.Bold))
        self.micro_label.setStyleSheet("color: #F1C40F;")
        status_layout.addWidget(self.micro_label)

        main_layout.addLayout(status_layout)

        self.canvas.status_updated.connect(self._on_status_updated)
        self.setFixedSize(self.sizeHint())

    def _on_status_updated(self, status: dict):
        alive_p = status.get("alive_players", 0)
        enemies = status.get("enemies_left", 0)
        enemies_spotted = status.get("enemies_spotted", 0)
        base_alive = status.get("base_alive", True)
        selected_cnt = status.get("selected_count", 0)
        micro_id = status.get("micro_tank_id", "None")
        micro_tactic = status.get("micro_tactic", "manual")
        auto_clr = status.get("micro_auto_clear", False)
        clr_str = "开路:ON" if auto_clr else "开路:OFF"

        micro_ammo = status.get("micro_ammo", -1)
        if micro_ammo == -1:
            ammo_str = "弹药:无限"
        elif micro_ammo == 0:
            ammo_str = "弹药:0 (耗尽!)"
        else:
            ammo_str = f"弹药:{micro_ammo}"

        fog_on = status.get("fog_enabled", True)
        fog_str = f"侦测:{enemies_spotted}/{enemies}" if fog_on else f"敌军:{enemies}"
        base_str = "安全" if base_alive else "失守!"

        hud_text = f"我方:{alive_p}辆 | 选中:{selected_cnt} | {fog_str} | 要塞:{base_str}"
        self.hud_label.setText(hud_text)

        self.micro_label.setText(f"[{micro_id} | {ammo_str} | 战术:{micro_tactic} | {clr_str}]")

        if status.get("game_over", False):
            self.hud_label.setStyleSheet("color: #E74C3C;")
            self.hud_label.setText(f"GAME OVER: {status.get('defeat_desc', '作战失败')} (按 R 重开)")
        elif status.get("game_victory", False):
            self.hud_label.setStyleSheet("color: #F1C40F;")
            self.hud_label.setText(f"★ 战役大捷！{status.get('victory_desc', '达成作战目标')} (按 R 重开)")
        else:
            self.hud_label.setStyleSheet("color: #4AF626;")
