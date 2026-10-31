from typing import List, Optional, Tuple
from map_loader.models import GameMap, TileType
from .entities import Tank, Bullet, Direction, Rect, Camp

class PhysicsEngine:
    def __init__(self, game_map: GameMap):
        self.game_map = game_map
        self.player_tank: Optional[Tank] = None
        self.enemy_tanks: List[Tank] = []
        self.bullets: List[Bullet] = []

    def set_player_tank(self, tank: Tank) -> None:
        self.player_tank = tank

    def add_enemy_tank(self, tank: Tank) -> None:
        self.enemy_tanks.append(tank)

    def get_all_active_tanks(self) -> List[Tank]:
        tanks = []
        if self.player_tank and self.player_tank.alive:
            tanks.append(self.player_tank)
        tanks.extend([t for t in self.enemy_tanks if t.alive])
        return tanks

    def can_move_to(self, moving_tank: Tank, new_x: float, new_y: float) -> bool:
        """检查移动是否合法（出界、撞墙、撞其他存活坦克）"""
        # 1. 地图边界
        if new_x < 0 or new_x + moving_tank.size > self.game_map.pixel_width:
            return False
        if new_y < 0 or new_y + moving_tank.size > self.game_map.pixel_height:
            return False

        # 2. 地图障碍物瓦片
        tile_size = self.game_map.tile_size
        tank_rect = Rect(new_x, new_y, moving_tank.size, moving_tank.size)

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

        # 3. 与其他存活坦克的碰撞检测
        for other in self.get_all_active_tanks():
            if other is not moving_tank and other.alive:
                if tank_rect.collides_with(other.rect):
                    return False

        return True

    def find_nearest_free_position(self, start_x: float, start_y: float, size: int) -> Tuple[float, float]:
        """寻找距离指定位置最近的无碰撞开阔位置，防止出生在障碍物里卡死"""
        dummy_tank = Tank(start_x, start_y, size=size)
        if self.can_move_to(dummy_tank, start_x, start_y):
            return start_x, start_y

        tile_size = self.game_map.tile_size
        # 螺旋外扩搜索
        for radius in range(1, max(self.game_map.cols, self.game_map.rows)):
            for r in range(-radius, radius + 1):
                for c in range(-radius, radius + 1):
                    test_x = start_x + c * tile_size
                    test_y = start_y + r * tile_size
                    if self.can_move_to(dummy_tank, test_x, test_y):
                        return test_x, test_y

        return start_x, start_y

    def move_tank(self, tank: Tank, direction: Direction) -> bool:
        """
        尝试沿指定方向移动坦克。
        带有经典坦克大战的【网格辅助对齐 (Turn Alignment)】：
        转向时若微偏离网格中线，自动吸附对齐，避免因几个像素偏差卡在窄巷拐角。
        """
        if not tank.alive:
            return False

        tile_size = self.game_map.tile_size
        is_turning = (tank.direction != direction)
        tank.direction = direction

        # 网格辅助吸附 (Turn Alignment)
        curr_x, curr_y = tank.x, tank.y
        if is_turning:
            align_threshold = tile_size * 0.45
            if direction in (Direction.UP, Direction.DOWN):
                # 垂直转向，吸附 x 轴到最近网格
                nearest_col = round(curr_x / tile_size)
                target_x = nearest_col * tile_size
                if abs(curr_x - target_x) <= align_threshold:
                    if self.can_move_to(tank, target_x, curr_y):
                        curr_x = target_x
            elif direction in (Direction.LEFT, Direction.RIGHT):
                # 水平转向，吸附 y 轴到最近网格
                nearest_row = round(curr_y / tile_size)
                target_y = nearest_row * tile_size
                if abs(curr_y - target_y) <= align_threshold:
                    if self.can_move_to(tank, curr_x, target_y):
                        curr_y = target_y

        new_x = curr_x + direction.dx * tank.speed
        new_y = curr_y + direction.dy * tank.speed

        if self.can_move_to(tank, new_x, new_y):
            tank.x = new_x
            tank.y = new_y
            return True
        else:
            # 移动受阻，但保留刚才的辅助吸附（如果有）
            tank.x = curr_x
            tank.y = curr_y
            return False

    def spawn_bullet(self, tank: Tank, bullet_speed: float, bullet_size: int, color: str = "#FFFFFF") -> Optional[Bullet]:
        """根据坦克的位置与朝向从车头生成品字形炮弹"""
        if not tank.can_fire():
            return None

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
        """更新所有炮弹位置，并处理与边界、障碍物、坦克和互相对撞的碰撞"""
        tile_size = self.game_map.tile_size

        # 1. 更新位置
        for bullet in self.bullets:
            if not bullet.alive:
                continue
            bullet.update()

            # 地图边界检测
            if (bullet.x < -bullet.size or
                bullet.x > self.game_map.pixel_width or
                bullet.y < -bullet.size or
                bullet.y > self.game_map.pixel_height):
                bullet.alive = False

        # 2. 炮弹互相对撞抵消
        active_bullets = [b for b in self.bullets if b.alive]
        for i in range(len(active_bullets)):
            for j in range(i + 1, len(active_bullets)):
                b1 = active_bullets[i]
                b2 = active_bullets[j]
                if b1.alive and b2.alive and b1.camp != b2.camp:
                    if b1.rect.collides_with(b2.rect):
                        b1.alive = False
                        b2.alive = False

        # 3. 炮弹与地图瓦片碰撞
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

        # 4. 炮弹与坦克碰撞
        all_tanks = self.get_all_active_tanks()
        for bullet in self.bullets:
            if not bullet.alive:
                continue

            for tank in all_tanks:
                if tank.alive and tank.camp != bullet.camp:
                    if bullet.rect.collides_with(tank.rect):
                        tank.take_damage(1)
                        bullet.alive = False
                        break

        # 5. 清理死亡实体
        self.bullets = [b for b in self.bullets if b.alive]
        self.enemy_tanks = [t for t in self.enemy_tanks if t.alive]

    def update(self) -> None:
        """步进物理状态"""
        if self.player_tank:
            self.player_tank.update_cooldown()
        for t in self.enemy_tanks:
            t.update_cooldown()

        self.update_bullets()
