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

    @classmethod
    def from_json(cls, file_path: str or Path) -> "TankConfig":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    def to_json(self, file_path: str or Path) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=2, ensure_ascii=False)
