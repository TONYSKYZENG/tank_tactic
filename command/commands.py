import math
import random
from abc import ABC, abstractmethod
from typing import Optional, Tuple, List
from physics.entities import Tank, Direction, Camp
from map_loader.models import GameMap, TileType

class BaseCommand(ABC):
    """坦克命令抽象基类"""

    @abstractmethod
    def execute(self, tank: Tank, physics_engine, game_map: GameMap) -> bool:
        pass

    @staticmethod
    def is_line_of_sight_clear(x1: float, y1: float, x2: float, y2: float,
                               game_map: GameMap) -> bool:
        tile_size = game_map.tile_size
        col1, row1 = int(x1 // tile_size), int(y1 // tile_size)
        col2, row2 = int(x2 // tile_size), int(y2 // tile_size)

        if col1 == col2:
            step = 1 if row2 > row1 else -1
            for r in range(row1 + step, row2, step):
                if game_map.get_tile(col1, r) in (TileType.BRICK, TileType.STEEL):
                    return False
            return True
        elif row1 == row2:
            step = 1 if col2 > col1 else -1
            for c in range(col1 + step, col2, step):
                if game_map.get_tile(c, row1) in (TileType.BRICK, TileType.STEEL):
                    return False
            return True
        return False


class MoveCommand(BaseCommand):
    """
    移动到目标点命令 (支持自动开路)
    """
    def __init__(self, dest_x: float, dest_y: float, tolerance: float = 8.0,
                 auto_clear_path: bool = False):
        self.dest_x = dest_x
        self.dest_y = dest_y
        self.tolerance = tolerance
        self.auto_clear_path = auto_clear_path
        self.stuck_frames = 0

    def _check_front_has_brick(self, tank: Tank, direction: Direction,
                               game_map: GameMap) -> bool:
        tile_size = game_map.tile_size
        check_points = []
        if direction in (Direction.UP, Direction.DOWN):
            cy = tank.y + (tank.size + 4 if direction == Direction.DOWN else -4)
            check_points.append((tank.x + 4, cy))
            check_points.append((tank.x + tank.size - 4, cy))
        else:
            cx = tank.x + (tank.size + 4 if direction == Direction.RIGHT else -4)
            check_points.append((cx, tank.y + 4))
            check_points.append((cx, tank.y + tank.size - 4))

        for px, py in check_points:
            col = int(px // tile_size)
            row = int(py // tile_size)
            if game_map.get_tile(col, row) == TileType.BRICK:
                return True
        return False

    def execute(self, tank: Tank, physics_engine, game_map: GameMap) -> bool:
        if not tank.alive or tank.is_tower:
            return True

        dx = self.dest_x - tank.x
        dy = self.dest_y - tank.y
        dist = math.hypot(dx, dy)

        if dist <= self.tolerance:
            return True

        if abs(dx) > abs(dy):
            primary = Direction.RIGHT if dx > 0 else Direction.LEFT
            secondary = Direction.DOWN if dy > 0 else Direction.UP
        else:
            primary = Direction.DOWN if dy > 0 else Direction.UP
            secondary = Direction.RIGHT if dx > 0 else Direction.LEFT

        if self.auto_clear_path:
            if self._check_front_has_brick(tank, primary, game_map):
                tank.direction = primary
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    cfg = getattr(tank, "_config", None)
                    b_speed = cfg.bullet_speed if cfg else 6.0
                    b_size = cfg.bullet_size if cfg else 12
                    b_color = cfg.bullet_color if cfg else "#FFFFFF"
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
                return False

        moved = physics_engine.move_tank(tank, primary)

        if not moved and (abs(dx) > 2 or abs(dy) > 2):
            if self.auto_clear_path and self._check_front_has_brick(tank, secondary, game_map):
                tank.direction = secondary
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    cfg = getattr(tank, "_config", None)
                    b_speed = cfg.bullet_speed if cfg else 6.0
                    b_size = cfg.bullet_size if cfg else 12
                    b_color = cfg.bullet_color if cfg else "#FFFFFF"
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
                return False

            moved = physics_engine.move_tank(tank, secondary)

        if not moved:
            self.stuck_frames += 1
            if self.auto_clear_path or self.stuck_frames > 12:
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    cfg = getattr(tank, "_config", None)
                    b_speed = cfg.bullet_speed if cfg else 6.0
                    b_size = cfg.bullet_size if cfg else 12
                    b_color = cfg.bullet_color if cfg else "#FFFFFF"
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)

            if self.stuck_frames > 25 and not self.auto_clear_path:
                for alt_d in Direction.all_directions():
                    if alt_d not in (primary, secondary):
                        if physics_engine.move_tank(tank, alt_d):
                            break

            if self.stuck_frames > 70:
                return True
        else:
            self.stuck_frames = 0

        return False


class AttackTargetCommand(BaseCommand):
    """
    集火攻击目标命令
    """
    def __init__(self, target_tank: Tank, auto_clear_path: bool = False):
        self.target_tank = target_tank
        self.auto_clear_path = auto_clear_path

    def execute(self, tank: Tank, physics_engine, game_map: GameMap) -> bool:
        if not tank.alive or not self.target_tank.alive:
            return True

        center_x = tank.x + tank.size / 2.0
        center_y = tank.y + tank.size / 2.0
        target_center_x = self.target_tank.x + self.target_tank.size / 2.0
        target_center_y = self.target_tank.y + self.target_tank.size / 2.0

        dx = target_center_x - center_x
        dy = target_center_y - center_y
        align_threshold = tank.size * 0.7

        is_aligned_v = abs(dx) < align_threshold
        is_aligned_h = abs(dy) < align_threshold

        cfg = getattr(tank, "_config", None)
        b_speed = cfg.bullet_speed if cfg else 6.0
        b_size = cfg.bullet_size if cfg else 12
        b_color = cfg.bullet_color if cfg else "#FFFFFF"

        if is_aligned_v:
            tank.direction = Direction.DOWN if dy > 0 else Direction.UP
            if self.is_line_of_sight_clear(center_x, center_y, target_center_x, target_center_y, game_map):
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
            else:
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
            return False

        if is_aligned_h:
            tank.direction = Direction.RIGHT if dx > 0 else Direction.LEFT
            if self.is_line_of_sight_clear(center_x, center_y, target_center_x, target_center_y, game_map):
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
            else:
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
            return False

        # 如果自身是固定防御塔，不执行物理移动位移，只转向射击
        if tank.is_tower or tank.speed <= 0:
            tank.direction = Direction.DOWN if abs(dy) > abs(dx) and dy > 0 else (Direction.UP if abs(dy) > abs(dx) else (Direction.RIGHT if dx > 0 else Direction.LEFT))
            if tank.can_fire(physics_engine.limited_ammo_enabled):
                physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
            return False

        if abs(dx) > abs(dy):
            primary = Direction.RIGHT if dx > 0 else Direction.LEFT
            secondary = Direction.DOWN if dy > 0 else Direction.UP
        else:
            primary = Direction.DOWN if dy > 0 else Direction.UP
            secondary = Direction.RIGHT if dx > 0 else Direction.LEFT

        if not physics_engine.move_tank(tank, primary):
            physics_engine.move_tank(tank, secondary)

        return False


class GuardUnitCommand(BaseCommand):
    """
    战术指令：【跟踪并保卫特定己方单位 (Guard / Escort Unit)】
    - 跟随被保卫的己方单位（如核心防御塔或领袖战车），保持在护卫距离内；
    - 当有威胁敌军靠近时，主动开火并拦截威胁者；
    - 威胁解除后回归被保卫者身旁。
    """
    def __init__(self, target_to_guard: Tank, guard_dist: float = 65.0):
        self.target_to_guard = target_to_guard
        self.guard_dist = guard_dist
        self.attack_subcmd: Optional[AttackTargetCommand] = None

    def execute(self, tank: Tank, physics_engine, game_map: GameMap) -> bool:
        if not tank.alive or not self.target_to_guard.alive:
            return True  # 目标阵亡，护卫任务结束

        center_x = tank.x + tank.size / 2.0
        center_y = tank.y + tank.size / 2.0
        target_cx = self.target_to_guard.x + self.target_to_guard.size / 2.0
        target_cy = self.target_to_guard.y + self.target_to_guard.size / 2.0

        # 1. 扫描周围可见敌军中对被护卫目标最具威胁者 (200 像素内)
        visible_enemies = physics_engine.get_visible_enemies()
        threat_enemies = []
        for e in visible_enemies:
            e_cx = e.x + e.size / 2.0
            e_cy = e.y + e.size / 2.0
            dist_to_guarded = math.hypot(e_cx - target_cx, e_cy - target_cy)
            dist_to_me = math.hypot(e_cx - center_x, e_cy - center_y)
            if dist_to_guarded < 220.0 or dist_to_me < 160.0:
                threat_enemies.append((dist_to_guarded, e))

        # 2. 如果存在威胁敌军，优先开火迎击
        if threat_enemies:
            threat_enemies.sort(key=lambda item: item[0])
            most_dangerous_enemy = threat_enemies[0][1]

            if not self.attack_subcmd or self.attack_subcmd.target_tank != most_dangerous_enemy:
                self.attack_subcmd = AttackTargetCommand(most_dangerous_enemy, auto_clear_path=True)

            self.attack_subcmd.execute(tank, physics_engine, game_map)
            return False
        else:
            self.attack_subcmd = None

        # 3. 无威胁时，跟随被护卫单位
        if tank.is_tower or tank.speed <= 0:
            return False

        dist_to_guarded = math.hypot(target_cx - center_x, target_cy - center_y)
        if dist_to_guarded > self.guard_dist:
            # 靠拢被护卫者
            dx = target_cx - center_x
            dy = target_cy - center_y
            if abs(dx) > abs(dy):
                primary = Direction.RIGHT if dx > 0 else Direction.LEFT
                secondary = Direction.DOWN if dy > 0 else Direction.UP
            else:
                primary = Direction.DOWN if dy > 0 else Direction.UP
                secondary = Direction.RIGHT if dx > 0 else Direction.LEFT

            if not physics_engine.move_tank(tank, primary):
                physics_engine.move_tank(tank, secondary)

        return False


class HoldCommand(BaseCommand):
    """原地驻守命令"""
    def execute(self, tank: Tank, physics_engine, game_map: GameMap) -> bool:
        return False
