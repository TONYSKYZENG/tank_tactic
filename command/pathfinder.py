import math
import heapq
from typing import List, Tuple, Optional, Dict, Set
from map_loader.models import GameMap, TileType
from physics.entities import Tank, Direction

class GridPathfinder:
    """
    智能 A* 寻路与最省弹药破障规划器：
    - 无限弹药模式 (tank.ammo < 0 或 limited_ammo_enabled == False):
      低成本自动破障：优先直线破障开路，大幅缩短绕路行军距离。
    - 有限弹药模式 (tank.ammo >= 0 且 limited_ammo_enabled == True):
      最省弹药破障：破障附加极高弹药惩罚成本 (100.0)，优先自动寻找绕过障碍的零耗弹路线；
      若所有绕行通道均被阻断（死胡同或铁墙全封死），则自动计算耗弹量绝对最小的破障路线；
      若当前弹药不足以打通最少障碍，则判定不可通行。
    """

    AMMO_PENALTY_LIMITED = 100.0   # 有限弹药时每破坏 1 块砖的沉重代价
    BREACH_PENALTY_INFINITE = 0.8  # 无限弹药时破坏 1 块砖的轻微开销 (优先直线破障直达)

    def __init__(self, game_map: GameMap):
        self.game_map = game_map

    def find_path(self, start_x: float, start_y: float,
                  dest_x: float, dest_y: float,
                  tank: Optional[Tank] = None,
                  limited_ammo_enabled: bool = True,
                  avoid_tiles: Optional[Set[Tuple[int, int]]] = None) -> Tuple[List[Tuple[float, float]], int]:
        """
        计算最优通行路径与需摧毁的障碍数
        :return: (waypoint_list, ammo_needed)
                 waypoint_list: 像素坐标航点列表 [(x0, y0), (x1, y1), ...]
                 ammo_needed: 此路径需要消耗的弹药数（破障砖块数）
        """
        tile_size = self.game_map.tile_size
        cols = self.game_map.cols
        rows = self.game_map.rows

        # 转换为格子坐标
        start_c = max(0, min(cols - 1, int(round(start_x / tile_size))))
        start_r = max(0, min(rows - 1, int(round(start_y / tile_size))))
        goal_c = max(0, min(cols - 1, int(round(dest_x / tile_size))))
        goal_r = max(0, min(rows - 1, int(round(dest_y / tile_size))))

        if start_c == goal_c and start_r == goal_r:
            return [(dest_x, dest_y)], 0

        # 判断是否为无限弹药模式
        is_infinite_ammo = True
        current_ammo = 999999
        if tank is not None and limited_ammo_enabled:
            if tank.ammo >= 0:
                is_infinite_ammo = False
                current_ammo = tank.ammo

        # 若目标点本身是不可穿越实体，在目标周围寻找最近的可达空地
        if self.game_map.get_tile(goal_c, goal_r) in (TileType.STEEL, TileType.BASE):
            best_sub = None
            best_sub_d = 999999.0
            for dc, dr in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]:
                tc, tr = goal_c + dc, goal_r + dr
                if 0 <= tc < cols and 0 <= tr < rows:
                    if self.game_map.get_tile(tc, tr) not in (TileType.STEEL, TileType.BASE):
                        d = abs(tc - start_c) + abs(tr - start_r)
                        if d < best_sub_d:
                            best_sub_d = d
                            best_sub = (tc, tr)
            if best_sub:
                goal_c, goal_r = best_sub

        # A* 优先队列
        # 元素格式: (priority, current_cost, ammo_spent, col, row)
        pq: List[Tuple[float, float, int, int, int]] = []
        heapq.heappush(pq, (0.0, 0.0, 0, start_c, start_r))

        best_g: Dict[Tuple[int, int], float] = {(start_c, start_r): 0.0}
        parent: Dict[Tuple[int, int], Tuple[int, int]] = {}
        brick_count: Dict[Tuple[int, int], int] = {(start_c, start_r): 0}

        reached_goal = False

        while pq:
            _, g, ammo_spent, c, r = heapq.heappop(pq)

            if g > best_g.get((c, r), float('inf')):
                continue

            if c == goal_c and r == goal_r:
                reached_goal = True
                break

            # 四方向扩展
            for dc, dr in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                nc = c + dc
                nr = r + dr

                if not (0 <= nc < cols and 0 <= nr < rows):
                    continue

                tile = self.game_map.get_tile(nc, nr)

                # 铁墙不可穿透
                if tile in (TileType.STEEL, TileType.BASE):
                    continue

                # 基地核心仅允许作为终点
                if tile == TileType.BASE and (nc != goal_c or nr != goal_r):
                    continue

                step_cost = 1.0
                step_ammo = 0

                # 避开冲突单位所在的格子（赋予极高绕行代价，若存在空闲通道则优先绕道）
                if avoid_tiles and (nc, nr) in avoid_tiles:
                    if nc != goal_c or nr != goal_r:
                        step_cost += 60.0

                if tile == TileType.BRICK:
                    if getattr(tank, "can_crush_bricks", False):
                        # 具备碾压普通砖块能力（清障车）：只避让不能碾的方块，无视弹药限制直接碾碎通行
                        factor = max(0.1, getattr(tank, "crush_speed_factor", 0.5))
                        step_cost += (1.0 / factor - 1.0)
                        step_ammo = 0
                    else:
                        step_ammo = 1
                        if is_infinite_ammo:
                            # 无限弹药：轻微开火时间开销，鼓励破障
                            step_cost += self.BREACH_PENALTY_INFINITE
                        else:
                            # 有限弹药：弹药不足则无法破障
                            if ammo_spent + 1 > current_ammo:
                                continue
                            # 施加极高弹药惩罚，确保优先选择零耗弹绕行路线
                            step_cost += self.AMMO_PENALTY_LIMITED

                new_g = g + step_cost
                new_ammo = ammo_spent + step_ammo

                if new_g < best_g.get((nc, nr), float('inf')):
                    best_g[(nc, nr)] = new_g
                    parent[(nc, nr)] = (c, r)
                    brick_count[(nc, nr)] = new_ammo
                    # 曼哈顿启发函数
                    h = float(abs(nc - goal_c) + abs(nr - goal_r))
                    priority = new_g + h
                    heapq.heappush(pq, (priority, new_g, new_ammo, nc, nr))

        if not reached_goal:
            # 若目标不可达（如无解或弹药不足打通），寻找离目标最近的已探索节点
            if not parent:
                return [(dest_x, dest_y)], 0
            best_fallback = min(
                parent.keys(),
                key=lambda pos: abs(pos[0] - goal_c) + abs(pos[1] - goal_r)
            )
            curr = best_fallback
        else:
            curr = (goal_c, goal_r)

        # 重建路径
        grid_path = []
        while curr in parent:
            grid_path.append(curr)
            curr = parent[curr]
        grid_path.reverse()

        total_ammo = brick_count.get(grid_path[-1] if grid_path else (start_c, start_r), 0)

        # 转换为像素坐标列表
        pixel_path = []
        for gc, gr in grid_path:
            px = gc * tile_size
            py = gr * tile_size
            pixel_path.append((px, py))

        # 追加最终精确目的地
        if pixel_path:
            pixel_path.append((dest_x, dest_y))
        else:
            pixel_path = [(dest_x, dest_y)]

        return pixel_path, total_ammo
