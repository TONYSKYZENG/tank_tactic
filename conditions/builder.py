from typing import Any, Dict, Union, List
from physics.entities import Rect
from conditions.primitives import (
    BaseCondition,
    UnitSurviveTimeCondition,
    UnitDestroyedCondition,
    AreaVisibleCondition,
    AllEnemiesDestroyedCondition,
    AllPlayersDestroyedCondition,
    ResourceAmountCondition
)
from conditions.composite import (
    AndCondition,
    OrCondition,
    NotCondition,
    ConstantCondition
)

class ConditionBuilder:
    """胜负条件解析构建器，支持与/或/非树状递归结构解析"""

    @classmethod
    def build(cls, config: Any) -> BaseCondition:
        if config is None:
            return ConstantCondition(False, "无条件")

        # 如果顶层是列表，默认视为 AND 组合
        if isinstance(config, list):
            sub_conds = [cls.build(item) for item in config]
            return AndCondition(sub_conds)

        # 字符串快捷语法
        if isinstance(config, str):
            c_str = config.lower().strip()
            if c_str == "all_enemies_destroyed":
                return AllEnemiesDestroyedCondition()
            elif c_str == "all_players_destroyed":
                return AllPlayersDestroyedCondition()
            elif c_str in ("true", "always"):
                return ConstantCondition(True, "总是达成")
            elif c_str in ("false", "never"):
                return ConstantCondition(False, "从不达成")
            raise ValueError(f"未知的条件字符串表达式: {config}")

        if not isinstance(config, dict):
            raise ValueError(f"条件配置格式错误，必须为 dict, list 或 str，得到: {type(config)}")

        # 检查快捷键格式：如 {"and": [...]}, {"or": [...]}, {"not": {...}}
        if "and" in config:
            sub_items = config["and"]
            if not isinstance(sub_items, list):
                sub_items = [sub_items]
            return AndCondition([cls.build(item) for item in sub_items])

        if "or" in config:
            sub_items = config["or"]
            if not isinstance(sub_items, list):
                sub_items = [sub_items]
            return OrCondition([cls.build(item) for item in sub_items])

        if "not" in config:
            return NotCondition(cls.build(config["not"]))

        # 检查 type 字段
        cond_type = config.get("type", "").lower()

        if cond_type == "and":
            children = config.get("conditions", [])
            return AndCondition([cls.build(c) for c in children])

        elif cond_type == "or":
            children = config.get("conditions", [])
            return OrCondition([cls.build(c) for c in children])

        elif cond_type == "not":
            child = config.get("condition") or config.get("conditions")
            if isinstance(child, list):
                # not 里面如果是列表，默认为 not (and(c1, c2))
                child = AndCondition([cls.build(c) for c in child])
            else:
                child = cls.build(child)
            return NotCondition(child)

        # 原语1: unit_survive_time
        elif cond_type in ("unit_survive_time", "survive_time"):
            unit_id = str(config.get("unit_id", ""))
            seconds = float(config.get("seconds", config.get("time", 0.0)))
            return UnitSurviveTimeCondition(unit_id, seconds)

        # 原语2: unit_destroyed
        elif cond_type in ("unit_destroyed", "unit_dead", "unit_kill"):
            unit_id = str(config.get("unit_id", ""))
            return UnitDestroyedCondition(unit_id)

        # 原语3: area_visible
        elif cond_type in ("area_visible", "scout_area", "area_scouted"):
            rect = cls._parse_rect(config)
            return AreaVisibleCondition(rect)

        # 经济原语: resource_amount
        elif cond_type in ("resource_amount", "resource", "has_resource"):
            res_type = str(config.get("resource_type", config.get("resource", "dark_matter")))
            amt = float(config.get("amount", config.get("count", 100.0)))
            camp = str(config.get("camp", "player"))
            return ResourceAmountCondition(res_type, amt, camp=camp)

        # 扩展通用原语
        elif cond_type == "all_enemies_destroyed":
            return AllEnemiesDestroyedCondition()

        elif cond_type == "all_players_destroyed":
            return AllPlayersDestroyedCondition()

        elif cond_type == "constant":
            val = bool(config.get("value", True))
            desc = config.get("description", "")
            return ConstantCondition(val, desc)

        else:
            raise ValueError(f"未知的条件类型: '{cond_type}' 在配置: {config}")

    @classmethod
    def _parse_rect(cls, config: Dict[str, Any]) -> Rect:
        """从字典或列表解析出目标 Rect"""
        # 支持 {"area": [x, y, w, h]}
        if "area" in config:
            area_val = config["area"]
            if isinstance(area_val, (list, tuple)) and len(area_val) >= 4:
                return Rect(float(area_val[0]), float(area_val[1]), float(area_val[2]), float(area_val[3]))
            elif isinstance(area_val, dict):
                return cls._rect_from_dict(area_val)

        # 支持 {"x": 100, "y": 100, "width": 50, "height": 50}
        if "x" in config and "y" in config:
            return cls._rect_from_dict(config)

        # 支持网格瓦片坐标 {"tile_x": 5, "tile_y": 5, "tile_w": 2, "tile_h": 2} (32px每格)
        if "tile_x" in config and "tile_y" in config:
            tx = float(config["tile_x"]) * 32.0
            ty = float(config["tile_y"]) * 32.0
            tw = float(config.get("tile_w", 1)) * 32.0
            th = float(config.get("tile_h", 1)) * 32.0
            return Rect(tx, ty, tw, th)

        raise ValueError(f"无法解析目标区域 Rect，配置为: {config}")

    @staticmethod
    def _rect_from_dict(d: Dict[str, Any]) -> Rect:
        x = float(d.get("x", 0.0))
        y = float(d.get("y", 0.0))
        w = float(d.get("width", d.get("w", 32.0)))
        h = float(d.get("height", d.get("h", 32.0)))
        return Rect(x, y, w, h)
