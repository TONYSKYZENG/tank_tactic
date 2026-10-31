from typing import Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QRadioButton,
    QButtonGroup, QGroupBox, QSpinBox, QLineEdit, QScrollArea, QFrame,
    QCheckBox, QMessageBox, QFileDialog, QSlider
)
from PyQt5.QtGui import QFont, QColor, QIcon
from PyQt5.QtCore import Qt, pyqtSignal

from map_loader.models import GameMap, TileType
from map_loader.loader import MapLoader
from .canvas import EditorCanvas, EditorMode, TerrainTool

class MapEditorWidget(QWidget):
    """
    【模式 1：可视化地图编辑】
    - 实时显示光标的地图坐标位置
    - 既能拖框框设置地形 (Box Fill)，又能一格一格的点 (Brush)
    - 地图大小 (Cols, Rows, TileSize, Name) 自由设置与调整
    - 瓦片画板：空地、可摧毁砖墙、不可摧毁钢墙、金鹰基地
    """

    map_modified = pyqtSignal()
    coord_status_changed = pyqtSignal(str)

    def __init__(self, canvas: Optional[EditorCanvas] = None, parent=None):
        super().__init__(parent)
        self.canvas = canvas if canvas is not None else EditorCanvas()
        self.canvas.mode = EditorMode.MAP_EDIT
        self._init_ui()

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

        title_label = QLabel("⚔ 地图建造工具箱")
        title_label.setFont(QFont("Palatino", 13, QFont.Bold))
        title_label.setStyleSheet("color: #F1C40F; border: none;")
        left_layout.addWidget(title_label)

        # 1. 地形笔刷工具
        tool_group = QGroupBox("★ 操作工具")
        tool_layout = QVBoxLayout(tool_group)

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

        left_layout.addWidget(tool_group)

        # 2. 地形材质画板 (Tile Palette)
        tile_group = QGroupBox("★ 瓦片材质选择")
        tile_layout = QVBoxLayout(tile_group)

        self.tile_btn_group = QButtonGroup(self)
        self.tiles_info = [
            (TileType.BRICK, "🧱 普通红砖墙 (可摧毁)", "#9E3B1B"),
            (TileType.STEEL, "⛓ 强化钢铁墙 (不可摧毁)", "#B5B9C2"),
            (TileType.EMPTY, "⬛ 荒野空地 (畅通无阻)", "#11100D"),
            (TileType.BASE, "🦅 帝国老鹰基地 (核心)", "#D35400")
        ]

        for i, (ttype, label_text, color_code) in enumerate(self.tiles_info):
            btn = QPushButton(f"  {label_text}")
            btn.setCheckable(True)
            if ttype == TileType.BRICK:
                btn.setChecked(True)
            btn.setStyleSheet(f"text-align: left; padding-left: 10px; border-left: 6px solid {color_code};")
            btn.clicked.connect(lambda checked, t=ttype: self._set_tile(t))
            tile_layout.addWidget(btn)
            self.tile_btn_group.addButton(btn, i)

        left_layout.addWidget(tile_group)

        # 3. 批量操作工具
        batch_group = QGroupBox("★ 区域快捷操作")
        batch_layout = QVBoxLayout(batch_group)

        btn_fill_all = QPushButton("🪣 当前材质填充全图")
        btn_fill_all.clicked.connect(self._fill_all_map)
        batch_layout.addWidget(btn_fill_all)

        btn_clear_all = QPushButton("🗑 清空全图为空地")
        btn_clear_all.clicked.connect(self._clear_all_map)
        batch_layout.addWidget(btn_clear_all)

        left_layout.addWidget(batch_group)

        # 4. 地图大小与参数设置
        size_group = QGroupBox("★ 地图大小设置")
        size_layout = QVBoxLayout(size_group)

        # 地图名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("名称:"))
        self.edit_name = QLineEdit("Custom Map")
        name_layout.addWidget(self.edit_name)
        size_layout.addLayout(name_layout)

        # 列数 Cols
        cols_layout = QHBoxLayout()
        cols_layout.addWidget(QLabel("列数 (宽):"))
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(8, 80)
        self.spin_cols.setValue(20)
        cols_layout.addWidget(self.spin_cols)
        size_layout.addLayout(cols_layout)

        # 行数 Rows
        rows_layout = QHBoxLayout()
        rows_layout.addWidget(QLabel("行数 (高):"))
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(8, 80)
        self.spin_rows.setValue(16)
        rows_layout.addWidget(self.spin_rows)
        size_layout.addLayout(rows_layout)

        # 瓦片尺寸
        ts_layout = QHBoxLayout()
        ts_layout.addWidget(QLabel("网格边长:"))
        self.spin_tile_size = QSpinBox()
        self.spin_tile_size.setRange(24, 48)
        self.spin_tile_size.setValue(36)
        self.spin_tile_size.setSuffix(" px")
        ts_layout.addWidget(self.spin_tile_size)
        size_layout.addLayout(ts_layout)

        btn_apply_size = QPushButton("✓ 应用地图大小调整")
        btn_apply_size.setStyleSheet("background-color: #5D4037; border: 1px solid #C8A048; color: #FFF3BD;")
        btn_apply_size.clicked.connect(self._apply_map_resize)
        size_layout.addWidget(btn_apply_size)

        left_layout.addWidget(size_group)

        # 5. 视图辅助控制
        view_group = QGroupBox("★ 视图控制")
        view_layout = QVBoxLayout(view_group)

        self.chk_grid = QCheckBox("显示网格标线")
        self.chk_grid.setChecked(True)
        self.chk_grid.toggled.connect(self._toggle_grid)
        view_layout.addWidget(self.chk_grid)

        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("缩放:"))
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

        left_layout.addWidget(view_group)

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
            TileType.EMPTY: "空地 [EMPTY]",
            TileType.BRICK: "普通红砖 [BRICK]",
            TileType.STEEL: "不可摧毁钢墙 [STEEL]",
            TileType.BASE: "老鹰基地 [BASE]"
        }
        tname = tile_names.get(tile, f"未知({tile})")
        msg = f"光标位置: 列 {col:02d}, 行 {row:02d} | 像素: ({px}, {py}) | 地形: {tname} | 模式: 拖框/点画"
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
        reply = QMessageBox.question(self, "确认全图填充", "确定将全图所有格子替换为当前选中的材质吗？", QMessageBox.Yes | QMessageBox.No)
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
        reply = QMessageBox.question(self, "确认清空地图", "确定清空全图所有瓦片吗？", QMessageBox.Yes | QMessageBox.No)
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
