import random
import time
import math
from typing import List, Optional, Tuple, Dict, Any
from map_loader.models import GameMap, TileType
from .entities import Tank, Bullet, Direction, Rect, Camp, EnemyMemoryEntry

class PhysicsEngine:
    def __init__(self, game_map: GameMap, fog_of_war_enabled: bool = True,
                 limited_ammo_enabled: bool = True):
        self.game_map = game_map
        self.fog_of_war_enabled = fog_of_war_enabled
        self.limited_ammo_enabled = limited_ammo_enabled

        self.player_tanks: List[Tank] = []
        self.enemy_tanks: List[Tank] = []
        self.bullets: List[Bullet] = []

        # ===== 敌方全局记忆系统 (Enemy Memory) =====
        # 记录被实锤发现过的敌军最后坐标、类型与追踪状态
        self.enemy_memory: Dict[str, EnemyMemoryEntry] = {}

    @property
    def player_tank(self) -> Optional[Tank]:
        for t in self.player_tanks:
            if t.alive and not t.is_tower:
                return t
        for t in self.player_tanks:
            if t.alive:
                return t
        return None

    def set_player_tank(self, tank: Tank) -> None:
        self.player_tanks = [tank]

    def add_player_tank(self, tank: Tank) -> None:
        self.player_tanks.append(tank)

    def add_enemy_tank(self, tank: Tank) -> None:
        self.enemy_tanks.append(tank)

    def get_all_active_tanks(self) -> List[Tank]:
        tanks = [t for t in self.player_tanks if t.alive]
        tanks.extend([t for t in self.enemy_tanks if t.alive])
        return tanks

    # ================= 视线与战争迷雾系统 =================

    def get_player_sight_rects(self) -> List[Rect]:
        """获取所有我方存活单位及基地周边的正方形视线区域"""
        map_w = self.game_map.pixel_width
        map_h = self.game_map.pixel_height
        sight_rects: List[Rect] = []

        # 1. 我方坦克视线
        for t in self.player_tanks:
            if t.alive:
                sight_rects.append(t.get_sight_rect(map_w, map_h))

        return sight_rects

    def update_vision_and_stealth(self) -> None:
        """
        每帧更新单位视线范围与敌军在视线内的辨识度探测：
        - 迷雾关闭时全图可见
        - 迷雾开启时：
          - 视线区外的敌军绝对不可见 (is_spotted = False)
          - 视线区内的敌军，根据其辨识度 visibility (0.0~1.0) 判定是否被发现显形
        """
        if not self.fog_of_war_enabled:
            for e in self.enemy_tanks:
                e.is_spotted = True
            return

        sight_rects = self.get_player_sight_rects()
        map_w = self.game_map.pixel_width
        map_h = self.game_map.pixel_height

        # 检查是否有我方单位拥有全图视野 (-1)
        has_full_map_vision = any(t.vision_size < 0 for t in self.player_tanks if t.alive)

        for enemy in self.enemy_tanks:
            if not enemy.alive:
                enemy.is_spotted = False
                continue

            if has_full_map_vision:
                in_sight = True
            else:
                in_sight = any(enemy.rect.collides_with(sr) for sr in sight_rects)

            if not in_sight:
                enemy.is_spotted = False
                enemy.spotted_timer = 0
            else:
                # 在视线区内
                if enemy.visibility >= 1.0:
                    enemy.is_spotted = True
                    enemy.spotted_timer = 20
                else:
                    # 概率抽样判定
                    if random.random() < enemy.visibility:
                        enemy.is_spotted = True
                        enemy.spotted_timer = 20  # 保持显形防止高频闪烁
                    else:
                        if enemy.spotted_timer <= 0:
                            enemy.is_spotted = False

            # ===== 敌方全局记忆系统更新 =====
            # 1. 一旦被任何我方实锤发现 (带视野 + 带可见度)，建立或更新字典
            if enemy.is_spotted:
                u_type = getattr(enemy, "unit_type", None)
                if not u_type:
                    cfg = getattr(enemy, "_config", None)
                    u_type = cfg.name if cfg else "tank"

                if enemy.id not in self.enemy_memory:
                    self.enemy_memory[enemy.id] = EnemyMemoryEntry(
                        enemy_id=enemy.id,
                        x=enemy.x,
                        y=enemy.y,
                        size=enemy.size,
                        unit_type=u_type,
                        color=enemy.color,
                        is_tracking=True,
                        last_seen_time=time.time()
                    )
                else:
                    mem = self.enemy_memory[enemy.id]
                    mem.x = enemy.x
                    mem.y = enemy.y
                    mem.is_tracking = True
                    mem.last_seen_time = time.time()
            else:
                # 2. 如果跟丢了 (不再处于视野或未通过辨识度)，仅标记 is_tracking 为 False，保留最后一次坐标
                if enemy.id in self.enemy_memory:
                    self.enemy_memory[enemy.id].is_tracking = False

    def get_visible_enemies(self) -> List[Tank]:
        """获取当前对我方可见的所有敌军坦克 (迷雾外的敌军无法被追踪或攻击)"""
        if not self.fog_of_war_enabled:
            return [e for e in self.enemy_tanks if e.alive]
        return [e for e in self.enemy_tanks if e.alive and e.is_spotted]

    def is_enemy_visible(self, enemy: Tank) -> bool:
        """指定敌军当前是否对我方可见"""
        if not self.fog_of_war_enabled:
            return enemy.alive
        return enemy.alive and enemy.is_spotted

    # ================= 碰撞与移动系统 =================

    def can_move_to(self, moving_tank: Tank, new_x: float, new_y: float) -> bool:
        if new_x < 0 or new_x + moving_tank.size > self.game_map.pixel_width:
            return False
        if new_y < 0 or new_y + moving_tank.size > self.game_map.pixel_height:
            return False

        tile_size = self.game_map.tile_size
        # 使用 0.5 像素轻微内缩检测障碍瓦片，消除在标准宽度通道内微小浮点误差导致的贴墙刮蹭阻死
        tank_rect = Rect(new_x + 0.5, new_y + 0.5, moving_tank.size - 1.0, moving_tank.size - 1.0)

        col_start = max(0, int(new_x // tile_size))
        col_end = min(self.game_map.cols - 1, int((new_x + moving_tank.size - 0.01) // tile_size))
        row_start = max(0, int(new_y // tile_size))
        row_end = min(self.game_map.rows - 1, int((new_y + moving_tank.size - 0.01) // tile_size))

        can_crush = getattr(moving_tank, "can_crush_bricks", False)
        for row in range(row_start, row_end + 1):
            for col in range(col_start, col_end + 1):
                tile = self.game_map.get_tile(col, row)
                # 若坦克具备碾压砖块能力，普通砖块不作为阻碍
                blocks = (TileType.STEEL, TileType.BASE) if can_crush else (TileType.BRICK, TileType.STEEL, TileType.BASE)
                if tile in blocks:
                    tile_rect = Rect(col * tile_size, row * tile_size, tile_size, tile_size)
                    if tank_rect.collides_with(tile_rect):
                        return False

        exact_tank_rect = Rect(new_x, new_y, moving_tank.size, moving_tank.size)
        for other in self.get_all_active_tanks():
            if other is not moving_tank and other.alive:
                if exact_tank_rect.collides_with(other.rect):
                    return False

        return True

    def get_blocking_tank(self, moving_tank: Tank, new_x: float, new_y: float) -> Optional[Tank]:
        """返回在 (new_x, new_y) 处阻挡 moving_tank 前进的其他活动坦克（若有）"""
        exact_tank_rect = Rect(new_x, new_y, moving_tank.size, moving_tank.size)
        for other in self.get_all_active_tanks():
            if other is not moving_tank and other.alive:
                if exact_tank_rect.collides_with(other.rect):
                    return other
        return None

    def find_nearest_free_position(self, start_x: float, start_y: float, size: int) -> Tuple[float, float]:
        tile_size = self.game_map.tile_size
        aligned_start_x = round(start_x / tile_size) * tile_size
        aligned_start_y = round(start_y / tile_size) * tile_size
        dummy_tank = Tank(aligned_start_x, aligned_start_y, size=size)
        if self.can_move_to(dummy_tank, aligned_start_x, aligned_start_y):
            return aligned_start_x, aligned_start_y

        for radius in range(1, max(self.game_map.cols, self.game_map.rows)):
            for r in range(-radius, radius + 1):
                for c in range(-radius, radius + 1):
                    test_x = aligned_start_x + c * tile_size
                    test_y = aligned_start_y + r * tile_size
                    if self.can_move_to(dummy_tank, test_x, test_y):
                        return test_x, test_y

        return aligned_start_x, aligned_start_y

    def _is_crushing_bricks(self, tank: Tank, x: float, y: float) -> bool:
        """检查坦克在 (x, y) 处是否与普通砖块接触重叠"""
        tile_size = self.game_map.tile_size
        col_start = max(0, int(x // tile_size))
        col_end = min(self.game_map.cols - 1, int((x + tank.size - 0.01) // tile_size))
        row_start = max(0, int(y // tile_size))
        row_end = min(self.game_map.rows - 1, int((y + tank.size - 0.01) // tile_size))
        tank_rect = Rect(x, y, tank.size, tank.size)
        for row in range(row_start, row_end + 1):
            for col in range(col_start, col_end + 1):
                if self.game_map.get_tile(col, row) == TileType.BRICK:
                    tile_rect = Rect(col * tile_size, row * tile_size, tile_size, tile_size)
                    if tank_rect.collides_with(tile_rect):
                        return True
        return False

    def _crush_bricks_at(self, tank: Tank, x: float, y: float) -> bool:
        """摧毁坦克当前位置覆盖到的所有普通砖块（碾压破坏）"""
        if not getattr(tank, "can_crush_bricks", False):
            return False
        tile_size = self.game_map.tile_size
        col_start = max(0, int(x // tile_size))
        col_end = min(self.game_map.cols - 1, int((x + tank.size - 0.01) // tile_size))
        row_start = max(0, int(y // tile_size))
        row_end = min(self.game_map.rows - 1, int((y + tank.size - 0.01) // tile_size))
        tank_rect = Rect(x, y, tank.size, tank.size)
        crushed = False
        for row in range(row_start, row_end + 1):
            for col in range(col_start, col_end + 1):
                if self.game_map.get_tile(col, row) == TileType.BRICK:
                    tile_rect = Rect(col * tile_size, row * tile_size, tile_size, tile_size)
                    if tank_rect.collides_with(tile_rect):
                        self.game_map.destroy_tile(col, row)
                        crushed = True
        return crushed

    def move_tank(self, tank: Tank, direction: Any, speed: Optional[float] = None) -> bool:
        """
        移动坦克（支持四向枚举、任意浮点角度 0~360°、或 2D 向量元组 (dx, dy)）
        支持自由旋转、平滑全向机动、碾压普通砖块速度衰减与贴墙滑动 (Wall Sliding)
        """
        if not tank.alive or tank.is_tower or tank.speed <= 0 or getattr(tank, "is_converting", False):
            return False

        tile_size = self.game_map.tile_size
        step_speed = tank.speed if speed is None else float(speed)

        if isinstance(direction, Direction):
            angle = direction.to_angle()
            tank.angle = angle
            dx_norm = float(direction.dx)
            dy_norm = float(direction.dy)
        elif isinstance(direction, (int, float)):
            angle = float(direction) % 360.0
            tank.angle = angle
            rad = math.radians(angle)
            dx_norm = math.sin(rad)
            dy_norm = -math.cos(rad)
        elif isinstance(direction, (tuple, list)) and len(direction) == 2:
            vx, vy = float(direction[0]), float(direction[1])
            dist = math.hypot(vx, vy)
            if dist < 1e-5:
                return False
            dx_norm = vx / dist
            dy_norm = vy / dist
            angle = math.degrees(math.atan2(dx_norm, -dy_norm)) % 360.0
            tank.angle = angle
        else:
            return False

        curr_x, curr_y = tank.x, tank.y

        # 若坦克具备碾压砖块能力，且当前或即将接触砖块，移速衰减
        if getattr(tank, "can_crush_bricks", False):
            if self._is_crushing_bricks(tank, curr_x, curr_y) or self._is_crushing_bricks(tank, curr_x + dx_norm * step_speed, curr_y + dy_norm * step_speed):
                factor = getattr(tank, "crush_speed_factor", 0.5)
                step_speed = max(0.5, step_speed * factor)

        vx = dx_norm * step_speed
        vy = dy_norm * step_speed

        # 1. 优先尝试沿目标向量完整自由位移（不强行吸附网格，确保任意角度斜向平滑移动）
        new_x = curr_x + vx
        new_y = curr_y + vy

        if self.can_move_to(tank, new_x, new_y):
            tank.x = new_x
            tank.y = new_y
            self._crush_bricks_at(tank, tank.x, tank.y)
            return True

        # 2. 走廊拐角对齐辅助：仅当直接位移受阻且行进方向接近正交轴向时，微调吸附通道中心线
        align_threshold = tile_size * 0.45
        aligned_x, aligned_y = curr_x, curr_y
        if abs(dx_norm) < 0.25:
            nearest_col = round(curr_x / tile_size)
            target_x = nearest_col * tile_size
            diff_x = abs(curr_x - target_x)
            if 0.0 < diff_x <= align_threshold:
                step_x = min(step_speed, diff_x)
                cand_x = curr_x + (step_x if target_x > curr_x else -step_x) if diff_x > 0.05 else target_x
                if self.can_move_to(tank, cand_x, curr_y):
                    aligned_x = cand_x
        elif abs(dy_norm) < 0.25:
            nearest_row = round(curr_y / tile_size)
            target_y = nearest_row * tile_size
            diff_y = abs(curr_y - target_y)
            if 0.0 < diff_y <= align_threshold:
                step_y = min(step_speed, diff_y)
                cand_y = curr_y + (step_y if target_y > curr_y else -step_y) if diff_y > 0.05 else target_y
                if self.can_move_to(tank, curr_x, cand_y):
                    aligned_y = cand_y

        if (aligned_x != curr_x or aligned_y != curr_y) and self.can_move_to(tank, aligned_x + vx, aligned_y + vy):
            tank.x = aligned_x + vx
            tank.y = aligned_y + vy
            self._crush_bricks_at(tank, tank.x, tank.y)
            return True

        # 3. 贴墙滑动 (Wall Sliding)：斜向遇障碍时，分解为 X 与 Y 独立滑动
        moved_x = False
        moved_y = False
        base_x, base_y = aligned_x, aligned_y
        if base_x != curr_x or base_y != curr_y:
            tank.x = base_x
            tank.y = base_y
            self._crush_bricks_at(tank, tank.x, tank.y)
            return True

        if abs(vx) > 1e-4 and self.can_move_to(tank, curr_x + vx, curr_y):
            tank.x = curr_x + vx
            moved_x = True

        test_y_base_x = tank.x if moved_x else curr_x
        if abs(vy) > 1e-4 and self.can_move_to(tank, test_y_base_x, curr_y + vy):
            tank.y = curr_y + vy
            moved_y = True

        if moved_x or moved_y:
            self._crush_bricks_at(tank, tank.x, tank.y)
            return True

        # 无法移动，恢复原始坐标
        tank.x = curr_x
        tank.y = curr_y
        return False

    def spawn_bullet(self, tank: Tank, bullet_speed: Optional[float] = None, bullet_size: Optional[int] = None,
                     color: Optional[str] = None, angle: Optional[float] = None,
                     target_pos: Optional[Tuple[float, float]] = None) -> Optional[Bullet]:
        """发射炮弹（支持 360° 任意角度瞄准发射，支持指定地块目标、命中精度、闪避与范围伤害结算）"""
        if not tank.can_fire(self.limited_ammo_enabled):
            return None

        # 消耗一发弹药
        tank.consume_ammo(self.limited_ammo_enabled)

        b_speed = float(getattr(tank, "bullet_speed", 6.0) if bullet_speed is None else bullet_speed)
        b_size = int(getattr(tank, "bullet_size", 12) if bullet_size is None else bullet_size)
        b_color = str(getattr(tank, "bullet_color", "#FFFFFF") if color is None else color)
        accuracy = float(getattr(tank, "accuracy", 1.0))
        splash_radius = float(getattr(tank, "splash_radius", 0.0))
        friendly_fire = int(getattr(tank, "friendly_fire", 0))
        damage = int(getattr(tank, "damage", 1))

        center_x = tank.x + tank.size / 2.0
        center_y = tank.y + tank.size / 2.0

        if target_pos is not None:
            tdx = float(target_pos[0]) - center_x
            tdy = float(target_pos[1]) - center_y
            shoot_angle = (math.degrees(math.atan2(tdx, -tdy))) % 360.0
            tank.angle = shoot_angle
        else:
            shoot_angle = tank.angle if angle is None else (float(angle) % 360.0)

        rad = math.radians(shoot_angle)

        # 沿炮管朝向将炮弹生成在坦克包围盒外边缘
        offset = tank.size / 2.0 + b_size / 2.0 + 2.0
        bx = center_x + math.sin(rad) * offset - b_size / 2.0
        by = center_y - math.cos(rad) * offset - b_size / 2.0

        bullet = Bullet(
            x=bx,
            y=by,
            direction=tank.direction,
            speed=b_speed,
            size=b_size,
            camp=tank.camp,
            color=b_color,
            angle=shoot_angle,
            accuracy=accuracy,
            splash_radius=splash_radius,
            friendly_fire=friendly_fire,
            damage=damage,
            shooter=tank,
            target_pos=target_pos
        )
        self.bullets.append(bullet)
        tank.trigger_cooldown()
        return bullet

    def explode_bullet(self, bullet: Bullet, ex: float, ey: float) -> None:
        """范围伤害爆炸结算：对半径内的瓦片和单位造成 AoE 破坏，遵循命中精度/闪避判定与友军误伤设置"""
        bullet.alive = False
        radius = getattr(bullet, "splash_radius", 0.0)
        if radius <= 0:
            return

        tile_size = self.game_map.tile_size
        accuracy = getattr(bullet, "accuracy", 1.0)
        friendly_fire = int(getattr(bullet, "friendly_fire", 0))
        damage = getattr(bullet, "damage", 1)

        # 1. 范围内的瓦片摧毁（BRICK, BASE）
        min_col = max(0, int((ex - radius) // tile_size))
        max_col = min(self.game_map.cols - 1, int((ex + radius) // tile_size))
        min_row = max(0, int((ey - radius) // tile_size))
        max_row = min(self.game_map.rows - 1, int((ey + radius) // tile_size))

        for r in range(min_row, max_row + 1):
            for c in range(min_col, max_col + 1):
                tile = self.game_map.get_tile(c, r)
                if tile in (TileType.BRICK, TileType.BASE):
                    tc_x = (c + 0.5) * tile_size
                    tc_y = (r + 0.5) * tile_size
                    if math.hypot(tc_x - ex, tc_y - ey) <= radius + tile_size * 0.35:
                        self.game_map.destroy_tile(c, r)

        # 2. 范围内的单位伤害结算
        all_tanks = self.get_all_active_tanks()
        sight_rects = self.get_player_sight_rects()
        has_full_vision = any(p.vision_size < 0 for p in self.player_tanks if p.alive)

        for tank in all_tanks:
            if not tank.alive:
                continue

            # 射击者自身免疫自己的范围伤害 (具备范围伤害和友军误伤的单位不会误伤到自己)
            is_shooter = (tank is bullet.shooter) or (isinstance(bullet.shooter, str) and tank.id == bullet.shooter) or (
                bullet.shooter is not None and tank.id != "tank" and tank.id == getattr(bullet.shooter, "id", None)
            )
            if is_shooter:
                continue

            # 友军误伤校验：如果 friendly_fire == 0，跳过同阵营单位
            if friendly_fire == 0 and tank.camp == bullet.camp:
                continue

            # 距离判定：中心距离 <= radius + tank.size/2
            tcx = tank.x + tank.size / 2.0
            tcy = tank.y + tank.size / 2.0
            dist = math.hypot(tcx - ex, tcy - ey)
            if dist <= radius + tank.size / 2.0:
                # 按照攻击者瞄准精度 p 与 被攻击者闪避 q 计算命中率: P = p * (1 - q)
                p = max(0.0, min(1.0, accuracy))
                q = max(0.0, min(1.0, getattr(tank, "dodge", 0.0)))
                hit_prob = max(0.0, min(1.0, p * (1.0 - q)))

                if random.random() < hit_prob:
                    killed = tank.take_damage(damage)
                    if killed and tank.camp == Camp.ENEMY:
                        was_seen = (not self.fog_of_war_enabled) or has_full_vision or tank.is_spotted or any(tank.rect.collides_with(sr) for sr in sight_rects)
                        if was_seen and tank.id in self.enemy_memory:
                            del self.enemy_memory[tank.id]

    def update_bullets(self) -> None:
        tile_size = self.game_map.tile_size

        for bullet in self.bullets:
            if not bullet.alive:
                continue
            bullet.update()

            if (bullet.x < -bullet.size or
                bullet.x > self.game_map.pixel_width or
                bullet.y < -bullet.size or
                bullet.y > self.game_map.pixel_height):
                bullet.alive = False

        # 检查是否到达强制攻击地块的目标坐标
        for bullet in self.bullets:
            if getattr(bullet, "exploded_at_target", False):
                bullet.exploded_at_target = False
                bullet.alive = False
                ex = bullet.target_pos[0] if bullet.target_pos else (bullet.x + bullet.size / 2.0)
                ey = bullet.target_pos[1] if bullet.target_pos else (bullet.y + bullet.size / 2.0)
                self.explode_bullet(bullet, ex, ey)

        # 炮弹互相对撞抵消
        active_bullets = [b for b in self.bullets if b.alive]
        for i in range(len(active_bullets)):
            for j in range(i + 1, len(active_bullets)):
                b1 = active_bullets[i]
                b2 = active_bullets[j]
                if b1.alive and b2.alive and b1.camp != b2.camp:
                    if b1.rect.collides_with(b2.rect):
                        b1.alive = False
                        b2.alive = False
                        if getattr(b1, "splash_radius", 0.0) > 0:
                            self.explode_bullet(b1, b1.x + b1.size / 2.0, b1.y + b1.size / 2.0)
                        if getattr(b2, "splash_radius", 0.0) > 0:
                            self.explode_bullet(b2, b2.x + b2.size / 2.0, b2.y + b2.size / 2.0)

        # 瓦片碰撞
        for bullet in self.bullets:
            if not bullet.alive:
                continue

            bullet_rect = bullet.rect
            col_start = max(0, int(bullet.x // tile_size))
            col_end = min(self.game_map.cols - 1, int((bullet.x + bullet.size - 0.01) // tile_size))
            row_start = max(0, int(bullet.y // tile_size))
            row_end = min(self.game_map.rows - 1, int((bullet.y + bullet.size - 0.01) // tile_size))

            hit_obstacle = False
            hit_col, hit_row = -1, -1
            hit_tile = None
            for row in range(row_start, row_end + 1):
                for col in range(col_start, col_end + 1):
                    tile = self.game_map.get_tile(col, row)
                    if tile in (TileType.BRICK, TileType.STEEL, TileType.BASE):
                        tile_rect = Rect(col * tile_size, row * tile_size, tile_size, tile_size)
                        if bullet_rect.collides_with(tile_rect):
                            hit_obstacle = True
                            hit_col, hit_row = col, row
                            hit_tile = tile
                            break
                if hit_obstacle:
                    break

            if hit_obstacle:
                bullet.alive = False
                if getattr(bullet, "splash_radius", 0.0) > 0:
                    self.explode_bullet(bullet, bullet.x + bullet.size / 2.0, bullet.y + bullet.size / 2.0)
                else:
                    if hit_tile in (TileType.BRICK, TileType.BASE):
                        self.game_map.destroy_tile(hit_col, hit_row)

        # 坦克碰撞
        all_tanks = self.get_all_active_tanks()
        sight_rects = self.get_player_sight_rects()
        has_full_vision = any(p.vision_size < 0 for p in self.player_tanks if p.alive)

        for bullet in self.bullets:
            if not bullet.alive:
                continue

            for tank in all_tanks:
                if not tank.alive:
                    continue

                # 射击者自身免疫自身炮弹碰撞与伤害
                is_shooter = (tank is bullet.shooter) or (isinstance(bullet.shooter, str) and tank.id == bullet.shooter) or (
                    bullet.shooter is not None and tank.id != "tank" and tank.id == getattr(bullet.shooter, "id", None)
                )
                if is_shooter:
                    continue

                is_enemy = (tank.camp != bullet.camp)
                can_collide = is_enemy or (getattr(bullet, "friendly_fire", 0) == 1)

                if can_collide and bullet.rect.collides_with(tank.rect):
                    bullet.alive = False
                    if getattr(bullet, "splash_radius", 0.0) > 0:
                        self.explode_bullet(bullet, bullet.x + bullet.size / 2.0, bullet.y + bullet.size / 2.0)
                    else:
                        p = max(0.0, min(1.0, getattr(bullet, "accuracy", 1.0)))
                        q = max(0.0, min(1.0, getattr(tank, "dodge", 0.0)))
                        hit_prob = max(0.0, min(1.0, p * (1.0 - q)))

                        if random.random() < hit_prob:
                            killed = tank.take_damage(getattr(bullet, "damage", 1))
                            if killed and tank.camp == Camp.ENEMY:
                                was_seen = (not self.fog_of_war_enabled) or has_full_vision or tank.is_spotted or any(tank.rect.collides_with(sr) for sr in sight_rects)
                                if was_seen and tank.id in self.enemy_memory:
                                    del self.enemy_memory[tank.id]
                    break

        self.bullets = [b for b in self.bullets if b.alive]
        self.player_tanks = [t for t in self.player_tanks if t.alive]
        self.enemy_tanks = [t for t in self.enemy_tanks if t.alive]

    def update(self) -> None:
        """物理世界步进：更新视线与隐蔽、防御塔补给、冷却与炮弹"""
        self.update_vision_and_stealth()

        # 防御塔补给逻辑
        for t in self.player_tanks:
            if t.alive and t.is_tower and t.resupply_radius > 0:
                t.update_resupply(self.player_tanks, self.limited_ammo_enabled)

        for t in self.player_tanks:
            t.update_cooldown()
        for t in self.enemy_tanks:
            t.update_cooldown()

        self.update_bullets()
