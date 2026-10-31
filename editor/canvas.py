import math
from typing import Optional, List, Dict, Tuple, Any
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QMouseEvent, QPaintEvent
from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal

from map_loader.models import GameMap, TileType
from mission_loader.models import PlayerMissionInfo, EnemyMissionInfo
from resource.loader import ResourceLoader

class EditorMode:
    MAP_EDIT = "map_edit"
    UNIT_EDIT = "unit_edit"

class TerrainTool:
    BRUSH = "brush"
    BOX_FILL = "box_fill"
    ERASER = "eraser"

class EditorCanvas(QWidget):
    """
    帝国时代2风格地图与单位主视口画布
    - 支持高精细度瓦片绘制 (空地/砖墙/钢墙/基地)
    - 实时光标坐标反馈 (列号 Col, 行号 Row, 像素坐标 X, Y)
    - 既支持单格点画，又支持拖拽矩形框批量填充
    - 单位可视化叠层渲染、点击选择与拖拽重置出生点
    """

    hover_coord_changed = pyqtSignal(int, int, int, int, int) # (col, row, px, py, tile_type)
    map_modified = pyqtSignal()
    unit_selected = pyqtSignal(object) # PlayerMissionInfo or EnemyMissionInfo
    unit_moved = pyqtSignal(object, int, int) # (unit, new_col, new_row)
    unit_place_requested = pyqtSignal(int, int) # (col, row)

    def __init__(self, parent=None, game_map: Optional[GameMap] = None):
        if isinstance(parent, GameMap):
            super().__init__(None)
            self.game_map: Optional[GameMap] = parent
        else:
            super().__init__(parent)
            self.game_map: Optional[GameMap] = game_map
        self.mode = EditorMode.MAP_EDIT
        self.tool = TerrainTool.BRUSH
        self.selected_tile = TileType.BRICK
        self.resource_configs = ResourceLoader.load_configs()
        self.resource_tiles = {cfg.tile_id: cfg for cfg in self.resource_configs.values()}

        # 视图缩放与网格
        self.zoom = 1.0
        self.show_grid = True
        if self.game_map:
            self.update_canvas_size()

        # 光标与拖拽状态
        self.hover_col = -1
        self.hover_row = -1
        self.is_mouse_down = False
        self.drag_start_col = -1
        self.drag_start_row = -1
        self.drag_current_col = -1
        self.drag_current_row = -1

        # 单位编辑状态
        self.player_units: List[PlayerMissionInfo] = []
        self.enemies: List[EnemyMissionInfo] = []
        self.selected_unit: Optional[Any] = None
        self.dragging_unit: Optional[Any] = None
        self.placing_new_unit: bool = False

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_tile_type(self, tile_type: int):
        self.selected_tile = tile_type

    def set_tool(self, tool: TerrainTool):
        self.tool = tool

    def set_map(self, game_map: GameMap) -> None:
        self.game_map = game_map
        self.update_canvas_size()
        self.update()

    def set_units(self, player_units: List[PlayerMissionInfo], enemies: List[EnemyMissionInfo]) -> None:
        self.player_units = player_units
        self.enemies = enemies
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self.zoom = max(0.5, min(2.5, zoom))
        self.update_canvas_size()
        self.update()

    def update_canvas_size(self) -> None:
        if not self.game_map:
            self.setFixedSize(640, 480)
            return
        w = int(self.game_map.pixel_width * self.zoom)
        h = int(self.game_map.pixel_height * self.zoom)
        self.setFixedSize(w, h)

    def get_tile_size(self) -> float:
        if not self.game_map:
            return 32.0 * self.zoom
        return self.game_map.tile_size * self.zoom

    # ================= 鼠标交互事件 =================

    def mousePressEvent(self, event: QMouseEvent):
        if not self.game_map:
            return

        ts = self.get_tile_size()
        col = int(event.x() // ts)
        row = int(event.y() // ts)

        if not (0 <= col < self.game_map.cols and 0 <= row < self.game_map.rows):
            return

        self.is_mouse_down = True
        self.drag_start_col = col
        self.drag_start_row = row
        self.drag_current_col = col
        self.drag_current_row = row

        if event.button() == Qt.LeftButton:
            if self.mode == EditorMode.MAP_EDIT:
                if self.tool == TerrainTool.BRUSH:
                    self._apply_tile(col, row, self.selected_tile)
                elif self.tool == TerrainTool.ERASER:
                    self._apply_tile(col, row, TileType.EMPTY)
                # BOX_FILL 等待 mouseReleaseEvent
            elif self.mode == EditorMode.UNIT_EDIT:
                if self.placing_new_unit:
                    self.unit_place_requested.emit(col, row)
                    self.placing_new_unit = False
                else:
                    # 检查是否点击了已有单位
                    clicked_unit = self._find_unit_at(col, row)
                    self.selected_unit = clicked_unit
                    self.dragging_unit = clicked_unit
                    self.unit_selected.emit(clicked_unit)
                    self.update()

        elif event.button() == Qt.RightButton:
            # 右键快捷吸色或右键取消放置
            if self.mode == EditorMode.MAP_EDIT:
                tile = self.game_map.get_tile(col, row)
                self.selected_tile = tile
            elif self.mode == EditorMode.UNIT_EDIT:
                self.placing_new_unit = False
                self.selected_unit = None
                self.unit_selected.emit(None)
                self.update()

    def handle_mouse_move(self, px: float, py: float):
        if not self.game_map:
            return
        ts = self.get_tile_size()
        col = int(px // ts)
        row = int(py // ts)

        if 0 <= col < self.game_map.cols and 0 <= row < self.game_map.rows:
            self.hover_col = col
            self.hover_row = row
            tile_val = self.game_map.get_tile(col, row)
            self.hover_coord_changed.emit(col, row, int(px), int(py), tile_val)
        else:
            self.hover_col = -1
            self.hover_row = -1
        self.update()

    def _handle_mouse_move(self, px: float, py: float):
        self.handle_mouse_move(px, py)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.game_map:
            return

        ts = self.get_tile_size()
        col = int(event.x() // ts)
        row = int(event.y() // ts)

        # 实时光标信号发送
        if 0 <= col < self.game_map.cols and 0 <= row < self.game_map.rows:
            self.hover_col = col
            self.hover_row = row
            tile_val = self.game_map.get_tile(col, row)
            self.hover_coord_changed.emit(col, row, int(event.x()), int(event.y()), tile_val)
        else:
            self.hover_col = -1
            self.hover_row = -1

        if self.is_mouse_down:
            self.drag_current_col = col
            self.drag_current_row = row

            if self.mode == EditorMode.MAP_EDIT:
                if self.tool == TerrainTool.BRUSH:
                    if 0 <= col < self.game_map.cols and 0 <= row < self.game_map.rows:
                        self._apply_tile(col, row, self.selected_tile)
                elif self.tool == TerrainTool.ERASER:
                    if 0 <= col < self.game_map.cols and 0 <= row < self.game_map.rows:
                        self._apply_tile(col, row, TileType.EMPTY)

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self.game_map or not self.is_mouse_down:
            self.is_mouse_down = False
            return

        ts = self.get_tile_size()
        col = int(event.x() // ts)
        row = int(event.y() // ts)

        if self.mode == EditorMode.MAP_EDIT and self.tool == TerrainTool.BOX_FILL:
            c_min = max(0, min(self.drag_start_col, self.drag_current_col))
            c_max = min(self.game_map.cols - 1, max(self.drag_start_col, self.drag_current_col))
            r_min = max(0, min(self.drag_start_row, self.drag_current_row))
            r_max = min(self.game_map.rows - 1, max(self.drag_start_row, self.drag_current_row))

            for r in range(r_min, r_max + 1):
                for c in range(c_min, c_max + 1):
                    self.game_map.set_tile(c, r, self.selected_tile)
            self.map_modified.emit()

        elif self.mode == EditorMode.UNIT_EDIT and self.dragging_unit:
            if 0 <= col < self.game_map.cols and 0 <= row < self.game_map.rows:
                self.dragging_unit.spawn.x = col
                self.dragging_unit.spawn.y = row
                self.unit_moved.emit(self.dragging_unit, col, row)
            self.dragging_unit = None

        self.is_mouse_down = False
        self.update()

    def apply_brush_at_pixel(self, px: float, py: float, tile: Optional[int] = None) -> None:
        if not self.game_map:
            return
        ts = self.get_tile_size()
        col = int(px // ts)
        row = int(py // ts)
        t = self.selected_tile if tile is None else tile
        self._apply_tile(col, row, t)

    def apply_box_fill(self, c1: int, r1: int, c2: int, r2: int, tile: Optional[int] = None) -> None:
        if not self.game_map:
            return
        t = self.selected_tile if tile is None else tile
        c_min = max(0, min(c1, c2))
        c_max = min(self.game_map.cols - 1, max(c1, c2))
        r_min = max(0, min(r1, r2))
        r_max = min(self.game_map.rows - 1, max(r1, r2))
        for r in range(r_min, r_max + 1):
            for c in range(c_min, c_max + 1):
                self.game_map.set_tile(c, r, t)
        self.map_modified.emit()
        self.update()

    def _apply_tile(self, col: int, row: int, tile: int) -> None:
        if self.game_map and self.game_map.get_tile(col, row) != tile:
            self.game_map.set_tile(col, row, tile)
            self.map_modified.emit()
            self.update()

    def _find_unit_at(self, col: int, row: int) -> Optional[Any]:
        for u in self.player_units:
            if u.spawn.x == col and u.spawn.y == row:
                return u
        for e in self.enemies:
            if e.spawn.x == col and e.spawn.y == row:
                return e
        return None

    # ================= 画面绘制渲染 =================

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        if not self.game_map:
            painter.fillRect(self.rect(), QColor("#151310"))
            painter.setPen(QColor("#8C734B"))
            painter.setFont(QFont("Palatino", 16, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, "★ 帝国时代2风格战局编辑器 ★\n请新建或加载一张地图以开始")
            return

        ts = self.get_tile_size()
        cols = self.game_map.cols
        rows = self.game_map.rows

        # 1. 绘制各瓦片地形
        for r in range(rows):
            for c in range(cols):
                tile = self.game_map.get_tile(c, r)
                rx = c * ts
                ry = r * ts
                self._draw_tile(painter, rx, ry, ts, tile)

        # 2. 网格线
        if self.show_grid:
            painter.setPen(QPen(QColor(75, 60, 42, 190), 1))
            for c in range(cols + 1):
                x = int(c * ts)
                painter.drawLine(x, 0, x, int(rows * ts))
            for r in range(rows + 1):
                y = int(r * ts)
                painter.drawLine(0, y, int(cols * ts), y)

        # 3. 拖框框填充预览 (Box Fill Preview)
        if self.is_mouse_down and self.mode == EditorMode.MAP_EDIT and self.tool == TerrainTool.BOX_FILL:
            c_min = max(0, min(self.drag_start_col, self.drag_current_col))
            c_max = min(cols - 1, max(self.drag_start_col, self.drag_current_col))
            r_min = max(0, min(self.drag_start_row, self.drag_current_row))
            r_max = min(rows - 1, max(self.drag_start_row, self.drag_current_row))

            box_x = c_min * ts
            box_y = r_min * ts
            box_w = (c_max - c_min + 1) * ts
            box_h = (r_max - r_min + 1) * ts

            painter.setPen(QPen(QColor("#FFD700"), 2, Qt.DashLine))
            painter.setBrush(QBrush(QColor(230, 198, 110, 60)))
            painter.drawRect(QRectF(box_x, box_y, box_w, box_h))

        # 4. 单位叠层渲染 (Mode 2)
        if self.mode == EditorMode.UNIT_EDIT:
            self._draw_units(painter, ts)

        # 5. 地图金色外边框 (AoE2 Gold Border)
        map_w = cols * ts
        map_h = rows * ts
        painter.setPen(QPen(QColor("#D4AF37"), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(0, 0, map_w, map_h))

        # 6. 光标悬停框与坐标浮窗
        if 0 <= self.hover_col < cols and 0 <= self.hover_row < rows:
            hx = self.hover_col * ts
            hy = self.hover_row * ts
            painter.setPen(QPen(QColor("#FFE066"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(hx, hy, ts, ts))

            # 浮雕光标内角
            painter.setPen(QPen(QColor("#FFF5CC"), 1))
            painter.drawRect(QRectF(hx + 2, hy + 2, ts - 4, ts - 4))

    def _draw_tile(self, painter: QPainter, x: float, y: float, size: float, tile: int):
        rect = QRectF(x, y, size, size)
        if tile == TileType.EMPTY:
            # 荒原空地：暗原色羊皮地表微纹理
            painter.fillRect(rect, QColor("#1D1914"))
        elif tile == TileType.BRICK:
            # 经典红砖瓦片
            painter.fillRect(rect, QColor("#9E3B1B"))
            painter.setPen(QPen(QColor("#421508"), 1))
            painter.drawRect(rect)
            # 砖缝纹理
            half = size / 2.0
            painter.drawLine(int(x), int(y + half), int(x + size), int(y + half))
            painter.drawLine(int(x + half), int(y), int(x + half), int(y + half))
            painter.drawLine(int(x + size * 0.25), int(y + half), int(x + size * 0.25), int(y + size))
            painter.drawLine(int(x + size * 0.75), int(y + half), int(x + size * 0.75), int(y + size))
        elif tile == TileType.STEEL:
            # 钢砖板带四角铆钉
            painter.fillRect(rect, QColor("#B5B9C2"))
            painter.setPen(QPen(QColor("#545860"), 1))
            painter.drawRect(rect)
            # 铆钉
            rivet_s = max(2.0, size * 0.15)
            painter.fillRect(QRectF(x + 2, y + 2, rivet_s, rivet_s), QColor("#FFFFFF"))
            painter.fillRect(QRectF(x + size - 2 - rivet_s, y + 2, rivet_s, rivet_s), QColor("#FFFFFF"))
            painter.fillRect(QRectF(x + 2, y + size - 2 - rivet_s, rivet_s, rivet_s), QColor("#FFFFFF"))
            painter.fillRect(QRectF(x + size - 2 - rivet_s, y + size - 2 - rivet_s, rivet_s, rivet_s), QColor("#FFFFFF"))
        elif tile in self.resource_tiles:
            # 动态 JSON 加载资源矿块 (按配置色彩与外边框渲染)
            cfg = self.resource_tiles[tile]
            base_color = QColor(cfg.color)
            painter.fillRect(rect, base_color.darker(280))
            painter.setPen(QPen(base_color, 1))
            painter.drawRect(rect)
            half = size / 2.0
            painter.fillRect(QRectF(x + size * 0.25, y + size * 0.25, half, half), base_color)
            painter.fillRect(QRectF(x + size * 0.38, y + size * 0.38, size * 0.24, size * 0.24), base_color.lighter(140))
        elif tile == TileType.DARK_MATTER:
            painter.fillRect(rect, QColor("#341143"))
            painter.setPen(QPen(QColor("#8E44AD"), 1))
            painter.drawRect(rect)
            half = size / 2.0
            painter.fillRect(QRectF(x + size * 0.25, y + size * 0.25, half, half), QColor("#A569BD"))
            painter.fillRect(QRectF(x + size * 0.38, y + size * 0.38, size * 0.24, size * 0.24), QColor("#E8DAEF"))
        elif tile == TileType.ALLOY:
            painter.fillRect(rect, QColor("#1B2631"))
            painter.setPen(QPen(QColor("#2980B9"), 1))
            painter.drawRect(rect)
            painter.fillRect(QRectF(x + 3, y + 3, size - 6, size - 6), QColor("#3498DB"))
            painter.setPen(QPen(QColor("#AED6F1"), 1))
            painter.drawLine(int(x + 3), int(y + size / 2.0), int(x + size - 3), int(y + size / 2.0))
        elif tile == TileType.BASE:
            # 金鹰基地核心
            painter.fillRect(rect, QColor("#D35400"))
            painter.setPen(QPen(QColor("#F39C12"), 2))
            painter.drawRect(rect)
            painter.fillRect(QRectF(x + size * 0.2, y + size * 0.2, size * 0.6, size * 0.6), QColor("#F1C40F"))
            painter.setPen(QPen(QColor("#000000"), 1))
            painter.setFont(QFont("Arial", int(size * 0.3), QFont.Bold))
            painter.drawText(rect, Qt.AlignCenter, "★")

    def _draw_units(self, painter: QPainter, ts: float):
        # 绘制所有我方单位 (蓝/金主题)
        for u in self.player_units:
            is_sel = (u == self.selected_unit)
            self._draw_single_unit(painter, u, ts, is_player=True, is_selected=is_sel)

        # 绘制所有敌军单位 (猩红主题)
        for e in self.enemies:
            is_sel = (e == self.selected_unit)
            self._draw_single_unit(painter, e, ts, is_player=False, is_selected=is_sel)

    def _draw_single_unit(self, painter: QPainter, unit: Any, ts: float, is_player: bool, is_selected: bool):
        col = unit.spawn.x
        row = unit.spawn.y
        ux = col * ts
        uy = row * ts

        center_x = ux + ts / 2.0
        center_y = uy + ts / 2.0
        radius = ts * 0.42

        # 阵营色彩
        if is_player:
            main_col = QColor("#2980B9") if "tower" not in unit.config_file else QColor("#8E44AD")
            border_col = QColor("#5DADE2")
            if "clearing" in unit.config_file:
                main_col = QColor("#D35400")
                border_col = QColor("#F39C12")
        else:
            main_col = QColor("#C0392B")
            border_col = QColor("#E74C3C")

        # 选中高亮光环
        if is_selected:
            painter.setPen(QPen(QColor("#2ECC71"), 2, Qt.DashLine))
            painter.setBrush(QBrush(QColor(46, 204, 113, 50)))
            painter.drawEllipse(QPointF(center_x, center_y), radius + 4, radius + 4)

        # 单位底盘徽标
        painter.setPen(QPen(border_col, 2))
        painter.setBrush(QBrush(main_col))
        painter.drawEllipse(QPointF(center_x, center_y), radius, radius)

        # 视线虚线圈标记（若有）
        if unit.vision_size > 0:
            sight_r = (unit.vision_size / 2.0) * (ts / (self.game_map.tile_size if self.game_map else 32.0))
            painter.setPen(QPen(QColor(main_col.red(), main_col.green(), main_col.blue(), 70), 1, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(center_x - sight_r, center_y - sight_r, sight_r * 2, sight_r * 2))

        # ID 标签
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        id_rect = QRectF(ux - 10, uy + ts - 4, ts + 20, 12)
        painter.drawText(id_rect, Qt.AlignCenter, unit.id)
