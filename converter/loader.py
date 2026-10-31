import json
from pathlib import Path
from typing import Dict, Optional, List
from .models import ConverterRecipe

class RecipeRegistry:
    """配方全量注册表，从 converter/ 目录读取并缓存所有配方 JSON"""
    _recipes: Dict[str, ConverterRecipe] = {}

    @classmethod
    def load_recipes(cls, recipe_dir: Optional[Path or str] = None) -> Dict[str, ConverterRecipe]:
        if recipe_dir is None:
            recipe_dir = Path(__file__).parent
        else:
            recipe_dir = Path(recipe_dir)

        cls._recipes.clear()
        if not recipe_dir.exists():
            return cls._recipes

        for json_path in recipe_dir.glob("recipe_*.json"):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                r_id = data.get("id", json_path.stem)
                outputs = data.get("outputs", {})
                output_type = data.get("output_type", "resource")
                if outputs == "tank" or (isinstance(outputs, dict) and "tank" in outputs):
                    output_type = "tank"

                recipe = ConverterRecipe(
                    id=r_id,
                    name=data.get("name", r_id),
                    inputs=data.get("inputs", {}),
                    outputs=outputs,
                    duration=float(data.get("duration", 4.0)),
                    output_type=output_type,
                    tank_config=data.get("tank_config", None),
                    visibility=float(data.get("visibility", 1.0)),
                    vision_size=float(data.get("vision_size", 280.0)),
                    ammo=int(data.get("ammo", -1))
                )
                cls._recipes[r_id] = recipe
            except Exception as e:
                print(f"[RecipeRegistry] Failed to load {json_path}: {e}")

        return cls._recipes

    @classmethod
    def get(cls, recipe_id: str) -> Optional[ConverterRecipe]:
        if not cls._recipes:
            cls.load_recipes()
        return cls._recipes.get(recipe_id)

    @classmethod
    def get_all(cls) -> Dict[str, ConverterRecipe]:
        if not cls._recipes:
            cls.load_recipes()
        return dict(cls._recipes)
