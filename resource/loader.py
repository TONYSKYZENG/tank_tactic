import json
from pathlib import Path
from typing import Dict, Optional
from .models import ResourceBlockConfig, ResourceType

class ResourceLoader:
    @staticmethod
    def load_configs(resource_dir: Optional[Path or str] = None) -> Dict[str, ResourceBlockConfig]:
        """从 resource/ 目录读取所有资源块配置 JSON"""
        if resource_dir is None:
            resource_dir = Path(__file__).parent
        else:
            resource_dir = Path(resource_dir)

        configs: Dict[str, ResourceBlockConfig] = {}
        if not resource_dir.exists():
            return configs

        for json_path in resource_dir.glob("*.json"):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                r_type = data.get("resource_type", json_path.stem)
                default_tile_id = 3 if r_type == ResourceType.DARK_MATTER else 4
                cfg = ResourceBlockConfig(
                    resource_type=r_type,
                    name=data.get("name", r_type),
                    tile_id=int(data.get("tile_id", default_tile_id)),
                    initial_amount=float(data.get("initial_amount", 100.0)),
                    regen_rate=float(data.get("regen_rate", 1.0)),
                    max_amount=float(data.get("max_amount", 5000.0)),
                    harvest_radius=float(data.get("harvest_radius", 64.0)),
                    exclusive_radius=float(data.get("exclusive_radius", 96.0)),
                    color=data.get("color", "#8E44AD")
                )
                configs[r_type] = cfg
            except Exception as e:
                print(f"[ResourceLoader] Failed to load {json_path}: {e}")

        return configs
