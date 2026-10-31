from pathlib import Path
from typing import Optional, List, Dict, Any
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QComboBox, QPushButton, QSpinBox, QProgressBar, QGroupBox
)
from PyQt5.QtGui import QFont, QColor, QPalette
from PyQt5.QtCore import Qt

from map_loader.models import GameMap
from mission_loader.models import Mission
from translations import i18n, t
from converter.loader import RecipeRegistry
from .game_widget import GameCanvasWidget

class MainWindow(QMainWindow):
    """游戏主窗口：融合 RTS 框选与微操的坦克战略前线，附带资源经济与配方转换侧边栏"""

    def __init__(self, mission: Mission, game_map: GameMap, base_dir: Path):
        super().__init__()
        self.mission = mission
        self.game_map = game_map
        self.base_dir = base_dir
        self.last_status: dict = {}
        self._current_conv_table: List[str] = []

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

        # 2. 中间区域：左边主游戏画布 + 右边战术侧边栏 (Sidebar)
        mid_layout = QHBoxLayout()
        mid_layout.setSpacing(12)

        # 游戏画布容器
        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setStyleSheet("border: 2px solid #333344; background-color: #000000;")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = GameCanvasWidget(self.mission, self.game_map, self.base_dir, self)
        frame_layout.addWidget(self.canvas, alignment=Qt.AlignCenter)
        mid_layout.addWidget(frame, alignment=Qt.AlignCenter)

        # 右侧战术与转换控制面板 (Sidebar)
        sidebar = self._create_sidebar()
        mid_layout.addWidget(sidebar)

        main_layout.addLayout(mid_layout)

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

    def _create_sidebar(self) -> QWidget:
        """构建右侧经济与转换器侧边栏"""
        sidebar = QFrame()
        sidebar.setFixedWidth(270)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #181822;
                border: 1px solid #3A3A52;
                border-radius: 4px;
            }
            QGroupBox {
                color: #F1C40F;
                font-weight: bold;
                border: 1px solid #444460;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
        """)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # 1. 战术资源储备面板
        self.res_group = QGroupBox("★ 战术资源储备")
        res_layout = QVBoxLayout(self.res_group)
        res_layout.setSpacing(6)

        self.lbl_res_dm = QLabel("🔮 暗物质: 0.0 (+0.0/s)")
        self.lbl_res_dm.setFont(QFont("Courier New", 10, QFont.Bold))
        self.lbl_res_dm.setStyleSheet("color: #C39BD3; border: none;")
        res_layout.addWidget(self.lbl_res_dm)

        self.lbl_res_alloy = QLabel("⚙️ 合金: 0.0 (+0.0/s)")
        self.lbl_res_alloy.setFont(QFont("Courier New", 10, QFont.Bold))
        self.lbl_res_alloy.setStyleSheet("color: #5DADE2; border: none;")
        res_layout.addWidget(self.lbl_res_alloy)

        layout.addWidget(self.res_group)

        # 2. 转换机控制中枢面板
        self.conv_group = QGroupBox("⚗️ 资源转换工坊")
        conv_layout = QVBoxLayout(self.conv_group)
        conv_layout.setSpacing(8)

        self.lbl_conv_unit = QLabel("执行车: --")
        self.lbl_conv_unit.setFont(QFont("Courier New", 10, QFont.Bold))
        self.lbl_conv_unit.setStyleSheet("color: #F4D03F; border: none;")
        conv_layout.addWidget(self.lbl_conv_unit)

        # 无转换机时的提示标签
        self.lbl_no_converter = QLabel("此单位未搭载转换机")
        self.lbl_no_converter.setStyleSheet("color: #888899; font-style: italic; border: none; padding: 10px 0;")
        conv_layout.addWidget(self.lbl_no_converter)

        # 有转换机时的操作控件容器
        self.conv_controls_widget = QWidget()
        self.conv_controls_widget.setStyleSheet("border: none;")
        ctrl_layout = QVBoxLayout(self.conv_controls_widget)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(8)

        self.lbl_recipe_select = QLabel("转换配方:")
        self.lbl_recipe_select.setStyleSheet("color: #D5D8DC; font-weight: bold;")
        ctrl_layout.addWidget(self.lbl_recipe_select)

        self.combo_recipe = QComboBox()
        self.combo_recipe.setStyleSheet("""
            QComboBox {
                background-color: #222230;
                color: #FFFFFF;
                border: 1px solid #555577;
                padding: 3px 6px;
                font-size: 11px;
            }
        """)
        self.combo_recipe.currentIndexChanged.connect(self._on_recipe_combo_changed)
        ctrl_layout.addWidget(self.combo_recipe)

        self.lbl_recipe_detail = QLabel("")
        self.lbl_recipe_detail.setStyleSheet("color: #AAB7B8; font-size: 10px;")
        self.lbl_recipe_detail.setWordWrap(True)
        ctrl_layout.addWidget(self.lbl_recipe_detail)

        # 批次数量输入
        count_layout = QHBoxLayout()
        self.lbl_count_tag = QLabel("批次:")
        self.lbl_count_tag.setStyleSheet("color: #D5D8DC;")
        count_layout.addWidget(self.lbl_count_tag)

        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, 99)
        self.spin_count.setValue(1)
        self.spin_count.setStyleSheet("background-color: #222230; color: #FFF; border: 1px solid #555577;")
        count_layout.addWidget(self.spin_count)
        ctrl_layout.addLayout(count_layout)

        # 开始转换按钮
        self.btn_convert = QPushButton("⚗️ 开始转换")
        self.btn_convert.setStyleSheet("""
            QPushButton {
                background-color: #1A5276;
                color: #EBF5FB;
                border: 1px solid #2980B9;
                padding: 5px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #2471A3; }
            QPushButton:pressed { background-color: #154360; }
        """)
        self.btn_convert.clicked.connect(self._on_start_convert_clicked)
        ctrl_layout.addWidget(self.btn_convert)

        # 转换状态与进度条
        self.lbl_conv_status = QLabel("状态: 空闲 (就绪)")
        self.lbl_conv_status.setFont(QFont("Courier New", 9))
        self.lbl_conv_status.setStyleSheet("color: #A0A0B0;")
        ctrl_layout.addWidget(self.lbl_conv_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #44445A;
                border-radius: 2px;
                text-align: center;
                background-color: #111118;
                color: #FFFFFF;
                height: 16px;
                font-size: 10px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #117A65, stop:1 #1ABC9C);
            }
        """)
        ctrl_layout.addWidget(self.progress_bar)

        info_grid = QHBoxLayout()
        self.lbl_conv_batch = QLabel("批次: 0 / 0")
        self.lbl_conv_batch.setStyleSheet("color: #BDC3C7; font-size: 10px;")
        info_grid.addWidget(self.lbl_conv_batch)

        self.lbl_conv_time = QLabel("剩余: 0.0s")
        self.lbl_conv_time.setStyleSheet("color: #BDC3C7; font-size: 10px;")
        info_grid.addWidget(self.lbl_conv_time)
        ctrl_layout.addLayout(info_grid)

        self.lbl_conv_queue = QLabel("队列: 0 项")
        self.lbl_conv_queue.setStyleSheet("color: #99A3A4; font-size: 10px;")
        ctrl_layout.addWidget(self.lbl_conv_queue)

        # 终止转换按钮
        self.btn_terminate = QPushButton("⛔ 终止转换")
        self.btn_terminate.setStyleSheet("""
            QPushButton {
                background-color: #78281F;
                color: #FDEDEC;
                border: 1px solid #B03A2E;
                padding: 4px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #922B21; }
            QPushButton:pressed { background-color: #641E16; }
            QPushButton:disabled { background-color: #332222; color: #665555; border-color: #443333; }
        """)
        self.btn_terminate.clicked.connect(self._on_terminate_convert_clicked)
        self.btn_terminate.setEnabled(False)
        ctrl_layout.addWidget(self.btn_terminate)

        conv_layout.addWidget(self.conv_controls_widget)
        self.conv_controls_widget.setVisible(False)

        layout.addWidget(self.conv_group)
        layout.addStretch()
        return sidebar

    def _on_recipe_combo_changed(self):
        r_id = self.combo_recipe.currentData()
        if not r_id:
            self.lbl_recipe_detail.setText("")
            return
        recipe = RecipeRegistry.get(r_id)
        if not recipe:
            self.lbl_recipe_detail.setText("")
            return

        if recipe.inputs:
            in_str = ", ".join(f"{v:g} {k}" for k, v in recipe.inputs.items())
        else:
            in_str = "无 (Free)"

        if recipe.output_type == "tank":
            ammo_str = "∞" if recipe.ammo < 0 else str(recipe.ammo)
            out_str = f"战车 (Tank) [辨识度:{recipe.visibility:.1f}, 视野:{recipe.vision_size:.0f}, 弹药:{ammo_str}]"
        elif isinstance(recipe.outputs, dict):
            out_str = ", ".join(f"{v:g} {k}" for k, v in recipe.outputs.items())
        else:
            out_str = str(recipe.outputs)
        self.lbl_recipe_detail.setText(f"消耗: {in_str}\n产出: {out_str} ({recipe.duration:.1f}s)")

    def _on_start_convert_clicked(self):
        micro = self.last_status.get("micro_tank")
        if not micro or not micro.alive:
            return
        recipe_id = self.combo_recipe.currentData()
        if not recipe_id:
            return
        count = self.spin_count.value()
        self.canvas.api_controller.convert({"unit_id": micro.id, "recipe_id": recipe_id, "count": count})

    def _on_terminate_convert_clicked(self):
        micro = self.last_status.get("micro_tank")
        if micro:
            self.canvas.api_controller.terminate_convert({"unit_id": micro.id})
        else:
            self.canvas.api_controller.terminate_convert({})

    def _on_lang_combo_changed(self, idx: int):
        new_lang = "zh" if idx == 0 else "en"
        i18n.set_language(new_lang)

    def _on_i18n_changed(self, lang: str):
        self.combo_lang.blockSignals(True)
        self.combo_lang.setCurrentIndex(0 if lang == "zh" else 1)
        self.combo_lang.blockSignals(False)
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(t("game.window_title"))
        self.title_label.setText(t("game.header_title"))
        self.help_label.setText(t("game.help_text"))
        self.res_group.setTitle(t("converter.resources_title"))
        self.conv_group.setTitle(t("converter.title"))
        self.lbl_no_converter.setText(t("converter.no_converter"))
        self.lbl_recipe_select.setText(t("converter.recipe_select"))
        self.lbl_count_tag.setText(t("converter.count"))
        self.btn_convert.setText(t("converter.start"))
        self.btn_terminate.setText(t("converter.terminate"))

        # 刷新下拉框文字
        curr_recipe_id = self.combo_recipe.currentData()
        self.combo_recipe.blockSignals(True)
        self.combo_recipe.clear()
        for r_id in self._current_conv_table:
            r = RecipeRegistry.get(r_id)
            if r:
                display = t(f"converter.recipe.{r.name.split('.')[-1]}") if r.name.startswith("converter.") else r.name
                self.combo_recipe.addItem(display, r_id)
        if curr_recipe_id:
            idx = self.combo_recipe.findData(curr_recipe_id)
            if idx >= 0:
                self.combo_recipe.setCurrentIndex(idx)
        self.combo_recipe.blockSignals(False)
        self._on_recipe_combo_changed()

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
        micro = status.get("micro_tank")
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

        # 1. 刷新侧边栏经济资源储备
        res = status.get("resources", {})
        rates = status.get("resource_rates", {})
        dm_amt = res.get("dark_matter", 0.0)
        alloy_amt = res.get("alloy", 0.0)
        dm_rate = rates.get("dark_matter", 0.0)
        alloy_rate = rates.get("alloy", 0.0)
        self.lbl_res_dm.setText(f"🔮 {t('converter.dark_matter')}: {dm_amt:.1f} ({t('converter.rate', rate=f'{dm_rate:.1f}')})")
        self.lbl_res_alloy.setText(f"⚙️ {t('converter.alloy')}: {alloy_amt:.1f} ({t('converter.rate', rate=f'{alloy_rate:.1f}')})")

        # 2. 刷新微操坦克的转换器面板
        conv_tbl = status.get("converter_table", [])
        conv_stat = status.get("converter_status")

        if micro and conv_tbl:
            self.lbl_no_converter.setVisible(False)
            self.conv_controls_widget.setVisible(True)
            self.lbl_conv_unit.setText(f"{t('converter.unit_tag')} {micro.id} [{micro.unit_type}]")

            # 若配方表发生变更，重新填充配方下拉框
            if conv_tbl != self._current_conv_table:
                self._current_conv_table = list(conv_tbl)
                self.combo_recipe.blockSignals(True)
                self.combo_recipe.clear()
                for r_id in conv_tbl:
                    r = RecipeRegistry.get(r_id)
                    if r:
                        display = t(f"converter.recipe.{r.name.split('.')[-1]}") if r.name.startswith("converter.") else r.name
                        self.combo_recipe.addItem(display, r_id)
                self.combo_recipe.blockSignals(False)
                self._on_recipe_combo_changed()

            # 刷新转换进度与队列状态
            if conv_stat and conv_stat.get("is_converting"):
                self.lbl_conv_status.setText(t("converter.status_converting"))
                self.lbl_conv_status.setStyleSheet("color: #00E5FF; font-weight: bold;")
                self.progress_bar.setValue(int(conv_stat.get("progress_percentage", 0)))
                curr_b = conv_stat.get("completed_count", 0) + 1
                tot_b = conv_stat.get("total_count", 1)
                self.lbl_conv_batch.setText(t("converter.batch", curr=curr_b, total=tot_b))
                self.lbl_conv_time.setText(t("converter.remaining", sec=f"{conv_stat.get('remaining_seconds', 0.0):.1f}"))
                self.lbl_conv_queue.setText(t("converter.queue_len", len=conv_stat.get("queue_length", 0)))
                self.btn_terminate.setEnabled(True)
            else:
                self.lbl_conv_status.setText(t("converter.status_idle"))
                self.lbl_conv_status.setStyleSheet("color: #A0A0B0;")
                self.progress_bar.setValue(0)
                self.lbl_conv_batch.setText(t("converter.batch", curr=0, total=0))
                self.lbl_conv_time.setText(t("converter.remaining", sec="0.0"))
                self.lbl_conv_queue.setText(t("converter.queue_len", len=0))
                self.btn_terminate.setEnabled(False)
        else:
            self.lbl_conv_unit.setText(f"{t('converter.unit_tag')} {micro.id if micro else '--'}")
            self.lbl_no_converter.setVisible(True)
            self.conv_controls_widget.setVisible(False)
            self._current_conv_table.clear()

        # 3. 胜负判断展示
        if status.get("game_over", False):
            self.hud_label.setStyleSheet("color: #E74C3C;")
            self.hud_label.setText(t("game.game_over", desc=status.get('defeat_desc', '作战失败')))
        elif status.get("game_victory", False):
            self.hud_label.setStyleSheet("color: #F1C40F;")
            self.hud_label.setText(t("game.game_victory", desc=status.get('victory_desc', '达成作战目标')))
        else:
            self.hud_label.setStyleSheet("color: #4AF626;")
