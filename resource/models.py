import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from map_loader.models import GameMap, TileType

class ResourceType:
    DARK_MATTER = "dark_matter"
    ALLOY = "alloy"

    @classmethod
    def all_types(cls) -> List[str]:
        return [cls.DARK_MATTER, cls.ALLOY]


@dataclass
class ResourceBlockConfig:
    resource_type: str
    name: str
    tile_id: int = 3
    initial_amount: float = 100.0
    regen_rate: float = 1.0  # 每秒再生量
    max_amount: float = 1000.0
    harvest_radius: float = 64.0     # 可采集半径 (像素)
    exclusive_radius: float = 96.0   # 排他半径 (像素，无敌方在半径内方可采集)
    color: str = "#8E44AD"


@dataclass
class ResourceBlock:
    """地图上的实体资源块节点"""
    col: int
    row: int
    resource_type: str
    current_amount: float
    initial_amount: float
    regen_rate: float
    max_amount: float = 5000.0
    harvest_radius: float = 64.0
    exclusive_radius: float = 96.0

    def center(self, tile_size: int = 32) -> Tuple[float, float]:
        """返回资源块几何中心的世界像素坐标"""
        return ((self.col + 0.5) * tile_size, (self.row + 0.5) * tile_size)

    def is_in_harvest_range(self, tank: Any, tile_size: int = 32) -> bool:
        """判定目标单位是否处于该资源块的可采集半径内"""
        if not tank:
            return False
        cx, cy = self.center(tile_size)
        tx = tank.x + tank.size / 2.0
        ty = tank.y + tank.size / 2.0
        dist = math.hypot(tx - cx, ty - cy)
        return dist <= self.harvest_radius

    def is_exclusive(self, camp: Any, all_tanks: List[Any], tile_size: int = 32) -> bool:
        """
        核心排他判定：
        只有当排他半径 (exclusive_radius) 内【没有任何敌对存活单位】时，排他条件成立 (返回 True)
        若存在任何敌方战车踏入排他半径，则产生争夺阻滞 (返回 False)
        """
        cx, cy = self.center(tile_size)
        camp_val = camp.value if hasattr(camp, "value") else str(camp)

        for other in all_tanks:
            if not getattr(other, "alive", False):
                continue
            other_camp = other.camp.value if hasattr(other.camp, "value") else str(other.camp)
            if other_camp != camp_val:
                ox = other.x + other.size / 2.0
                oy = other.y + other.size / 2.0
                dist = math.hypot(ox - cx, oy - cy)
                if dist <= self.exclusive_radius:
                    return False
        return True

    def harvest(self, amount: float) -> float:
        """从资源块采集资源，返回实际开采量"""
        if amount <= 0:
            return 0.0
        actual = min(self.current_amount, float(amount))
        self.current_amount = max(0.0, self.current_amount - actual)
        return actual

    def update(self, dt: float) -> float:
        """
        更新资源块自身再生，返回本帧生成的资源增量
        """
        if self.regen_rate <= 0:
            return 0.0
        generated = self.regen_rate * dt
        self.current_amount = min(self.max_amount, self.current_amount + generated)
        return generated


class ResourceManager:
    """
    全战局双阵营经济资源管理器：
    - 管理双方阵营拥有的战略资源储备库 (stockpiles: player / enemy)
    - 绑定并管理地图上的所有资源块，随游戏主循环再生
    - 提供坦克单位开采 (harvest)、排他性判定与胜负判定接口
    """

    def __init__(self, initial_resources: Optional[Dict[str, float]] = None,
                 player_initial_resources: Optional[Dict[str, float]] = None,
                 enemy_initial_resources: Optional[Dict[str, float]] = None):
        p_init = player_initial_resources if player_initial_resources is not None else (initial_resources or {})
        e_init = enemy_initial_resources if enemy_initial_resources is not None else {}

        self.stockpiles: Dict[str, Dict[str, float]] = {
            "player": {
                ResourceType.DARK_MATTER: float(p_init.get(ResourceType.DARK_MATTER, 100.0)),
                ResourceType.ALLOY: float(p_init.get(ResourceType.ALLOY, 50.0))
            },
            "enemy": {
                ResourceType.DARK_MATTER: float(e_init.get(ResourceType.DARK_MATTER, 0.0)),
                ResourceType.ALLOY: float(e_init.get(ResourceType.ALLOY, 0.0))
            }
        }
        # 兼容自定义资源键
        for k, v in p_init.items():
            self.stockpiles["player"][k] = float(v)
        for k, v in e_init.items():
            self.stockpiles["enemy"][k] = float(v)

        self.blocks: List[ResourceBlock] = []
        self._block_configs: Dict[str, ResourceBlockConfig] = {}
        self._block_by_pos: Dict[Tuple[int, int], ResourceBlock] = {}
        self._current_harvest_rates: Dict[str, Dict[str, float]] = {
            "player": {ResourceType.DARK_MATTER: 0.0, ResourceType.ALLOY: 0.0},
            "enemy": {ResourceType.DARK_MATTER: 0.0, ResourceType.ALLOY: 0.0}
        }

    def _normalize_camp(self, camp: Any) -> str:
        if hasattr(camp, "value"):
            val = str(camp.value).lower()
        else:
            val = str(camp).lower()
        return "enemy" if "enemy" in val else "player"

    def register_block_config(self, config: ResourceBlockConfig) -> None:
        self._block_configs[config.resource_type] = config

    def init_from_map(self, game_map: GameMap, configs: Optional[Dict[str, ResourceBlockConfig]] = None) -> None:
        """从地图瓦片数据中动态解析并注册资源块（支持 JSON 配置中定义的自定义瓦片 ID）"""
        if configs:
            self._block_configs.update(configs)
        elif not self._block_configs:
            from .loader import ResourceLoader
            self._block_configs = ResourceLoader.load_configs()

        if not self._block_configs:
            self._block_configs = {
                ResourceType.DARK_MATTER: ResourceBlockConfig(ResourceType.DARK_MATTER, "Dark Matter", tile_id=3, initial_amount=500.0, regen_rate=2.0),
                ResourceType.ALLOY: ResourceBlockConfig(ResourceType.ALLOY, "Alloy", tile_id=4, initial_amount=300.0, regen_rate=1.0)
            }

        self.blocks.clear()
        self._block_by_pos.clear()

        # 构建 tile_id -> ResourceBlockConfig 动态映射
        tile_to_cfg: Dict[int, ResourceBlockConfig] = {}
        for cfg in self._block_configs.values():
            tile_to_cfg[cfg.tile_id] = cfg

        # 兜底默认枚举
        if TileType.DARK_MATTER not in tile_to_cfg and ResourceType.DARK_MATTER in self._block_configs:
            tile_to_cfg[TileType.DARK_MATTER] = self._block_configs[ResourceType.DARK_MATTER]
        if TileType.ALLOY not in tile_to_cfg and ResourceType.ALLOY in self._block_configs:
            tile_to_cfg[TileType.ALLOY] = self._block_configs[ResourceType.ALLOY]

        for r in range(game_map.rows):
            for c in range(game_map.cols):
                tile = game_map.get_tile(c, r)
                if tile in tile_to_cfg:
                    cfg = tile_to_cfg[tile]
                    block = ResourceBlock(
                        col=c,
                        row=r,
                        resource_type=cfg.resource_type,
                        current_amount=cfg.initial_amount,
                        initial_amount=cfg.initial_amount,
                        regen_rate=cfg.regen_rate,
                        max_amount=cfg.max_amount,
                        harvest_radius=cfg.harvest_radius,
                        exclusive_radius=cfg.exclusive_radius
                    )
                    self.blocks.append(block)
                    self._block_by_pos[(c, r)] = block

    def get_block_at(self, col: int, row: int) -> Optional[ResourceBlock]:
        return self._block_by_pos.get((col, row))

    def update(self, dt: float) -> None:
        """主循环推进地图实体资源块再生"""
        for block in self.blocks:
            block.update(dt)

    def update_harvest(self, tanks: List[Any], dt: float, tile_size: int = 32) -> Dict[str, float]:
        """
        主循环推进坦克单位对资源块的开采逻辑：
        1. 检查单位是否存活且下达了 is_harvesting 状态
        2. 校验目标资源块存在性与可采集半径 (harvest_radius)
        3. 核心排他判定：校验排他半径 (exclusive_radius) 内是否有敌方单位，只有排他时方可采集
        4. 结算开采量，存入对应阵营 (player / enemy) 的战略资源库
        """
        harvested_summary: Dict[str, float] = {}
        current_rates: Dict[str, Dict[str, float]] = {
            "player": {ResourceType.DARK_MATTER: 0.0, ResourceType.ALLOY: 0.0},
            "enemy": {ResourceType.DARK_MATTER: 0.0, ResourceType.ALLOY: 0.0}
        }

        for tank in tanks:
            if not getattr(tank, "alive", False) or not getattr(tank, "is_harvesting", False):
                continue
            target = getattr(tank, "harvest_target", None)
            if not target:
                continue

            col, row = target
            block = self.get_block_at(col, row)
            if not block:
                tank.harvest_state = "invalid_target"
                continue

            # 1. 距离校验
            if not block.is_in_harvest_range(tank, tile_size):
                tank.harvest_state = "out_of_range"
                continue

            # 2. 排他性校验：只有排他的时候可以采集
            if not block.is_exclusive(tank.camp, tanks, tile_size):
                tank.harvest_state = "contested"  # 敌军进入排他半径，被争夺阻滞
                continue

            # 3. 正常开采
            if block.current_amount <= 0:
                tank.harvest_state = "depleted"
                continue

            tank.harvest_state = "harvesting"
            speeds = getattr(tank, "harvest_speed", {}) or {}
            speed = speeds.get(block.resource_type, speeds.get("default", 2.0))
            to_harvest = speed * dt
            actual = block.harvest(to_harvest)

            camp_key = self._normalize_camp(tank.camp)
            self.add_resource(block.resource_type, actual, camp=camp_key)
            harvested_summary[block.resource_type] = harvested_summary.get(block.resource_type, 0.0) + actual

            if actual > 0:
                current_rates[camp_key][block.resource_type] = current_rates[camp_key].get(block.resource_type, 0.0) + speed

            if block.current_amount <= 0:
                tank.harvest_state = "depleted"

        self._current_harvest_rates = current_rates
        return harvested_summary

    def get_amount(self, resource_type: str, camp: Any = "player") -> float:
        camp_key = self._normalize_camp(camp)
        return self.stockpiles.get(camp_key, {}).get(resource_type, 0.0)

    def get_all_resources(self, camp: Any = "player") -> Dict[str, float]:
        camp_key = self._normalize_camp(camp)
        return dict(self.stockpiles.get(camp_key, {}))

    def get_both_stockpiles(self) -> Dict[str, Dict[str, float]]:
        return {
            "player": dict(self.stockpiles.get("player", {})),
            "enemy": dict(self.stockpiles.get("enemy", {}))
        }

    def get_harvest_rates(self, camp: Any = "player") -> Dict[str, float]:
        """获取指定阵营当前的实际开采流入速率 (每秒)"""
        camp_key = self._normalize_camp(camp)
        return dict(self._current_harvest_rates.get(camp_key, {}))

    def get_block_regen_rates(self) -> Dict[str, float]:
        """计算当前地图所有实体资源块自身的自然再生总速率 (每秒)"""
        rates: Dict[str, float] = {}
        for block in self.blocks:
            rates[block.resource_type] = rates.get(block.resource_type, 0.0) + block.regen_rate
        return rates

    def get_rates(self, camp: Optional[Any] = None) -> Dict[str, float]:
        """
        若指定阵营，返回该阵营实际开采流入速率 (每秒)；
        缺省时兼容旧接口，返回地图所有实体资源块自身的自然再生总速率。
        """
        if camp is not None:
            return self.get_harvest_rates(camp)
        return self.get_block_regen_rates()

    def has_enough(self, costs: Dict[str, float], camp: Any = "player") -> bool:
        camp_key = self._normalize_camp(camp)
        for res_type, cost in costs.items():
            if self.get_amount(res_type, camp=camp_key) < cost:
                return False
        return True

    def consume(self, costs: Dict[str, float], camp: Any = "player") -> bool:
        camp_key = self._normalize_camp(camp)
        if not self.has_enough(costs, camp=camp_key):
            return False
        for res_type, cost in costs.items():
            current = self.stockpiles[camp_key].get(res_type, 0.0)
            self.stockpiles[camp_key][res_type] = max(0.0, current - cost)
        return True

    def add_resource(self, resource_type: str, amount: float, camp: Any = "player") -> None:
        amt = float(amount)
        if amt > 0:
            camp_key = self._normalize_camp(camp)
            current = self.stockpiles[camp_key].get(resource_type, 0.0)
            self.stockpiles[camp_key][resource_type] = current + amt

    def add_resources(self, rewards: Dict[str, float], camp: Any = "player") -> None:
        for res_type, amt in rewards.items():
            self.add_resource(res_type, amt, camp=camp)
