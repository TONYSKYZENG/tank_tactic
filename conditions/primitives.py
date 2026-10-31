import time
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from physics.entities import Tank, Rect, Camp
from map_loader.models import GameMap

class ConditionContext:
    """胜负条件评估上下文环境"""

    def __init__(self, physics_engine, game_map: GameMap):
        self.physics_engine = physics_engine
        self.game_map = game_map
        self.elapsed_time: float = 0.0  # 游戏运行累计秒数
        # 记录每个单位的当前存活秒数 (只要还活着就增加)
        self.unit_alive_seconds: Dict[str, float] = {}
        # 记录单位是否曾经存在以及死亡状态
        self.registered_unit_ids: set = set()

    def update(self, delta_time: float):
        self.elapsed_time += delta_time

        all_active_tanks = self.physics_engine.get_all_active_tanks()
        for t in all_active_tanks:
            self.registered_unit_ids.add(t.id)
            if t.alive:
                self.unit_alive_seconds[t.id] = self.unit_alive_seconds.get(t.id, 0.0) + delta_time

    def get_tank_by_id(self, unit_id: str) -> Optional[Tank]:
        for t in self.physics_engine.player_tanks:
            if t.id == unit_id:
                return t
        for e in self.physics_engine.enemy_tanks:
            if e.id == unit_id:
                return e
        return None

    def is_unit_alive(self, unit_id: str) -> bool:
        tank = self.get_tank_by_id(unit_id)
        return tank is not None and tank.alive

    def get_unit_survive_time(self, unit_id: str) -> float:
        return self.unit_alive_seconds.get(unit_id, 0.0)

    def is_area_visible(self, area: Rect) -> bool:
        """检查指定矩形区域是否对我方可见（无迷雾、全图视野或与我方视线相交）"""
        if not self.physics_engine.fog_of_war_enabled:
            return True

        # 检查我方单位是否有全图挂
        for t in self.physics_engine.player_tanks:
            if t.alive and t.vision_size < 0:
                return True

        sight_rects = self.physics_engine.get_player_sight_rects()
        for sr in sight_rects:
            if area.collides_with(sr):
                return True
        return False


class BaseCondition(ABC):
    """条件表达式抽象基类"""

    @abstractmethod
    def evaluate(self, ctx: ConditionContext) -> bool:
        pass

    @abstractmethod
    def get_description(self) -> str:
        pass


class UnitSurviveTimeCondition(BaseCondition):
    """
    原语1：特定单位存活超过特定时间
    - unit_id: 单位 ID
    - seconds: 存活秒数
    """
    def __init__(self, unit_id: str, seconds: float):
        self.unit_id = unit_id
        self.seconds = float(seconds)

    def evaluate(self, ctx: ConditionContext) -> bool:
        # 单位必须活着且存活累计时间达到指定秒数
        if not ctx.is_unit_alive(self.unit_id):
            return False
        return ctx.get_unit_survive_time(self.unit_id) >= self.seconds

    def get_description(self) -> str:
        return f"单位 [{self.unit_id}] 存活超过 {self.seconds}s"


class UnitDestroyedCondition(BaseCondition):
    """
    原语2：特定单位死亡
    - unit_id: 单位 ID
    """
    def __init__(self, unit_id: str):
        self.unit_id = unit_id

    def evaluate(self, ctx: ConditionContext) -> bool:
        tank = ctx.get_tank_by_id(self.unit_id)
        # 如果单位已经不在存活列表，或者存在且 alive 为 False
        if tank is None:
            # 如果曾经登记过该单位但现在不在活跃引擎中，说明已被清理
            return self.unit_id in ctx.registered_unit_ids
        return not tank.alive

    def get_description(self) -> str:
        return f"特定单位 [{self.unit_id}] 被摧毁"


class AreaVisibleCondition(BaseCondition):
    """
    原语3：特定区域可见
    - area: Rect 目标矩形侦察区域
    """
    def __init__(self, area: Rect):
        self.area = area

    def evaluate(self, ctx: ConditionContext) -> bool:
        return ctx.is_area_visible(self.area)

    def get_description(self) -> str:
        return f"侦测到指定区域 ({self.area.x:.0f},{self.area.y:.0f},{self.area.width:.0f}x{self.area.height:.0f})"


class AllEnemiesDestroyedCondition(BaseCondition):
    """辅助原语：所有敌方单位全灭"""
    def evaluate(self, ctx: ConditionContext) -> bool:
        alive_enemies = [e for e in ctx.physics_engine.enemy_tanks if e.alive]
        return len(alive_enemies) == 0

    def get_description(self) -> str:
        return "全歼敌军所有部队"


class AllPlayersDestroyedCondition(BaseCondition):
    """辅助原语：我方所有单位全灭"""
    def evaluate(self, ctx: ConditionContext) -> bool:
        alive_players = [p for p in ctx.physics_engine.player_tanks if p.alive]
        return len(alive_players) == 0

    def get_description(self) -> str:
        return "我方所有装甲部队覆灭"
