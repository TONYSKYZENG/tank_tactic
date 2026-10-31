import math
from typing import List, Optional
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QImage
from PyQt5.QtCore import QRectF, Qt
from map_loader.models import GameMap, TileType
from physics.entities import Tank, Bullet, Direction, Camp, Rect

class PixelRenderer:
    """像素风渲染器：使用正方形方块组合渲染品字形坦克、防御塔、品字形炮弹、地图、RTS 选框与战争迷雾"""

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
                elif tile == TileType.DARK_MATTER:
                    PixelRenderer._draw_dark_matter_tile(painter, x, y, tile_size)
                elif tile == TileType.ALLOY:
                    PixelRenderer._draw_alloy_tile(painter, x, y, tile_size)
                elif tile == TileType.BASE:
                    PixelRenderer._draw_base_tile(painter, x, y, tile_size)

    @staticmethod
    def _draw_brick_tile(painter: QPainter, x: float, y: float, size: float) -> None:
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
        painter.fillRect(QRectF(x, y, size, size), QColor("#111111"))
        margin = size * 0.15
        core_size = size - margin * 2
        painter.fillRect(QRectF(x + margin, y + margin, core_size, core_size), QColor("#D4AF37"))
        sub = size * 0.35
        painter.fillRect(QRectF(x + sub, y + sub, size - sub * 2, size - sub * 2), QColor("#E74C3C"))

    @staticmethod
    def _draw_dark_matter_tile(painter: QPainter, x: float, y: float, size: float) -> None:
        # 暗物质神秘矿块：深暗紫色基底 + 晶体切面 + 霓虹晶核
        painter.fillRect(QRectF(x, y, size, size), QColor("#1A092A"))
        half = size / 2.0
        quarter = size / 4.0

        # 外围水晶切面
        painter.fillRect(QRectF(x + 2, y + 2, half - 3, half - 3), QColor("#4A235A"))
        painter.fillRect(QRectF(x + half + 1, y + 2, half - 3, half - 3), QColor("#5B2C6F"))
        painter.fillRect(QRectF(x + 2, y + half + 1, half - 3, half - 3), QColor("#6C3483"))
        painter.fillRect(QRectF(x + half + 1, y + half + 1, half - 3, half - 3), QColor("#512E5F"))

        # 核心晶核脉冲菱形
        painter.fillRect(QRectF(x + quarter, y + quarter, half, half), QColor("#8E44AD"))
        inner_m = size * 0.35
        painter.fillRect(QRectF(x + inner_m, y + inner_m, size - inner_m * 2, size - inner_m * 2), QColor("#D2B4DE"))

        # 高光晶体棱线
        pen_glow = QPen(QColor("#BB8FCE"), 1)
        painter.setPen(pen_glow)
        painter.drawLine(int(x + 2), int(y + 2), int(x + size - 2), int(y + 2))
        painter.drawLine(int(x + 2), int(y + 2), int(x + 2), int(y + size - 2))

    @staticmethod
    def _draw_alloy_tile(painter: QPainter, x: float, y: float, size: float) -> None:
        # 合金工业装甲矿块：科技金属蓝 + 铆钉防滑纹 + 高科铭板
        painter.fillRect(QRectF(x, y, size, size), QColor("#1B2631"))
        half = size / 2.0
        # 金属防弹板
        painter.fillRect(QRectF(x + 2, y + 2, size - 4, size - 4), QColor("#2874A6"))
        painter.fillRect(QRectF(x + 5, y + 5, size - 10, size - 10), QColor("#3498DB"))

        # 强化棱条与铆钉
        pen_line = QPen(QColor("#85C1E9"), 1)
        painter.setPen(pen_line)
        painter.drawLine(int(x + 5), int(y + half), int(x + size - 5), int(y + half))
        painter.drawLine(int(x + half), int(y + 5), int(x + half), int(y + size - 5))

        # 4角高科铆钉
        pen_dot = QPen(QColor("#EBF5FB"), 2)
        painter.setPen(pen_dot)
        painter.drawPoint(int(x + 6), int(y + 6))
        painter.drawPoint(int(x + size - 6), int(y + 6))
        painter.drawPoint(int(x + 6), int(y + size - 6))
        painter.drawPoint(int(x + size - 6), int(y + size - 6))

    @staticmethod
    def draw_tank(painter: QPainter, tank: Tank, is_selected: bool = False,
                  is_micro: bool = False, auto_clear: bool = False,
                  tile_size: float = 36.0) -> None:
        """
        绘制机动坦克或防御塔（雷达塔、重炮塔、补给要塞）
        """
        if not tank.alive:
            return

        size = tank.size
        x = tank.x
        y = tank.y

        # 如果是防御塔，采用堡垒像素风渲染
        if tank.is_tower:
            PixelRenderer._draw_defense_tower(painter, tank, is_selected, is_micro)
            return

        # ===== 常规机动坦克品字形渲染 =====
        unit = size / 2.0
        main_color = QColor(tank.color)
        light_color = main_color.lighter(130)
        dark_color = main_color.darker(150)
        border_pen = QPen(QColor("#111111"), 1)

        # 1. 选中框
        if is_selected:
            sel_pen = QPen(QColor("#2ECC71"), 1.5, Qt.DashLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(x - 3, y - 3, size + 6, size + 6))

        # 2. 微操光标
        if is_micro:
            micro_pen = QPen(QColor("#F1C40F"), 2)
            painter.setPen(micro_pen)
            corner_len = 6
            painter.drawLine(int(x - 5), int(y - 5), int(x - 5 + corner_len), int(y - 5))
            painter.drawLine(int(x - 5), int(y - 5), int(x - 5), int(y - 5 + corner_len))
            painter.drawLine(int(x + size + 5), int(y - 5), int(x + size + 5 - corner_len), int(y - 5))
            painter.drawLine(int(x + size + 5), int(y - 5), int(x + size + 5), int(y - 5 + corner_len))
            painter.drawLine(int(x - 5), int(y + size + 5), int(x - 5 + corner_len), int(y + size + 5))
            painter.drawLine(int(x - 5), int(y + size + 5), int(x - 5), int(y + size + 5 - corner_len))
            painter.drawLine(int(x + size + 5), int(y + size + 5), int(x + size + 5 - corner_len), int(y + size + 5))
            painter.drawLine(int(x + size + 5), int(y + size + 5), int(x + size + 5), int(y + size + 5 - corner_len))

            painter.setFont(QFont("Courier New", 8, QFont.Bold))
            painter.setPen(QPen(QColor("#F1C40F")))
            if auto_clear:
                tag_text = "▼MICRO [开路]"
            elif getattr(tank, "can_crush_bricks", False):
                tag_text = "▼MICRO [清障]"
            else:
                tag_text = "▼MICRO"
            painter.drawText(QRectF(x - 25, y - 16, size + 50, 12), Qt.AlignCenter, tag_text)
        elif getattr(tank, "can_crush_bricks", False):
            painter.setFont(QFont("Courier New", 8, QFont.Bold))
            painter.setPen(QPen(QColor("#E67E22")))
            painter.drawText(QRectF(x - 10, y - 12, size + 20, 10), Qt.AlignCenter, "[清障]")
        elif auto_clear:
            painter.setFont(QFont("Courier New", 8, QFont.Bold))
            painter.setPen(QPen(QColor("#E67E22")))
            painter.drawText(QRectF(x - 10, y - 12, size + 20, 10), Qt.AlignCenter, "[开路]")

        if getattr(tank, "is_converting", False):
            painter.setFont(QFont("Courier New", 8, QFont.Bold))
            painter.setPen(QPen(QColor("#00E5FF")))
            painter.drawText(QRectF(x - 25, y - 26 if is_micro else y - 14, size + 50, 12), Qt.AlignCenter, "[⚙CONVERT]")
        elif getattr(tank, "is_harvesting", False):
            h_state = getattr(tank, "harvest_state", "harvesting")
            painter.setFont(QFont("Courier New", 8, QFont.Bold))
            if h_state == "contested":
                painter.setPen(QPen(QColor("#E74C3C")))
                tag = "[⚡争夺]"
            elif h_state == "out_of_range":
                painter.setPen(QPen(QColor("#F39C12")))
                tag = "[超距]"
            elif h_state == "depleted":
                painter.setPen(QPen(QColor("#7F8C8D")))
                tag = "[枯竭]"
            else:
                painter.setPen(QPen(QColor("#F1C40F")))
                tag = "[⛏采集]"
            painter.drawText(QRectF(x - 25, y - 26 if is_micro else y - 14, size + 50, 12), Qt.AlignCenter, tag)

            # 绘制开采牵引光束到目标资源块
            if h_state == "harvesting" and getattr(tank, "harvest_target", None):
                target = tank.harvest_target
                ts = float(tile_size)
                bx = (target[0] + 0.5) * ts
                by = (target[1] + 0.5) * ts
                tcx = x + size / 2.0
                tcy = y + size / 2.0
                painter.save()
                painter.setPen(QPen(QColor(0, 229, 255, 160), 2, Qt.DashLine))
                painter.drawLine(int(tcx), int(tcy), int(bx), int(by))
                painter.restore()

        # 3. 品字形方块（支持自由旋转角度）
        painter.save()
        cx = x + size / 2.0
        cy = y + size / 2.0
        painter.translate(cx, cy)
        painter.rotate(tank.angle)

        lx = -size / 2.0
        ly = -size / 2.0

        # 若具备碾压普通砖块能力（清障车），在车头前方绘制重型防撞推土铲斗 (Dozer Blade)
        if getattr(tank, "can_crush_bricks", False):
            blade_w = size + 4.0
            blade_h = 4.0
            blade_x = -blade_w / 2.0
            blade_y = ly - 3.0
            painter.fillRect(QRectF(blade_x, blade_y, blade_w, blade_h), QColor("#E67E22"))
            painter.setPen(border_pen)
            painter.drawRect(QRectF(blade_x, blade_y, blade_w, blade_h))
            painter.setPen(QPen(QColor("#F39C12"), 1))
            painter.drawLine(int(blade_x + 2), int(blade_y + 1), int(blade_x + blade_w - 2), int(blade_y + 1))

        # 基准朝上品字形：(前置主炮, 后置左履带, 后置右履带)
        squares = [
            (lx + unit / 2.0, ly),
            (lx, ly + unit),
            (lx + unit, ly + unit)
        ]

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

            if i == 0:
                pad = unit * 0.35
                muzzle_color = QColor("#D35400") if auto_clear else QColor("#000000")
                painter.fillRect(QRectF(sx + pad, sy + pad, unit - pad * 2, unit - pad * 2), muzzle_color)

        painter.restore()

        # 4. 血条、补给特效与弹药
        top_offset = 18 if (is_micro or auto_clear) else 8
        if tank.max_health > 1:
            bar_w = size * 0.8
            bar_h = 3
            bar_x = x + size * 0.1
            bar_y = y - top_offset
            painter.fillRect(QRectF(bar_x, bar_y, bar_w, bar_h), QColor("#333333"))
            curr_w = bar_w * (tank.health / tank.max_health)
            painter.fillRect(QRectF(bar_x, bar_y, curr_w, bar_h), QColor("#2ECC71"))
            top_offset += 5

        # 补给获得特效 (+AMMO) 与不可控友军 AI 标记
        if tank.just_resupplied_timer > 0:
            painter.setFont(QFont("Courier New", 8, QFont.Bold))
            painter.setPen(QPen(QColor("#2ECC71")))
            painter.drawText(QRectF(x - 10, y - top_offset - 10, size + 20, 10), Qt.AlignCenter, "+AMMO")
        elif tank.camp == Camp.PLAYER and not getattr(tank, "controllable", True):
            painter.setFont(QFont("Courier New", 7, QFont.Bold))
            painter.setPen(QPen(QColor("#00D2D3")))
            painter.drawText(QRectF(x - 15, y - top_offset - 8, size + 30, 10), Qt.AlignCenter, "[AI AUTO]")
        elif tank.camp == Camp.PLAYER and tank.ammo == 0:
            painter.setFont(QFont("Courier New", 7, QFont.Bold))
            painter.setPen(QPen(QColor("#E74C3C")))
            painter.drawText(QRectF(x - 10, y - top_offset - 8, size + 20, 10), Qt.AlignCenter, "NO AMMO")

    @staticmethod
    def _draw_defense_tower(painter: QPainter, tower: Tank, is_selected: bool, is_micro: bool) -> None:
        """
        绘制坚固的防御要塞（纯视野雷达哨所、加农防御炮台、弹药补给要塞）
        """
        size = tower.size
        x = tower.x
        y = tower.y
        base_color = QColor(tower.color)
        border_pen = QPen(QColor("#111111"), 1.5)

        # 1. 补给塔有效半径光环
        if tower.resupply_radius > 0:
            cx = x + size / 2.0
            cy = y + size / 2.0
            r = tower.resupply_radius
            aura_pen = QPen(QColor(46, 204, 113, 100), 1, Qt.DashLine)
            painter.setPen(aura_pen)
            painter.setBrush(QColor(46, 204, 113, 15))
            painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # 2. 选中绿框
        if is_selected:
            sel_pen = QPen(QColor("#2ECC71"), 1.5, Qt.DashLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(x - 4, y - 4, size + 8, size + 8))

        # 3. 要塞四角外包围防壁（四个角块）
        corner_s = size * 0.3
        for cx in (x, x + size - corner_s):
            for cy in (y, y + size - corner_s):
                painter.fillRect(QRectF(cx, cy, corner_s, corner_s), base_color.darker(130))
                painter.setPen(border_pen)
                painter.drawRect(QRectF(cx, cy, corner_s, corner_s))

        # 4. 要塞中心主方块
        margin = size * 0.15
        core_rect = QRectF(x + margin, y + margin, size - margin * 2, size - margin * 2)
        painter.fillRect(core_rect, base_color)
        painter.setPen(border_pen)
        painter.drawRect(core_rect)

        # 5. 根据防御塔类型绘制核心功能装置
        cx = x + size / 2.0
        cy = y + size / 2.0

        if tower.tower_type == "radar":
            # 纯视野雷达塔：中心雷达天线阵列与微光绿核
            r_size = size * 0.35
            painter.fillRect(QRectF(cx - r_size / 2.0, cy - r_size / 2.0, r_size, r_size), QColor("#1ABC9C"))
            painter.setPen(QPen(QColor("#FFFFFF"), 1))
            painter.drawCross(int(cx), int(cy), int(r_size / 2.0)) if hasattr(painter, 'drawCross') else None
            painter.drawLine(int(cx - r_size / 2.0), int(cy), int(cx + r_size / 2.0), int(cy))
            painter.drawLine(int(cx), int(cy - r_size / 2.0), int(cx), int(cy + r_size / 2.0))

            painter.setFont(QFont("Courier New", 8, QFont.Bold))
            painter.setPen(QPen(QColor("#1ABC9C")))
            painter.drawText(QRectF(x - 15, y - 14, size + 30, 10), Qt.AlignCenter, "[RADAR]")

        elif tower.tower_type == "cannon":
            # 带炮台的加农防御塔：中心粗壮旋转加农炮口（支持全向旋转）
            cannon_len = size * 0.45
            bar_w = size * 0.22
            t_angle = getattr(tower, "angle", tower.direction.to_angle())
            rad = math.radians(t_angle)
            p_dx = math.sin(rad) * cannon_len
            p_dy = -math.cos(rad) * cannon_len
            painter.fillRect(QRectF(cx - bar_w / 2.0 + p_dx * 0.4, cy - bar_w / 2.0 + p_dy * 0.4, bar_w, bar_w), QColor("#000000"))

            # 炮塔座
            painter.fillRect(QRectF(cx - 5, cy - 5, 10, 10), QColor("#333333"))

            painter.setFont(QFont("Courier New", 8, QFont.Bold))
            painter.setPen(QPen(QColor("#BB8FCE")))
            painter.drawText(QRectF(x - 15, y - 14, size + 30, 10), Qt.AlignCenter, "[CANNON]")

        elif tower.tower_type == "supply":
            # 弹药补给要塞 (核心鹰巢重制版)：中心白色与金黄色弹药补给十字
            plus_len = size * 0.35
            plus_w = size * 0.12
            painter.fillRect(QRectF(cx - plus_w / 2.0, cy - plus_len / 2.0, plus_w, plus_len), QColor("#FFFFFF"))
            painter.fillRect(QRectF(cx - plus_len / 2.0, cy - plus_w / 2.0, plus_len, plus_w), QColor("#FFFFFF"))

            painter.setFont(QFont("Courier New", 8, QFont.Bold))
            painter.setPen(QPen(QColor("#F1C40F")))
            painter.drawText(QRectF(x - 20, y - 14, size + 40, 10), Qt.AlignCenter, "[BASE+AMMO]")

        # 6. 血条
        if tower.max_health > 1:
            bar_w = size * 0.85
            bar_h = 3
            bar_x = x + size * 0.075
            bar_y = y - 6
            painter.fillRect(QRectF(bar_x, bar_y, bar_w, bar_h), QColor("#333333"))
            curr_w = bar_w * (tower.health / tower.max_health)
            painter.fillRect(QRectF(bar_x, bar_y, curr_w, bar_h), QColor("#2ECC71"))

    @staticmethod
    def draw_bullet(painter: QPainter, bullet: Bullet) -> None:
        if not bullet.alive:
            return

        size = bullet.size
        unit = size / 2.0
        x = bullet.x
        y = bullet.y

        bullet_color = QColor(bullet.color)
        border_pen = QPen(QColor("#000000"), 1)

        painter.save()
        bcx = bullet.x + bullet.size / 2.0
        bcy = bullet.y + bullet.size / 2.0
        painter.translate(bcx, bcy)
        b_angle = getattr(bullet, "angle", bullet.direction.to_angle())
        painter.rotate(b_angle)

        lx = -bullet.size / 2.0
        ly = -bullet.size / 2.0
        # 向上发射基准品字形
        squares = [
            (lx + unit / 2.0, ly),
            (lx, ly + unit),
            (lx + unit, ly + unit)
        ]

        for sx, sy in squares:
            rect = QRectF(sx, sy, unit, unit)
            painter.fillRect(rect, bullet_color)
            painter.setPen(border_pen)
            painter.drawRect(rect)

        painter.restore()

    @staticmethod
    def draw_selection_box(painter: QPainter, x1: float, y1: float, x2: float, y2: float) -> None:
        rx = min(x1, x2)
        ry = min(y1, y2)
        rw = abs(x2 - x1)
        rh = abs(y2 - y1)

        if rw <= 1 and rh <= 1:
            return

        rect = QRectF(rx, ry, rw, rh)
        painter.fillRect(rect, QColor(46, 204, 113, 40))
        painter.setPen(QPen(QColor(46, 204, 113), 1, Qt.SolidLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)

    @staticmethod
    def draw_command_marker(painter: QPainter, x: float, y: float, is_attack: bool = False) -> None:
        if is_attack:
            painter.setPen(QPen(QColor("#E74C3C"), 2))
            r = 10
            painter.drawEllipse(QRectF(x - r, y - r, r * 2, r * 2))
            painter.drawLine(int(x - r - 4), int(y), int(x + r + 4), int(y))
            painter.drawLine(int(x), int(y - r - 4), int(x), int(y + r + 4))
        else:
            painter.setPen(QPen(QColor("#2ECC71"), 1.5))
            r = 8
            painter.drawEllipse(QRectF(x - r, y - r, r * 2, r * 2))
            painter.drawLine(int(x - 4), int(y), int(x + 4), int(y))
            painter.drawLine(int(x), int(y - 4), int(x), int(y + 4))

    @staticmethod
    def draw_fog_of_war(painter: QPainter, width: int, height: int, sight_rects: List[Rect]) -> None:
        fog_img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        fog_img.fill(QColor(10, 10, 16, 225))

        fog_painter = QPainter(fog_img)
        fog_painter.setCompositionMode(QPainter.CompositionMode_Clear)
        for r in sight_rects:
            fog_painter.fillRect(QRectF(r.x, r.y, r.width, r.height), Qt.transparent)

        fog_painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        radar_pen = QPen(QColor(46, 204, 113, 60), 1, Qt.DashLine)
        fog_painter.setPen(radar_pen)
        fog_painter.setBrush(Qt.NoBrush)
        for r in sight_rects:
            fog_painter.drawRect(QRectF(r.x, r.y, r.width, r.height))

        fog_painter.end()
        painter.drawImage(0, 0, fog_img)

    @staticmethod
    def draw_lost_enemy_memory(painter: QPainter, mem) -> None:
        """
        绘制跟丢敌军记忆残影：
        使用醒目的红色虚线框标记，标注问号及单位类型，只标记最后一次发现的坐标
        """
        painter.save()
        rect = QRectF(mem.x, mem.y, mem.size, mem.size)

        # 红色虚线框
        pen = QPen(QColor(231, 76, 60, 220), 1.8, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QColor(231, 76, 60, 35))
        painter.drawRect(rect)

        # 居中文本标记 ? 及单位类型
        painter.setPen(QPen(QColor(231, 76, 60, 255)))
        font = QFont("Courier New", 8, QFont.Bold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, f"?\n{mem.unit_type}")
        painter.restore()
