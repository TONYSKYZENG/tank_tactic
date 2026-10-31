import random
from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
from physics.entities import Tank, Direction, Camp
from map_loader.models import GameMap, TileType

class BaseTactic(ABC):
    """敌军战术行为抽象基类"""

    def __init__(self, tank_config=None):
        self.tank_config = tank_config
        # 转向锁定计时器：防止高频抖动转向
        self.direction_lock: int = 0
        self.blocked_counter: int = 0

    @abstractmethod
    def decide(self, tank: Tank, physics_engine, game_map: GameMap) -> Tuple[Optional[Direction], bool]:
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
        """检查两点间视线是否被不可穿透的铁墙或砖墙阻挡"""
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
    - 锁定下方老鹰基地，坚定不移向下与向中心推进；
    - 遇到砖墙挡路直接开火轰开道路；
    - 带有方向锁定，防止高频震荡抽搐。
    """
    def __init__(self, tank_config=None):
        super().__init__(tank_config)
        self.direction_lock = 25

    def decide(self, tank: Tank, physics_engine, game_map: GameMap) -> Tuple[Optional[Direction], bool]:
        base_x = game_map.pixel_width / 2.0
        base_y = game_map.pixel_height - game_map.tile_size

        should_fire = False

        # 检查当前方向能否前进
        test_x = tank.x + tank.direction.dx * tank.speed
        test_y = tank.y + tank.direction.dy * tank.speed
        can_continue = physics_engine.can_move_to(tank, test_x, test_y)

        if not can_continue:
            self.blocked_counter += 1
            should_fire = True
        else:
            self.blocked_counter = 0

        # 锁定期内且可走则继续走
        if can_continue and self.direction_lock > 0:
            self.direction_lock -= 1
            return tank.direction, should_fire

        # 重新评估最佳前进方向
        self.direction_lock = 30
        dx = base_x - (tank.x + tank.size / 2.0)
        dy = base_y - (tank.y + tank.size / 2.0)

        preferred: List[Direction] = []
        if dy > tank.size * 0.5:
            preferred.append(Direction.DOWN)
        if abs(dx) > tank.size * 0.5:
            preferred.append(Direction.RIGHT if dx > 0 else Direction.LEFT)

        # 补充其他方向
        for d in (Direction.DOWN, Direction.LEFT, Direction.RIGHT, Direction.UP):
            if d not in preferred:
                preferred.append(d)

        # 依次寻找可行方向
        for d in preferred:
            tx = tank.x + d.dx * tank.speed
            ty = tank.y + d.dy * tank.speed
            if physics_engine.can_move_to(tank, tx, ty):
                tank.direction = d
                return tank.direction, should_fire

        # 都受阻时保持首选方向并开火破障
        tank.direction = preferred[0]
        return tank.direction, True


class HunterTactic(BaseTactic):
    """
    战术3：猎杀追踪战术
    - 追踪玩家坦克坐标；
    - 视线对齐时果断瞄准并连续开火；
    - 移动带有防抖防抽搐锁定，保持稳定跟进。
    """
    def __init__(self, tank_config=None):
        super().__init__(tank_config)
        self.direction_lock = 20

    def decide(self, tank: Tank, physics_engine, game_map: GameMap) -> Tuple[Optional[Direction], bool]:
        player = physics_engine.player_tank
        if not player or not player.alive:
            return tank.direction, False

        should_fire = False
        center_x = tank.x + tank.size / 2.0
        center_y = tank.y + tank.size / 2.0
        p_center_x = player.x + player.size / 2.0
        p_center_y = player.y + player.size / 2.0

        align_threshold = tank.size * 0.65
        dx = p_center_x - center_x
        dy = p_center_y - center_y

        # 1. 优先检查是否与玩家对齐（同一行或同一列）
        is_aligned_v = abs(dx) < align_threshold
        is_aligned_h = abs(dy) < align_threshold

        if is_aligned_v:
            target_dir = Direction.DOWN if dy > 0 else Direction.UP
            tank.direction = target_dir
            if self.is_line_of_sight_clear(center_x, center_y, p_center_x, p_center_y, game_map):
                should_fire = True
            return tank.direction, should_fire

        if is_aligned_h:
            target_dir = Direction.RIGHT if dx > 0 else Direction.LEFT
            tank.direction = target_dir
            if self.is_line_of_sight_clear(center_x, center_y, p_center_x, p_center_y, game_map):
                should_fire = True
            return tank.direction, should_fire

        # 2. 未对齐时向玩家移动
        test_x = tank.x + tank.direction.dx * tank.speed
        test_y = tank.y + tank.direction.dy * tank.speed
        can_continue = physics_engine.can_move_to(tank, test_x, test_y)

        if can_continue and self.direction_lock > 0:
            self.direction_lock -= 1
            return tank.direction, should_fire

        self.direction_lock = 25

        # 确定主副方向
        if abs(dx) > abs(dy):
            primary = Direction.RIGHT if dx > 0 else Direction.LEFT
            secondary = Direction.DOWN if dy > 0 else Direction.UP
        else:
            primary = Direction.DOWN if dy > 0 else Direction.UP
            secondary = Direction.RIGHT if dx > 0 else Direction.LEFT

        candidates = [primary, secondary]
        for d in Direction.all_directions():
            if d not in candidates:
                candidates.append(d)

        for d in candidates:
            tx = tank.x + d.dx * tank.speed
            ty = tank.y + d.dy * tank.speed
            if physics_engine.can_move_to(tank, tx, ty):
                tank.direction = d
                return tank.direction, should_fire

        # 被阻挡时开火破障
        return tank.direction, True
