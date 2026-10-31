import json
from pathlib import Path
from dataclasses import dataclass

@dataclass
class TankConfig:
    name: str = "Classic Tank"
    speed: float = 3.0
    size: int = 36
    color: str = "#E69C24"
    track_color: str = "#4A6B2F"
    bullet_speed: float = 6.0
    bullet_size: int = 12
    bullet_color: str = "#FFFFFF"
    fire_cooldown: int = 15
    health: int = 3
    # ===== 防御塔专属扩展属性 =====
    is_tower: bool = False             # 是否为防御塔 (固定不可移动)
    can_attack: bool = True           # 是否具备攻击炮台
    tower_type: str = "general"       # 类型: "radar"(纯雷达视野), "cannon"(重型炮台), "supply"(弹药补给要塞)
    resupply_radius: float = 0.0      # 弹药补给有效半径 (像素)
    resupply_interval: int = 30       # 补充弹药的时间间隔 (帧数，30 帧约 0.5 秒)

    @classmethod
    def from_json(cls, file_path: str or Path) -> "TankConfig":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    def to_json(self, file_path: str or Path) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=2, ensure_ascii=False)
