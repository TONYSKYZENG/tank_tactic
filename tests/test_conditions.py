import sys
import unittest
from pathlib import Path

# 确保项目根目录在 sys.path 中
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from physics.entities import Tank, Camp, Rect
from physics.engine import PhysicsEngine
from map_loader.models import GameMap
from mission_loader.loader import MissionLoader
from conditions import (
    ConditionContext,
    ConditionBuilder,
    UnitSurviveTimeCondition,
    UnitDestroyedCondition,
    AreaVisibleCondition,
    AllEnemiesDestroyedCondition,
    AllPlayersDestroyedCondition,
    AndCondition,
    OrCondition,
    NotCondition,
    ConstantCondition
)

class TestConditions(unittest.TestCase):
    def setUp(self):
        self.game_map = GameMap(
            name="TestMap",
            tile_size=32,
            cols=20,
            rows=20,
            grid=[[0]*20 for _ in range(20)]
        )
        self.engine = PhysicsEngine(self.game_map, fog_of_war_enabled=True, limited_ammo_enabled=True)
        self.ctx = ConditionContext(self.engine, self.game_map)

        # 添加玩家与敌军测试单位
        self.p1 = Tank(x=100, y=100, size=28, speed=2, camp=Camp.PLAYER, tank_id="player_core", vision_size=200)
        self.e1 = Tank(x=500, y=500, size=28, speed=2, camp=Camp.ENEMY, tank_id="enemy_boss", vision_size=200)

        self.engine.add_player_tank(self.p1)
        self.engine.add_enemy_tank(self.e1)

    def test_unit_survive_time(self):
        """测试原语1：特定单位存活时间"""
        cond = UnitSurviveTimeCondition(unit_id="player_core", seconds=2.0)
        self.assertFalse(cond.evaluate(self.ctx))

        # 模拟运行 1.5 秒
        self.ctx.update(1.5)
        self.assertFalse(cond.evaluate(self.ctx))

        # 累计达到 2.1 秒
        self.ctx.update(0.6)
        self.assertTrue(cond.evaluate(self.ctx))

        # 若单位死亡，则存活条件不满足
        self.p1.alive = False
        self.assertFalse(cond.evaluate(self.ctx))

    def test_unit_destroyed(self):
        """测试原语2：特定单位被摧毁"""
        cond = UnitDestroyedCondition(unit_id="enemy_boss")
        self.assertFalse(cond.evaluate(self.ctx))

        self.e1.alive = False
        self.assertTrue(cond.evaluate(self.ctx))

    def test_area_visible(self):
        """测试原语3：特定区域可见性（迷雾/视线正方形）"""
        # p1 位置在 (100, 100), size=28, vision_size=200
        # 视线正方形范围：中心(114, 114), 边长200 => x in [14, 214], y in [14, 214]

        # 区域 A 在视线内部 (100, 100, 32, 32)
        cond_visible = AreaVisibleCondition(Rect(100, 100, 32, 32))
        self.assertTrue(cond_visible.evaluate(self.ctx))

        # 区域 B 在视线外部 (500, 500, 32, 32)
        cond_fogged = AreaVisibleCondition(Rect(500, 500, 32, 32))
        self.assertFalse(cond_fogged.evaluate(self.ctx))

        # 若我方拥有全图视野单位 (vision_size < 0)
        p_scout = Tank(x=0, y=0, size=28, camp=Camp.PLAYER, tank_id="radar", vision_size=-1)
        self.engine.add_player_tank(p_scout)
        self.assertTrue(cond_fogged.evaluate(self.ctx))

        # 移除全图单位，关闭迷雾系统，同样全图可见
        self.engine.player_tanks.remove(p_scout)
        self.assertFalse(cond_fogged.evaluate(self.ctx))
        self.engine.fog_of_war_enabled = False
        self.assertTrue(cond_fogged.evaluate(self.ctx))

    def test_composite_logic(self):
        """测试与或非复合逻辑"""
        c1 = UnitDestroyedCondition("enemy_boss")
        c2 = UnitSurviveTimeCondition("player_core", 3.0)

        # AND: c1 AND c2
        and_cond = AndCondition([c1, c2])
        self.assertFalse(and_cond.evaluate(self.ctx))

        self.e1.alive = False  # c1 is True
        self.assertFalse(and_cond.evaluate(self.ctx))

        self.ctx.update(3.1)   # c2 is True
        self.assertTrue(and_cond.evaluate(self.ctx))

        # NOT: NOT(c1)
        not_cond = NotCondition(c1)
        self.assertFalse(not_cond.evaluate(self.ctx))

        # OR: (NOT c1) OR c2
        or_cond = OrCondition([not_cond, c2])
        self.assertTrue(or_cond.evaluate(self.ctx))

    def test_json_builder(self):
        """测试从复杂 JSON 配置构建 AST 树"""
        config = {
            "or": [
                {
                    "and": [
                        {"type": "unit_survive_time", "unit_id": "player_core", "seconds": 5.0},
                        {"type": "area_visible", "area": [100, 100, 20, 20]}
                    ]
                },
                {
                    "and": [
                        {"type": "unit_destroyed", "unit_id": "enemy_boss"},
                        {"not": {"type": "unit_destroyed", "unit_id": "player_core"}}
                    ]
                }
            ]
        }

        tree = ConditionBuilder.build(config)
        self.assertIsInstance(tree, OrCondition)
        self.assertEqual(len(tree.conditions), 2)
        self.assertIsInstance(tree.conditions[0], AndCondition)
        self.assertIsInstance(tree.conditions[1], AndCondition)

        # 初始时，时间不够，boss 未死 => False
        self.assertFalse(tree.evaluate(self.ctx))

        # 击杀 boss，且 player_core 仍活着 => 命中分支 2 => True
        self.e1.alive = False
        self.assertTrue(tree.evaluate(self.ctx))

        # 若 player_core 也死了，分支 2 的 NOT 失败，整个 OR 失败 => False
        self.p1.alive = False
        self.assertFalse(tree.evaluate(self.ctx))

    def test_tile_coordinates_parsing(self):
        """测试瓦片坐标形式的 area_visible"""
        cfg = {
            "type": "area_visible",
            "tile_x": 3,
            "tile_y": 3,
            "tile_w": 2,
            "tile_h": 2
        }
        cond = ConditionBuilder.build(cfg)
        self.assertIsInstance(cond, AreaVisibleCondition)
        # 3 * 32 = 96, 2 * 32 = 64 => Rect(96, 96, 64, 64)
        self.assertEqual(cond.area.x, 96.0)
        self.assertEqual(cond.area.y, 96.0)
        self.assertEqual(cond.area.width, 64.0)
        self.assertEqual(cond.area.height, 64.0)
        # p1 (100, 100) 的视野正方形覆盖了该区域
        self.assertTrue(cond.evaluate(self.ctx))

    def test_mission_01_loading(self):
        """测试加载 missions/mission_01.json 并解析条件"""
        mission_file = BASE_DIR / "missions/mission_01.json"
        mission = MissionLoader.load_from_file(mission_file)
        self.assertIsNotNone(mission.victory_conditions)
        self.assertIsNotNone(mission.defeat_conditions)

        v_tree = ConditionBuilder.build(mission.victory_conditions)
        d_tree = ConditionBuilder.build(mission.defeat_conditions)

        self.assertIn("enemy_radar", v_tree.get_description())
        self.assertIn("player_radar", d_tree.get_description())

if __name__ == "__main__":
    unittest.main()
