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
    SQRT2 = math.sqrt(2.0)

    # 八方向扩展: (dc, dr, base_cost)
    DIRS_8 = [
        (0, -1, 1.0), (0, 1, 1.0), (-1, 0, 1.0), (1, 0, 1.0),
        (-1, -1, SQRT2), (-1, 1, SQRT2), (1, -1, SQRT2), (1, 1, SQRT2),
    ]

    def __init__(self, game_map: GameMap):
        self.game_map = game_map

    def _is_oversized_blocked_at(self, px: float, py: float, tank_size: float) -> bool:
        """检查尺寸大于单格的大型单位在 (px, py) 是否会刮蹭不可摧毁的铁墙/基地或越界"""
        map_w = self.game_map.pixel_width
        map_h = self.game_map.pixel_height
        if px < 0 or px + tank_size > map_w or py < 0 or py + tank_size > map_h:
            return True
        tile_size = self.game_map.tile_size
        margin = 0.5
        rx1 = px + margin
        ry1 = py + margin
        rx2 = px + tank_size - margin
        ry2 = py + tank_size - margin
        c0 = max(0, int(rx1 // tile_size))
        c1 = min(self.game_map.cols - 1, int((rx2 - 0.001) // tile_size))
        r0 = max(0, int(ry1 // tile_size))
        r1 = min(self.game_map.rows - 1, int((ry2 - 0.001) // tile_size))
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if self.game_map.get_tile(c, r) in (TileType.STEEL, TileType.BASE):
                    return True
        return False

    def is_segment_passable(self, x1: float, y1: float, x2: float, y2: float,
                            tank: Optional[Tank] = None,
                            avoid_tiles: Optional[Set[Tuple[int, int]]] = None) -> bool:
        """
        检测坦克从 (x1, y1) 沿任意角度斜线直达 (x2, y2) 的扫掠包围盒通道是否完全畅通：
        - 沿途不触碰任何阻挡瓦片与待回避动态单位网格
        - 保障斜向拉直后的路径在实际物理移动中 100% 不卡墙角
        """
        tile_size = self.game_map.tile_size
        tank_size = float(tank.size) if tank is not None else float(tile_size)
        blocks = (TileType.BRICK, TileType.STEEL, TileType.BASE)

        dist = math.hypot(x2 - x1, y2 - y1)
        if dist < 1e-4:
            return True

        start_c = int(round(x1 / tile_size))
        start_r = int(round(y1 / tile_size))
        goal_c = int(round(x2 / tile_size))
        goal_r = int(round(y2 / tile_size))

        step_len = min(3.0, tile_size * 0.12)
        steps = max(1, int(math.ceil(dist / step_len)))
        margin = 0.45
        eff_w = max(1.0, tank_size - margin * 2.0)

        map_w = self.game_map.pixel_width
        map_h = self.game_map.pixel_height

        for i in range(1, steps + 1):
            t = i / float(steps)
            px = x1 + (x2 - x1) * t
            py = y1 + (y2 - y1) * t

            if px < 0 or px + tank_size > map_w or py < 0 or py + tank_size > map_h:
                return False

            rx1 = px + margin
            ry1 = py + margin
            rx2 = rx1 + eff_w
            ry2 = ry1 + eff_w

            col_start = max(0, int(rx1 // tile_size))
            col_end = min(self.game_map.cols - 1, int((rx2 - 0.001) // tile_size))
            row_start = max(0, int(ry1 // tile_size))
            row_end = min(self.game_map.rows - 1, int((ry2 - 0.001) // tile_size))

            for r in range(row_start, row_end + 1):
                for c in range(col_start, col_end + 1):
                    tile = self.game_map.get_tile(c, r)
                    if tile in blocks:
                        return False
                    if avoid_tiles and (c, r) in avoid_tiles:
                        if (c, r) != (start_c, start_r) and (c, r) != (goal_c, goal_r):
                            return False
        return True

    def _smooth_path(self, start_x: float, start_y: float,
                     grid_path: List[Tuple[int, int]],
                     dest_x: float, dest_y: float,
                     tank: Optional[Tank] = None,
                     avoid_tiles: Optional[Set[Tuple[int, int]]] = None) -> List[Tuple[float, float]]:
        """
        任意角度视线拉直平滑 (Any-Angle String Pulling)：
        - 将 A* 网格折线压缩为最少拐点的斜向直达航点序列；
        - 保留必须开火破障的砖块锚点（确保正交对准开火破墙）；
        - 对所有无障碍区间直接拉直为斜线航点，彻底消除“先横再竖/先竖再横”现象。
        """
        tile_size = self.game_map.tile_size
        can_crush = getattr(tank, "can_crush_bricks", False) if tank is not None else False

        raw_pts: List[Tuple[float, float]] = [(start_x, start_y)]
        protected_indices: Set[int] = set()

        for gc, gr in grid_path:
            px = float(gc * tile_size)
            py = float(gr * tile_size)
            if math.hypot(px - raw_pts[-1][0], py - raw_pts[-1][1]) > 0.5:
                raw_pts.append((px, py))
                idx = len(raw_pts) - 1
                if self.game_map.get_tile(gc, gr) == TileType.BRICK and not can_crush:
                    protected_indices.add(max(0, idx - 1))
                    protected_indices.add(idx)
                    protected_indices.add(idx + 1)

        if math.hypot(dest_x - raw_pts[-1][0], dest_y - raw_pts[-1][1]) > 0.5:
            raw_pts.append((dest_x, dest_y))
        else:
            raw_pts[-1] = (dest_x, dest_y)

        if len(raw_pts) <= 2:
            return [raw_pts[-1]]

        smoothed: List[Tuple[float, float]] = []
        curr_idx = 0
        n = len(raw_pts)

        while curr_idx < n - 1:
            next_idx = curr_idx + 1
            for cand_idx in range(n - 1, curr_idx + 1, -1):
                # 若中间包含待开火破障锚点，禁止跨越该砖块锚点拉直
                has_protected = any(m in protected_indices for m in range(curr_idx + 1, cand_idx))
                if has_protected:
                    continue
                if self.is_segment_passable(
                    raw_pts[curr_idx][0], raw_pts[curr_idx][1],
                    raw_pts[cand_idx][0], raw_pts[cand_idx][1],
                    tank=tank, avoid_tiles=avoid_tiles
                ):
                    next_idx = cand_idx
                    break
            smoothed.append(raw_pts[next_idx])
            curr_idx = next_idx

        return smoothed if smoothed else [(dest_x, dest_y)]

    def find_path(self, start_x: float, start_y: float,
                  dest_x: float, dest_y: float,
                  tank: Optional[Tank] = None,
                  limited_ammo_enabled: bool = True,
                  avoid_tiles: Optional[Set[Tuple[int, int]]] = None) -> Tuple[List[Tuple[float, float]], int]:
        """
        计算最优通行路径与需摧毁的障碍数（支持八方向扩展 + 任意角度斜向视线拉直）
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

        # 快速通道：若起点到终点直线通道完全畅通无阻，直接斜线直达终点
        if self.is_segment_passable(start_x, start_y, dest_x, dest_y, tank=tank, avoid_tiles=avoid_tiles):
            return [(dest_x, dest_y)], 0

        # 判断是否为无限弹药模式
        is_infinite_ammo = True
        current_ammo = 999999
        if tank is not None and limited_ammo_enabled:
            if tank.ammo >= 0:
                is_infinite_ammo = False
                current_ammo = tank.ammo

        can_crush = getattr(tank, "can_crush_bricks", False) if tank is not None else False
        is_oversized = (tank is not None and tank.size > tile_size + 1)

        # 若目标点本身是不可穿越实体，在目标周围寻找最近的可达空地
        if self.game_map.get_tile(goal_c, goal_r) in (TileType.STEEL, TileType.BASE):
            best_sub = None
            best_sub_d = 999999.0
            for dc, dr in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]:
                tc, tr = goal_c + dc, goal_r + dr
                if 0 <= tc < cols and 0 <= tr < rows:
                    if self.game_map.get_tile(tc, tr) not in (TileType.STEEL, TileType.BASE):
                        d = math.hypot(tc - start_c, tr - start_r)
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

            # 八方向扩展 (四正交 + 四对角)
            for dc, dr, base_cost in self.DIRS_8:
                nc = c + dc
                nr = r + dr

                if not (0 <= nc < cols and 0 <= nr < rows):
                    continue

                tile = self.game_map.get_tile(nc, nr)

                # 铁墙与非终点基地不可穿透
                if tile in (TileType.STEEL, TileType.BASE):
                    continue

                # 对角线移动防切角碰撞检查：两侧正交相邻格必须同时畅通无阻
                if dc != 0 and dr != 0:
                    tile_h = self.game_map.get_tile(c + dc, r)
                    tile_v = self.game_map.get_tile(c, r + dr)
                    if tile in (TileType.STEEL, TileType.BASE, TileType.BRICK):
                        continue
                    if tile_h in (TileType.STEEL, TileType.BASE, TileType.BRICK):
                        continue
                    if tile_v in (TileType.STEEL, TileType.BASE, TileType.BRICK):
                        continue
                    if avoid_tiles and ((c + dc, r) in avoid_tiles or (c, r + dr) in avoid_tiles):
                        continue

                # 超大体型单位（如 MCV）防卡墙检查
                if is_oversized and (nc, nr) != (goal_c, goal_r):
                    if self._is_oversized_blocked_at(nc * tile_size, nr * tile_size, tank.size):
                        continue

                step_cost = base_cost
                step_ammo = 0

                # 避开冲突单位所在的格子（赋予极高绕行代价，若存在空闲通道则优先绕道）
                if avoid_tiles and (nc, nr) in avoid_tiles:
                    if nc != goal_c or nr != goal_r:
                        step_cost += 60.0

                if tile == TileType.BRICK:
                    if can_crush:
                        # 具备碾压普通砖块能力（清障车）：只避让不能碾的方块，无视弹药限制直接碾碎通行
                        factor = max(0.1, getattr(tank, "crush_speed_factor", 0.5))
                        step_cost += base_cost * (1.0 / factor - 1.0)
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
                    # 八方向 Octile 启发函数
                    dx_g = abs(nc - goal_c)
                    dy_g = abs(nr - goal_r)
                    h = (dx_g + dy_g) + (self.SQRT2 - 2.0) * min(dx_g, dy_g)
                    priority = new_g + h * 1.0001
                    heapq.heappush(pq, (priority, new_g, new_ammo, nc, nr))

        if not reached_goal:
            # 若目标不可达（如无解或弹药不足打通），寻找离目标最近的已探索节点
            if not parent:
                return [(dest_x, dest_y)], 0
            best_fallback = min(
                parent.keys(),
                key=lambda pos: math.hypot(pos[0] - goal_c, pos[1] - goal_r)
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

        # 使用任意角度视线拉直平滑路径，生成直接斜向航点
        final_dest_x = dest_x if reached_goal else float(grid_path[-1][0] * tile_size if grid_path else dest_x)
        final_dest_y = dest_y if reached_goal else float(grid_path[-1][1] * tile_size if grid_path else dest_y)
        pixel_path = self._smooth_path(
            start_x, start_y, grid_path, final_dest_x, final_dest_y,
            tank=tank, avoid_tiles=avoid_tiles
        )

        return pixel_path, total_ammo
