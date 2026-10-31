from pathlib import Path
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox
from PyQt5.QtGui import QFont, QColor, QPalette
from PyQt5.QtCore import Qt

from map_loader.models import GameMap
from mission_loader.models import Mission
from translations import i18n, t
from .game_widget import GameCanvasWidget

class MainWindow(QMainWindow):
    """游戏主窗口：融合 RTS 框选与微操的坦克战略前线"""

    def __init__(self, mission: Mission, game_map: GameMap, base_dir: Path):
        super().__init__()
        self.mission = mission
        self.game_map = game_map
        self.base_dir = base_dir
        self.last_status: dict = {}

        self._init_ui()
        self.retranslate_ui()
        i18n.language_changed.connect(self._on_i18n_changed)

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

        self.title_label = QLabel("★ TANK TACTICS · RTS MODE ★")
        self.title_label.setFont(QFont("Courier New", 14, QFont.Bold))
        self.title_label.setStyleSheet("color: #E69C24;")
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        self.help_label = QLabel(
            "操作: [左键] 框选 | [右键] 移动/集火/护卫友军 | [Tab] 切换微操 | [3] 护卫单位 | [B] 自动开路 | [1/2] 进攻/防守"
        )
        self.help_label.setFont(QFont("Courier New", 10))
        self.help_label.setStyleSheet("color: #9999AA;")
        header_layout.addWidget(self.help_label)

        header_layout.addSpacing(10)

        # 语言切换下拉框
        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["🌐 中文", "🌐 English"])
        self.combo_lang.setCurrentIndex(0 if i18n.get_language() == "zh" else 1)
        self.combo_lang.setStyleSheet(
            "QComboBox { background-color: #22222E; color: #E6C66E; border: 1px solid #44445A; "
            "border-radius: 3px; padding: 2px 8px; font-weight: bold; } "
            "QComboBox QAbstractItemView { background-color: #22222E; color: #E6C66E; selection-background-color: #44445A; }"
        )
        self.combo_lang.currentIndexChanged.connect(self._on_lang_combo_changed)
        header_layout.addWidget(self.combo_lang)

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

    def _on_lang_combo_changed(self, idx: int):
        new_lang = "zh" if idx == 0 else "en"
        i18n.set_language(new_lang)

    def _on_i18n_changed(self, lang: str):
        # 阻断下拉框信号以防循环触发
        self.combo_lang.blockSignals(True)
        self.combo_lang.setCurrentIndex(0 if lang == "zh" else 1)
        self.combo_lang.blockSignals(False)
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(t("game.window_title"))
        self.title_label.setText(t("game.header_title"))
        self.help_label.setText(t("game.help_text"))
        if self.last_status:
            self._render_hud(self.last_status)
        else:
            self.hud_label.setText(t("game.building_battalion"))

    def _on_status_updated(self, status: dict):
        self.last_status = status
        self._render_hud(status)

    def _render_hud(self, status: dict):
        alive_p = status.get("alive_players", 0)
        enemies = status.get("enemies_left", 0)
        enemies_spotted = status.get("enemies_spotted", 0)
        base_alive = status.get("base_alive", True)
        selected_cnt = status.get("selected_count", 0)
        micro_id = status.get("micro_tank_id", "None")
        micro_tactic = status.get("micro_tactic", "manual")
        auto_clr = status.get("micro_auto_clear", False)
        clr_str = t("game.clear_on") if auto_clr else t("game.clear_off")

        micro_ammo = status.get("micro_ammo", -1)
        if micro_ammo == -1:
            ammo_str = t("game.ammo_infinite")
        elif micro_ammo == 0:
            ammo_str = t("game.ammo_empty")
        else:
            ammo_str = t("game.ammo_count", ammo=micro_ammo)

        fog_on = status.get("fog_enabled", True)
        fog_str = t("game.fog_detected", spotted=enemies_spotted, total=enemies) if fog_on else t("game.enemy_count", count=enemies)
        base_str = t("game.base_safe") if base_alive else t("game.base_lost")

        hud_text = t("game.hud_format", alive=alive_p, selected=selected_cnt, fog=fog_str, base=base_str)
        self.hud_label.setText(hud_text)

        self.micro_label.setText(f"[{micro_id} | {ammo_str} | {micro_tactic} | {clr_str}]")

        if status.get("game_over", False):
            self.hud_label.setStyleSheet("color: #E74C3C;")
            self.hud_label.setText(t("game.game_over", desc=status.get('defeat_desc', '作战失败')))
        elif status.get("game_victory", False):
            self.hud_label.setStyleSheet("color: #F1C40F;")
            self.hud_label.setText(t("game.game_victory", desc=status.get('victory_desc', '达成作战目标')))
        else:
            self.hud_label.setStyleSheet("color: #4AF626;")
