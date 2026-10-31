from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class SpawnPoint:
    x: int  # 瓦片列号 (col)
    y: int  # 瓦片行号 (row)

@dataclass
class PlayerMissionInfo:
    config_file: str
    spawn: SpawnPoint
    id: str = "player_1"
    vision_size: float = 280.0  # 视线正方形边长，-1 为全图视野
    ammo: int = -1              # 弹药数量，-1 为无限弹药
    visibility: float = 1.0     # 辨识度：1.0 永远可见，0.0~1.0 每 tick/查询 发现概率

@dataclass
class EnemyMissionInfo:
    id: str
    config_file: str
    spawn: SpawnPoint
    tactic: str = "patrol"
    vision_size: float = 250.0  # 视线正方形边长，-1 为全图视野
    ammo: int = -1              # 弹药数量，-1 为无限弹药
    visibility: float = 1.0     # 辨识度：1.0 永远可见，0.0~1.0 每 tick 侦测概率

@dataclass
class Mission:
    name: str
    map_file: str
    player: PlayerMissionInfo
    enemies: List[EnemyMissionInfo]
    player_units: List[PlayerMissionInfo] = field(default_factory=list)
    fog_of_war: bool = True     # 是否启用战争迷雾系统
    limited_ammo: bool = True   # 是否启用有限弹药系统
    victory_conditions: Optional[Any] = None  # 获胜条件表达式（支持与或非及原语）
    defeat_conditions: Optional[Any] = None   # 失败条件表达式（支持与或非及原语）
