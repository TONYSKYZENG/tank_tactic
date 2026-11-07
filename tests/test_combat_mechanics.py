import unittest
import math
import random
from pathlib import Path
from map_loader.models import GameMap, TileType
from physics.entities import Tank, Bullet, Camp, Rect
from physics.engine import PhysicsEngine
from tank_configs.config_loader import TankConfig
from command.dispatcher import CommandDispatcher
from command.commands import AttackGroundCommand
from api.controller import GameAPIController
from ai_python.bridge import TankScriptAPI
from mission_loader.loader import MissionLoader

class MockGameContext:
    def __init__(self, physics_engine, dispatcher, game_map):
        self.physics_engine = physics_engine
        self.command_dispatcher = dispatcher
        self.game_map = game_map
        self.is_paused = False
        self.base_dir = Path(".")
        self.resource_manager = None
        self.ai_controller = None

class TestCombatMechanics(unittest.TestCase):
    def setUp(self):
        # 10x10 empty map
        self.game_map = GameMap(name="test", tile_size=40, cols=10, rows=10, grid=[[0]*10 for _ in range(10)])
        self.physics = PhysicsEngine(self.game_map, fog_of_war_enabled=False, limited_ammo_enabled=False)
        self.dispatcher = CommandDispatcher()
        self.context = MockGameContext(self.physics, self.dispatcher, self.game_map)
        self.api = GameAPIController(self.context)

    def test_accuracy_and_dodge_prob(self):
        """测试命中精度 p 与闪避率 q：命中概率 P = p * (1 - q)"""
        # 1. 100% 精度与 0% 闪避 -> 必然命中
        attacker = Tank(100, 100, size=30, camp=Camp.PLAYER, accuracy=1.0)
        defender = Tank(200, 100, size=30, camp=Camp.ENEMY, health=100, dodge=0.0)
        self.physics.set_player_tank(attacker)
        self.physics.add_enemy_tank(defender)

        bullet = self.physics.spawn_bullet(attacker, bullet_speed=10.0, bullet_size=10, angle=90.0)
        self.assertIsNotNone(bullet)
        self.assertEqual(bullet.accuracy, 1.0)

        # 移动炮弹使其碰撞 defender
        bullet.x = defender.x
        bullet.y = defender.y
        initial_hp = defender.health
        self.physics.update_bullets()
        self.assertEqual(defender.health, initial_hp - 1)
        self.assertFalse(bullet.alive)

        # 2. 100% 闪避 q = 1.0 -> 绝对闪避 (伤害为 0)
        defender.dodge = 1.0
        attacker.fire_cooldown = 0
        bullet2 = self.physics.spawn_bullet(attacker, bullet_speed=10.0, bullet_size=10, angle=90.0)
        bullet2.x = defender.x
        bullet2.y = defender.y
        curr_hp = defender.health
        self.physics.update_bullets()
        self.assertEqual(defender.health, curr_hp)
        self.assertFalse(bullet2.alive)

        # 3. 统计抽样验证 P = p * (1 - q): p=0.8, q=0.5 -> P = 0.4
        attacker.accuracy = 0.8
        defender.dodge = 0.5
        defender.health = 10000

        hits = 0
        total_trials = 600
        for _ in range(total_trials):
            b = Bullet(defender.x, defender.y, direction=None, speed=5, size=10,
                       camp=Camp.PLAYER, accuracy=0.8, splash_radius=0.0)
            self.physics.bullets = [b]
            prev_hp = defender.health
            self.physics.update_bullets()
            if defender.health < prev_hp:
                hits += 1

        empirical_p = hits / total_trials
        # 理论 P = 0.4，容差在 0.33 ~ 0.47 之间
        self.assertTrue(0.33 <= empirical_p <= 0.47, f"Empirical P was {empirical_p}")

    def test_splash_damage_and_friendly_fire(self):
        """测试范围伤害与友军误伤机制"""
        # 放置多个敌方与友方单位围绕中心 (200, 200)
        # 敌军 1: 距离 30px (在 50px 爆炸半径内)
        e1 = Tank(230, 200, size=20, camp=Camp.ENEMY, health=5, dodge=0.0)
        # 敌军 2: 距离 120px (在 50px 爆炸半径外)
        e2 = Tank(320, 200, size=20, camp=Camp.ENEMY, health=5, dodge=0.0)
        # 友军 1: 距离 30px
        p_ally = Tank(170, 200, size=20, camp=Camp.PLAYER, health=5, dodge=0.0)

        self.physics.player_tanks = [p_ally]
        self.physics.enemy_tanks = [e1, e2]

        # 1. friendly_fire = 0 (不误伤友军)
        bullet_safe = Bullet(200, 200, direction=None, speed=0, size=10, camp=Camp.PLAYER,
                             accuracy=1.0, splash_radius=50.0, friendly_fire=0)
        self.physics.explode_bullet(bullet_safe, 200, 200)

        self.assertEqual(e1.health, 4)      # 敌军在范围内，受到 1 点伤害
        self.assertEqual(e2.health, 5)      # 敌军在范围外，未受伤害
        self.assertEqual(p_ally.health, 5)  # 友军在范围内但 friendly_fire=0，未受伤害

        # 2. friendly_fire = 1 (开启误伤友军)
        bullet_ff = Bullet(200, 200, direction=None, speed=0, size=10, camp=Camp.PLAYER,
                           accuracy=1.0, splash_radius=50.0, friendly_fire=1)
        self.physics.explode_bullet(bullet_ff, 200, 200)

        self.assertEqual(e1.health, 3)      # 敌军再受 1 点伤害
        self.assertEqual(p_ally.health, 4)  # 友军在范围内且 friendly_fire=1，受到伤害！

        # 3. 爆炸摧毁范围内的普通砖块
        self.game_map.set_tile(5, 5, TileType.BRICK) # (200~240, 200~240)
        self.assertEqual(self.game_map.get_tile(5, 5), TileType.BRICK)
        self.physics.explode_bullet(bullet_ff, 220, 220)
        self.assertEqual(self.game_map.get_tile(5, 5), TileType.EMPTY)

    def test_splash_friendly_fire_does_not_hurt_self(self):
        """测试具备范围伤害和友军误伤的单位在近距离爆炸或地块强制攻击时，绝对不会误伤到自己"""
        # 自身单位 (如喷火坦克)
        flame_shooter = Tank(200, 200, size=30, camp=Camp.PLAYER, health=10, accuracy=1.0,
                             splash_radius=60.0, friendly_fire=1, tank_id="shooter_1")
        # 友军
        ally = Tank(215, 200, size=30, camp=Camp.PLAYER, health=10, accuracy=1.0, dodge=0.0, tank_id="ally_1")
        # 敌军
        enemy = Tank(230, 200, size=30, camp=Camp.ENEMY, health=10, accuracy=1.0, dodge=0.0, tank_id="enemy_1")

        self.physics.player_tanks = [flame_shooter, ally]
        self.physics.enemy_tanks = [enemy]

        # 1. 直接在其自身坐标 (200, 200) 处爆炸，shooter 为 flame_shooter
        bullet = Bullet(200, 200, direction=None, speed=0, size=10, camp=Camp.PLAYER,
                        accuracy=1.0, splash_radius=60.0, friendly_fire=1,
                        damage=2, shooter=flame_shooter)
        self.physics.explode_bullet(bullet, 200, 200)

        # 验证：
        # - flame_shooter (shooter) 生命值保持不变 (不误伤自己)
        # - ally (友军) 受到 2 点伤害 (因 friendly_fire=1)
        # - enemy (敌军) 受到 2 点伤害
        self.assertEqual(flame_shooter.health, 10, "Shooter must not damage itself in splash AoE!")
        self.assertEqual(ally.health, 8, "Ally in range should take damage when friendly_fire=1")
        self.assertEqual(enemy.health, 8, "Enemy in range should take damage")

        # 2. 通过 update_bullets 测试
        flame_shooter.fire_cooldown = 0
        bullet2 = self.physics.spawn_bullet(flame_shooter, bullet_speed=5.0, bullet_size=10, angle=0.0)
        self.physics.update_bullets()
        self.assertEqual(flame_shooter.health, 10)

    def test_reworked_tank_configs(self):
        """验证重做后的灰熊、天启与新增加的喷火坦克配置"""
        # 灰熊
        grizzly = TankConfig.from_json("tank_configs/grizzly_tank.json")
        self.assertEqual(grizzly.name, "Grizzly Tank")
        self.assertEqual(grizzly.accuracy, 0.9)
        self.assertEqual(grizzly.dodge, 0.25)
        self.assertEqual(grizzly.splash_radius, 0.0)
        self.assertEqual(grizzly.friendly_fire, 0)

        # 天启
        apoc = TankConfig.from_json("tank_configs/apocalypse_tank.json")
        self.assertEqual(apoc.name, "Apocalypse Tank")
        self.assertEqual(apoc.accuracy, 0.85)
        self.assertEqual(apoc.dodge, 0.05)
        self.assertGreater(apoc.splash_radius, 0.0)
        self.assertEqual(apoc.friendly_fire, 0)

        # 喷火坦克
        flame = TankConfig.from_json("tank_configs/flame_tank.json")
        self.assertEqual(flame.name, "Flame Tank")
        self.assertEqual(flame.accuracy, 0.95)
        self.assertGreater(flame.splash_radius, 0.0)
        self.assertEqual(flame.friendly_fire, 1)

    def test_attribute_overrides_in_mission_loader(self):
        """测试 mission json 能够 overwrite 单位模板的任意属性 (health, speed, accuracy, splash_radius 等)"""
        mission_dict = {
            "name": "Custom Overwrite Mission",
            "map_file": "maps/level_01.json",
            "player_units": [
                {
                    "id": "hero_grizzly",
                    "config_file": "tank_configs/grizzly_tank.json",
                    "spawn": {"x": 2, "y": 2},
                    "health": 25,
                    "speed": 6.8,
                    "accuracy": 0.99,
                    "dodge": 0.6,
                    "splash_radius": 40.0,
                    "friendly_fire": 1,
                    "custom_stat": "super_shield"
                }
            ],
            "enemies": [
                {
                    "id": "boss_apoc",
                    "config_file": "tank_configs/apocalypse_tank.json",
                    "spawn": {"x": 5, "y": 5},
                    "health": 99,
                    "accuracy": 0.77,
                    "splash_radius": 80.0
                }
            ]
        }
        import json, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(mission_dict, f)
            temp_path = f.name

        try:
            mission = MissionLoader.load_from_file(temp_path)
            p_info = mission.player_units[0]
            self.assertEqual(p_info.extra_attrs.get("health"), 25)
            self.assertEqual(p_info.extra_attrs.get("speed"), 6.8)
            self.assertEqual(p_info.extra_attrs.get("accuracy"), 0.99)
            self.assertEqual(p_info.extra_attrs.get("dodge"), 0.6)
            self.assertEqual(p_info.extra_attrs.get("splash_radius"), 40.0)
            self.assertEqual(p_info.extra_attrs.get("friendly_fire"), 1)
            self.assertEqual(p_info.extra_attrs.get("custom_stat"), "super_shield")

            e_info = mission.enemies[0]
            self.assertEqual(e_info.extra_attrs.get("health"), 99)
            self.assertEqual(e_info.extra_attrs.get("accuracy"), 0.77)
            self.assertEqual(e_info.extra_attrs.get("splash_radius"), 80.0)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_attribute_overrides_in_api_and_ai_python(self):
        """测试网络 API 和 ai_python 能在 create_unit 与 edit_attr 中 overwrite 模板中任意属性"""
        # 1. API create_unit 重载任意属性
        resp = self.api.create_unit({
            "camp": "player",
            "unit_id": "custom_apoc_1",
            "config_file": "apocalypse_tank",
            "x": 100,
            "y": 100,
            "speed": 5.5,
            "health": 18,
            "accuracy": 0.98,
            "dodge": 0.45,
            "splash_radius": 65.0,
            "friendly_fire": 1,
            "custom_tag": "alpha_leader"
        })
        self.assertEqual(resp["status"], "ok")
        created_tank = next(t for t in self.physics.player_tanks if t.id == "custom_apoc_1")
        self.assertEqual(created_tank.speed, 5.5)
        self.assertEqual(created_tank.health, 18)
        self.assertEqual(created_tank.accuracy, 0.98)
        self.assertEqual(created_tank.dodge, 0.45)
        self.assertEqual(created_tank.splash_radius, 65.0)
        self.assertEqual(created_tank.friendly_fire, 1)
        self.assertEqual(getattr(created_tank, "custom_tag"), "alpha_leader")

        # 2. API edit_attr 动态修改属性
        resp_edit = self.api.edit_attr({
            "unit_ids": ["custom_apoc_1"],
            "attr": "splash_radius",
            "value": 120.0
        })
        self.assertEqual(resp_edit["status"], "ok")
        self.assertEqual(created_tank.splash_radius, 120.0)

        # 3. ai_python bridge
        bridge = TankScriptAPI(tank_id="custom_apoc_1", api_controller=self.api)
        resp_br = bridge.edit_attr("custom_apoc_1", "dodge", 0.8)
        self.assertEqual(resp_br["status"], "ok")
        self.assertEqual(created_tank.dodge, 0.8)

    def test_force_attack_ground_mechanic(self):
        """测试对地强制攻击地块操作（限范围伤害单位）：Dispatcher、API 与 ai_python 协同"""
        # 1. 灰熊坦克 (splash_radius = 0) 不能进行强制对地攻击
        grizzly = Tank(100, 100, size=30, camp=Camp.PLAYER, splash_radius=0.0, tank_id="g1")
        # 2. 天启坦克 (splash_radius = 48) 可以进行强制对地攻击
        apoc = Tank(150, 150, size=32, camp=Camp.PLAYER, splash_radius=48.0, tank_id="a1")
        self.physics.player_tanks = [grizzly, apoc]
        self.dispatcher.register_tank(grizzly)
        self.dispatcher.register_tank(apoc)

        # Dispatcher issue_attack_ground
        dispatched = self.dispatcher.issue_attack_ground([grizzly, apoc], 300, 300)
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(dispatched[0].id, "a1")
        self.assertIsInstance(self.dispatcher.tank_commands["a1"], AttackGroundCommand)
        self.assertIsNone(self.dispatcher.tank_commands["g1"])

        # API command_attack_ground
        api_resp = self.api.command_attack_ground({"unit_ids": ["g1"], "x": 200, "y": 200})
        # 单独让无范围伤害单位对地攻击应报错或提示无有效单位
        self.assertEqual(api_resp["status"], "error")

        api_resp2 = self.api.command_attack_ground({"unit_ids": ["a1"], "x": 250, "y": 250})
        self.assertEqual(api_resp2["status"], "ok")
        self.assertEqual(api_resp2["command"], "command_attack_ground")

        # ai_python bridge attack_ground
        bridge = TankScriptAPI(tank_id="a1", api_controller=self.api)
        br_resp = bridge.attack_ground(180, 180)
        self.assertEqual(br_resp["status"], "ok")
        self.assertEqual(self.dispatcher.tank_commands["a1"].target_x, 180.0)

        # 瓦片坐标 attack_tile
        br_resp_tile = bridge.attack_tile(col=3, row=4)
        self.assertEqual(br_resp_tile["status"], "ok")
        # 3 * 40 + 20 = 140, 4 * 40 + 20 = 180
        self.assertEqual(self.dispatcher.tank_commands["a1"].target_x, 140.0)
        self.assertEqual(self.dispatcher.tank_commands["a1"].target_y, 180.0)

    def test_attack_range_preset_behavior(self):
        """测试单位默认预设行为：当被攻击对象刚好进入自己射程后就不继续前进，只有出了射程才追击前进"""
        from command.commands import AttackTargetCommand
        from ai.tactics import HunterTactic

        # 1. 测试 AttackTargetCommand
        # 目标处于 (400, 100)，生命值 100
        target = Tank(x=400, y=100, size=30, camp=Camp.ENEMY, health=100, tank_id="target_dummy")
        # 攻击者处于 (100, 100)，射程设定为 200 像素
        attacker = Tank(x=100, y=100, size=30, speed=4.0, camp=Camp.PLAYER, health=10,
                        attack_range=200.0, tank_id="ranged_attacker")
        self.physics.player_tanks = [attacker]
        self.physics.enemy_tanks = [target]

        cmd = AttackTargetCommand(target)

        # 初始距离为 300 > 200 (超出射程)，坦克应追击前进
        for _ in range(35):
            cmd.execute(attacker, self.physics, self.game_map)
            self.physics.update()

        # 攻击者应当向前推进，但绝不会贴脸撞向 target (不会超过 400 - 200 = 200)
        self.assertGreater(attacker.x, 100.0, "超出射程时应主动追击前进")
        # 验证刚好到达射程边缘 (dist <= 200) 时立即停止前进
        curr_dist = target.x - attacker.x
        self.assertLessEqual(curr_dist, 204.0, "进入射程后应及时刹停")
        stopped_x = attacker.x

        # 持续运行 20 帧，目标仍在射程内：攻击者坐标保持不变，不再继续前进，但持续开火
        initial_bullets = len(self.physics.bullets)
        for _ in range(20):
            cmd.execute(attacker, self.physics, self.game_map)
            self.physics.update()

        self.assertAlmostEqual(attacker.x, stopped_x, delta=1.0, msg="目标在射程内时不应继续前进")

        # 将目标后撤至 (600, 100) (使目标移出射程，距离扩大为 400 > 200)
        target.x = 600
        # 再次执行：只有出了射程才恢复追击前进
        for _ in range(15):
            cmd.execute(attacker, self.physics, self.game_map)
            self.physics.update()

        self.assertGreater(attacker.x, stopped_x + 5.0, "目标脱离射程后应恢复追击推进")

        # 2. 测试内置 AI HunterTactic
        hunter_cfg = TankConfig(attack_range=150.0)
        hunter_tank = Tank(x=100, y=100, size=30, camp=Camp.ENEMY, attack_range=150.0, tank_id="hunter_ai")
        tactic = HunterTactic(hunter_cfg)

        # 玩家在 (200, 100)，距离 100 <= 150 (在射程内且视线畅通)
        player_in_range = Tank(x=200, y=100, size=30, camp=Camp.PLAYER, health=10, tank_id="player_in_range")
        self.physics.set_player_tank(player_in_range)

        move_dir, should_fire = tactic.decide(hunter_tank, self.physics, self.game_map)
        self.assertIsNone(move_dir, "在射程内且视线畅通时，HunterTactic 移动方向应为 None (停止前进)")
        self.assertTrue(should_fire, "在射程内且视线畅通时，应执行开火")

        # 玩家后撤至 (400, 100)，距离 300 > 150 (脱离射程)
        player_in_range.x = 400
        move_dir2, should_fire2 = tactic.decide(hunter_tank, self.physics, self.game_map)
        self.assertIsNotNone(move_dir2, "目标脱离射程后，HunterTactic 必须给出机动追击方向")

if __name__ == "__main__":
    unittest.main()
