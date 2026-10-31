import random
import time
from typing import List, Optional, Tuple, Dict
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

        # 2. 鹰巢基地周边守备视线 (140x140 正方形)
        tile_size = self.game_map.tile_size
        base_center_x = self.game_map.pixel_width / 2.0
        base_center_y = self.game_map.pixel_height - tile_size
        base_sight_size = 144.0
        sight_rects.append(Rect(
            base_center_x - base_sight_size / 2.0,
            base_center_y - base_sight_size / 2.0,
            base_sight_size,
            base_sight_size
        ))

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

        for row in range(row_start, row_end + 1):
            for col in range(col_start, col_end + 1):
                tile = self.game_map.get_tile(col, row)
                if tile in (TileType.BRICK, TileType.STEEL, TileType.BASE):
                    tile_rect = Rect(col * tile_size, row * tile_size, tile_size, tile_size)
                    if tank_rect.collides_with(tile_rect):
                        return False

        exact_tank_rect = Rect(new_x, new_y, moving_tank.size, moving_tank.size)
        for other in self.get_all_active_tanks():
            if other is not moving_tank and other.alive:
                if exact_tank_rect.collides_with(other.rect):
                    return False

        return True

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

    def move_tank(self, tank: Tank, direction: Direction) -> bool:
        if not tank.alive or tank.is_tower or tank.speed <= 0:
            return False

        tile_size = self.game_map.tile_size
        tank.direction = direction

        curr_x, curr_y = tank.x, tank.y
        align_threshold = tile_size * 0.45

        # 连续通道中心线对齐：沿主方向移动时，自动将垂直轴向平滑吸附到通道中心，彻底避免刮蹭砖块卡死
        if direction in (Direction.UP, Direction.DOWN):
            nearest_col = round(curr_x / tile_size)
            target_x = nearest_col * tile_size
            diff_x = abs(curr_x - target_x)
            if diff_x <= align_threshold:
                step_x = min(tank.speed, diff_x)
                cand_x = curr_x + (step_x if target_x > curr_x else -step_x) if diff_x > 0.05 else target_x
                if self.can_move_to(tank, cand_x, curr_y):
                    curr_x = cand_x
        elif direction in (Direction.LEFT, Direction.RIGHT):
            nearest_row = round(curr_y / tile_size)
            target_y = nearest_row * tile_size
            diff_y = abs(curr_y - target_y)
            if diff_y <= align_threshold:
                step_y = min(tank.speed, diff_y)
                cand_y = curr_y + (step_y if target_y > curr_y else -step_y) if diff_y > 0.05 else target_y
                if self.can_move_to(tank, curr_x, cand_y):
                    curr_y = cand_y

        new_x = curr_x + direction.dx * tank.speed
        new_y = curr_y + direction.dy * tank.speed

        if self.can_move_to(tank, new_x, new_y):
            tank.x = new_x
            tank.y = new_y
            return True
        else:
            tank.x = curr_x
            tank.y = curr_y
            return False

    def spawn_bullet(self, tank: Tank, bullet_speed: float, bullet_size: int, color: str = "#FFFFFF") -> Optional[Bullet]:
        """发射炮弹（含有限弹药消耗与判定）"""
        if not tank.can_fire(self.limited_ammo_enabled):
            return None

        # 消耗一发弹药
        tank.consume_ammo(self.limited_ammo_enabled)

        offset_distance = 4.0
        center_x = tank.x + tank.size / 2.0
        center_y = tank.y + tank.size / 2.0

        if tank.direction == Direction.UP:
            bx = center_x - bullet_size / 2.0
            by = tank.y - bullet_size - offset_distance
        elif tank.direction == Direction.DOWN:
            bx = center_x - bullet_size / 2.0
            by = tank.y + tank.size + offset_distance
        elif tank.direction == Direction.LEFT:
            bx = tank.x - bullet_size - offset_distance
            by = center_y - bullet_size / 2.0
        elif tank.direction == Direction.RIGHT:
            bx = tank.x + tank.size + offset_distance
            by = center_y - bullet_size / 2.0
        else:
            bx = tank.x
            by = tank.y

        bullet = Bullet(
            x=bx,
            y=by,
            direction=tank.direction,
            speed=bullet_speed,
            size=bullet_size,
            camp=tank.camp,
            color=color
        )
        self.bullets.append(bullet)
        tank.trigger_cooldown()
        return bullet

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
            for row in range(row_start, row_end + 1):
                for col in range(col_start, col_end + 1):
                    tile = self.game_map.get_tile(col, row)
                    if tile in (TileType.BRICK, TileType.STEEL, TileType.BASE):
                        tile_rect = Rect(col * tile_size, row * tile_size, tile_size, tile_size)
                        if bullet_rect.collides_with(tile_rect):
                            hit_obstacle = True
                            if tile in (TileType.BRICK, TileType.BASE):
                                self.game_map.destroy_tile(col, row)
                            break
                if hit_obstacle:
                    break

            if hit_obstacle:
                bullet.alive = False

        # 坦克碰撞
        all_tanks = self.get_all_active_tanks()
        sight_rects = self.get_player_sight_rects()
        has_full_vision = any(p.vision_size < 0 for p in self.player_tanks if p.alive)

        for bullet in self.bullets:
            if not bullet.alive:
                continue

            for tank in all_tanks:
                if tank.alive and tank.camp != bullet.camp:
                    if bullet.rect.collides_with(tank.rect):
                        killed = tank.take_damage(1)
                        bullet.alive = False

                        # 只有在我方单位看见了敌方单位被杀死的情况下，才能删除字典项目
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
