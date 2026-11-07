import math
import random
from abc import ABC, abstractmethod
from typing import Optional, List, Tuple, Any
from physics.entities import Tank, Direction, Camp
from map_loader.models import GameMap, TileType

class BaseTactic(ABC):
    """敌军战术行为抽象基类"""

    def __init__(self, tank_config=None):
        self.tank_config = tank_config
        # 转向锁定计时器：防止高频抖动转向
        self.direction_lock: int = 0
        self.blocked_counter: int = 0
        self.evade_side: float = 1.0
        self.current_angle: Optional[float] = None

    @abstractmethod
    def decide(self, tank: Tank, physics_engine, game_map: GameMap) -> Tuple[Optional[Any], bool]:
        pass

    @staticmethod
    def get_opposite_direction(d: Direction) -> Direction:
        if d == Direction.UP:
            return Direction.DOWN
        elif d == Direction.DOWN:
            return Direction.UP
        elif d == Direction.LEFT:
            return Direction.RIGHT
        else:
            return Direction.LEFT

    @staticmethod
    def get_perpendicular_directions(d: Direction) -> List[Direction]:
        """获取与当前方向垂直的两个侧向方向"""
        if d in (Direction.UP, Direction.DOWN):
            return [Direction.LEFT, Direction.RIGHT]
        else:
            return [Direction.UP, Direction.DOWN]

    @staticmethod
    def is_line_of_sight_clear(x1: float, y1: float, x2: float, y2: float,
                               game_map: GameMap) -> bool:
        """检查两点间 360° 视线是否被不可穿透的铁墙或砖墙阻挡"""
        tile_size = game_map.tile_size
        col1, row1 = int(x1 // tile_size), int(y1 // tile_size)
        col2, row2 = int(x2 // tile_size), int(y2 // tile_size)

        if col1 == col2:
            step = 1 if row2 > row1 else -1
            for r in range(row1 + step, row2, step):
                if 0 <= col1 < game_map.cols and 0 <= r < game_map.rows:
                    if game_map.get_tile(col1, r) in (TileType.BRICK, TileType.STEEL):
                        return False
            return True
        elif row1 == row2:
            step = 1 if col2 > col1 else -1
            for c in range(col1 + step, col2, step):
                if 0 <= c < game_map.cols and 0 <= row1 < game_map.rows:
                    if game_map.get_tile(c, row1) in (TileType.BRICK, TileType.STEEL):
                        return False
            return True

        dx = x2 - x1
        dy = y2 - y1
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            return True
        steps = max(2, int(dist / (tile_size * 0.4)))
        for i in range(1, steps):
            t = i / float(steps)
            c = int((x1 + dx * t) // tile_size)
            r = int((y1 + dy * t) // tile_size)
            if 0 <= c < game_map.cols and 0 <= r < game_map.rows:
                if game_map.get_tile(c, r) in (TileType.BRICK, TileType.STEEL):
                    return False
        return True

    def _find_steered_angle(self, tank: Tank, target_angle: float, physics_engine) -> Optional[float]:
        """沿目标角度及两侧扇形寻找可通行的斜向/侧向移动角度"""
        step = max(1.0, tank.speed)
        rad0 = math.radians(target_angle)
        if physics_engine.can_move_to(tank, tank.x + math.sin(rad0) * step, tank.y - math.cos(rad0) * step):
            return target_angle

        fan = [25.0, 45.0, 65.0, 90.0, 120.0, 150.0]
        offsets = [a * self.evade_side for a in fan] + [a * (-self.evade_side) for a in fan]
        for off in offsets:
            cand = (target_angle + off) % 360.0
            rad = math.radians(cand)
            if physics_engine.can_move_to(tank, tank.x + math.sin(rad) * step, tank.y - math.cos(rad) * step):
                self.evade_side = 1.0 if off > 0 else -1.0
                return cand
        return None


class PatrolTactic(BaseTactic):
    """
    战术1：巡逻漫游战术
    - 坚持平稳直线行驶一段距离，禁止每帧抖动变向；
    - 遇到障碍物时优先侧向转弯，有概率开火破墙；
    - 偶尔在视线通畅或前进时开炮压制。
    """
    def __init__(self, tank_config=None):
        super().__init__(tank_config)
        self.direction_lock = random.randint(30, 70)

    def decide(self, tank: Tank, physics_engine, game_map: GameMap) -> Tuple[Optional[Direction], bool]:
        should_fire = random.random() < 0.03

        # 预测当前方向能否通行
        test_x = tank.x + tank.direction.dx * tank.speed
        test_y = tank.y + tank.direction.dy * tank.speed
        can_continue = physics_engine.can_move_to(tank, test_x, test_y)

        if not can_continue:
            self.blocked_counter += 1
            # 遇阻时开火尝试炸开砖墙
            if self.blocked_counter > 5:
                should_fire = True
        else:
            self.blocked_counter = 0

        # 若处于方向锁定期间且未被阻挡，继续保持当前方向
        if can_continue and self.direction_lock > 0:
            self.direction_lock -= 1
            return tank.direction, should_fire

        # 需要变向（时间到期或被阻挡）
        self.direction_lock = random.randint(35, 75)
        self.blocked_counter = 0

        # 优先选择可通行的方向，且优先侧向而非180度调头（避免原地抽搐）
        perp_dirs = self.get_perpendicular_directions(tank.direction)
        random.shuffle(perp_dirs)

        valid_perp = []
        for d in perp_dirs:
            tx = tank.x + d.dx * tank.speed
            ty = tank.y + d.dy * tank.speed
            if physics_engine.can_move_to(tank, tx, ty):
                valid_perp.append(d)

        if valid_perp:
            tank.direction = valid_perp[0]
            return tank.direction, should_fire

        # 侧向不通，检查是否还能继续向前
        if can_continue:
            return tank.direction, should_fire

        # 侧向和前进都不通，才选择掉头后退
        opp_dir = self.get_opposite_direction(tank.direction)
        tx = tank.x + opp_dir.dx * tank.speed
        ty = tank.y + opp_dir.dy * tank.speed
        if physics_engine.can_move_to(tank, tx, ty):
            tank.direction = opp_dir
        else:
            # 四周皆堵，开火轰墙
            should_fire = True

        return tank.direction, should_fire


class ChargeBaseTactic(BaseTactic):
    """
    战术2：突袭基地战术
    - 锁定下方老鹰基地，直接沿斜向最优角度向基地推进；
    - 遇到砖墙挡路直接开火轰开道路，遇不可穿透障碍时扇形避障绕行。
    """
    def __init__(self, tank_config=None):
        super().__init__(tank_config)
        self.direction_lock = 15

    def decide(self, tank: Tank, physics_engine, game_map: GameMap) -> Tuple[Optional[Any], bool]:
        target_tower = None
        for pt in physics_engine.player_tanks:
            if pt.alive and pt.is_tower and pt.tower_type == "supply":
                target_tower = pt
                break
        if not target_tower:
            for pt in physics_engine.player_tanks:
                if pt.alive and pt.is_tower:
                    target_tower = pt
                    break

        if not target_tower:
            alive_pts = [t for t in physics_engine.player_tanks if t.alive]
            if alive_pts:
                target_tower = min(alive_pts, key=lambda t: (t.x - tank.x)**2 + (t.y - tank.y)**2)

        if target_tower:
            base_x = target_tower.x + target_tower.size / 2.0
            base_y = target_tower.y + target_tower.size / 2.0
        else:
            base_x = game_map.pixel_width / 2.0
            base_y = game_map.pixel_height - game_map.tile_size

        cx = tank.x + tank.size / 2.0
        cy = tank.y + tank.size / 2.0
        dx = base_x - cx
        dy = base_y - cy
        dist = math.hypot(dx, dy)
        target_angle = math.degrees(math.atan2(dx, -dy)) % 360.0 if dist > 1e-4 else tank.angle

        cfg = getattr(tank, "_config", self.tank_config)
        attack_range = float(getattr(tank, "attack_range", getattr(cfg, "attack_range", 240.0) if cfg else 240.0))
        if attack_range <= 0:
            attack_range = 240.0

        if self.is_line_of_sight_clear(cx, cy, base_x, base_y, game_map):
            tank.angle = target_angle
            # 进入射程后停止前进直接开火
            if dist <= attack_range:
                return None, True
            steered = self._find_steered_angle(tank, target_angle, physics_engine)
            return (steered if steered is not None else target_angle), True

        steered = self._find_steered_angle(tank, target_angle, physics_engine)
        if steered is not None:
            return steered, (abs(steered - target_angle) > 20.0)

        tank.angle = target_angle
        return target_angle, True


class HunterTactic(BaseTactic):
    """
    战术3：猎杀追踪战术
    - 追踪玩家坦克坐标，支持 360° 斜向视线瞄准与斜线直达追击；
    - 遇阻挡时使用多角度扇形动态避障。
    """
    def __init__(self, tank_config=None):
        super().__init__(tank_config)
        self.direction_lock = 15

    def decide(self, tank: Tank, physics_engine, game_map: GameMap) -> Tuple[Optional[Any], bool]:
        player = physics_engine.player_tank
        if not player or not player.alive:
            alive_pts = [t for t in physics_engine.player_tanks if t.alive]
            if alive_pts:
                player = min(alive_pts, key=lambda t: (t.x - tank.x)**2 + (t.y - tank.y)**2)
            else:
                return tank.direction, False

        center_x = tank.x + tank.size / 2.0
        center_y = tank.y + tank.size / 2.0
        p_center_x = player.x + player.size / 2.0
        p_center_y = player.y + player.size / 2.0

        dx = p_center_x - center_x
        dy = p_center_y - center_y
        dist = math.hypot(dx, dy)
        target_angle = math.degrees(math.atan2(dx, -dy)) % 360.0 if dist > 1e-4 else tank.angle

        cfg = getattr(tank, "_config", self.tank_config)
        attack_range = float(getattr(tank, "attack_range", getattr(cfg, "attack_range", 240.0) if cfg else 240.0))
        if attack_range <= 0:
            attack_range = 240.0

        # 1. 360° 视线畅通时：当被攻击对象刚好进入自己射程后就不继续前进，只有出了射程才追击前进
        if self.is_line_of_sight_clear(center_x, center_y, p_center_x, p_center_y, game_map):
            tank.angle = target_angle
            if dist <= attack_range:
                return None, True
            steered = self._find_steered_angle(tank, target_angle, physics_engine)
            return (steered if steered is not None else target_angle), True

        # 2. 视线受阻时沿斜向 + 动态扇形避障追击玩家
        steered = self._find_steered_angle(tank, target_angle, physics_engine)
        if steered is not None:
            return steered, False

        tank.angle = target_angle
        return target_angle, True
