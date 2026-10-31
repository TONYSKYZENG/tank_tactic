import unittest
import math
from map_loader.models import GameMap, TileType
from physics.entities import Tank, Bullet, Camp, Direction, Rect
from physics.engine import PhysicsEngine
from command.commands import BaseCommand, MoveCommand, AttackTargetCommand

class TestFreeMovementAndRotation(unittest.TestCase):
    def setUp(self):
        self.game_map = GameMap(name="test_map", cols=10, rows=10, tile_size=32,
                                grid=[[TileType.EMPTY for _ in range(10)] for _ in range(10)])
        self.physics = PhysicsEngine(self.game_map, fog_of_war_enabled=False, limited_ammo_enabled=False)

    def test_tank_free_rotation_and_direction_mapping(self):
        """测试坦克自由角度赋值以及与旧 Direction 枚举的双向映射"""
        tank = Tank(x=100, y=100, camp=Camp.PLAYER)
        # 初始角度为 0° (朝上 UP)
        self.assertEqual(tank.angle, 0.0)
        self.assertEqual(tank.direction, Direction.UP)

        # 自由旋转到 90° (朝右 RIGHT)
        tank.angle = 90.0
        self.assertEqual(tank.direction, Direction.RIGHT)

        # 自由旋转到 135° (朝右下角)
        tank.angle = 135.0
        self.assertEqual(tank.angle, 135.0)
        self.assertEqual(tank.direction, Direction.DOWN)

        # 逆时针角度规范化 (-45° -> 315°)
        tank.angle = -45.0
        self.assertEqual(tank.angle, 315.0)
        self.assertEqual(tank.direction, Direction.UP)

        # 向后兼容：直接设置 Direction 枚举自动同步 angle
        tank.direction = Direction.LEFT
        self.assertEqual(tank.angle, 270.0)

    def test_bullet_free_trajectory(self):
        """测试子弹沿任意角度发射及向量速度更新"""
        tank = Tank(x=100, y=100, speed=3.0, camp=Camp.PLAYER)
        # 沿 45° (右上方) 发射
        tank.angle = 45.0
        bullet = self.physics.spawn_bullet(tank, bullet_speed=10.0, bullet_size=8, angle=45.0)

        self.assertIsNotNone(bullet)
        self.assertAlmostEqual(bullet.angle, 45.0)
        # 45°: vx = sin(45°)*10 > 0, vy = -cos(45°)*10 < 0
        self.assertGreater(bullet.vx, 0)
        self.assertLess(bullet.vy, 0)

        orig_x, orig_y = bullet.x, bullet.y
        bullet.update()
        self.assertAlmostEqual(bullet.x, orig_x + bullet.vx)
        self.assertAlmostEqual(bullet.y, orig_y + bullet.vy)

    def test_diagonal_movement_and_wall_sliding(self):
        """测试对角线自由移动与遇墙滑动 (Wall Sliding)"""
        tank = Tank(x=100, y=100, size=32, speed=4.0, camp=Camp.PLAYER)
        self.physics.add_player_tank(tank)

        # 自由向右上方移动 (vx=1, vy=-1)
        moved = self.physics.move_tank(tank, (1.0, -1.0))
        self.assertTrue(moved)
        self.assertGreater(tank.x, 100)
        self.assertLess(tank.y, 100)
        self.assertAlmostEqual(tank.angle, 45.0)

        # 放置一堵在顶部的墙壁，测试贴墙滑动
        # 把 row 1 (y=32..64) 全填为 STEEL
        for c in range(10):
            self.game_map.set_tile(c, 1, TileType.STEEL)

        tank.x = 100
        tank.y = 65  # 紧贴在钢墙下方 (y=64为钢墙底沿)
        # 尝试继续向右上角前进 (vx=1, vy=-1)
        # Y 方向受阻，但 X 方向应该成功沿墙平滑向右滑动
        old_x, old_y = tank.x, tank.y
        moved = self.physics.move_tank(tank, (1.0, -1.0))
        self.assertTrue(moved)
        self.assertGreater(tank.x, old_x) # X 方向成功滑动
        self.assertEqual(tank.y, old_y)    # Y 方向被墙挡住未穿模

    def test_360_raycast_line_of_sight(self):
        """测试自由 360° 射线视线检测"""
        # (32, 32) 到 (160, 160) 斜向无障碍
        self.assertTrue(BaseCommand.is_line_of_sight_clear(32, 32, 160, 160, self.game_map))

        # 在斜向中间 (96, 96) 放置砖墙 (col 3, row 3)
        self.game_map.set_tile(3, 3, TileType.BRICK)
        # 视线应当被砖墙阻挡
        self.assertFalse(BaseCommand.is_line_of_sight_clear(32, 32, 160, 160, self.game_map))

    def test_direct_diagonal_pathfinding_no_orthogonal_zig_zag(self):
        """测试寻路与移动直接走斜线到达目标，而不是先横再竖或先竖再横"""
        from command.pathfinder import GridPathfinder

        tank = Tank(x=32.0, y=32.0, size=32, speed=4.0, camp=Camp.PLAYER)
        self.physics.add_player_tank(tank)

        pf = GridPathfinder(self.game_map)
        # 非 45° 任意斜向目标：(256, 160)，即 dx=224, dy=128
        path, ammo = pf.find_path(32.0, 32.0, 256.0, 160.0, tank=tank, limited_ammo_enabled=True)
        self.assertEqual(ammo, 0)
        # 开阔地形应直接拉直为单一终点航点，无任何先横再竖的折点
        self.assertEqual(path, [(256.0, 160.0)])

        cmd = MoveCommand(dest_x=256.0, dest_y=160.0, tolerance=4.0)
        prev_x, prev_y = tank.x, tank.y
        cmd.execute(tank, self.physics, self.game_map)

        # 第一帧即同时在 X 和 Y 方向斜向推进，而非单轴正交移动
        self.assertGreater(tank.x, prev_x)
        self.assertGreater(tank.y, prev_y)

        # 全程沿直线到达目标，帧数接近欧氏距离 (hypot(224, 128)/4.0 ≈ 64.5 帧)，远小于曼哈顿折线 (352/4 = 88 帧)
        frames = 1
        while frames < 80:
            if cmd.execute(tank, self.physics, self.game_map):
                break
            frames += 1

        self.assertLessEqual(frames, 68)
        self.assertLessEqual(math.hypot(tank.x - 256.0, tank.y - 160.0), 4.0)


if __name__ == "__main__":
    unittest.main()
