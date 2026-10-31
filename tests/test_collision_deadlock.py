import unittest
from map_loader.models import GameMap, TileType
from physics.entities import Tank, Camp, Direction
from physics.engine import PhysicsEngine
from command.commands import MoveCommand, AttackTargetCommand
from command.dispatcher import CommandDispatcher
from command.tactics_mode import TacticMode

class TestCollisionDeadlock(unittest.TestCase):
    def setUp(self):
        # 10x10 empty map, tile_size=32
        self.game_map = GameMap(name="test_grid", cols=10, rows=10, tile_size=32,
                                grid=[[TileType.EMPTY for _ in range(10)] for _ in range(10)])
        self.physics = PhysicsEngine(self.game_map, fog_of_war_enabled=False, limited_ammo_enabled=False)
        self.dispatcher = CommandDispatcher()

    def test_head_on_collision_yield(self):
        """测试两辆己方坦克在狭窄路径上迎头相撞时的避让/让行机制"""
        # Tank A at x=32, y=64 moving right towards (160, 64)
        tank_a = Tank(x=32, y=64, size=32, speed=4.0, camp=Camp.PLAYER, tank_id="unit_1")
        # Tank B at x=128, y=64 moving left towards (0, 64)
        tank_b = Tank(x=128, y=64, size=32, speed=4.0, camp=Camp.PLAYER, tank_id="unit_2")

        self.physics.add_player_tank(tank_a)
        self.physics.add_player_tank(tank_b)
        self.dispatcher.register_tank(tank_a)
        self.dispatcher.register_tank(tank_b)

        cmd_a = MoveCommand(dest_x=160, dest_y=64)
        cmd_b = MoveCommand(dest_x=0, dest_y=64)
        self.dispatcher.tank_commands[tank_a.id] = cmd_a
        self.dispatcher.tank_commands[tank_b.id] = cmd_b

        # Simulate movement frames
        for _ in range(40):
            self.dispatcher.update(self.physics.player_tanks, None, False, self.physics, self.game_map)
            self.physics.update()

        # Both units should not freeze indefinitely; either they lateral-evaded or unit_2 yielded/unlocked
        # Verify that total_stuck_frames is kept in check or units made position progress
        self.assertTrue(tank_a.x != 32 or tank_b.x != 128)

    def test_enemy_blocking_opportunistic_fire(self):
        """测试移动中遇到敌军阻挡时主动转向开火迎击"""
        # Player tank at x=32, y=32 moving right
        p_tank = Tank(x=32, y=32, size=32, speed=4.0, camp=Camp.PLAYER, tank_id="p1")
        # Enemy tank directly in the way at x=64, y=32
        e_tank = Tank(x=64, y=32, size=32, speed=0.0, camp=Camp.ENEMY, tank_id="e1", health=1)

        self.physics.add_player_tank(p_tank)
        self.physics.add_enemy_tank(e_tank)

        cmd = MoveCommand(dest_x=160, dest_y=32)
        cmd.execute(p_tank, self.physics, self.game_map)

        # Player tank should detect blocking enemy and spawn a bullet
        self.assertGreater(len(self.physics.bullets), 0)
        # Bullet should be fired towards the right (at the enemy)
        self.assertEqual(self.physics.bullets[0].direction, Direction.RIGHT)

    def test_standoff_flank_differentiation(self):
        """测试多辆坦克攻击同一目标时，自动分散占位（不挤在同一个阵位）"""
        target = Tank(x=160, y=160, size=32, speed=0.0, camp=Camp.ENEMY, tank_id="boss")
        p1 = Tank(x=160, y=128, size=32, speed=3.0, camp=Camp.PLAYER, tank_id="p1") # already at (c, r-1)
        p2 = Tank(x=128, y=128, size=32, speed=3.0, camp=Camp.PLAYER, tank_id="p2")

        self.physics.add_player_tank(p1)
        self.physics.add_player_tank(p2)
        self.physics.add_enemy_tank(target)

        cmd2 = AttackTargetCommand(target)
        cmd2.execute(p2, self.physics, self.game_map)

        # Because p1 is occupying (160, 128), p2 should pick another flank
        dest_x = cmd2.move_subcmd.dest_x
        dest_y = cmd2.move_subcmd.dest_y
        self.assertFalse(dest_x == 160 and dest_y == 128)

    def test_stuck_attack_switches_target(self):
        """测试当攻击目标因完全被阻挡无法到达时，超时放弃并自动锁定下一个目标"""
        # Create a steel box around target_a so it's unreachable
        for c in range(2, 5):
            for r in range(2, 5):
                if c == 3 and r == 3:
                    continue
                self.game_map.set_tile(c, r, TileType.STEEL)

        unreachable_target = Tank(x=3 * 32, y=3 * 32, size=32, speed=0.0, camp=Camp.ENEMY, tank_id="e_locked")
        reachable_target = Tank(x=8 * 32, y=8 * 32, size=32, speed=0.0, camp=Camp.ENEMY, tank_id="e_open")

        attacker = Tank(x=0, y=0, size=32, speed=3.0, camp=Camp.PLAYER, tank_id="p1", ai_script="test_script")
        self.physics.add_player_tank(attacker)
        self.physics.add_enemy_tank(unreachable_target)
        self.physics.add_enemy_tank(reachable_target)

        self.dispatcher.register_tank(attacker)
        # Issue attack on unreachable target
        self.dispatcher.issue_attack_target([attacker], unreachable_target, self.physics)

        # Simulate stuck attack execution
        cmd = self.dispatcher.tank_commands[attacker.id]
        cmd.stuck_attack_frames = 75  # Simulate prolonged deadlock

        self.dispatcher.update([attacker], None, False, self.physics, self.game_map)

        # The stuck command should have completed and dispatcher should retarget reachable_target
        new_cmd = self.dispatcher.tank_commands.get(attacker.id)
        self.assertIsNotNone(new_cmd)
        self.assertIsInstance(new_cmd, AttackTargetCommand)
        self.assertEqual(new_cmd.target_tank, reachable_target)


if __name__ == "__main__":
    unittest.main()
