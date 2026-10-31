import math
import random
from abc import ABC, abstractmethod
from typing import Optional, Tuple, List, Any
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

        # 快速正交路径检测
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

        # 自由 360° 射线穿透检测 (Raycasting)
        dx = x2 - x1
        dy = y2 - y1
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            return True

        steps = max(2, int(dist / (tile_size * 0.4)))
        for i in range(1, steps):
            t = i / float(steps)
            px = x1 + dx * t
            py = y1 + dy * t
            c = int(px // tile_size)
            r = int(py // tile_size)
            if 0 <= c < game_map.cols and 0 <= r < game_map.rows:
                if game_map.get_tile(c, r) in (TileType.BRICK, TileType.STEEL, TileType.BASE):
                    return False
        return True


class MoveCommand(BaseCommand):
    """
    智能 A* 移动到目标点命令：
    - 当无限弹药时：自动破障，以极小时间开销直接炸开砖墙，直达目标；
    - 当有限弹药时：自动计算最省弹药的破障办法，优先零耗弹绕过障碍；若必须破障，选择摧毁砖块数绝对最少的路线。
    - 动态避碰与死锁防卡死机制：遇其他单位阻挡时自动侧向回避、A* 绕行或主动让行，杜绝碰撞死锁。
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
        self.total_stuck_frames: int = 0
        self.replan_timer: int = 0
        self.ammo_needed: int = 0
        self.pathfinder: Optional[GridPathfinder] = None
        self.blocking_tank_id: Optional[str] = None
        self.yield_timer: int = 0
        self.yield_direction: Optional[Direction] = None

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
        if getattr(tank, "is_converting", False):
            return False

        dist_to_final = math.hypot(self.dest_x - tank.x, self.dest_y - tank.y)
        if dist_to_final <= self.tolerance:
            return True

        if self.pathfinder is None or self.pathfinder.game_map != game_map:
            self.pathfinder = GridPathfinder(game_map)

        tile_size = game_map.tile_size

        # 让行倒车缓冲期：当两辆友军对撞死锁时，低优先级战车后退让道
        if self.yield_timer > 0:
            self.yield_timer -= 1
            if self.yield_direction:
                physics_engine.move_tank(tank, self.yield_direction)
            return False

        # 路径规划与自适应周期重规划
        if self.path is None or self.replan_timer <= 0:
            avoid_tiles = set()
            if self.blocking_tank_id:
                for other in physics_engine.get_all_active_tanks():
                    if other.id == self.blocking_tank_id and other.alive:
                        avoid_tiles.add((int(round(other.x / tile_size)), int(round(other.y / tile_size))))
                        break

            # 若卡死帧数累积，把周围 2 格范围内的其他坦克格子全部加入回避列表促使大范围绕道
            if self.stuck_frames > 6:
                for other in physics_engine.get_all_active_tanks():
                    if other != tank and other.alive:
                        d = math.hypot(other.x - tank.x, other.y - tank.y)
                        if d < tile_size * 2.5:
                            avoid_tiles.add((int(round(other.x / tile_size)), int(round(other.y / tile_size))))

            self.path, self.ammo_needed = self.pathfinder.find_path(
                tank.x, tank.y, self.dest_x, self.dest_y,
                tank=tank,
                limited_ammo_enabled=physics_engine.limited_ammo_enabled,
                avoid_tiles=avoid_tiles if avoid_tiles else None
            )
            self.path_idx = 0
            self.replan_timer = 40

        self.replan_timer -= 1

        # 沿路径航点向前推进：确保真正达到当前航点后才切入垂直拐弯，杜绝过早拐弯刮蹭拐角砖块
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
        dist_to_target = math.hypot(dx, dy)

        if dist_to_target > 1e-4:
            move_angle = math.degrees(math.atan2(dx, -dy)) % 360.0
        else:
            move_angle = tank.angle

        primary = Direction.from_angle(move_angle)

        cfg = getattr(tank, "_config", None)
        b_speed = cfg.bullet_speed if cfg else 6.0
        b_size = cfg.bullet_size if cfg else 12
        b_color = cfg.bullet_color if cfg else ("#E69C24" if tank.camp == Camp.PLAYER else "#E63946")

        # 检测前路是否有砖块障碍待破障 (Auto-Breaching)
        # 若具备碾压砖块能力（清障车），则无视普通砖块直接碾压开赴，不需要停下开火破障
        if not getattr(tank, "can_crush_bricks", False):
            target_col = int(round(target_x / tile_size))
            target_row = int(round(target_y / tile_size))
            next_is_brick = (0 <= target_col < game_map.cols and 0 <= target_row < game_map.rows and
                             game_map.get_tile(target_col, target_row) == TileType.BRICK)

            if next_is_brick or self._check_front_has_brick(tank, primary, game_map):
                tank.angle = move_angle
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color, angle=move_angle)
                return False

        # 自由全向推进机动
        moved = physics_engine.move_tank(tank, (dx, dy))
        blocking_tank = None

        if not moved:
            step_x = tank.x + (dx / dist_to_target if dist_to_target > 0 else 0) * tank.speed
            step_y = tank.y + (dy / dist_to_target if dist_to_target > 0 else 0) * tank.speed
            blocking_tank = physics_engine.get_blocking_tank(tank, step_x, step_y)

            # 阻挡者为敌军时，主动朝敌军开火迎击
            if blocking_tank and blocking_tank.camp != tank.camp:
                tank.angle = move_angle
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color, angle=move_angle)

        # 侧向滑步规避脱困 (Lateral Evasion)
        if not moved and blocking_tank:
            self.blocking_tank_id = blocking_tank.id
            lateral_angles = [(move_angle + 90.0) % 360.0, (move_angle - 90.0) % 360.0]
            for l_angle in lateral_angles:
                if physics_engine.move_tank(tank, l_angle):
                    moved = True
                    break

        if not moved:
            self.stuck_frames += 1
            self.total_stuck_frames += 1

            # 触发即时重寻路（带回避方格）
            if self.stuck_frames > 6:
                self.path = None
                self.replan_timer = 0

            # 对撞死锁主动让行：若两辆友军对头卡死超过 18 帧，ID 较大的坦克倒车让道
            if self.stuck_frames > 18 and blocking_tank and blocking_tank.camp == tank.camp:
                if str(tank.id) > str(blocking_tank.id):
                    rev_dir = Direction.DOWN if primary == Direction.UP else (
                        Direction.UP if primary == Direction.DOWN else (
                            Direction.RIGHT if primary == Direction.LEFT else Direction.LEFT
                        )
                    )
                    self.yield_direction = rev_dir
                    self.yield_timer = 12
                    self.stuck_frames = 0

            # 长期彻底卡死堵塞（>70 帧约 1.1s），放弃本次寻路，令上层切换阵位或换目标
            if self.total_stuck_frames > 70:
                self.stuck_frames = 0
                return True
        else:
            self.stuck_frames = 0
            self.total_stuck_frames = 0
            self.blocking_tank_id = None

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
        self.standoff_idx: int = 0
        self.stuck_attack_frames: int = 0

    def execute(self, tank: Tank, physics_engine, game_map: GameMap) -> bool:
        if not tank.alive or not self.target_tank.alive:
            return True
        if getattr(tank, "is_converting", False):
            return False

        tile_size = game_map.tile_size
        center_x = tank.x + tank.size / 2.0
        center_y = tank.y + tank.size / 2.0
        target_center_x = self.target_tank.x + self.target_tank.size / 2.0
        target_center_y = self.target_tank.y + self.target_tank.size / 2.0

        dx = target_center_x - center_x
        dy = target_center_y - center_y
        dist = math.hypot(dx, dy)

        target_angle = (math.degrees(math.atan2(dx, -dy))) % 360.0

        align_threshold = min(20.0, tank.size * 0.55)
        is_aligned_v = abs(dx) <= align_threshold
        is_aligned_h = abs(dy) <= align_threshold

        cfg = getattr(tank, "_config", None)
        b_speed = cfg.bullet_speed if cfg else 6.0
        b_size = cfg.bullet_size if cfg else 12
        b_color = cfg.bullet_color if cfg else ("#E69C24" if tank.camp == Camp.PLAYER else "#E63946")

        # 1. 自由 360° 全向瞄准视线与直接射击
        los_clear = self.is_line_of_sight_clear(center_x, center_y, target_center_x, target_center_y, game_map)
        if los_clear:
            tank.angle = target_angle
            self.stuck_attack_frames = 0
            if tank.can_fire(physics_engine.limited_ammo_enabled):
                physics_engine.spawn_bullet(tank, b_speed, b_size, b_color, angle=target_angle)
        else:
            is_infinite = (tank.ammo < 0 or not physics_engine.limited_ammo_enabled)
            if is_infinite and (is_aligned_v or is_aligned_h):
                tank.angle = target_angle
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    self.stuck_attack_frames = 0
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color, angle=target_angle)
                    return False

        # 2. 机会射击 (Opportunistic Fire)：360° 检查视野内是否有其他可直接开火的敌军
        opp_tanks = physics_engine.enemy_tanks if tank.camp == Camp.PLAYER else physics_engine.player_tanks
        if tank.camp == Camp.PLAYER and getattr(tank, "ai_script", None) is None:
            cands = physics_engine.get_visible_enemies()
        else:
            cands = [t for t in opp_tanks if t.alive]

        for cand in cands:
            if cand == self.target_tank or not cand.alive:
                continue
            cand_cx = cand.x + cand.size / 2.0
            cand_cy = cand.y + cand.size / 2.0
            c_dx = cand_cx - center_x
            c_dy = cand_cy - center_y
            c_dist = math.hypot(c_dx, c_dy)
            if c_dist < 260.0 and self.is_line_of_sight_clear(center_x, center_y, cand_cx, cand_cy, game_map):
                c_angle = (math.degrees(math.atan2(c_dx, -c_dy))) % 360.0
                tank.angle = c_angle
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color, angle=c_angle)
                break

        # 如果自身是固定防御塔，不执行位移
        if tank.is_tower or tank.speed <= 0:
            tank.angle = target_angle
            if tank.can_fire(physics_engine.limited_ammo_enabled):
                physics_engine.spawn_bullet(tank, b_speed, b_size, b_color, angle=target_angle)
            return False

        # 4. 寻找进攻占位阵位 (Standoff Attack Position)
        tx, ty = self.target_tank.x, self.target_tank.y
        dist_moved = math.hypot(self.last_target_pos[0] - tx, self.last_target_pos[1] - ty)

        # 检查是否需要重新挑选阵位：
        # - move_subcmd 为空
        # - 目标移动超过半格
        # - 当前机动子命令严重卡顿 (stuck_frames > 12)
        should_replan_standoff = (
            self.move_subcmd is None or
            dist_moved > 18.0 or
            (self.move_subcmd and self.move_subcmd.stuck_frames > 12)
        )

        if should_replan_standoff:
            if self.move_subcmd and self.move_subcmd.stuck_frames > 12:
                self.standoff_idx += 1
                self.stuck_attack_frames += self.move_subcmd.stuck_frames

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
            allied_tanks = physics_engine.player_tanks if tank.camp == Camp.PLAYER else physics_engine.enemy_tanks
            for sc, sr in standoff_candidates:
                if 0 <= sc < game_map.cols and 0 <= sr < game_map.rows:
                    tile = game_map.get_tile(sc, sr)
                    if tile != TileType.STEEL:
                        d = float(abs(sc - c_me) + abs(sr - r_me))
                        # 若已有友军占据该阵位，增加权重促使坦克选择包抄另一侧
                        for other in allied_tanks:
                            if other.alive and other != tank:
                                if math.hypot(other.x - sc * tile_size, other.y - sr * tile_size) < tile_size * 0.9:
                                    d += 50.0
                        valid_candidates.append((d, sc * tile_size, sr * tile_size))

            if valid_candidates:
                valid_candidates.sort(key=lambda item: item[0])
                chosen = valid_candidates[self.standoff_idx % len(valid_candidates)]
                dest_x, dest_y = chosen[1], chosen[2]
            else:
                dest_x, dest_y = tx, ty

            self.move_subcmd = MoveCommand(dest_x, dest_y, tolerance=4.0, auto_clear_path=self.auto_clear_path)
            self.last_target_pos = (tx, ty)

        subcmd_done = self.move_subcmd.execute(tank, physics_engine, game_map)

        if self.move_subcmd.stuck_frames > 0:
            self.stuck_attack_frames += 1
        else:
            self.stuck_attack_frames = max(0, self.stuck_attack_frames - 1)

        # 若子命令因为死锁而提前返回（非真正到达目标点），或者累计死锁卡死超过 70 帧，放弃当前目标以便接续新目标
        dist_to_subdest = math.hypot(self.move_subcmd.dest_x - tank.x, self.move_subcmd.dest_y - tank.y)
        if (subcmd_done and dist_to_subdest > self.move_subcmd.tolerance) or self.stuck_attack_frames > 70:
            return True

        # 到达射击阵位后，若仍存在微小轴向未对齐，主动朝目标轴线微调对齐，确保立刻开火
        if subcmd_done and dist_to_subdest <= self.move_subcmd.tolerance:
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


class HarvestCommand(BaseCommand):
    """
    智能资源开采命令：
    - 目标为地图上的资源块 (target_col, target_row)
    - 若不在可采集半径 (harvest_radius) 内，自动寻路移动到资源块周围最近的合法可通行地块
    - 到达开采半径内后停止位移，开启 tank.start_harvest(target_col, target_row)
    - 在开采过程中维持驻守开采，实时结算开采与排他检测
    - 当资源块耗尽或目标不存在时，任务结束
    """
    def __init__(self, target_col: int, target_row: int, resource_manager: Any, auto_clear_path: bool = True):
        self.target_col = int(target_col)
        self.target_row = int(target_row)
        self.resource_manager = resource_manager
        self.auto_clear_path = auto_clear_path
        self.move_subcmd: Optional[MoveCommand] = None

    def _find_standable_harvest_pos(self, tank: Tank, physics_engine, game_map: GameMap, block: Any) -> Optional[Tuple[float, float]]:
        ts = game_map.tile_size
        cx, cy = block.center(ts)
        S = tank.size
        bx1, by1 = block.col * ts, block.row * ts
        bx2, by2 = bx1 + ts, by1 + ts

        pts = []
        # 1. 绝对中心点优先 (cx - S/2, cy - S/2)
        pts.append((cx - S / 2.0, cy - S / 2.0))
        pts.append((bx1 + (ts - S) / 2.0, by1 + (ts - S) / 2.0))
        pts.append((bx1, by1))

        # 2. 从中心向外同心圆密集径向采样 (尽可能靠近中心)
        for dist_r in [2.0, 4.0, 8.0, 12.0, 16.0, 20.0, 24.0, 32.0, 40.0, 48.0, 64.0, block.harvest_radius]:
            if dist_r <= block.harvest_radius:
                for deg in range(0, 360, 20):
                    rad = math.radians(deg)
                    pts.append((cx + math.cos(rad) * dist_r - S / 2.0, cy + math.sin(rad) * dist_r - S / 2.0))

        # 3. 瓦片网格常规对齐采样
        r = int(math.ceil(block.harvest_radius / ts)) + 1
        for dr in range(-r, r + 1):
            for dc in range(-r, r + 1):
                col = self.target_col + dc
                row = self.target_row + dr
                if 0 <= col < game_map.cols and 0 <= row < game_map.rows:
                    pts.append((col * ts + (ts - S) / 2.0, row * ts + (ts - S) / 2.0))
                    pts.append((col * ts, row * ts))

        # 4. 贴紧资源块外缘平铺采样
        gap = 1.0
        offsets = [0.0, (ts - S) / 2.0, -(S - ts), ts - S]
        for offset in offsets:
            pts.append((bx1 - S - gap, by1 + offset))
            pts.append((bx2 + gap, by1 + offset))
            pts.append((bx1 + offset, by1 - S - gap))
            pts.append((bx1 + offset, by2 + gap))

        candidates = []
        seen = set()
        for tx, ty in pts:
            key = (round(tx, 1), round(ty, 1))
            if key in seen:
                continue
            seen.add(key)
            if 0 <= tx and tx + S <= game_map.pixel_width and 0 <= ty and ty + S <= game_map.pixel_height:
                if physics_engine.can_move_to(tank, tx, ty):
                    tcx, tcy = tx + S / 2.0, ty + S / 2.0
                    dist_center = math.hypot(tcx - cx, tcy - cy)
                    if dist_center <= block.harvest_radius:
                        dist_to_tank = math.hypot(tx - tank.x, ty - tank.y)
                        # 核心排序准则：尽可能逼近目标中心 (dist_center 优先升序)
                        candidates.append((dist_center, dist_to_tank, tx, ty))

        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1]))
            return candidates[0][2], candidates[0][3]
        return None

    def execute(self, tank: Tank, physics_engine, game_map: GameMap) -> bool:
        if not tank.alive or tank.is_tower:
            tank.stop_harvest()
            return True

        if getattr(tank, "is_converting", False):
            tank.stop_harvest()
            return False

        block = self.resource_manager.get_block_at(self.target_col, self.target_row) if self.resource_manager else None
        if not block or block.current_amount <= 0:
            tank.stop_harvest()
            return True

        ts = game_map.tile_size
        cx, cy = block.center(ts)

        # 1. 寻找尽可能靠近目标中心的最佳站立位置
        dest = self._find_standable_harvest_pos(tank, physics_engine, game_map, block)
        if not dest:
            # 若无法找到任何可站立位置，且当前在采集范围内，就地采集
            if block.is_in_harvest_range(tank, ts):
                if not tank.is_harvesting or tank.harvest_target != (self.target_col, self.target_row):
                    tank.start_harvest(self.target_col, self.target_row)
                return False
            tank.stop_harvest()
            return True

        dest_x, dest_y = dest
        dist_to_dest = math.hypot(tank.x - dest_x, tank.y - dest_y)

        # 2. 如果已经到达最佳位置（误差 4.0 像素以内）
        if dist_to_dest <= 4.0:
            self.move_subcmd = None
            if not tank.is_harvesting or tank.harvest_target != (self.target_col, self.target_row):
                tank.start_harvest(self.target_col, self.target_row)
            return False

        # 3. 尚未到达最佳中心位置：在途不提前采矿，持续驱动移向目标中心
        if getattr(tank, "is_harvesting", False):
            tank.stop_harvest()

        if self.move_subcmd is None or abs(self.move_subcmd.dest_x - dest_x) > 2.0 or abs(self.move_subcmd.dest_y - dest_y) > 2.0:
            self.move_subcmd = MoveCommand(dest_x, dest_y, tolerance=3.0, auto_clear_path=self.auto_clear_path)

        done = self.move_subcmd.execute(tank, physics_engine, game_map)

        # 若在移动过程中卡住且无法再靠近中心，但已处于采集范围内，就地开始采集
        if self.move_subcmd and self.move_subcmd.stuck_frames > 25:
            if block.is_in_harvest_range(tank, ts):
                self.move_subcmd = None
                tank.start_harvest(self.target_col, self.target_row)
                return False

        # 检查是否已达到目标点
        if done or math.hypot(tank.x - dest_x, tank.y - dest_y) <= 4.0:
            self.move_subcmd = None
            if block.is_in_harvest_range(tank, ts):
                tank.start_harvest(self.target_col, self.target_row)
                return False
            else:
                tank.stop_harvest()
                return True

        return False
