import math
import random
from abc import ABC, abstractmethod
from typing import Optional, Tuple, List
from physics.entities import Tank, Direction, Camp
from map_loader.models import GameMap, TileType
from .pathfinder import GridPathfinder

class BaseCommand(ABC):
    """坦克命令抽象基类"""

    @abstractmethod
    def execute(self, tank: Tank, physics_engine, game_map: GameMap) -> bool:
        pass

    @staticmethod
    def is_line_of_sight_clear(x1: float, y1: float, x2: float, y2: float,
                               game_map: GameMap) -> bool:
        tile_size = game_map.tile_size
        col1, row1 = int(round(x1 / tile_size)), int(round(y1 / tile_size))
        col2, row2 = int(round(x2 / tile_size)), int(round(y2 / tile_size))

        if col1 == col2:
            step = 1 if row2 > row1 else -1
            for r in range(row1 + step, row2, step):
                if 0 <= col1 < game_map.cols and 0 <= r < game_map.rows:
                    if game_map.get_tile(col1, r) in (TileType.BRICK, TileType.STEEL, TileType.BASE):
                        return False
            return True
        elif row1 == row2:
            step = 1 if col2 > col1 else -1
            for c in range(col1 + step, col2, step):
                if 0 <= c < game_map.cols and 0 <= row1 < game_map.rows:
                    if game_map.get_tile(c, row1) in (TileType.BRICK, TileType.STEEL, TileType.BASE):
                        return False
            return True
        return False


class MoveCommand(BaseCommand):
    """
    智能 A* 移动到目标点命令：
    - 当无限弹药时：自动破障，以极小时间开销直接炸开砖墙，直达目标；
    - 当有限弹药时：自动计算最省弹药的破障办法，优先零耗弹绕过障碍；若必须破障，选择摧毁砖块数绝对最少的路线。
    """
    def __init__(self, dest_x: float, dest_y: float, tolerance: float = 8.0,
                 auto_clear_path: bool = True):
        self.dest_x = dest_x
        self.dest_y = dest_y
        self.tolerance = tolerance
        self.auto_clear_path = auto_clear_path
        self.path: Optional[List[Tuple[float, float]]] = None
        self.path_idx: int = 0
        self.stuck_frames: int = 0
        self.replan_timer: int = 0
        self.ammo_needed: int = 0
        self.pathfinder: Optional[GridPathfinder] = None

    def _check_front_has_brick(self, tank: Tank, direction: Direction,
                               game_map: GameMap) -> bool:
        tile_size = game_map.tile_size
        ahead = 6.0
        # 仅检测坦克正前方通道范围内的障碍砖块，避免侧向边缘误差判定
        if direction in (Direction.UP, Direction.DOWN):
            cy = tank.y + (tank.size + ahead if direction == Direction.DOWN else -ahead)
            cx = tank.x + tank.size / 2.0
            check_points = [(cx, cy), (tank.x + 8.0, cy), (tank.x + tank.size - 8.0, cy)]
        else:
            cx = tank.x + (tank.size + ahead if direction == Direction.RIGHT else -ahead)
            cy = tank.y + tank.size / 2.0
            check_points = [(cx, cy), (cx, tank.y + 8.0), (cx, tank.y + tank.size - 8.0)]

        for px, py in check_points:
            col = int(px // tile_size)
            row = int(py // tile_size)
            if 0 <= col < game_map.cols and 0 <= row < game_map.rows:
                if game_map.get_tile(col, row) == TileType.BRICK:
                    return True
        return False

    def execute(self, tank: Tank, physics_engine, game_map: GameMap) -> bool:
        if not tank.alive or tank.is_tower:
            return True

        dist_to_final = math.hypot(self.dest_x - tank.x, self.dest_y - tank.y)
        if dist_to_final <= self.tolerance:
            return True

        if self.pathfinder is None or self.pathfinder.game_map != game_map:
            self.pathfinder = GridPathfinder(game_map)

        # 路径规划与自适应周期重规划
        if self.path is None or self.replan_timer <= 0:
            self.path, self.ammo_needed = self.pathfinder.find_path(
                tank.x, tank.y, self.dest_x, self.dest_y,
                tank=tank,
                limited_ammo_enabled=physics_engine.limited_ammo_enabled
            )
            self.path_idx = 0
            self.replan_timer = 45

        self.replan_timer -= 1

        # 沿路径航点向前推进：确保真正达到当前航点后才切入垂直拐弯，杜绝过早拐弯刮蹭拐角砖块
        tile_size = game_map.tile_size
        wp_reach_dist = max(3.0, tank.speed * 1.1)

        while self.path_idx < len(self.path):
            wx, wy = self.path[self.path_idx]
            dist_to_wp = math.hypot(wx - tank.x, wy - tank.y)
            if dist_to_wp <= wp_reach_dist:
                if abs(tank.x - wx) <= wp_reach_dist:
                    tank.x = wx
                if abs(tank.y - wy) <= wp_reach_dist:
                    tank.y = wy
                self.path_idx += 1
            else:
                break

        if self.path_idx < len(self.path):
            target_x, target_y = self.path[self.path_idx]
        else:
            target_x, target_y = self.dest_x, self.dest_y

        dx = target_x - tank.x
        dy = target_y - tank.y

        if abs(dx) > abs(dy):
            primary = Direction.RIGHT if dx > 0 else Direction.LEFT
            secondary = Direction.DOWN if dy > 0 else Direction.UP
        else:
            primary = Direction.DOWN if dy > 0 else Direction.UP
            secondary = Direction.RIGHT if dx > 0 else Direction.LEFT

        # 检测前路是否有砖块障碍待破障 (Auto-Breaching)
        target_col = int(round(target_x / tile_size))
        target_row = int(round(target_y / tile_size))
        next_is_brick = (0 <= target_col < game_map.cols and 0 <= target_row < game_map.rows and
                         game_map.get_tile(target_col, target_row) == TileType.BRICK)

        if next_is_brick or self._check_front_has_brick(tank, primary, game_map):
            tank.direction = primary
            if tank.can_fire(physics_engine.limited_ammo_enabled):
                cfg = getattr(tank, "_config", None)
                b_speed = cfg.bullet_speed if cfg else 6.0
                b_size = cfg.bullet_size if cfg else 12
                b_color = cfg.bullet_color if cfg else ("#E69C24" if tank.camp == Camp.PLAYER else "#E63946")
                physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
            return False

        moved = physics_engine.move_tank(tank, primary)

        if not moved and (abs(dx) > 2 or abs(dy) > 2):
            if self._check_front_has_brick(tank, secondary, game_map):
                tank.direction = secondary
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    cfg = getattr(tank, "_config", None)
                    b_speed = cfg.bullet_speed if cfg else 6.0
                    b_size = cfg.bullet_size if cfg else 12
                    b_color = cfg.bullet_color if cfg else ("#E69C24" if tank.camp == Camp.PLAYER else "#E63946")
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
                return False

            moved = physics_engine.move_tank(tank, secondary)

        if not moved:
            self.stuck_frames += 1
            if self.stuck_frames > 6:
                # 遇阻无法前进时，立即触发重新寻路
                self.path = None
                self.stuck_frames = 0
                self.replan_timer = 0
        else:
            self.stuck_frames = 0

        return False


class AttackTargetCommand(BaseCommand):
    """
    集火攻击目标命令 (基于 A* 智能机动占位与最省弹药破障)
    """
    def __init__(self, target_tank: Tank, auto_clear_path: bool = True):
        self.target_tank = target_tank
        self.auto_clear_path = auto_clear_path
        self.move_subcmd: Optional[MoveCommand] = None
        self.last_target_pos = (0.0, 0.0)

    def execute(self, tank: Tank, physics_engine, game_map: GameMap) -> bool:
        if not tank.alive or not self.target_tank.alive:
            return True

        tile_size = game_map.tile_size
        center_x = tank.x + tank.size / 2.0
        center_y = tank.y + tank.size / 2.0
        target_center_x = self.target_tank.x + self.target_tank.size / 2.0
        target_center_y = self.target_tank.y + self.target_tank.size / 2.0

        dx = target_center_x - center_x
        dy = target_center_y - center_y
        dist = math.hypot(dx, dy)

        # 视线轴向对齐阈值：确保对齐后射击弹道切实覆盖目标包围盒
        align_threshold = min(20.0, tank.size * 0.55)

        is_aligned_v = abs(dx) <= align_threshold
        is_aligned_h = abs(dy) <= align_threshold

        cfg = getattr(tank, "_config", None)
        b_speed = cfg.bullet_speed if cfg else 6.0
        b_size = cfg.bullet_size if cfg else 12
        b_color = cfg.bullet_color if cfg else ("#E69C24" if tank.camp == Camp.PLAYER else "#E63946")

        # 检查垂直轴对齐开火
        if is_aligned_v:
            tank.direction = Direction.DOWN if dy > 0 else Direction.UP
            los_clear = self.is_line_of_sight_clear(center_x, center_y, target_center_x, target_center_y, game_map)
            if los_clear:
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
                return False
            else:
                is_infinite = (tank.ammo < 0 or not physics_engine.limited_ammo_enabled)
                if is_infinite and tank.can_fire(physics_engine.limited_ammo_enabled):
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
                    return False

        # 检查水平轴对齐开火
        if is_aligned_h:
            tank.direction = Direction.RIGHT if dx > 0 else Direction.LEFT
            los_clear = self.is_line_of_sight_clear(center_x, center_y, target_center_x, target_center_y, game_map)
            if los_clear:
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
                return False
            else:
                is_infinite = (tank.ammo < 0 or not physics_engine.limited_ammo_enabled)
                if is_infinite and tank.can_fire(physics_engine.limited_ammo_enabled):
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
                    return False

        # 如果自身是固定防御塔，不执行位移
        if tank.is_tower or tank.speed <= 0:
            tank.direction = Direction.DOWN if abs(dy) > abs(dx) and dy > 0 else (Direction.UP if abs(dy) > abs(dx) else (Direction.RIGHT if dx > 0 else Direction.LEFT))
            if tank.can_fire(physics_engine.limited_ammo_enabled):
                physics_engine.spawn_bullet(tank, b_speed, b_size, b_color)
            return False

        # 寻找进攻占位阵位 (Standoff Attack Position)
        tx, ty = self.target_tank.x, self.target_tank.y
        dist_moved = math.hypot(self.last_target_pos[0] - tx, self.last_target_pos[1] - ty)

        if self.move_subcmd is None or dist_moved > 18.0:
            c_target = int(round(tx / tile_size))
            r_target = int(round(ty / tile_size))
            c_me = int(round(tank.x / tile_size))
            r_me = int(round(tank.y / tile_size))

            standoff_candidates = [
                (c_target, r_target - 1),
                (c_target, r_target + 1),
                (c_target - 1, r_target),
                (c_target + 1, r_target),
            ]
            valid_candidates = []
            for sc, sr in standoff_candidates:
                if 0 <= sc < game_map.cols and 0 <= sr < game_map.rows:
                    tile = game_map.get_tile(sc, sr)
                    if tile != TileType.STEEL:
                        d = abs(sc - c_me) + abs(sr - r_me)
                        valid_candidates.append((d, sc * tile_size, sr * tile_size))

            if valid_candidates:
                valid_candidates.sort(key=lambda item: item[0])
                dest_x, dest_y = valid_candidates[0][1], valid_candidates[0][2]
            else:
                dest_x, dest_y = tx, ty

            self.move_subcmd = MoveCommand(dest_x, dest_y, tolerance=4.0, auto_clear_path=self.auto_clear_path)
            self.last_target_pos = (tx, ty)

        arrived = self.move_subcmd.execute(tank, physics_engine, game_map)
        # 到达射击阵位后，若仍存在微小轴向未对齐，主动朝目标轴线微调对齐，确保立刻开火
        if arrived:
            if abs(dx) < abs(dy):
                step_dir = Direction.RIGHT if target_center_x > center_x else Direction.LEFT
                physics_engine.move_tank(tank, step_dir)
            else:
                step_dir = Direction.DOWN if target_center_y > center_y else Direction.UP
                physics_engine.move_tank(tank, step_dir)

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
