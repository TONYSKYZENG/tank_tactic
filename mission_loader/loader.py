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

        fog_of_war = data.get("fog_of_war", True)
        limited_ammo = data.get("limited_ammo", True)

        # 1. 兼容单人 player 字段
        player_data = data.get("player", {})
        player_spawn = player_data.get("spawn", {"x": 6, "y": 14})
        single_player_info = PlayerMissionInfo(
            id=player_data.get("id", "player_alpha"),
            config_file=player_data.get("config_file", "tank_configs/player_tank.json"),
            spawn=SpawnPoint(x=player_spawn["x"], y=player_spawn["y"]),
            vision_size=float(player_data.get("vision_size", 288.0)),
            ammo=int(player_data.get("ammo", -1)),
            visibility=float(player_data.get("visibility", 1.0)),
            controllable=bool(player_data.get("controllable", True)),
            ai_script=player_data.get("ai_script", None)
        )

        # 2. 我方多车编队列表 player_units
        player_units = []
        if "player_units" in data:
            for p in data["player_units"]:
                pspawn = p.get("spawn", {"x": 0, "y": 0})
                player_units.append(PlayerMissionInfo(
                    id=p.get("id", f"player_{len(player_units)+1}"),
                    config_file=p.get("config_file", "tank_configs/player_tank.json"),
                    spawn=SpawnPoint(x=pspawn["x"], y=pspawn["y"]),
                    vision_size=float(p.get("vision_size", 288.0)),
                    ammo=int(p.get("ammo", -1)),
                    visibility=float(p.get("visibility", 1.0)),
                    controllable=bool(p.get("controllable", True)),
                    ai_script=p.get("ai_script", None)
                ))
        else:
            player_units = [single_player_info]

        # 3. 敌军列表 (含视线、弹药、辨识度与外挂战术脚本)
        enemies_info = []
        for e in data.get("enemies", []):
            espawn = e.get("spawn", {"x": 0, "y": 0})
            enemies_info.append(EnemyMissionInfo(
                id=e.get("id", f"enemy_{len(enemies_info)+1}"),
                config_file=e.get("config_file", "tank_configs/enemy_basic.json"),
                spawn=SpawnPoint(x=espawn["x"], y=espawn["y"]),
                tactic=e.get("tactic", "patrol"),
                vision_size=float(e.get("vision_size", 250.0)),
                ammo=int(e.get("ammo", -1)),
                visibility=float(e.get("visibility", 1.0)),
                controllable=bool(e.get("controllable", False)),
                ai_script=e.get("ai_script", None)
            ))

        return Mission(
            name=data.get("name", "Unnamed Mission"),
            map_file=data.get("map_file", "maps/level_01.json"),
            player=single_player_info,
            enemies=enemies_info,
            player_units=player_units,
            fog_of_war=fog_of_war,
            limited_ammo=limited_ammo,
            victory_conditions=data.get("victory_conditions", None),
            defeat_conditions=data.get("defeat_conditions", None)
        )
