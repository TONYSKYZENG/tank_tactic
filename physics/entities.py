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


class Bullet:
    def __init__(self, x: float, y: float, direction: Direction, speed: float, size: int,
                 camp: Camp = Camp.PLAYER, color: str = "#FFFFFF"):
        self.x = x
        self.y = y
        self.direction = direction
        self.speed = speed
        self.size = size  # 炮弹外接矩形大小
        self.camp = camp  # 所属阵营
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
                 health: int = 1, tank_id: str = "tank"):
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

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.size, self.size)

    def update_cooldown(self) -> None:
        if self.fire_cooldown > 0:
            self.fire_cooldown -= 1

    def can_fire(self) -> bool:
        return self.alive and self.fire_cooldown <= 0

    def trigger_cooldown(self) -> None:
        self.fire_cooldown = self.fire_cooldown_max

    def take_damage(self, amount: int = 1) -> bool:
        """扣除生命值，死亡返回 True"""
        self.health -= amount
        if self.health <= 0:
            self.alive = False
            return True
        return False
