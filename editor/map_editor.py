from typing import Optional, List
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QButtonGroup,
    QGroupBox, QSpinBox, QLineEdit, QScrollArea, QFrame,
    QCheckBox, QMessageBox, QFileDialog, QSlider
)
from PyQt5.QtGui import QFont, QColor, QIcon
from PyQt5.QtCore import Qt, pyqtSignal

from map_loader.models import GameMap, TileType
from map_loader.loader import MapLoader
from resource.loader import ResourceLoader
from translations import i18n, t
from .canvas import EditorCanvas, EditorMode, TerrainTool

class MapEditorWidget(QWidget):
    """
    模式 1：帝国时代2 风格地图可视化编辑工作台
    """

    map_modified = pyqtSignal()
    coord_status_changed = pyqtSignal(str)

    def __init__(self, canvas: Optional[EditorCanvas] = None, parent=None):
        super().__init__(parent)
        self.canvas = canvas if canvas is not None else EditorCanvas()
        self.canvas.mode = EditorMode.MAP_EDIT
        self.tile_buttons: List[QPushButton] = []
        self._init_ui()
        self.retranslate_ui()

    def set_map(self, game_map: GameMap):
        self.canvas.set_map(game_map)
        self.sync_from_map(game_map)

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        # ===== 左侧控制面板 =====
        left_panel = QFrame()
        left_panel.setFixedWidth(280)
        left_panel.setStyleSheet("background-color: #221E19; border: 1px solid #4D3C26; border-radius: 4px;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(12)

        self.title_label = QLabel("⚔ 地图建造工具箱")
        self.title_label.setFont(QFont("Palatino", 13, QFont.Bold))
        self.title_label.setStyleSheet("color: #F1C40F; border: none;")
        left_layout.addWidget(self.title_label)

        # 1. 地形笔刷工具
        self.tool_group = QGroupBox("★ 操作工具")
        tool_layout = QVBoxLayout(self.tool_group)

        self.btn_brush = QPushButton("🖌 单格画笔 (Brush)")
        self.btn_brush.setCheckable(True)
        self.btn_brush.setChecked(True)
        self.btn_brush.clicked.connect(lambda: self._set_tool(TerrainTool.BRUSH))
        tool_layout.addWidget(self.btn_brush)

        self.btn_box_fill = QPushButton("⬚ 拖框批量填充 (Box Fill)")
        self.btn_box_fill.setCheckable(True)
        self.btn_box_fill.clicked.connect(lambda: self._set_tool(TerrainTool.BOX_FILL))
        tool_layout.addWidget(self.btn_box_fill)

        self.btn_eraser = QPushButton("🧹 橡皮擦 (Eraser)")
        self.btn_eraser.setCheckable(True)
        self.btn_eraser.clicked.connect(lambda: self._set_tool(TerrainTool.ERASER))
        tool_layout.addWidget(self.btn_eraser)

        self.tool_btn_group = QButtonGroup(self)
        self.tool_btn_group.addButton(self.btn_brush)
        self.tool_btn_group.addButton(self.btn_box_fill)
        self.tool_btn_group.addButton(self.btn_eraser)

        left_layout.addWidget(self.tool_group)

        # 2. 地形材质画板 (Tile Palette)
        self.tile_group = QGroupBox("★ 瓦片材质选择")
        tile_layout = QVBoxLayout(self.tile_group)

        self.tile_btn_group = QButtonGroup(self)
        res_configs = ResourceLoader.load_configs()
        self.tiles_info = [
            (TileType.BRICK, "#9E3B1B", "brick", "砖块 (Brick)"),
            (TileType.STEEL, "#B5B9C2", "steel", "钢墙 (Steel)")
        ]
        # 动态从 resource/*.json 读取全部资源块信息，不再硬编码
        for cfg in res_configs.values():
            self.tiles_info.append((cfg.tile_id, cfg.color, cfg.resource_type, f"{cfg.name} (ID:{cfg.tile_id})"))

        self.tiles_info.extend([
            (TileType.EMPTY, "#11100D", "empty", "空地 (Empty)"),
            (TileType.BASE, "#D35400", "base", "基地 (Base)")
        ])

        self.tile_buttons = []
        for i, info in enumerate(self.tiles_info):
            ttype, color_code = info[0], info[1]
            btn = QPushButton()
            btn.setCheckable(True)
            if ttype == TileType.BRICK:
                btn.setChecked(True)
            btn.setStyleSheet(f"text-align: left; padding-left: 10px; border-left: 6px solid {color_code};")
            btn.clicked.connect(lambda checked, t=ttype: self._set_tile(t))
            tile_layout.addWidget(btn)
            self.tile_btn_group.addButton(btn, i)
            self.tile_buttons.append(btn)

        left_layout.addWidget(self.tile_group)

        # 3. 批量操作工具
        self.batch_group = QGroupBox("★ 区域快捷操作")
        batch_layout = QVBoxLayout(self.batch_group)

        self.btn_fill_all = QPushButton("🪣 当前材质填充全图")
        self.btn_fill_all.clicked.connect(self._fill_all_map)
        batch_layout.addWidget(self.btn_fill_all)

        self.btn_clear_all = QPushButton("🗑 清空全图为空地")
        self.btn_clear_all.clicked.connect(self._clear_all_map)
        batch_layout.addWidget(self.btn_clear_all)

        left_layout.addWidget(self.batch_group)

        # 4. 地图大小与参数设置
        self.size_group = QGroupBox("★ 地图大小设置")
        size_layout = QVBoxLayout(self.size_group)

        # 地图名称
        name_layout = QHBoxLayout()
        self.lbl_name_tag = QLabel("名称:")
        name_layout.addWidget(self.lbl_name_tag)
        self.edit_name = QLineEdit("Custom Map")
        name_layout.addWidget(self.edit_name)
        size_layout.addLayout(name_layout)

        # 列数 Cols
        cols_layout = QHBoxLayout()
        self.lbl_cols_tag = QLabel("列数 (宽):")
        cols_layout.addWidget(self.lbl_cols_tag)
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(8, 80)
        self.spin_cols.setValue(20)
        cols_layout.addWidget(self.spin_cols)
        size_layout.addLayout(cols_layout)

        # 行数 Rows
        rows_layout = QHBoxLayout()
        self.lbl_rows_tag = QLabel("行数 (高):")
        rows_layout.addWidget(self.lbl_rows_tag)
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(8, 80)
        self.spin_rows.setValue(16)
        rows_layout.addWidget(self.spin_rows)
        size_layout.addLayout(rows_layout)

        # 瓦片尺寸
        ts_layout = QHBoxLayout()
        self.lbl_ts_tag = QLabel("网格边长:")
        ts_layout.addWidget(self.lbl_ts_tag)
        self.spin_tile_size = QSpinBox()
        self.spin_tile_size.setRange(24, 48)
        self.spin_tile_size.setValue(36)
        self.spin_tile_size.setSuffix(" px")
        ts_layout.addWidget(self.spin_tile_size)
        size_layout.addLayout(ts_layout)

        self.btn_apply_size = QPushButton("✓ 应用地图大小调整")
        self.btn_apply_size.setStyleSheet("background-color: #5D4037; border: 1px solid #C8A048; color: #FFF3BD;")
        self.btn_apply_size.clicked.connect(self._apply_map_resize)
        size_layout.addWidget(self.btn_apply_size)

        left_layout.addWidget(self.size_group)

        # 5. 视图辅助控制
        self.view_group = QGroupBox("★ 视图控制")
        view_layout = QVBoxLayout(self.view_group)

        self.chk_grid = QCheckBox("显示网格标线")
        self.chk_grid.setChecked(True)
        self.chk_grid.toggled.connect(self._toggle_grid)
        view_layout.addWidget(self.chk_grid)

        zoom_layout = QHBoxLayout()
        self.lbl_zoom_tag = QLabel("缩放:")
        zoom_layout.addWidget(self.lbl_zoom_tag)
        btn_zoom_out = QPushButton("-")
        btn_zoom_out.setFixedWidth(28)
        btn_zoom_out.clicked.connect(lambda: self._adjust_zoom(-0.2))
        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedWidth(28)
        btn_zoom_in.clicked.connect(lambda: self._adjust_zoom(0.2))
        self.lbl_zoom = QLabel("100%")
        zoom_layout.addWidget(btn_zoom_out)
        zoom_layout.addWidget(self.lbl_zoom)
        zoom_layout.addWidget(btn_zoom_in)
        view_layout.addLayout(zoom_layout)

        left_layout.addWidget(self.view_group)

        left_layout.addStretch()
        main_layout.addWidget(left_panel)

        # ===== 右侧滚动视口 =====
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background-color: #12100E; border: 2px solid #5C482C;")
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setWidget(self.canvas)
        main_layout.addWidget(self.scroll_area, stretch=1)

        # 监听画布信号
        self.canvas.hover_coord_changed.connect(self._on_coord_changed)
        self.canvas.map_modified.connect(self.map_modified.emit)

    def retranslate_ui(self):
        self.title_label.setText(t("editor.map.toolbox_title"))
        self.tool_group.setTitle(t("editor.map.tools_group"))
        self.btn_brush.setText(t("editor.map.brush"))
        self.btn_box_fill.setText(t("editor.map.box_fill"))
        self.btn_eraser.setText(t("editor.map.eraser"))

        self.tile_group.setTitle(t("editor.map.tile_palette"))
        for btn, info in zip(self.tile_buttons, self.tiles_info):
            key_name = info[2]
            default_label = info[3]
            trans_key = f"editor.map.tiles.{key_name}"
            translated = t(trans_key)
            if translated == trans_key:
                translated = default_label
            btn.setText(f"  {translated}")

        self.batch_group.setTitle(t("editor.map.batch_ops"))
        self.btn_fill_all.setText(t("editor.map.fill_all"))
        self.btn_clear_all.setText(t("editor.map.clear_all"))

        self.size_group.setTitle(t("editor.map.size_settings"))
        self.lbl_name_tag.setText(t("editor.map.name"))
        self.lbl_cols_tag.setText(t("editor.map.cols"))
        self.lbl_rows_tag.setText(t("editor.map.rows"))
        self.lbl_ts_tag.setText(t("editor.map.tile_size"))
        self.btn_apply_size.setText(t("editor.map.apply_size"))

        self.view_group.setTitle(t("editor.map.view_control"))
        self.chk_grid.setText(t("editor.map.show_grid"))
        self.lbl_zoom_tag.setText(t("editor.map.zoom"))

    def _set_tool(self, tool: str):
        self.canvas.tool = tool
        if tool == TerrainTool.ERASER:
            self.canvas.selected_tile = TileType.EMPTY

    def _set_tile(self, tile_type: int):
        self.canvas.selected_tile = tile_type
        if self.canvas.tool == TerrainTool.ERASER:
            self.btn_brush.setChecked(True)
            self.canvas.tool = TerrainTool.BRUSH

    def _toggle_grid(self, enabled: bool):
        self.canvas.show_grid = enabled
        self.canvas.update()

    def _adjust_zoom(self, delta: float):
        new_zoom = round(self.canvas.zoom + delta, 1)
        self.canvas.set_zoom(new_zoom)
        self.lbl_zoom.setText(f"{int(self.canvas.zoom * 100)}%")

    def _on_coord_changed(self, col: int, row: int, px: int, py: int, tile: int):
        tile_names = {
            TileType.EMPTY: t("editor.map.tiles.empty"),
            TileType.BRICK: t("editor.map.tiles.brick"),
            TileType.STEEL: t("editor.map.tiles.steel"),
            TileType.DARK_MATTER: t("editor.map.tiles.dark_matter"),
            TileType.ALLOY: t("editor.map.tiles.alloy"),
            TileType.BASE: t("editor.map.tiles.base")
        }
        tname = tile_names.get(tile, f"未知({tile})")
        msg = t("editor.map.cursor_status", col=col, row=row, px=px, py=py, tile=tname)
        self.coord_status_changed.emit(msg)

    def _apply_map_resize(self):
        if not self.canvas.game_map:
            return

        new_cols = self.spin_cols.value()
        new_rows = self.spin_rows.value()
        new_ts = self.spin_tile_size.value()
        new_name = self.edit_name.text().strip() or "Custom Map"

        cur_map = self.canvas.game_map
        old_cols = cur_map.cols
        old_rows = cur_map.rows

        # 重构 grid
        new_grid = [[TileType.EMPTY for _ in range(new_cols)] for _ in range(new_rows)]
        for r in range(min(old_rows, new_rows)):
            for c in range(min(old_cols, new_cols)):
                new_grid[r][c] = cur_map.grid[r][c]

        cur_map.cols = new_cols
        cur_map.rows = new_rows
        cur_map.tile_size = new_ts
        cur_map.name = new_name
        cur_map.grid = new_grid

        self.canvas.update_canvas_size()
        self.canvas.update()
        self.map_modified.emit()
        self.coord_status_changed.emit(f"地图尺寸已更新为: {new_cols} 列 x {new_rows} 行 (网格: {new_ts}px)")
        if self.isVisible():
            QMessageBox.information(self, "地图大小已调整", f"地图尺寸已更新为: {new_cols} 列 x {new_rows} 行 (网格: {new_ts}px)")

    def _fill_all_map(self):
        if not self.canvas.game_map:
            return
        reply = QMessageBox.question(
            self,
            t("editor.map.confirm_fill_title"),
            t("editor.map.confirm_fill_msg"),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            tile = self.canvas.selected_tile
            for r in range(self.canvas.game_map.rows):
                for c in range(self.canvas.game_map.cols):
                    self.canvas.game_map.set_tile(c, r, tile)
            self.canvas.update()
            self.map_modified.emit()

    def _clear_all_map(self):
        if not self.canvas.game_map:
            return
        reply = QMessageBox.question(
            self,
            t("editor.map.confirm_clear_title"),
            t("editor.map.confirm_clear_msg"),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for r in range(self.canvas.game_map.rows):
                for c in range(self.canvas.game_map.cols):
                    self.canvas.game_map.set_tile(c, r, TileType.EMPTY)
            self.canvas.update()
            self.map_modified.emit()

    def sync_from_map(self, game_map: GameMap):
        self.edit_name.setText(game_map.name)
        self.spin_cols.setValue(game_map.cols)
        self.spin_rows.setValue(game_map.rows)
        self.spin_tile_size.setValue(game_map.tile_size)
