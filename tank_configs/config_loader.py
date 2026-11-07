import json
from pathlib import Path
from dataclasses import dataclass, field

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
    # ===== 清障车/破障能力属性 =====
    can_crush_bricks: bool = False     # 允许无视普通砖块直接碾压过去
    crush_speed_factor: float = 0.5    # 碾压普通砖块时的速度衰减系数 (如 0.5 表示移速降低为 50%)
    # ===== 资源转换机与采集属性 =====
    converter_table: list = field(default_factory=list)  # 支持的转换配方 ID 列表
    harvest_speed: dict = field(default_factory=lambda: {"dark_matter": 2.0, "alloy": 1.5})  # 各类资源采集速度 (单位/秒)
    # ===== 战斗机制属性：命中精度、闪避、范围伤害与友军误伤、有效射程 =====
    accuracy: float = 1.0              # 瞄准精度 p (0.0~1.0)，默认 1.0
    dodge: float = 0.0                 # 闪避率 q (0.0~1.0)，默认 0.0
    splash_radius: float = 0.0         # 范围伤害半径 (像素)，<=0 或 -1 代表不启用范围伤害，>0 启用
    friendly_fire: int = 0             # 是否伤害范围内友军：0 为不伤害友军，1 为伤害友军
    attack_range: float = 240.0        # 默认有效攻击射程 (像素)，进入射程后即停止前进原地开火

    @classmethod
    def from_json(cls, file_path: str or Path) -> "TankConfig":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "converter_table" not in data:
            data["converter_table"] = []
        if "harvest_speed" not in data:
            data["harvest_speed"] = {"dark_matter": 2.0, "alloy": 1.5}
        # 兼容只传入定义字段
        from dataclasses import fields as dc_fields
        field_names = {f.name for f in dc_fields(cls)}
        known_data = {k: v for k, v in data.items() if k in field_names}
        instance = cls(**known_data)
        # 允许实例挂载额外的任意动态属性
        for k, v in data.items():
            if k not in field_names:
                setattr(instance, k, v)
        return instance

    def to_json(self, file_path: str or Path) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=2, ensure_ascii=False)
