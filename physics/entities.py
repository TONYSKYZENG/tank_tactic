import math
from enum import Enum
from dataclasses import dataclass
from typing import Tuple, List, Optional

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
    def __init__(self, x: float, y: float, direction: Direction, speed: float, size: int,
                 camp: Camp = Camp.PLAYER, color: str = "#FFFFFF"):
        self.x = x
        self.y = y
        self.direction = direction
        self.speed = speed
        self.size = size
        self.camp = camp
        self.color = color
        self.alive = True

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.size, self.size)

    def update(self) -> None:
        if not self.alive:
            return
        self.x += self.direction.dx * self.speed
        self.y += self.direction.dy * self.speed


class Tank:
    def __init__(self, x: float, y: float, size: int = 36, speed: float = 3.0,
                 camp: Camp = Camp.PLAYER, color: str = "#E69C24",
                 health: int = 1, tank_id: str = "tank",
                 vision_size: float = -1.0, ammo: int = -1, visibility: float = 1.0,
                 is_tower: bool = False, can_attack: bool = True, tower_type: str = "general",
                 resupply_radius: float = 0.0, resupply_interval: int = 30):
        self.id = tank_id
        self.x = x
        self.y = y
        self.size = size
        self.speed = speed
        self.camp = camp
        self.direction = Direction.UP if camp == Camp.PLAYER else Direction.DOWN
        self.color = color
        self.fire_cooldown_max = 15
        self.fire_cooldown = 0
        self.health = health
        self.max_health = health
        self.alive = True

        # ===== 视线、弹药与辨识度系统 =====
        self.vision_size = vision_size
        self.ammo = ammo
        self.max_ammo = ammo
        self.visibility = visibility
        self.is_spotted = False
        self.spotted_timer = 0

        # ===== 防御塔专属属性 =====
        self.is_tower = is_tower
        self.can_attack = can_attack
        self.tower_type = tower_type
        self.resupply_radius = resupply_radius
        self.resupply_interval = resupply_interval
        self.resupply_timer = 0
        self.just_resupplied_timer = 0  # 获得补给视觉闪烁标记

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
        if not self.alive or not self.can_attack or self.fire_cooldown > 0:
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
            return True
        return False
