from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class SpawnPoint:
    x: int  # 瓦片列号 (col)
    y: int  # 瓦片行号 (row)

@dataclass
class PlayerMissionInfo:
    config_file: str
    spawn: SpawnPoint

@dataclass
class EnemyMissionInfo:
    id: str
    config_file: str
    spawn: SpawnPoint
    tactic: str  # e.g. "patrol", "charge_base", "hunter"

@dataclass
class Mission:
    name: str
    map_file: str
    player: PlayerMissionInfo
    enemies: List[EnemyMissionInfo]
