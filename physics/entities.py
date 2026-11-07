import math
from enum import Enum
from dataclasses import dataclass
from typing import Tuple, List, Optional, Any, Dict

class Direction(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    @property
    def dx(self) -> int:
        return self.value[0]

    @property
    def dy(self) -> int:
        return self.value[1]

    @classmethod
    def all_directions(cls) -> List["Direction"]:
        return [cls.UP, cls.DOWN, cls.LEFT, cls.RIGHT]

    @classmethod
    def from_angle(cls, angle_deg: float) -> "Direction":
        """将自由角度映射到最近的四向正交枚举"""
        deg = float(angle_deg) % 360.0
        if 45.0 <= deg < 135.0:
            return cls.RIGHT
        elif 135.0 <= deg < 225.0:
            return cls.DOWN
        elif 225.0 <= deg < 315.0:
            return cls.LEFT
        else:
            return cls.UP

    @classmethod
    def from_vector(cls, dx: float, dy: float) -> "Direction":
        if abs(dx) < 1e-5 and abs(dy) < 1e-5:
            return cls.UP
        angle_deg = math.degrees(math.atan2(dx, -dy)) % 360.0
        return cls.from_angle(angle_deg)

    def to_angle(self) -> float:
        if self == Direction.UP:
            return 0.0
        elif self == Direction.RIGHT:
            return 90.0
        elif self == Direction.DOWN:
            return 180.0
        elif self == Direction.LEFT:
            return 270.0
        return 0.0


class Camp(Enum):
    PLAYER = "player"
    ENEMY = "enemy"


@dataclass
class Rect:
    x: float
    y: float
    width: float
    height: float

    def collides_with(self, other: "Rect") -> bool:
        return (
            self.x < other.x + other.width and
            self.x + self.width > other.x and
            self.y < other.y + other.height and
            self.y + self.height > other.y
        )

    def contains_point(self, px: float, py: float) -> bool:
        return (self.x <= px <= self.x + self.width and
                self.y <= py <= self.y + self.height)


class Bullet:
    def __init__(self, x: float, y: float, direction: Any, speed: float, size: int,
                 camp: Camp = Camp.PLAYER, color: str = "#FFFFFF", angle: Optional[float] = None,
                 accuracy: float = 1.0, splash_radius: float = 0.0, friendly_fire: int = 0,
                 damage: int = 1, shooter: Optional[Any] = None,
                 target_pos: Optional[Tuple[float, float]] = None):
        self.x = x
        self.y = y
        self.speed = speed
        self.size = size
        self.camp = camp
        self.color = color
        self.alive = True
        self.accuracy = float(accuracy)
        self.splash_radius = float(splash_radius)
        self.friendly_fire = int(friendly_fire)
        self.damage = int(damage)
        self.shooter = shooter
        self.exploded_at_target = False

        self.target_pos = (float(target_pos[0]), float(target_pos[1])) if target_pos is not None else None
        if self.target_pos is not None:
            self.target_dist = math.hypot(self.target_pos[0] - (self.x + self.size / 2.0),
                                          self.target_pos[1] - (self.y + self.size / 2.0))
        else:
            self.target_dist = 0.0
        self.travelled_dist = 0.0

        if angle is not None:
            self._angle = float(angle) % 360.0
        elif isinstance(direction, Direction):
            self._angle = direction.to_angle()
        elif isinstance(direction, (int, float)):
            self._angle = float(direction) % 360.0
        else:
            self._angle = 0.0

        rad = math.radians(self._angle)
        self.vx = math.sin(rad) * self.speed
        self.vy = -math.cos(rad) * self.speed

    @property
    def angle(self) -> float:
        return self._angle

    @angle.setter
    def angle(self, val: float) -> None:
        self._angle = float(val) % 360.0
        rad = math.radians(self._angle)
        self.vx = math.sin(rad) * self.speed
        self.vy = -math.cos(rad) * self.speed

    @property
    def direction(self) -> Direction:
        return Direction.from_angle(self._angle)

    @direction.setter
    def direction(self, val: Any) -> None:
        if isinstance(val, Direction):
            self._angle = val.to_angle()
        elif isinstance(val, (int, float)):
            self._angle = float(val) % 360.0
        rad = math.radians(self._angle)
        self.vx = math.sin(rad) * self.speed
        self.vy = -math.cos(rad) * self.speed

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.size, self.size)

    def update(self) -> None:
        if not self.alive:
            return
        self.x += self.vx
        self.y += self.vy
        self.travelled_dist += self.speed
        if self.target_pos is not None and self.travelled_dist >= self.target_dist:
            self.alive = False
            self.exploded_at_target = True


@dataclass
class EnemyMemoryEntry:
    """敌军记忆体实体：记录被实锤发现过的敌军最后坐标与追踪状态"""
    enemy_id: str
    x: float
    y: float
    size: int
    unit_type: str
    color: str
    is_tracking: bool
    last_seen_time: float = 0.0


class Tank:
    def __init__(self, x: float, y: float, size: int = 36, speed: float = 3.0,
                 camp: Camp = Camp.PLAYER, color: str = "#E69C24",
                 health: int = 1, tank_id: str = "tank",
                 vision_size: float = -1.0, ammo: int = -1, visibility: float = 1.0,
                 is_tower: bool = False, can_attack: bool = True, tower_type: str = "general",
                 resupply_radius: float = 0.0, resupply_interval: int = 30,
                 unit_type: str = "tank", controllable: bool = True,
                 ai_script: Optional[str] = None,
                 angle: Optional[float] = None,
                 can_crush_bricks: bool = False,
                 crush_speed_factor: float = 0.5,
                 converter_table: Optional[List[str]] = None,
                 harvest_speed: Optional[Dict[str, float]] = None,
                 accuracy: float = 1.0,
                 dodge: float = 0.0,
                 splash_radius: float = 0.0,
                 friendly_fire: int = 0,
                 bullet_speed: float = 6.0,
                 bullet_size: int = 12,
                 bullet_color: str = "#FFFFFF",
                 damage: int = 1,
                 attack_range: float = 240.0,
                 **kwargs):
        self.id = tank_id
        self.unit_type = unit_type
        self.x = x
        self.y = y
        self.size = size
        self.speed = speed
        self.camp = camp
        if angle is not None:
            self._angle = float(angle) % 360.0
        else:
            self._angle = 0.0 if camp == Camp.PLAYER else 180.0
        self.color = color
        self.fire_cooldown_max = 15
        self.fire_cooldown = 0
        self.health = health
        self.max_health = health
        self.alive = True

        # ===== 命中精度、闪避、范围伤害与友军误伤 =====
        self.accuracy = float(accuracy)
        self.dodge = float(dodge)
        self.splash_radius = float(splash_radius)
        self.friendly_fire = int(friendly_fire)
        self.bullet_speed = float(bullet_speed)
        self.bullet_size = int(bullet_size)
        self.bullet_color = str(bullet_color)
        self.damage = int(damage)
        self.attack_range = float(attack_range)

        # 接收并挂载任意扩展属性覆盖
        for k, v in kwargs.items():
            setattr(self, k, v)

        # ===== 玩家控制与 AI 脚本机制 =====
        self.controllable = controllable
        self.ai_script = ai_script

        # ===== 视线、弹药与辨识度系统 =====
        self.vision_size = vision_size
        self.ammo = ammo
        self.max_ammo = ammo
        self.visibility = visibility
        self.is_spotted = False
        self.spotted_timer = 0

        # ===== 清障车/碾压普通砖块能力 =====
        self.can_crush_bricks = can_crush_bricks
        self.crush_speed_factor = crush_speed_factor

        # ===== 防御塔专属属性 =====
        self.is_tower = is_tower
        self.can_attack = can_attack
        self.tower_type = tower_type
        self.resupply_radius = resupply_radius
        self.resupply_interval = resupply_interval
        self.resupply_timer = 0
        self.just_resupplied_timer = 0  # 获得补给视觉闪烁标记

        # ===== 资源转换机系统 (Converter) =====
        self.converter_table = list(converter_table or [])
        if self.converter_table:
            from converter.models import UnitConverter
            self.converter = UnitConverter(self.converter_table, owner=self)
        else:
            self.converter = None

        # ===== 资源采集动作与速度 =====
        self.harvest_speed: Dict[str, float] = dict(harvest_speed) if harvest_speed is not None else {"dark_matter": 2.0, "alloy": 1.5}
        self.is_harvesting: bool = False
        self.harvest_target: Optional[Tuple[int, int]] = None
        self.harvest_state: str = "idle"  # "idle", "harvesting", "contested", "out_of_range", "depleted"

    def start_harvest(self, col: int, row: int) -> None:
        """对指定地图瓦片坐标 (col, row) 的资源块展开开采"""
        self.is_harvesting = True
        self.harvest_target = (int(col), int(row))
        self.harvest_state = "harvesting"

    def stop_harvest(self) -> None:
        """停止当前资源开采动作"""
        self.is_harvesting = False
        self.harvest_target = None
        self.harvest_state = "idle"

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "converter" and value is not None and getattr(value, "owner", None) is None:
            value.owner = self
        super().__setattr__(name, value)

    @property
    def is_converting(self) -> bool:
        return bool(self.converter and self.converter.is_converting)

    @property
    def angle(self) -> float:
        return self._angle

    @angle.setter
    def angle(self, val: float) -> None:
        self._angle = float(val) % 360.0

    @property
    def direction(self) -> Direction:
        return Direction.from_angle(self._angle)

    @direction.setter
    def direction(self, val: Any) -> None:
        if isinstance(val, Direction):
            self._angle = val.to_angle()
        elif isinstance(val, (int, float)):
            self._angle = float(val) % 360.0

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.size, self.size)

    def get_sight_rect(self, map_width: float, map_height: float) -> Rect:
        if self.vision_size < 0:
            return Rect(0, 0, map_width, map_height)

        center_x = self.x + self.size / 2.0
        center_y = self.y + self.size / 2.0
        half = self.vision_size / 2.0

        return Rect(center_x - half, center_y - half, self.vision_size, self.vision_size)

    def update_cooldown(self) -> None:
        if self.fire_cooldown > 0:
            self.fire_cooldown -= 1
        if self.spotted_timer > 0:
            self.spotted_timer -= 1
            if self.spotted_timer == 0:
                self.is_spotted = False
        if self.just_resupplied_timer > 0:
            self.just_resupplied_timer -= 1

    def update_resupply(self, friendly_tanks: List["Tank"], limited_ammo_enabled: bool) -> List["Tank"]:
        """若具备补给能力，周期性为半径内的己方非满弹单位补充 1 发弹药"""
        if not self.alive or self.resupply_radius <= 0:
            return []

        if self.resupply_timer > 0:
            self.resupply_timer -= 1
            return []

        resupplied = []
        center_x = self.x + self.size / 2.0
        center_y = self.y + self.size / 2.0

        for other in friendly_tanks:
            if other is not self and other.alive and other.camp == self.camp:
                # 只有有限弹药且不满时进行补充
                if limited_ammo_enabled and other.ammo != -1 and other.max_ammo > 0:
                    if other.ammo < other.max_ammo:
                        other_cx = other.x + other.size / 2.0
                        other_cy = other.y + other.size / 2.0
                        dist = math.hypot(other_cx - center_x, other_cy - center_y)
                        if dist <= self.resupply_radius:
                            other.ammo += 1
                            other.just_resupplied_timer = 20
                            resupplied.append(other)

        if resupplied:
            self.resupply_timer = self.resupply_interval

        return resupplied

    def can_fire(self, limited_ammo_enabled: bool = True) -> bool:
        if not self.alive or not self.can_attack or self.fire_cooldown > 0 or self.is_converting:
            return False
        if limited_ammo_enabled and self.ammo != -1:
            return self.ammo > 0
        return True

    def consume_ammo(self, limited_ammo_enabled: bool = True) -> bool:
        if limited_ammo_enabled and self.ammo != -1:
            if self.ammo > 0:
                self.ammo -= 1
                return True
            return False
        return True

    def trigger_cooldown(self) -> None:
        self.fire_cooldown = self.fire_cooldown_max

    def take_damage(self, amount: int = 1) -> bool:
        self.health -= amount
        if self.health <= 0:
            self.alive = False
            self.stop_harvest()
            return True
        return False
