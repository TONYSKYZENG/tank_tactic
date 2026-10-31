import json
from pathlib import Path
from .models import Mission, PlayerMissionInfo, EnemyMissionInfo, SpawnPoint

class MissionLoader:
    @staticmethod
    def load_from_file(file_path: str or Path) -> Mission:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Mission file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        player_data = data.get("player", {})
        player_spawn = player_data.get("spawn", {"x": 0, "y": 0})
        player_info = PlayerMissionInfo(
            config_file=player_data.get("config_file", "tank_configs/player_tank.json"),
            spawn=SpawnPoint(x=player_spawn["x"], y=player_spawn["y"])
        )

        enemies_info = []
        for e in data.get("enemies", []):
            espawn = e.get("spawn", {"x": 0, "y": 0})
            enemies_info.append(EnemyMissionInfo(
                id=e.get("id", "enemy"),
                config_file=e.get("config_file", "tank_configs/enemy_basic.json"),
                spawn=SpawnPoint(x=espawn["x"], y=espawn["y"]),
                tactic=e.get("tactic", "patrol")
            ))

        return Mission(
            name=data.get("name", "Unnamed Mission"),
            map_file=data.get("map_file", "maps/level_01.json"),
            player=player_info,
            enemies=enemies_info
        )
