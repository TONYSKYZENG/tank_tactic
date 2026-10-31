from typing import Dict, Optional, Type
from physics.entities import Tank
from physics.engine import PhysicsEngine
from map_loader.models import GameMap
from tank_configs.config_loader import TankConfig
from .tactics import BaseTactic, PatrolTactic, ChargeBaseTactic, HunterTactic

TACTIC_REGISTRY: Dict[str, Type[BaseTactic]] = {
    "patrol": PatrolTactic,
    "charge_base": ChargeBaseTactic,
    "hunter": HunterTactic,
}

class EnemyAgent:
    def __init__(self, tank: Tank, config: TankConfig, tactic: BaseTactic):
        self.tank = tank
        self.config = config
        self.tactic = tactic

class EnemyAIController:
    """管理所有敌军坦克的 AI 思考与执行"""

    def __init__(self, physics_engine: PhysicsEngine, game_map: GameMap):
        self.physics_engine = physics_engine
        self.game_map = game_map
        self.agents: Dict[str, EnemyAgent] = {}

    def register_enemy(self, tank: Tank, config: TankConfig, tactic_name: str = "patrol") -> None:
        tactic_class = TACTIC_REGISTRY.get(tactic_name, PatrolTactic)
        tactic_instance = tactic_class(config)
        agent = EnemyAgent(tank, config, tactic_instance)
        self.agents[tank.id] = agent
        self.physics_engine.add_enemy_tank(tank)

    def update(self) -> None:
        """主循环每帧调用一次，驱动所有敌军行动"""
        # 清除已消亡的 agent
        alive_ids = [t.id for t in self.physics_engine.enemy_tanks if t.alive]
        self.agents = {tid: ag for tid, ag in self.agents.items() if tid in alive_ids}

        for agent in self.agents.values():
            tank = agent.tank
            if not tank.alive:
                continue

            # 战术决策
            move_dir, should_fire = agent.tactic.decide(tank, self.physics_engine, self.game_map)

            # 执行移动
            if move_dir is not None:
                self.physics_engine.move_tank(tank, move_dir)

            # 执行开火
            if should_fire and tank.can_fire():
                self.physics_engine.spawn_bullet(
                    tank=tank,
                    bullet_speed=agent.config.bullet_speed,
                    bullet_size=agent.config.bullet_size,
                    color=agent.config.bullet_color
                )
