import unittest
from pathlib import Path
from map_loader.models import GameMap, TileType
from tank_configs.config_loader import TankConfig
from physics.entities import Tank, Camp
from physics.engine import PhysicsEngine
from command.pathfinder import GridPathfinder
from command.commands import MoveCommand

class TestClearingTank(unittest.TestCase):
    def setUp(self):
        self.game_map = GameMap(name="test_crush", cols=10, rows=10, tile_size=32,
                                grid=[[TileType.EMPTY for _ in range(10)] for _ in range(10)])
        self.physics = PhysicsEngine(self.game_map, fog_of_war_enabled=False, limited_ammo_enabled=True)

    def test_clearing_tank_config_template(self):
        """测试清障车模板配置加载"""
        cfg_path = Path("tank_configs/clearing_tank.json")
        self.assertTrue(cfg_path.exists())
        cfg = TankConfig.from_json(cfg_path)
        self.assertEqual(cfg.name, "Clearing Tank")
        self.assertTrue(cfg.can_crush_bricks)
        self.assertAlmostEqual(cfg.crush_speed_factor, 0.55)

    def test_crush_brick_movement_and_speed_decay(self):
        """测试清障车直接碾压普通砖块摧毁瓦片，且速度发生衰减"""
        # (c=2, r=1) 设置普通砖块 (x=64, y=32)
        self.game_map.set_tile(2, 1, TileType.BRICK)

        # 清障车放置在 (x=32, y=32)，正常移速 4.0，碾压衰减系数 0.5
        clearing_tank = Tank(
            x=32, y=32, size=32, speed=4.0, camp=Camp.PLAYER, tank_id="clearing_1",
            can_crush_bricks=True, crush_speed_factor=0.5
        )
        self.physics.add_player_tank(clearing_tank)

        # 向右移动碾压方块
        old_x = clearing_tank.x
        moved = self.physics.move_tank(clearing_tank, (1.0, 0.0))
        self.assertTrue(moved)
        # 移速因碾压衰减：4.0 * 0.5 = 2.0
        self.assertAlmostEqual(clearing_tank.x - old_x, 2.0)

        # 连续推进行进至覆盖砖块格
        for _ in range(18):
            self.physics.move_tank(clearing_tank, (1.0, 0.0))

        # 验证该处砖块已被碾碎清空为 EMPTY
        self.assertEqual(self.game_map.get_tile(2, 1), TileType.EMPTY)

    def test_cannot_crush_steel(self):
        """测试清障车无法碾压钢墙（避让不能碾的方块）"""
        self.game_map.set_tile(2, 1, TileType.STEEL)
        clearing_tank = Tank(
            x=32, y=32, size=32, speed=4.0, camp=Camp.PLAYER, tank_id="clearing_1",
            can_crush_bricks=True
        )
        self.physics.add_player_tank(clearing_tank)

        # 移动尝试穿过钢铁墙壁，应当被阻挡
        clearing_tank.x = 33 # 紧贴 (64, 32)
        moved = self.physics.move_tank(clearing_tank, (1.0, 0.0))
        # 无法穿透钢墙
        self.assertFalse(moved)
        self.assertEqual(self.game_map.get_tile(2, 1), TileType.STEEL)

    def test_pathfinding_only_avoids_uncrushable_blocks(self):
        """测试具备碾压属性的坦克寻路只避让不能碾的方块且零弹药消耗"""
        # 构建一道由砖块组成的横向屏障，但在最右侧有 STEEL
        for c in range(10):
            self.game_map.set_tile(c, 3, TileType.BRICK)
        self.game_map.set_tile(9, 3, TileType.STEEL)

        pathfinder = GridPathfinder(self.game_map)

        normal_tank = Tank(x=64, y=0, size=32, speed=3.0, camp=Camp.PLAYER, ammo=5, can_crush_bricks=False)
        clearing_tank = Tank(x=64, y=0, size=32, speed=3.0, camp=Camp.PLAYER, ammo=0, can_crush_bricks=True)

        # 普通坦克穿过砖块需要消耗弹药
        path_norm, ammo_norm = pathfinder.find_path(64, 0, 64, 160, tank=normal_tank, limited_ammo_enabled=True)
        self.assertGreater(ammo_norm, 0)

        # 清障车穿过砖块无需弹药 (ammo_needed = 0)
        path_clear, ammo_clear = pathfinder.find_path(64, 0, 64, 160, tank=clearing_tank, limited_ammo_enabled=True)
        self.assertEqual(ammo_clear, 0)
        self.assertGreater(len(path_clear), 0)


if __name__ == "__main__":
    unittest.main()
