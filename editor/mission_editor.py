import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QGroupBox, QSpinBox, QDoubleSpinBox, QLineEdit, QScrollArea, QFrame,
    QCheckBox, QMessageBox, QListWidget, QListWidgetItem, QTabWidget
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt, pyqtSignal

from map_loader.models import GameMap
from mission_loader.models import Mission, PlayerMissionInfo, EnemyMissionInfo, SpawnPoint
from tank_configs.config_loader import TankConfig
from .canvas import EditorCanvas, EditorMode

class MissionEditorWidget(QWidget):
    """
    【模式 2：任务与单位编辑】
    - 加载地图后可视化放置单位与设定出生点
    - 单位列表切换与地图点击互选
    - ★ 属性设置区域置入 QScrollArea 实现上下平滑滚动，杜绝属性过多显示不全
    - 支持我方编队、敌军战车、防御塔、AI战术脚本、迷雾与弹药总开关配置
    """

    mission_modified = pyqtSignal()
    coord_status_changed = pyqtSignal(str)
    new_mission_requested = pyqtSignal()

    def __init__(self, canvas: Optional[EditorCanvas] = None, base_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.canvas = canvas if canvas is not None else EditorCanvas()
        self.canvas.mode = EditorMode.UNIT_EDIT
        self.base_dir = base_dir if base_dir is not None else Path(".")

        self.current_mission: Optional[Mission] = None
        self.player_units: List[PlayerMissionInfo] = []
        self.enemies: List[EnemyMissionInfo] = []
        self.active_unit: Optional[Any] = None

        self._available_configs = self._scan_tank_configs()
        self._available_scripts = self._scan_ai_scripts()
        self._init_ui()

    def set_map(self, game_map: GameMap):
        self.canvas.set_map(game_map)
        self.canvas.set_units(self.player_units, self.enemies)

    @property
    def enemy_units(self) -> List[EnemyMissionInfo]:
        return self.enemies

    def _scan_tank_configs(self) -> List[str]:
        cfg_dir = self.base_dir / "tank_configs"
        if not cfg_dir.exists():
            return ["tank_configs/player_tank.json", "tank_configs/clearing_tank.json", "tank_configs/enemy_basic.json"]
        configs = []
        for p in sorted(cfg_dir.glob("*.json")):
            configs.append(f"tank_configs/{p.name}")
        return configs if configs else ["tank_configs/player_tank.json"]

    def _scan_ai_scripts(self) -> List[str]:
        ai_dir = self.base_dir / "ai_python"
        scripts = ["(无脚本 - 玩家控制/自主战术)"]
        if ai_dir.exists():
            for p in sorted(ai_dir.glob("*.py")):
                if p.name not in ("__init__.py", "manager.py", "bridge.py"):
                    scripts.append(f"ai_python/{p.name}")
        return scripts

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        # ===== 左侧单位管理器面板 =====
        left_panel = QFrame()
        left_panel.setFixedWidth(280)
        left_panel.setStyleSheet("background-color: #221E19; border: 1px solid #4D3C26; border-radius: 4px;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(10)

        title_label = QLabel("🛡 任务单位编队管理")
        title_label.setFont(QFont("Palatino", 13, QFont.Bold))
        title_label.setStyleSheet("color: #E6C66E; border: none;")
        left_layout.addWidget(title_label)

        # 1. 单位快捷放置按钮
        btn_layout = QHBoxLayout()
        self.btn_add_player = QPushButton("+ 我方单位")
        self.btn_add_player.setStyleSheet("background-color: #1F3A52; border: 1px solid #2980B9; color: #AED6F1;")
        self.btn_add_player.clicked.connect(self._on_add_player_clicked)
        btn_layout.addWidget(self.btn_add_player)

        self.btn_add_enemy = QPushButton("+ 敌军单位")
        self.btn_add_enemy.setStyleSheet("background-color: #4A1A17; border: 1px solid #C0392B; color: #F5B7B1;")
        self.btn_add_enemy.clicked.connect(self._on_add_enemy_clicked)
        btn_layout.addWidget(self.btn_add_enemy)
        left_layout.addLayout(btn_layout)

        # 2. 单位列表
        self.unit_list = QListWidget()
        self.unit_list.setStyleSheet("background-color: #151310; border: 1px solid #5C482C;")
        self.unit_list.currentRowChanged.connect(self._on_unit_list_selection_changed)
        left_layout.addWidget(self.unit_list, stretch=1)

        # 3. 列表管理按钮
        list_btn_layout = QHBoxLayout()
        self.btn_del_unit = QPushButton("- 删除选中")
        self.btn_del_unit.clicked.connect(self._on_delete_unit_clicked)
        list_btn_layout.addWidget(self.btn_del_unit)

        self.btn_dup_unit = QPushButton("⎘ 复制单位")
        self.btn_dup_unit.clicked.connect(self._on_duplicate_unit_clicked)
        list_btn_layout.addWidget(self.btn_dup_unit)
        left_layout.addLayout(list_btn_layout)

        # 4. 全局任务环境设置
        global_group = QGroupBox("★ 任务环境规则")
        global_layout = QVBoxLayout(global_group)

        # 任务名
        m_name_layout = QHBoxLayout()
        m_name_layout.addWidget(QLabel("任务名:"))
        self.edit_mission_name = QLineEdit("Custom Mission")
        self.edit_mission_name.textChanged.connect(self._on_mission_meta_changed)
        m_name_layout.addWidget(self.edit_mission_name)
        global_layout.addLayout(m_name_layout)

        # 关联地图路径
        m_map_layout = QHBoxLayout()
        m_map_layout.addWidget(QLabel("地图文件:"))
        self.edit_map_file = QLineEdit("maps/level_01.json")
        self.edit_map_file.textChanged.connect(self._on_mission_meta_changed)
        m_map_layout.addWidget(self.edit_map_file)
        global_layout.addLayout(m_map_layout)

        # 开关
        self.chk_fog = QCheckBox("启用战争迷雾系统 (Fog of War)")
        self.chk_fog.setChecked(True)
        self.chk_fog.toggled.connect(self._on_mission_meta_changed)
        global_layout.addWidget(self.chk_fog)

        self.chk_ammo = QCheckBox("启用有限弹药系统 (Limited Ammo)")
        self.chk_ammo.setChecked(True)
        self.chk_ammo.toggled.connect(self._on_mission_meta_changed)
        global_layout.addWidget(self.chk_ammo)

        btn_new_mission = QPushButton("⚔ 新建全新任务")
        btn_new_mission.setStyleSheet("background-color: #2E4053; border: 1px solid #5D6D7E; color: #EAECEE; margin-top: 6px;")
        btn_new_mission.clicked.connect(self._on_new_mission_clicked)
        global_layout.addWidget(btn_new_mission)

        left_layout.addWidget(global_group)
        main_layout.addWidget(left_panel)

        # ===== 中间地图画布视口 =====
        self.scroll_canvas = QScrollArea()
        self.scroll_canvas.setWidgetResizable(True)
        self.scroll_canvas.setStyleSheet("background-color: #12100E; border: 2px solid #5C482C;")
        self.scroll_canvas.setAlignment(Qt.AlignCenter)
        self.scroll_canvas.setWidget(self.canvas)
        main_layout.addWidget(self.scroll_canvas, stretch=2)

        # ===== 右侧：可滚动的属性设置区域 (Scrollable Property Inspector) =====
        right_panel = QFrame()
        right_panel.setFixedWidth(340)
        right_panel.setStyleSheet("background-color: #221E19; border: 1px solid #4D3C26; border-radius: 4px;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(6)

        prop_header = QLabel("⚙ 单位属性检视面板")
        prop_header.setFont(QFont("Palatino", 13, QFont.Bold))
        prop_header.setStyleSheet("color: #F1C40F; border: none; padding-left: 6px;")
        right_layout.addWidget(prop_header)

        # ★★★ 关键要求：属性设置区域上下滚动 ★★★
        self.prop_scroll_area = QScrollArea()
        self.prop_scroll_area.setWidgetResizable(True)
        self.prop_scroll_area.setStyleSheet("QScrollArea { border: 1px solid #3E301E; background-color: #191612; }")

        prop_container = QWidget()
        self.prop_layout = QVBoxLayout(prop_container)
        self.prop_layout.setContentsMargins(8, 8, 8, 8)
        self.prop_layout.setSpacing(12)

        # 1. 基础属性
        basic_group = QGroupBox("1. 身份与阵营")
        basic_layout = QVBoxLayout(basic_group)

        id_layout = QHBoxLayout()
        id_layout.addWidget(QLabel("唯一 ID:"))
        self.edit_id = QLineEdit()
        self.edit_id.textChanged.connect(self._on_prop_changed)
        id_layout.addWidget(self.edit_id)
        basic_layout.addLayout(id_layout)

        camp_layout = QHBoxLayout()
        camp_layout.addWidget(QLabel("所属阵营:"))
        self.combo_camp = QComboBox()
        self.combo_camp.addItems(["我方编组 (PLAYER)", "敌方军团 (ENEMY)"])
        self.combo_camp.currentIndexChanged.connect(self._on_camp_changed)
        camp_layout.addWidget(self.combo_camp)
        basic_layout.addLayout(camp_layout)

        cfg_layout = QHBoxLayout()
        cfg_layout.addWidget(QLabel("单位模板:"))
        self.combo_config = QComboBox()
        self.combo_config.addItems(self._available_configs)
        self.combo_config.currentIndexChanged.connect(self._on_config_template_changed)
        cfg_layout.addWidget(self.combo_config)
        basic_layout.addLayout(cfg_layout)

        self.prop_layout.addWidget(basic_group)

        # 2. 出生坐标
        pos_group = QGroupBox("2. 出生地图坐标")
        pos_layout = QVBoxLayout(pos_group)

        coord_layout = QHBoxLayout()
        coord_layout.addWidget(QLabel("列号 (Col X):"))
        self.spin_spawn_x = QSpinBox()
        self.spin_spawn_x.setRange(0, 100)
        self.spin_spawn_x.valueChanged.connect(self._on_prop_changed)
        coord_layout.addWidget(self.spin_spawn_x)

        coord_layout.addWidget(QLabel("行号 (Row Y):"))
        self.spin_spawn_y = QSpinBox()
        self.spin_spawn_y.setRange(0, 100)
        self.spin_spawn_y.valueChanged.connect(self._on_prop_changed)
        coord_layout.addWidget(self.spin_spawn_y)
        pos_layout.addLayout(coord_layout)

        self.btn_pick_spawn = QPushButton("📍 在地图上点击选定出生点")
        self.btn_pick_spawn.setStyleSheet("background-color: #5D4037; border: 1px solid #C8A048; color: #FFF3BD;")
        self.btn_pick_spawn.clicked.connect(self._on_pick_spawn_clicked)
        pos_layout.addWidget(self.btn_pick_spawn)

        self.prop_layout.addWidget(pos_group)

        # 3. 战斗、视野与弹药
        combat_group = QGroupBox("3. 战备与侦测参数")
        combat_layout = QVBoxLayout(combat_group)

        vis_size_layout = QHBoxLayout()
        vis_size_layout.addWidget(QLabel("视野尺寸:"))
        self.spin_vision = QDoubleSpinBox()
        self.spin_vision.setRange(-1.0, 2000.0)
        self.spin_vision.setSingleStep(20.0)
        self.spin_vision.setValue(260.0)
        self.spin_vision.setToolTip("-1 表示全图无迷雾视野")
        self.spin_vision.valueChanged.connect(self._on_prop_changed)
        vis_size_layout.addWidget(self.spin_vision)
        combat_layout.addLayout(vis_size_layout)

        ammo_layout = QHBoxLayout()
        ammo_layout.addWidget(QLabel("携弹数量:"))
        self.spin_ammo = QSpinBox()
        self.spin_ammo.setRange(-1, 999)
        self.spin_ammo.setValue(20)
        self.spin_ammo.setToolTip("-1 表示无限弹药")
        self.spin_ammo.valueChanged.connect(self._on_prop_changed)
        ammo_layout.addWidget(self.spin_ammo)
        combat_layout.addLayout(ammo_layout)

        disc_layout = QHBoxLayout()
        disc_layout.addWidget(QLabel("显形辨识度:"))
        self.spin_visibility = QDoubleSpinBox()
        self.spin_visibility.setRange(0.0, 1.0)
        self.spin_visibility.setSingleStep(0.1)
        self.spin_visibility.setValue(1.0)
        self.spin_visibility.setToolTip("1.0 永远清晰可见；0.7 表示视线内 70% 概率侦测显形")
        self.spin_visibility.valueChanged.connect(self._on_prop_changed)
        disc_layout.addWidget(self.spin_visibility)
        combat_layout.addLayout(disc_layout)

        self.prop_layout.addWidget(combat_group)

        # 4. 控制模式与战术脚本
        ctrl_group = QGroupBox("4. 玩家操控与 AI 战术脚本")
        ctrl_layout = QVBoxLayout(ctrl_group)

        self.chk_controllable = QCheckBox("允许玩家手动框选或微操控制")
        self.chk_controllable.setChecked(True)
        self.chk_controllable.toggled.connect(self._on_prop_changed)
        ctrl_layout.addWidget(self.chk_controllable)

        script_layout = QVBoxLayout()
        script_layout.addWidget(QLabel("独立线程战术脚本 (AI Script):"))
        self.combo_script = QComboBox()
        self.combo_script.addItems(self._available_scripts)
        self.combo_script.currentIndexChanged.connect(self._on_prop_changed)
        script_layout.addWidget(self.combo_script)
        ctrl_layout.addLayout(script_layout)

        tactic_layout = QHBoxLayout()
        tactic_layout.addWidget(QLabel("预置战术姿态:"))
        self.combo_tactic = QComboBox()
        self.combo_tactic.addItems(["patrol (巡逻突防)", "aggressive (激进冲锋)", "defensive (固守阵地)", "guard_unit (护卫核心)"])
        self.combo_tactic.currentIndexChanged.connect(self._on_prop_changed)
        tactic_layout.addWidget(self.combo_tactic)
        ctrl_layout.addLayout(tactic_layout)

        self.prop_layout.addWidget(ctrl_group)

        # 5. 单位模板规格速查
        self.lbl_template_info = QLabel("单位模板规格: --")
        self.lbl_template_info.setStyleSheet("color: #A6ACAF; font-size: 11px; padding: 6px; background: #13110E; border: 1px dashed #3E301E;")
        self.lbl_template_info.setWordWrap(True)
        self.prop_layout.addWidget(self.lbl_template_info)

        self.prop_layout.addStretch()
        self.prop_scroll_area.setWidget(prop_container)
        right_layout.addWidget(self.prop_scroll_area)

        main_layout.addWidget(right_panel)

        # 连接画布信号
        self.canvas.unit_selected.connect(self._on_canvas_unit_selected)
        self.canvas.unit_moved.connect(self._on_canvas_unit_moved)
        self.canvas.unit_place_requested.connect(self._on_canvas_unit_placed)
        self.canvas.hover_coord_changed.connect(self._on_coord_changed)

    def _on_coord_changed(self, col: int, row: int, px: int, py: int, tile: int):
        unit_at = self.canvas._find_unit_at(col, row)
        if unit_at:
            unit_info = f" | 目标单位: {unit_at.id} ({unit_at.config_file})"
        else:
            unit_info = ""
        msg = f"任务编队光标: 列 {col:02d}, 行 {row:02d} | 像素: ({px}, {py}){unit_info}"
        self.coord_status_changed.emit(msg)

    # ================= 属性面板同步与交互 =================

    def create_new_mission(self, map_file: str = "maps/level_01.json", mission_name: str = "New Campaign Mission") -> Mission:
        """重置并创建一个全新的战役任务"""
        default_player = PlayerMissionInfo(
            config_file="tank_configs/player_tank.json",
            spawn=SpawnPoint(x=2, y=2),
            id="player_alpha",
            vision_size=288.0,
            ammo=30,
            controllable=True
        )
        default_enemy = EnemyMissionInfo(
            id="enemy_1",
            config_file="tank_configs/enemy_basic.json",
            spawn=SpawnPoint(x=12, y=2),
            tactic="patrol",
            vision_size=250.0,
            ammo=-1,
            controllable=False
        )
        new_mission = Mission(
            name=mission_name,
            map_file=map_file,
            player=default_player,
            player_units=[default_player],
            enemies=[default_enemy],
            fog_of_war=True,
            limited_ammo=True,
            victory_conditions={"type": "all_enemies_destroyed"},
            defeat_conditions={"type": "all_players_destroyed"}
        )
        self.set_mission(new_mission)
        self.mission_modified.emit()
        return new_mission

    def _on_new_mission_clicked(self):
        self.new_mission_requested.emit()

    def set_mission(self, mission: Mission):
        self.current_mission = mission
        self.edit_mission_name.setText(mission.name)
        self.edit_map_file.setText(mission.map_file)
        self.chk_fog.setChecked(mission.fog_of_war)
        self.chk_ammo.setChecked(mission.limited_ammo)

        self.player_units = list(mission.player_units) if mission.player_units else [mission.player]
        self.enemies = list(mission.enemies)

        self.canvas.set_units(self.player_units, self.enemies)
        self._refresh_unit_list()
        if self.player_units:
            self._select_unit(self.player_units[0])

    def get_mission_data(self) -> Dict[str, Any]:
        """序列化输出标准 JSON 格式任务数据"""
        player_units_data = []
        for p in self.player_units:
            item = {
                "id": p.id,
                "config_file": p.config_file,
                "spawn": {"x": p.spawn.x, "y": p.spawn.y},
                "vision_size": p.vision_size,
                "ammo": p.ammo,
                "visibility": p.visibility,
                "controllable": p.controllable
            }
            if p.ai_script:
                item["ai_script"] = p.ai_script
            player_units_data.append(item)

        enemies_data = []
        for e in self.enemies:
            item = {
                "id": e.id,
                "config_file": e.config_file,
                "spawn": {"x": e.spawn.x, "y": e.spawn.y},
                "tactic": e.tactic,
                "vision_size": e.vision_size,
                "ammo": e.ammo,
                "visibility": e.visibility,
                "controllable": e.controllable
            }
            if e.ai_script:
                item["ai_script"] = e.ai_script
            enemies_data.append(item)

        primary_player = player_units_data[0] if player_units_data else {
            "config_file": "tank_configs/player_tank.json",
            "spawn": {"x": 6, "y": 14},
            "vision_size": 288.0,
            "ammo": 25
        }

        m_dict = {
            "name": self.edit_mission_name.text().strip() or "Custom Mission",
            "map_file": self.edit_map_file.text().strip() or "maps/level_01.json",
            "fog_of_war": self.chk_fog.isChecked(),
            "limited_ammo": self.chk_ammo.isChecked(),
            "player": primary_player,
            "player_units": player_units_data,
            "enemies": enemies_data
        }
        if self.current_mission and self.current_mission.victory_conditions:
            m_dict["victory_conditions"] = self.current_mission.victory_conditions
        if self.current_mission and self.current_mission.defeat_conditions:
            m_dict["defeat_conditions"] = self.current_mission.defeat_conditions
        return m_dict

    def _refresh_unit_list(self):
        self.unit_list.blockSignals(True)
        self.unit_list.clear()

        for u in self.player_units:
            item = QListWidgetItem(f"🔵 [我方] {u.id} ({u.spawn.x}, {u.spawn.y})")
            item.setData(Qt.UserRole, u)
            item.setForeground(QColor("#7FB3D5"))
            self.unit_list.addItem(item)

        for e in self.enemies:
            item = QListWidgetItem(f"🔴 [敌军] {e.id} ({e.spawn.x}, {e.spawn.y})")
            item.setData(Qt.UserRole, e)
            item.setForeground(QColor("#F1948A"))
            self.unit_list.addItem(item)

        self.unit_list.blockSignals(False)

    def _select_unit(self, unit: Any):
        self.active_unit = unit
        self.canvas.selected_unit = unit
        self.canvas.update()

        # 同步选中列表行
        for i in range(self.unit_list.count()):
            item = self.unit_list.item(i)
            if item.data(Qt.UserRole) == unit:
                self.unit_list.blockSignals(True)
                self.unit_list.setCurrentRow(i)
                self.unit_list.blockSignals(False)
                break

        self._populate_properties(unit)

    def _populate_properties(self, unit: Any):
        if not unit:
            return

        self.block_prop_signals(True)
        self.edit_id.setText(unit.id)

        is_player = isinstance(unit, PlayerMissionInfo)
        self.combo_camp.setCurrentIndex(0 if is_player else 1)

        # 模板
        cfg_idx = self.combo_config.findText(unit.config_file)
        if cfg_idx >= 0:
            self.combo_config.setCurrentIndex(cfg_idx)

        self.spin_spawn_x.setValue(unit.spawn.x)
        self.spin_spawn_y.setValue(unit.spawn.y)
        self.spin_vision.setValue(unit.vision_size)
        self.spin_ammo.setValue(unit.ammo)
        self.spin_visibility.setValue(unit.visibility)
        self.chk_controllable.setChecked(unit.controllable)

        # 脚本
        if unit.ai_script:
            idx = self.combo_script.findText(unit.ai_script)
            if idx >= 0:
                self.combo_script.setCurrentIndex(idx)
        else:
            self.combo_script.setCurrentIndex(0)

        # 战术姿态
        tactic_str = getattr(unit, "tactic", "patrol")
        for i in range(self.combo_tactic.count()):
            if tactic_str in self.combo_tactic.itemText(i):
                self.combo_tactic.setCurrentIndex(i)
                break

        self.block_prop_signals(False)
        self._update_template_preview(unit.config_file)

    def block_prop_signals(self, block: bool):
        self.edit_id.blockSignals(block)
        self.combo_camp.blockSignals(block)
        self.combo_config.blockSignals(block)
        self.spin_spawn_x.blockSignals(block)
        self.spin_spawn_y.blockSignals(block)
        self.spin_vision.blockSignals(block)
        self.spin_ammo.blockSignals(block)
        self.spin_visibility.blockSignals(block)
        self.chk_controllable.blockSignals(block)
        self.combo_script.blockSignals(block)
        self.combo_tactic.blockSignals(block)

    def _on_prop_changed(self):
        if not self.active_unit:
            return

        self.active_unit.id = self.edit_id.text().strip() or "unit"
        self.active_unit.config_file = self.combo_config.currentText()
        self.active_unit.spawn.x = self.spin_spawn_x.value()
        self.active_unit.spawn.y = self.spin_spawn_y.value()
        self.active_unit.vision_size = self.spin_vision.value()
        self.active_unit.ammo = self.spin_ammo.value()
        self.active_unit.visibility = self.spin_visibility.value()
        self.active_unit.controllable = self.chk_controllable.isChecked()

        script_text = self.combo_script.currentText()
        self.active_unit.ai_script = script_text if "(无脚本" not in script_text else None

        tactic_raw = self.combo_tactic.currentText().split()[0]
        if hasattr(self.active_unit, "tactic"):
            self.active_unit.tactic = tactic_raw

        self._refresh_unit_list()
        self.canvas.update()
        self.mission_modified.emit()

    def _on_camp_changed(self, idx: int):
        if not self.active_unit:
            return
        is_player_target = (idx == 0)
        is_currently_player = isinstance(self.active_unit, PlayerMissionInfo)

        if is_player_target != is_currently_player:
            # 阵营变更，转移所属集合
            if is_player_target:
                # 敌军转我方
                if self.active_unit in self.enemies:
                    self.enemies.remove(self.active_unit)
                new_u = PlayerMissionInfo(
                    id=self.active_unit.id,
                    config_file=self.active_unit.config_file,
                    spawn=self.active_unit.spawn,
                    vision_size=self.active_unit.vision_size,
                    ammo=self.active_unit.ammo,
                    visibility=self.active_unit.visibility,
                    controllable=True,
                    ai_script=self.active_unit.ai_script
                )
                self.player_units.append(new_u)
                self.active_unit = new_u
            else:
                # 我方转敌军
                if self.active_unit in self.player_units:
                    self.player_units.remove(self.active_unit)
                new_e = EnemyMissionInfo(
                    id=self.active_unit.id,
                    config_file=self.active_unit.config_file,
                    spawn=self.active_unit.spawn,
                    tactic="patrol",
                    vision_size=self.active_unit.vision_size,
                    ammo=self.active_unit.ammo,
                    visibility=self.active_unit.visibility,
                    controllable=False,
                    ai_script=self.active_unit.ai_script
                )
                self.enemies.append(new_e)
                self.active_unit = new_e

            self.canvas.set_units(self.player_units, self.enemies)
            self._refresh_unit_list()
            self._select_unit(self.active_unit)
            self.mission_modified.emit()

    def _on_config_template_changed(self):
        cfg_name = self.combo_config.currentText()
        self._update_template_preview(cfg_name)
        self._on_prop_changed()

    def _update_template_preview(self, cfg_file: str):
        path = self.base_dir / cfg_file
        if path.exists():
            try:
                cfg = TankConfig.from_json(path)
                crush_str = "是 (碾压速度衰减)" if getattr(cfg, "can_crush_bricks", False) else "否"
                tower_str = f"防御塔({cfg.tower_type})" if cfg.is_tower else "机动战车"
                info = (f"【{cfg.name}】类型: {tower_str} | 生命: {cfg.health} | 移速: {cfg.speed} | "
                        f"攻速: {cfg.fire_cooldown}帧 | 碾压普通砖块: {crush_str}")
                self.lbl_template_info.setText(info)
            except Exception as e:
                self.lbl_template_info.setText(f"模板解析失败: {e}")
        else:
            self.lbl_template_info.setText(f"模板文件不存在: {cfg_file}")

    def _on_unit_list_selection_changed(self, row: int):
        if row >= 0:
            item = self.unit_list.item(row)
            unit = item.data(Qt.UserRole)
            self._select_unit(unit)

    def _on_canvas_unit_selected(self, unit: Any):
        if unit:
            self._select_unit(unit)

    def _on_canvas_unit_moved(self, unit: Any, col: int, row: int):
        if self.active_unit == unit:
            self.spin_spawn_x.blockSignals(True)
            self.spin_spawn_y.blockSignals(True)
            self.spin_spawn_x.setValue(col)
            self.spin_spawn_y.setValue(row)
            self.spin_spawn_x.blockSignals(False)
            self.spin_spawn_y.blockSignals(False)
        self._refresh_unit_list()
        self.mission_modified.emit()

    def _on_pick_spawn_clicked(self):
        self.canvas.placing_new_unit = True
        QMessageBox.information(self, "点选出生点", "请在中间地图上单击任意地块，即可将当前单位移动至该位置。")

    def _on_canvas_unit_placed(self, col: int, row: int):
        if self.active_unit:
            self.active_unit.spawn.x = col
            self.active_unit.spawn.y = row
            self.spin_spawn_x.setValue(col)
            self.spin_spawn_y.setValue(row)
            self._refresh_unit_list()
            self.canvas.update()
            self.mission_modified.emit()

    def _on_add_player_clicked(self):
        new_id = f"player_{len(self.player_units) + 1}"
        default_cfg = "tank_configs/clearing_tank.json" if "clearing" in str(self._available_configs) else "tank_configs/player_tank.json"
        unit = PlayerMissionInfo(
            id=new_id,
            config_file=default_cfg,
            spawn=SpawnPoint(x=5, y=5),
            vision_size=280.0,
            ammo=25,
            visibility=1.0,
            controllable=True
        )
        self.player_units.append(unit)
        self.canvas.set_units(self.player_units, self.enemies)
        self._refresh_unit_list()
        self._select_unit(unit)
        self.mission_modified.emit()

    def _on_add_enemy_clicked(self):
        new_id = f"enemy_{len(self.enemies) + 1}"
        unit = EnemyMissionInfo(
            id=new_id,
            config_file="tank_configs/enemy_basic.json",
            spawn=SpawnPoint(x=2, y=2),
            tactic="patrol",
            vision_size=260.0,
            ammo=-1,
            visibility=1.0,
            controllable=False
        )
        self.enemies.append(unit)
        self.canvas.set_units(self.player_units, self.enemies)
        self._refresh_unit_list()
        self._select_unit(unit)
        self.mission_modified.emit()

    def _on_delete_unit_clicked(self):
        if not self.active_unit:
            return
        reply = QMessageBox.question(self, "确认删除", f"确定删除单位 '{self.active_unit.id}' 吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.active_unit in self.player_units:
                self.player_units.remove(self.active_unit)
            elif self.active_unit in self.enemies:
                self.enemies.remove(self.active_unit)
            self.active_unit = None
            self.canvas.selected_unit = None
            self.canvas.set_units(self.player_units, self.enemies)
            self._refresh_unit_list()
            if self.player_units:
                self._select_unit(self.player_units[0])
            elif self.enemies:
                self._select_unit(self.enemies[0])
            self.mission_modified.emit()

    def _on_duplicate_unit_clicked(self):
        if not self.active_unit:
            return
        if isinstance(self.active_unit, PlayerMissionInfo):
            dup_id = f"{self.active_unit.id}_copy"
            u = PlayerMissionInfo(
                id=dup_id,
                config_file=self.active_unit.config_file,
                spawn=SpawnPoint(x=min(20, self.active_unit.spawn.x + 1), y=self.active_unit.spawn.y),
                vision_size=self.active_unit.vision_size,
                ammo=self.active_unit.ammo,
                visibility=self.active_unit.visibility,
                controllable=self.active_unit.controllable,
                ai_script=self.active_unit.ai_script
            )
            self.player_units.append(u)
            self._select_unit(u)
        else:
            dup_id = f"{self.active_unit.id}_copy"
            e = EnemyMissionInfo(
                id=dup_id,
                config_file=self.active_unit.config_file,
                spawn=SpawnPoint(x=min(20, self.active_unit.spawn.x + 1), y=self.active_unit.spawn.y),
                tactic=self.active_unit.tactic,
                vision_size=self.active_unit.vision_size,
                ammo=self.active_unit.ammo,
                visibility=self.active_unit.visibility,
                controllable=self.active_unit.controllable,
                ai_script=self.active_unit.ai_script
            )
            self.enemies.append(e)
            self._select_unit(e)

        self.canvas.set_units(self.player_units, self.enemies)
        self._refresh_unit_list()
        self.mission_modified.emit()

    def _on_mission_meta_changed(self):
        self.mission_modified.emit()
