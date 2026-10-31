import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Optional

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QFileDialog, QMessageBox, QStatusBar, QToolBar, QAction
)
from PyQt5.QtGui import QFont, QIcon, QColor
from PyQt5.QtCore import Qt

from map_loader.models import GameMap, TileType
from map_loader.loader import MapLoader
from mission_loader.models import Mission
from mission_loader.loader import MissionLoader

from .theme import AOE2_STYLE
from .canvas import EditorCanvas, EditorMode
from .map_editor import MapEditorWidget
from .mission_editor import MissionEditorWidget
from .condition_editor import ConditionEditorWidget

class EditorMainWindow(QMainWindow):
    """
    【帝国时代2风格 All-In-One 战局全功能编辑器】
    - 模式 1：可视化编辑地图 (实时光标坐标反馈、单格点画、拖框批量填充、地图大小设置)
    - 模式 2：任务与单位编辑 (放置单位、在地图上直接拖动设置出生点、可滚动属性检视面板)
    - 模式 3：胜负条件树 (QTreeWidget 树状结构可视化编排与逻辑嵌套、实时校验)
    - 跨模式全自动双向同步 (地图即时渲染、单位 ID 自动供给条件树、一键实战启动测试)
    """

    def __init__(self, base_dir: Optional[Path] = None):
        super().__init__()
        self.base_dir = base_dir or Path.cwd()
        self.setWindowTitle("★ 帝国时代2风格战局全功能编辑器 ★ [坦克战略前线 All-in-One Editor]")
        self.resize(1360, 860)

        # 核心数据模型
        self.current_map: Optional[GameMap] = None
        self.current_map_path: Optional[Path] = None
        self.current_mission_path: Optional[Path] = None

        # 应用经典 AoE2 羊皮纸/古铜/深铁主题
        self.setStyleSheet(AOE2_STYLE)

        self._init_ui()
        self._load_initial_defaults()

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(6)

        # 1. 顶部操作栏与大模式切换器
        top_bar = QHBoxLayout()

        # 模式切换按钮组
        mode_btn_layout = QHBoxLayout()
        mode_btn_layout.setSpacing(4)

        self.btn_mode_map = QPushButton("⚔ 模式 1：地图建造")
        self.btn_mode_map.setCheckable(True)
        self.btn_mode_map.setChecked(True)
        self.btn_mode_map.clicked.connect(lambda: self._switch_mode(0))
        mode_btn_layout.addWidget(self.btn_mode_map)

        self.btn_mode_unit = QPushButton("🛡 模式 2：任务单位")
        self.btn_mode_unit.setCheckable(True)
        self.btn_mode_unit.clicked.connect(lambda: self._switch_mode(1))
        mode_btn_layout.addWidget(self.btn_mode_unit)

        self.btn_mode_cond = QPushButton("📜 模式 3：胜负条件树")
        self.btn_mode_cond.setCheckable(True)
        self.btn_mode_cond.clicked.connect(lambda: self._switch_mode(2))
        mode_btn_layout.addWidget(self.btn_mode_cond)

        top_bar.addLayout(mode_btn_layout)
        top_bar.addStretch()

        # 地图与任务文件操作按钮
        file_btn_layout = QHBoxLayout()
        file_btn_layout.setSpacing(6)

        btn_new_map = QPushButton("🗺 新建地图")
        btn_new_map.clicked.connect(self._on_new_map)
        file_btn_layout.addWidget(btn_new_map)

        btn_open_map = QPushButton("📂 打开地图")
        btn_open_map.clicked.connect(self._on_open_map)
        file_btn_layout.addWidget(btn_open_map)

        btn_save_map = QPushButton("💾 保存地图")
        btn_save_map.setStyleSheet("color: #F7DC6F;")
        btn_save_map.clicked.connect(self._on_save_map)
        file_btn_layout.addWidget(btn_save_map)

        sep = QLabel("|")
        sep.setStyleSheet("color: #6C5531; font-weight: bold;")
        file_btn_layout.addWidget(sep)

        btn_new_mission = QPushButton("⚔ 新建任务")
        btn_new_mission.clicked.connect(self._on_new_mission)
        file_btn_layout.addWidget(btn_new_mission)

        btn_open_mission = QPushButton("📂 打开任务")
        btn_open_mission.clicked.connect(self._on_open_mission)
        file_btn_layout.addWidget(btn_open_mission)

        btn_save_mission = QPushButton("💾 保存任务")
        btn_save_mission.setStyleSheet("color: #F7DC6F; background-color: #3E2723;")
        btn_save_mission.clicked.connect(self._on_save_mission)
        file_btn_layout.addWidget(btn_save_mission)

        btn_run_game = QPushButton("▶ 启动游戏实战测试")
        btn_run_game.setStyleSheet("background-color: #196F3D; border: 2px solid #52BE80; color: #EAFAF1;")
        btn_run_game.clicked.connect(self._on_run_game_test)
        file_btn_layout.addWidget(btn_run_game)

        top_bar.addLayout(file_btn_layout)
        main_layout.addLayout(top_bar)

        # 2. 多模式堆叠视口
        self.stack = QStackedWidget(self)

        # 模式 1: 地图编辑
        self.map_editor = MapEditorWidget(parent=self)
        self.map_editor.coord_status_changed.connect(self._update_status_msg)
        self.map_editor.map_modified.connect(self._on_map_modified)
        self.stack.addWidget(self.map_editor)

        # 模式 2: 任务与单位编辑
        self.mission_editor = MissionEditorWidget(base_dir=self.base_dir, parent=self)
        self.mission_editor.coord_status_changed.connect(self._update_status_msg)
        self.mission_editor.mission_modified.connect(self._update_file_info)
        self.mission_editor.new_mission_requested.connect(self._on_new_mission)
        self.stack.addWidget(self.mission_editor)

        # 模式 3: 胜负条件树状编辑
        self.condition_editor = ConditionEditorWidget(self)
        self.stack.addWidget(self.condition_editor)

        main_layout.addWidget(self.stack, stretch=1)

        # 3. 底部状态栏
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.lbl_status = QLabel("就绪 | 欢迎使用帝国时代2风格 All-In-One 战局编辑器")
        self.status_bar.addWidget(self.lbl_status, stretch=1)

        self.lbl_file_info = QLabel("地图: -- | 任务: --")
        self.lbl_file_info.setStyleSheet("color: #E6C66E;")
        self.status_bar.addPermanentWidget(self.lbl_file_info)

    @property
    def canvas(self) -> EditorCanvas:
        if hasattr(self, "stack") and self.stack.currentIndex() == 1:
            return self.mission_editor.canvas
        return self.map_editor.canvas

    def switch_mode(self, index: int):
        self._switch_mode(index)

    def _switch_mode(self, index: int):
        self.stack.setCurrentIndex(index)
        self.btn_mode_map.setChecked(index == 0)
        self.btn_mode_unit.setChecked(index == 1)
        self.btn_mode_cond.setChecked(index == 2)

        if index == 0:
            self.map_editor.canvas.update()
            self._update_status_msg("当前模式: ⚔ 地图建造模式 (支持拖框批量填充与单格材质点画)")
        elif index == 1:
            self.mission_editor.canvas.set_units(self.mission_editor.player_units, self.mission_editor.enemies)
            self.mission_editor.canvas.update()
            self._update_status_msg("当前模式: 🛡 任务单位编队模式 (可在地图上直接点选与拖拽设置单位出生点)")
        elif index == 2:
            all_units = self.mission_editor.player_units + self.mission_editor.enemies
            unit_ids = [u.id for u in all_units]
            self.condition_editor.set_unit_ids(unit_ids)
            self._update_status_msg("当前模式: 📜 胜负条件树模式 (树形层级可视化多级逻辑嵌套编排)")

    def _on_map_modified(self):
        if self.current_map:
            self.mission_editor.canvas.update_canvas_size()
            self.mission_editor.canvas.update()

    def _update_status_msg(self, msg: str):
        self.lbl_status.setText(msg)

    # ================= 数据加载与保存 =================

    def _load_initial_defaults(self):
        """启动时默认加载已有地图与任务作为基准"""
        map_path = self.base_dir / "maps/level_01.json"
        if map_path.exists():
            self._load_map_file(map_path)

        mission_path = self.base_dir / "missions/mission_01.json"
        if mission_path.exists():
            self._load_mission_file(mission_path)

    def _load_map_file(self, path: Path):
        try:
            game_map = MapLoader.load_from_file(path)
            self.current_map = game_map
            self.current_map_path = path
            self.map_editor.set_map(game_map)
            self.mission_editor.set_map(game_map)
            self._update_file_info()
            self._update_status_msg(f"成功加载地图: {path.name} ({game_map.cols}x{game_map.rows})")
        except Exception as e:
            QMessageBox.critical(self, "加载地图失败", f"无法解析地图文件: {path}\n{e}")

    def _load_mission_file(self, path: Path):
        try:
            mission = MissionLoader.load_from_file(path)
            self.current_mission_path = path
            self.mission_editor.set_mission(mission)
            self.condition_editor.load_conditions(mission.victory_conditions, mission.defeat_conditions)

            # 同步关联地图
            rel_map = path.parent / mission.map_file if not Path(mission.map_file).is_absolute() else Path(mission.map_file)
            if not rel_map.exists():
                rel_map = self.base_dir / mission.map_file
            if rel_map.exists() and rel_map != self.current_map_path:
                self._load_map_file(rel_map)

            self._update_file_info()
            self._update_status_msg(f"成功加载任务: {mission.name}")
        except Exception as e:
            QMessageBox.critical(self, "加载任务失败", f"无法解析任务文件: {path}\n{e}")

    def _update_file_info(self):
        m_name = self.current_map.name if self.current_map else "--"
        mis_name = self.mission_editor.edit_mission_name.text() if hasattr(self, "mission_editor") else "--"
        self.lbl_file_info.setText(f"当前地图: {m_name} | 当前任务: {mis_name}")

    def _on_new_map(self):
        new_map = GameMap(
            name="New Map",
            tile_size=36,
            cols=20,
            rows=16,
            grid=[[TileType.EMPTY for _ in range(20)] for _ in range(16)]
        )
        self.current_map = new_map
        self.current_map_path = None
        self.map_editor.set_map(new_map)
        self.mission_editor.set_map(new_map)
        self._update_file_info()
        self._update_status_msg("已创建全新空白地图 (20x16)")

    def _on_open_map(self):
        maps_dir = str(self.base_dir / "maps")
        file_path, _ = QFileDialog.getOpenFileName(self, "打开地图文件", maps_dir, "JSON 地图文件 (*.json)")
        if file_path:
            self._load_map_file(Path(file_path))

    def _on_save_map(self):
        if not self.canvas.game_map:
            return

        if not self.current_map_path:
            maps_dir = str(self.base_dir / "maps")
            file_path, _ = QFileDialog.getSaveFileName(self, "保存地图文件", maps_dir, "JSON 地图文件 (*.json)")
            if not file_path:
                return
            self.current_map_path = Path(file_path)

        try:
            MapLoader.save_to_file(self.canvas.game_map, self.current_map_path)
            self._update_file_info()
            QMessageBox.information(self, "保存成功", f"地图已成功保存至:\n{self.current_map_path}")
        except Exception as e:
            QMessageBox.critical(self, "保存地图失败", f"保存地图文件发生异常:\n{e}")

    def _on_new_mission(self):
        # 关联当前打开或保存的地图相对路径
        map_rel_path = "maps/level_01.json"
        if self.current_map_path:
            try:
                map_rel_path = str(self.current_map_path.relative_to(self.base_dir))
            except ValueError:
                map_rel_path = str(self.current_map_path)
        elif self.current_map and self.current_map.name:
            clean_name = self.current_map.name.lower().replace(" ", "_")
            map_rel_path = f"maps/{clean_name}.json"

        new_mission = self.mission_editor.create_new_mission(map_file=map_rel_path, mission_name="New Campaign Mission")
        self.current_mission_path = None
        self.condition_editor.load_conditions(new_mission.victory_conditions, new_mission.defeat_conditions)
        self._switch_mode(1)
        self._update_file_info()
        self._update_status_msg(f"已新建任务: '{new_mission.name}'，关联地图: '{map_rel_path}'，请开始配置部队与胜负目标")

    def _on_open_mission(self):
        missions_dir = str(self.base_dir / "missions")
        file_path, _ = QFileDialog.getOpenFileName(self, "打开任务文件", missions_dir, "JSON 任务文件 (*.json)")
        if file_path:
            self._load_mission_file(Path(file_path))

    def _on_save_mission(self):
        # 整合模式 2 任务单位数据与模式 3 胜负条件树数据
        mission_dict = self.mission_editor.get_mission_data()
        vic_cond, def_cond = self.condition_editor.export_conditions()
        if vic_cond:
            mission_dict["victory_conditions"] = vic_cond
        if def_cond:
            mission_dict["defeat_conditions"] = def_cond

        if not self.current_mission_path:
            missions_dir = str(self.base_dir / "missions")
            file_path, _ = QFileDialog.getSaveFileName(self, "保存任务文件", missions_dir, "JSON 任务文件 (*.json)")
            if not file_path:
                return
            self.current_mission_path = Path(file_path)

        try:
            with open(self.current_mission_path, "w", encoding="utf-8") as f:
                json.dump(mission_dict, f, indent=2, ensure_ascii=False)
            self._update_file_info()
            QMessageBox.information(self, "保存成功", f"任务与单位编队及胜负条件树已完整保存至:\n{self.current_mission_path}")
        except Exception as e:
            QMessageBox.critical(self, "保存任务失败", f"保存任务文件发生异常:\n{e}")

    def _on_run_game_test(self):
        """一键拉起坦克大战主程序实战测试当前任务"""
        # 先自动保存当前任务
        if self.current_mission_path:
            self._on_save_mission()
            cmd = [sys.executable, "tanks.py", "--mission", str(self.current_mission_path)]
        else:
            cmd = [sys.executable, "tanks.py"]

        try:
            subprocess.Popen(cmd, cwd=str(self.base_dir))
            self._update_status_msg("已拉起游戏实战测试窗口...")
        except Exception as e:
            QMessageBox.critical(self, "实战测试失败", f"拉起游戏引擎进程失败:\n{e}")
