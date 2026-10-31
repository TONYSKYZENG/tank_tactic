import json
from pathlib import Path
from .models import GameMap, TileType

class MapLoader:
    @staticmethod
    def load_from_file(file_path: str or Path) -> GameMap:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Map file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        name = data.get("name", "Unknown Map")
        tile_size = data.get("tile_size", 36)
        cols = data.get("cols", len(data.get("grid", [[]])[0]))
        rows = data.get("rows", len(data.get("grid", [])))
        grid = data.get("grid", [])

        copied_grid = [row[:] for row in grid]

        return GameMap(
            name=name,
            tile_size=tile_size,
            cols=cols,
            rows=rows,
            grid=copied_grid
        )

    @staticmethod
    def save_to_file(game_map: GameMap, file_path: str or Path) -> None:
        path = Path(file_path)
        data = {
            "name": game_map.name,
            "tile_size": game_map.tile_size,
            "cols": game_map.cols,
            "rows": game_map.rows,
            "grid": game_map.grid
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
