import math
import random
from abc import ABC, abstractmethod
from typing import Optional, Tuple, List, Any, Set
from physics.entities import Tank, Direction, Camp, Rect
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
    智能 A* 斜向直达移动与动态避障命令：
    - 支持八方向 A* 与任意角度视线拉直 (Any-Angle String Pulling)，直接沿斜线行进至目标；
    - 当无限弹药时：自动破障，以极小时间开销直接炸开砖墙，直达目标；
    - 当有限弹药时：自动计算最省弹药的破障办法，优先零耗弹绕过障碍；若必须破障，选择摧毁砖块数绝对最少的路线；
    - 多级动态避障系统：
      1. 预判感知：对己方驻守/采矿/转换单位及阻挡单位进行 Minkowski 包围盒网格膨胀回避；
      2. 前瞻引导与多角度扇形局部避障 (Context Steering)：遇动态障碍时按相对方位与右侧通行法则锁定绕行方向，优先选择斜向切角全速绕行，彻底消除左右抽搐与貼脸往复滑动；
      3. 动态视线前瞻捷径 (Dynamic Lookahead)：绕过障碍后立即斜向切入后续航点，无需折返原航点；
      4. 窄道会车让行：单格窄巷迎头死锁时低优先级单位自动寻找侧方避让口或倒车让道。
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
        self.impeded_frames: int = 0
        self.replan_timer: int = 0
        self.ammo_needed: int = 0
        self.pathfinder: Optional[GridPathfinder] = None
        self.blocking_tank_id: Optional[str] = None
        self.evade_side: float = 0.0
        self.evade_lock_timer: int = 0
        self.yield_timer: int = 0
        self.yield_direction: Optional[Direction] = None
        self.yield_angle: Optional[float] = None

    def _check_front_has_brick(self, tank: Tank, direction: Direction,
                               game_map: GameMap, move_angle: Optional[float] = None) -> bool:
        tile_size = game_map.tile_size
        ahead = 6.0
        check_points = []
        if direction in (Direction.UP, Direction.DOWN):
            cy = tank.y + (tank.size + ahead if direction == Direction.DOWN else -ahead)
            cx = tank.x + tank.size / 2.0
            check_points.extend([(cx, cy), (tank.x + 8.0, cy), (tank.x + tank.size - 8.0, cy)])
        else:
            cx = tank.x + (tank.size + ahead if direction == Direction.RIGHT else -ahead)
            cy = tank.y + tank.size / 2.0
            check_points.extend([(cx, cy), (cx, tank.y + 8.0), (cx, tank.y + tank.size - 8.0)])

        if move_angle is not None:
            rad = math.radians(move_angle)
            ux = math.sin(rad)
            uy = -math.cos(rad)
            center_x = tank.x + tank.size / 2.0
            center_y = tank.y + tank.size / 2.0
            reach = tank.size / 2.0 + ahead
            check_points.append((center_x + ux * reach, center_y + uy * reach))

        for px, py in check_points:
            col = int(px // tile_size)
            row = int(py // tile_size)
            if 0 <= col < game_map.cols and 0 <= row < game_map.rows:
                if game_map.get_tile(col, row) == TileType.BRICK:
                    return True
        return False

    def _collect_avoid_tiles(self, tank: Tank, physics_engine, game_map: GameMap) -> Set[Tuple[int, int]]:
        """
        构建动态障碍物的 Minkowski 膨胀回避网格集合：
        - 主动避开己方固定建筑、正在采矿或转换的驻留单位；
        - 避开当前造成阻挡的单位及受阻时周边的拥挤单位；
        - 将被避让单位的包围盒按本车尺寸膨胀映射到网格，确保规划出的绕行路径物理上绝不擦碰。
        """
        tile_size = game_map.tile_size
        start_c = int(round(tank.x / tile_size))
        start_r = int(round(tank.y / tile_size))
        goal_c = int(round(self.dest_x / tile_size))
        goal_r = int(round(self.dest_y / tile_size))

        avoid_tiles: Set[Tuple[int, int]] = set()
        is_impeded = (self.stuck_frames >= 2 or self.impeded_frames >= 3)

        for other in physics_engine.get_all_active_tanks():
            if other is tank or not other.alive:
                continue

            should_avoid = False
            if self.blocking_tank_id and other.id == self.blocking_tank_id:
                should_avoid = True
            elif is_impeded and math.hypot(other.x - tank.x, other.y - tank.y) < tile_size * 3.2:
                should_avoid = True
            elif other.camp == tank.camp and (
                other.is_tower or
                getattr(other, "is_converting", False) or
                getattr(other, "is_harvesting", False)
            ):
                should_avoid = True

            if should_avoid:
                c_min = max(0, int((other.x - tank.size + 2.0) // tile_size))
                c_max = min(game_map.cols - 1, int((other.x + other.size - 2.0) // tile_size))
                r_min = max(0, int((other.y - tank.size + 2.0) // tile_size))
                r_max = min(game_map.rows - 1, int((other.y + other.size - 2.0) // tile_size))
                for r in range(r_min, r_max + 1):
                    for c in range(c_min, c_max + 1):
                        if (c, r) != (start_c, start_r) and (c, r) != (goal_c, goal_r):
                            avoid_tiles.add((c, r))

        return avoid_tiles

    def _is_corridor_blocked_by_tank(self, tank: Tank, x2: float, y2: float,
                                     physics_engine, max_check_dist: float = 96.0) -> bool:
        """检测从当前位置直达 (x2, y2) 的近期扫掠走廊内是否有其他坦克阻挡"""
        dx = x2 - tank.x
        dy = y2 - tank.y
        dist = math.hypot(dx, dy)
        if dist < 1e-3:
            return False
        check_d = min(dist, max_check_dist)
        steps = max(1, int(math.ceil(check_d / max(4.0, tank.size * 0.35))))
        ux = dx / dist
        uy = dy / dist
        for i in range(1, steps + 1):
            d = (check_d * i) / float(steps)
            if physics_engine.get_blocking_tank(tank, tank.x + ux * d, tank.y + uy * d) is not None:
                return True
        return False

    def _steer_around_obstacle(self, tank: Tank, blocking_tank: Optional[Tank],
                               move_angle: float, physics_engine) -> bool:
        """
        多角度扇形局部动态避障 (Context Steering)：
        - 根据阻挡坦克相对航向的横向偏置 (side_dot) 与右侧通行法则确定最优绕行侧；
        - 在锁定期内保持绕行侧向一致，防止左右高频摇摆抖动；
        - 优先从最小偏角 (25° -> 45° -> 65° -> 90° -> 115° -> 135°) 探测可全速无碰撞通行的斜向角度，实现平滑切角绕障。
        """
        if blocking_tank is not None:
            if self.evade_lock_timer > 0 and self.blocking_tank_id == blocking_tank.id and self.evade_side != 0.0:
                prefer_sign = self.evade_side
            else:
                rad = math.radians(move_angle)
                ux = math.sin(rad)
                uy = -math.cos(rad)
                # 右手法则法向量 n_right = (-uy, ux)
                my_cx = tank.x + tank.size / 2.0
                my_cy = tank.y + tank.size / 2.0
                ot_cx = blocking_tank.x + blocking_tank.size / 2.0
                ot_cy = blocking_tank.y + blocking_tank.size / 2.0
                rel_x = ot_cx - my_cx
                rel_y = ot_cy - my_cy
                side_dot = rel_x * (-uy) + rel_y * ux
                # 若障碍物中心偏右 (side_dot > 2.0)，向左 (-1) 绕行更近；若偏左或迎头正对，向右 (+1，右侧通行法则) 绕行
                prefer_sign = -1.0 if side_dot > 2.0 else 1.0
                self.evade_side = prefer_sign
            self.blocking_tank_id = blocking_tank.id
            self.evade_lock_timer = 16
        else:
            prefer_sign = self.evade_side if self.evade_side != 0.0 else 1.0

        fan_Steps = [25.0, 45.0, 65.0, 90.0, 115.0, 135.0]
        candidate_offsets = [ang * prefer_sign for ang in fan_Steps] + [ang * (-prefer_sign) for ang in fan_Steps]

        # 第一遍：优先寻找能完整步进（不依赖贴墙降速滑动）的畅通斜向角度
        step_dist = max(1.0, tank.speed)
        for offset in candidate_offsets:
            cand_angle = (move_angle + offset) % 360.0
            rad = math.radians(cand_angle)
            nx = tank.x + math.sin(rad) * step_dist
            ny = tank.y - math.cos(rad) * step_dist
            if physics_engine.can_move_to(tank, nx, ny):
                if physics_engine.move_tank(tank, cand_angle):
                    self.evade_side = 1.0 if offset > 0 else -1.0
                    return True

        # 第二遍：窄角受限时允许利用物理引擎贴墙滑动脱困
        for offset in [90.0 * prefer_sign, -90.0 * prefer_sign, 135.0 * prefer_sign, -135.0 * prefer_sign, 180.0]:
            cand_angle = (move_angle + offset) % 360.0
            if physics_engine.move_tank(tank, cand_angle):
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

        if self.evade_lock_timer > 0:
            self.evade_lock_timer -= 1

        # 让行倒车缓冲期：当两辆友军在窄道对撞死锁时，低优先级战车优先切入侧方避让口或后退让道
        if self.yield_timer > 0:
            self.yield_timer -= 1
            if self.yield_angle is not None:
                # 若侧方出现空位，立即切入侧方让出主干道
                for side_off in (90.0, -90.0, 60.0, -60.0, 0.0, 35.0, -35.0):
                    cand_a = (self.yield_angle + side_off) % 360.0
                    rad = math.radians(cand_a)
                    if physics_engine.can_move_to(tank, tank.x + math.sin(rad) * tank.speed, tank.y - math.cos(rad) * tank.speed):
                        physics_engine.move_tank(tank, cand_a)
                        break
            elif self.yield_direction:
                physics_engine.move_tank(tank, self.yield_direction)
            return False

        # 路径规划与自适应周期重规划
        if self.path is None or self.replan_timer <= 0:
            avoid_tiles = self._collect_avoid_tiles(tank, physics_engine, game_map)
            self.path, self.ammo_needed = self.pathfinder.find_path(
                tank.x, tank.y, self.dest_x, self.dest_y,
                tank=tank,
                limited_ammo_enabled=physics_engine.limited_ammo_enabled,
                avoid_tiles=avoid_tiles if avoid_tiles else None
            )
            self.path_idx = 0
            self.replan_timer = 35

        self.replan_timer -= 1

        # 动态视线前瞻捷径 (Dynamic Lookahead)：若当前位置可直接斜向无阻通往后续航点，立即跳过中间过渡点
        can_crush = getattr(tank, "can_crush_bricks", False)
        while self.path_idx + 1 < len(self.path):
            curr_wx, curr_wy = self.path[self.path_idx]
            curr_c, curr_r = int(round(curr_wx / tile_size)), int(round(curr_wy / tile_size))
            if not can_crush and 0 <= curr_c < game_map.cols and 0 <= curr_r < game_map.rows:
                if game_map.get_tile(curr_c, curr_r) == TileType.BRICK:
                    break
            next_wx, next_wy = self.path[self.path_idx + 1]
            if (self.pathfinder.is_segment_passable(tank.x, tank.y, next_wx, next_wy, tank=tank) and
                    not self._is_corridor_blocked_by_tank(tank, next_wx, next_wy, physics_engine)):
                self.path_idx += 1
            else:
                break

        # 沿路径航点向前推进
        wp_reach_dist = max(3.5, tank.speed * 1.15)

        while self.path_idx < len(self.path):
            wx, wy = self.path[self.path_idx]
            dist_to_wp = math.hypot(wx - tank.x, wy - tank.y)
            if dist_to_wp <= wp_reach_dist:
                if physics_engine.can_move_to(tank, wx, wy):
                    tank.x = wx
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
        if not can_crush:
            target_col = int(round(target_x / tile_size))
            target_row = int(round(target_y / tile_size))
            next_is_brick = (0 <= target_col < game_map.cols and 0 <= target_row < game_map.rows and
                             game_map.get_tile(target_col, target_row) == TileType.BRICK)

            if next_is_brick or self._check_front_has_brick(tank, primary, game_map, move_angle=move_angle):
                tank.angle = move_angle
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color, angle=move_angle)
                return False

        # 前瞻与即时碰撞检测：识别正前方是否被其他坦克阻挡
        ux = dx / dist_to_target if dist_to_target > 1e-4 else 0.0
        uy = dy / dist_to_target if dist_to_target > 1e-4 else 0.0
        step_x = tank.x + ux * tank.speed
        step_y = tank.y + uy * tank.speed
        blocking_tank = physics_engine.get_blocking_tank(tank, step_x, step_y)

        # 对友军单位启用前瞻预判避障（在相撞前约 2.2 步距离提前平滑斜向切角分流）
        if blocking_tank is None and dist_to_target > tank.speed * 1.2:
            lookahead = min(dist_to_target, max(tank.speed * 2.2, 8.0))
            ahead_tank = physics_engine.get_blocking_tank(tank, tank.x + ux * lookahead, tank.y + uy * lookahead)
            if ahead_tank is not None and ahead_tank.camp == tank.camp:
                blocking_tank = ahead_tank

        moved = False
        if blocking_tank is not None:
            # 阻挡者为敌军时，主动朝敌军开火迎击
            if blocking_tank.camp != tank.camp:
                tank.angle = move_angle
                if tank.can_fire(physics_engine.limited_ammo_enabled):
                    physics_engine.spawn_bullet(tank, b_speed, b_size, b_color, angle=move_angle)

            # 执行智能多角度局部避障（禁止盲目贴墙回滑抵消侧移）
            moved = self._steer_around_obstacle(tank, blocking_tank, move_angle, physics_engine)
            self.impeded_frames += 1

            # 若持续受阻绕行满 5 帧，立即将阻挡单位加入回避网格触发全局 A* 重规划
            if self.impeded_frames >= 5:
                self.path = None
                self.replan_timer = 0
                self.impeded_frames = 0
        else:
            # 前方无动态单位阻挡，执行自由全向斜线推进
            moved = physics_engine.move_tank(tank, (dx, dy))
            if not moved:
                # 静态墙角微擦碰时，尝试小角度扇形切入脱困
                moved = self._steer_around_obstacle(tank, None, move_angle, physics_engine)
                self.impeded_frames += 1
            else:
                self.impeded_frames = max(0, self.impeded_frames - 1)
                if self.evade_lock_timer <= 0:
                    self.blocking_tank_id = None

        if not moved:
            self.stuck_frames += 1
            self.total_stuck_frames += 1

            # 触发即时重寻路（带膨胀回避方格）
            if self.stuck_frames > 4:
                self.path = None
                self.replan_timer = 0

            # 对撞死锁主动让行：若两辆友军在窄道卡死超过 10 帧，ID 较大的坦克主动避让/倒车让道
            if self.stuck_frames > 10 and blocking_tank and blocking_tank.camp == tank.camp:
                if str(tank.id) > str(blocking_tank.id):
                    rev_dir = Direction.DOWN if primary == Direction.UP else (
                        Direction.UP if primary == Direction.DOWN else (
                            Direction.RIGHT if primary == Direction.LEFT else Direction.LEFT
                        )
                    )
                    self.yield_direction = rev_dir
                    self.yield_angle = (move_angle + 180.0) % 360.0
                    self.yield_timer = 14
                    self.stuck_frames = 0

            # 若目的地紧邻处已被其他友军占据且本车已贴近目的地周围，判定为已就位，防止终点无限顶牛
            if dist_to_final <= tank.size * 1.35 and self.stuck_frames > 10:
                return True

            # 长期彻底卡死堵塞（>70 帧约 1.1s），放弃本次寻路，令上层切换阵位或换目标
            if self.total_stuck_frames > 70:
                self.stuck_frames = 0
                return True
        else:
            self.stuck_frames = 0
            if blocking_tank is None:
                self.total_stuck_frames = 0

        # 若终点已被友军驻留且本车已在终点旁持续绕行，提前结束移动
        if dist_to_final <= tank.size * 1.25 and self.impeded_frames > 12:
            return True

        return False


class AttackTargetCommand(BaseCommand):
    """
    集火攻击目标命令 (基于 A* 斜向机动占位与最省弹药破障)
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

        # 4. 寻找进攻占位阵位 (Standoff Attack Position，支持八方向环绕包抄)
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

            standoff_candidates = [
                (c_target, r_target - 1),
                (c_target, r_target + 1),
                (c_target - 1, r_target),
                (c_target + 1, r_target),
                (c_target - 1, r_target - 1),
                (c_target + 1, r_target - 1),
                (c_target - 1, r_target + 1),
                (c_target + 1, r_target + 1),
            ]
            valid_candidates = []
            allied_tanks = physics_engine.player_tanks if tank.camp == Camp.PLAYER else physics_engine.enemy_tanks
            for sc, sr in standoff_candidates:
                if 0 <= sc < game_map.cols and 0 <= sr < game_map.rows:
                    tile = game_map.get_tile(sc, sr)
                    if tile != TileType.STEEL:
                        cand_px = sc * tile_size
                        cand_py = sr * tile_size
                        d = math.hypot(cand_px - tank.x, cand_py - tank.y) / float(tile_size)
                        # 正交阵位在隔墙破障射击时具备天然优势，赋予轻微优先权
                        if sc != c_target and sr != r_target:
                            d += 0.35
                        # 若已有友军占据该阵位，增加权重促使坦克选择包抄另一侧
                        for other in allied_tanks:
                            if other.alive and other != tank:
                                if math.hypot(other.x - cand_px, other.y - cand_py) < tile_size * 0.9:
                                    d += 50.0
                        valid_candidates.append((d, cand_px, cand_py))

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

        # 到达射击阵位后，若视线被砖块阻挡且存在微小轴向未对齐，主动朝目标轴线微调对齐；若视线已畅通则保持瞄准角
        if subcmd_done and dist_to_subdest <= self.move_subcmd.tolerance:
            if not los_clear:
                if abs(dx) < abs(dy):
                    step_dir = Direction.RIGHT if target_center_x > center_x else Direction.LEFT
                    physics_engine.move_tank(tank, step_dir)
                else:
                    step_dir = Direction.DOWN if target_center_y > center_y else Direction.UP
                    physics_engine.move_tank(tank, step_dir)
            else:
                tank.angle = target_angle

        return False


class GuardUnitCommand(BaseCommand):
    """
    战术指令：【跟踪并保卫特定己方单位 (Guard / Escort Unit)】
    - 跟随被保卫的己方单位（如核心防御塔或领袖战车），保持在护卫距离内；
    - 当有威胁敌军靠近时，主动开火并拦截威胁者；
    - 威胁解除后沿斜向最优路径回归被保卫者身旁。
    """
    def __init__(self, target_to_guard: Tank, guard_dist: float = 65.0):
        self.target_to_guard = target_to_guard
        self.guard_dist = guard_dist
        self.attack_subcmd: Optional[AttackTargetCommand] = None
        self.move_subcmd: Optional[MoveCommand] = None

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

        # 3. 无威胁时，沿斜线直接跟随靠拢被护卫单位（带动态避障与 A* 绕障）
        if tank.is_tower or tank.speed <= 0:
            return False

        dist_to_guarded = math.hypot(target_cx - center_x, target_cy - center_y)
        if dist_to_guarded > self.guard_dist:
            gx, gy = self.target_to_guard.x, self.target_to_guard.y
            if self.move_subcmd is None or math.hypot(self.move_subcmd.dest_x - gx, self.move_subcmd.dest_y - gy) > 16.0:
                self.move_subcmd = MoveCommand(gx, gy, tolerance=self.guard_dist * 0.85, auto_clear_path=True)
            self.move_subcmd.execute(tank, physics_engine, game_map)
        else:
            self.move_subcmd = None

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
