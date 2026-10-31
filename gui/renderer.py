from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PyQt5.QtCore import QRectF, Qt
from map_loader.models import GameMap, TileType
from physics.entities import Tank, Bullet, Direction, Camp

class PixelRenderer:
    """像素风渲染器：使用正方形方块组合渲染品字形坦克、品字形炮弹与地图"""

    @staticmethod
    def draw_map(painter: QPainter, game_map: GameMap) -> None:
        tile_size = game_map.tile_size

        for row in range(game_map.rows):
            for col in range(game_map.cols):
                tile = game_map.get_tile(col, row)
                x = col * tile_size
                y = row * tile_size

                if tile == TileType.BRICK:
                    PixelRenderer._draw_brick_tile(painter, x, y, tile_size)
                elif tile == TileType.STEEL:
                    PixelRenderer._draw_steel_tile(painter, x, y, tile_size)
                elif tile == TileType.BASE:
                    PixelRenderer._draw_base_tile(painter, x, y, tile_size)

    @staticmethod
    def _draw_brick_tile(painter: QPainter, x: float, y: float, size: float) -> None:
        """老式小霸王像素砖墙：红褐色网格方块"""
        painter.fillRect(QRectF(x, y, size, size), QColor("#8B3A1A"))
        pen = QPen(QColor("#2B120A"), 1)
        painter.setPen(pen)

        mid_x = x + size / 2.0
        mid_y = y + size / 2.0

        painter.drawLine(int(x), int(mid_y), int(x + size), int(mid_y))
        painter.drawLine(int(mid_x), int(y), int(mid_x), int(mid_y))
        painter.drawLine(int(x + size * 0.25), int(mid_y), int(x + size * 0.25), int(y + size))
        painter.drawLine(int(x + size * 0.75), int(mid_y), int(x + size * 0.75), int(y + size))

        pen_light = QPen(QColor("#C86034"), 1)
        painter.setPen(pen_light)
        painter.drawLine(int(x), int(y), int(x + size - 1), int(y))
        painter.drawLine(int(x), int(y), int(x), int(y + size - 1))

    @staticmethod
    def _draw_steel_tile(painter: QPainter, x: float, y: float, size: float) -> None:
        """老式小霸王铁墙：白银色反光金属方块"""
        painter.fillRect(QRectF(x, y, size, size), QColor("#A8A8A8"))

        half = size / 2.0
        for dx in (0, half):
            for dy in (0, half):
                bx = x + dx
                by = y + dy
                painter.fillRect(QRectF(bx + 1, by + 1, half - 2, half - 2), QColor("#D0D0D0"))
                painter.setPen(QPen(QColor("#FFFFFF"), 1))
                painter.drawLine(int(bx + 1), int(by + 1), int(bx + half - 2), int(by + 1))
                painter.drawLine(int(bx + 1), int(by + 1), int(bx + 1), int(by + half - 2))
                painter.setPen(QPen(QColor("#505050"), 1))
                painter.drawLine(int(bx + half - 2), int(by + 1), int(bx + half - 2), int(by + half - 2))
                painter.drawLine(int(bx + 1), int(by + half - 2), int(bx + half - 2), int(by + half - 2))

    @staticmethod
    def _draw_base_tile(painter: QPainter, x: float, y: float, size: float) -> None:
        """基地大本营：老鹰/五角星基地"""
        painter.fillRect(QRectF(x, y, size, size), QColor("#111111"))
        margin = size * 0.15
        core_size = size - margin * 2
        painter.fillRect(QRectF(x + margin, y + margin, core_size, core_size), QColor("#D4AF37"))
        sub = size * 0.35
        painter.fillRect(QRectF(x + sub, y + sub, size - sub * 2, size - sub * 2), QColor("#E74C3C"))

    @staticmethod
    def draw_tank(painter: QPainter, tank: Tank) -> None:
        """
        绘制由正方形拼成的【品字形】坦克：
        品字形由 3 个正方形组成：1个朝前的凸起方块（炮塔），2个并排的后方方块（底座履带）
        """
        if not tank.alive:
            return

        size = tank.size
        unit = size / 2.0
        x = tank.x
        y = tank.y

        main_color = QColor(tank.color)
        light_color = main_color.lighter(130)
        dark_color = main_color.darker(150)
        border_pen = QPen(QColor("#111111"), 1)

        # 根据朝向计算品字形的3个正方形坐标 (第1个为前尖端炮塔，第2/3个为后底座)
        if tank.direction == Direction.UP:
            squares = [
                (x + unit / 2.0, y),
                (x, y + unit),
                (x + unit, y + unit)
            ]
        elif tank.direction == Direction.DOWN:
            squares = [
                (x + unit / 2.0, y + unit),
                (x, y),
                (x + unit, y)
            ]
        elif tank.direction == Direction.LEFT:
            squares = [
                (x, y + unit / 2.0),
                (x + unit, y),
                (x + unit, y + unit)
            ]
        elif tank.direction == Direction.RIGHT:
            squares = [
                (x + unit, y + unit / 2.0),
                (x, y),
                (x, y + unit)
            ]
        else:
            squares = [(x, y), (x + unit, y), (x, y + unit)]

        # 逐个绘制拼成“品”字形的正方形方块
        for i, (sx, sy) in enumerate(squares):
            rect = QRectF(sx, sy, unit, unit)
            painter.fillRect(rect, main_color)

            painter.setPen(border_pen)
            painter.drawRect(rect)

            painter.setPen(QPen(light_color, 1))
            painter.drawLine(int(sx + 1), int(sy + 1), int(sx + unit - 2), int(sy + 1))
            painter.drawLine(int(sx + 1), int(sy + 1), int(sx + 1), int(sy + unit - 2))

            painter.setPen(QPen(dark_color, 1))
            painter.drawLine(int(sx + unit - 2), int(sy + 1), int(sx + unit - 2), int(sy + unit - 2))
            painter.drawLine(int(sx + 1), int(sy + unit - 2), int(sx + unit - 2), int(sy + unit - 2))

            # 炮口方块（在尖端方块中央）
            if i == 0:
                pad = unit * 0.35
                painter.fillRect(QRectF(sx + pad, sy + pad, unit - pad * 2, unit - pad * 2), QColor("#000000"))

        # 如果血量大于1，在头顶显示迷你血槽方块
        if tank.max_health > 1:
            bar_w = size * 0.8
            bar_h = 3
            bar_x = x + size * 0.1
            bar_y = y - 6
            painter.fillRect(QRectF(bar_x, bar_y, bar_w, bar_h), QColor("#333333"))
            curr_w = bar_w * (tank.health / tank.max_health)
            painter.fillRect(QRectF(bar_x, bar_y, curr_w, bar_h), QColor("#2ECC71"))

    @staticmethod
    def draw_bullet(painter: QPainter, bullet: Bullet) -> None:
        """
        绘制由正方形拼成的【品字形】炮弹：
        微型的品字形，指向运动方向
        """
        if not bullet.alive:
            return

        size = bullet.size
        unit = size / 2.0
        x = bullet.x
        y = bullet.y

        bullet_color = QColor(bullet.color)
        border_pen = QPen(QColor("#000000"), 1)

        if bullet.direction == Direction.UP:
            squares = [
                (x + unit / 2.0, y),
                (x, y + unit),
                (x + unit, y + unit)
            ]
        elif bullet.direction == Direction.DOWN:
            squares = [
                (x + unit / 2.0, y + unit),
                (x, y),
                (x + unit, y)
            ]
        elif bullet.direction == Direction.LEFT:
            squares = [
                (x, y + unit / 2.0),
                (x + unit, y),
                (x + unit, y + unit)
            ]
        elif bullet.direction == Direction.RIGHT:
            squares = [
                (x + unit, y + unit / 2.0),
                (x, y),
                (x, y + unit)
            ]
        else:
            squares = [(x, y), (x + unit, y), (x, y + unit)]

        for sx, sy in squares:
            rect = QRectF(sx, sy, unit, unit)
            painter.fillRect(rect, bullet_color)
            painter.setPen(border_pen)
            painter.drawRect(rect)
