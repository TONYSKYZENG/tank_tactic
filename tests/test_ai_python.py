import unittest
import time
import json
import threading
from pathlib import Path
from map_loader.models import GameMap, TileType
from mission_loader.loader import MissionLoader
from physics.entities import Tank, Camp, Direction, Rect
from physics.engine import PhysicsEngine
from grouping.selection import SelectionManager
from command.dispatcher import CommandDispatcher
from command.tactics_mode import TacticMode
from api.controller import GameAPIController
from ai_python.bridge import TankScriptAPI
from ai_python.manager import AIScriptManager

class MockGameContext:
    def __init__(self):
        self.game_map = GameMap(name="test_map", cols=20, rows=20, tile_size=32, grid=[[TileType.EMPTY for _ in range(20)] for _ in range(20)])
        self.physics_engine = PhysicsEngine(self.game_map, fog_of_war_enabled=True, limited_ammo_enabled=True)
        self.command_dispatcher = CommandDispatcher()

        self.p1 = Tank(x=100, y=100, size=32, speed=3.0, camp=Camp.PLAYER, tank_id="player_1", controllable=True)
        self.p_auto = Tank(x=150, y=100, size=32, speed=3.0, camp=Camp.PLAYER, tank_id="player_bravo", controllable=False, ai_script="ai_python/ally_escort.py")
        self.e1 = Tank(x=400, y=400, size=32, speed=3.0, camp=Camp.ENEMY, tank_id="enemy_1", controllable=False, ai_script="ai_python/boss_hunter.py")

        self.physics_engine.add_player_tank(self.p1)
        self.physics_engine.add_player_tank(self.p_auto)
        self.physics_engine.add_enemy_tank(self.e1)

        self.command_dispatcher.register_tank(self.p1)
        self.command_dispatcher.register_tank(self.p_auto)
        self.command_dispatcher.register_tank(self.e1)

        self.is_paused = False
        self.game_over = False
        self.game_victory = False
        self.ai_script_manager = None

    def pause(self):
        self.is_paused = True
        if self.ai_script_manager:
            self.ai_script_manager.pause()

    def resume(self):
        self.is_paused = False
        if self.ai_script_manager:
            self.ai_script_manager.resume()


class TestAIControllability(unittest.TestCase):
    def setUp(self):
        self.mgr = SelectionManager()
        self.p_controllable = Tank(x=100, y=100, camp=Camp.PLAYER, tank_id="p1", controllable=True)
        self.p_uncontrollable = Tank(x=150, y=100, camp=Camp.PLAYER, tank_id="p2", controllable=False)
        self.all_tanks = [self.p_controllable, self.p_uncontrollable]

    def test_single_selection(self):
        # 可控单位可以单选
        self.mgr.select_single(self.p_controllable)
        self.assertEqual(self.mgr.selected_tanks, [self.p_controllable])
        self.assertEqual(self.mgr.micro_tank, self.p_controllable)

        # 不可控友军单选被忽略
        self.mgr.select_single(self.p_uncontrollable)
        self.assertEqual(self.mgr.selected_tanks, [self.p_controllable])

    def test_box_selection(self):
        # 拉大框框选包含两辆战车
        box = Rect(0, 0, 500, 500)
        self.mgr.select_box(box, self.all_tanks)
        # 仅可控战车被选中，不可控友军被排除
        self.assertIn(self.p_controllable, self.mgr.selected_tanks)
        self.assertNotIn(self.p_uncontrollable, self.mgr.selected_tanks)
        self.assertEqual(len(self.mgr.selected_tanks), 1)

    def test_select_all(self):
        self.mgr.select_all(self.all_tanks)
        self.assertIn(self.p_controllable, self.mgr.selected_tanks)
        self.assertNotIn(self.p_uncontrollable, self.mgr.selected_tanks)

    def test_cycle_micro_tank(self):
        # 循环微操候选列表过滤掉不可控友军
        t = self.mgr.cycle_micro_tank(self.all_tanks)
        self.assertEqual(t, self.p_controllable)
        # 再次循环切换，仍然只有 p_controllable
        t2 = self.mgr.cycle_micro_tank(self.all_tanks)
        self.assertEqual(t2, self.p_controllable)


class TestTankScriptAPITranslation(unittest.TestCase):
    def setUp(self):
        self.ctx = MockGameContext()
        self.api_controller = GameAPIController(self.ctx)
        self.stop_event = threading.Event()
        self.script_api = TankScriptAPI("player_bravo", self.api_controller, self.stop_event)

    def test_api_layer_translation_move(self):
        # 调用 move 会生成 JSON 请求分发给 api_controller
        res = self.script_api.move(200.0, 300.0)
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("command"), "command_move")
        self.assertEqual(res.get("destination"), {"x": 200.0, "y": 300.0})

    def test_api_layer_translation_fire(self):
        self.ctx.p_auto.fire_cooldown = 0
        self.ctx.p_auto.ammo = 10
        res = self.script_api.fire("UP")
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("player_bravo", res.get("fired_units", []))

    def test_api_layer_translation_status_and_report(self):
        status = self.script_api.get_status()
        self.assertEqual(status.get("id"), "player_bravo")
        self.assertEqual(status.get("controllable"), False)
        self.assertEqual(status.get("camp"), "player")

    def test_api_omniscient_intelligence(self):
        # 全知全能获取对手列表 (敌军 enemy_1)
        opponents = self.script_api.get_opponents()
        self.assertEqual(len(opponents), 1)
        self.assertEqual(opponents[0]["id"], "enemy_1")

        # 全知全能获取友军列表 (player_1)
        allies = self.script_api.get_allies()
        self.assertEqual(len(allies), 1)
        self.assertEqual(allies[0]["id"], "player_1")


class TestAIScriptManagerExecution(unittest.TestCase):
    def setUp(self):
        self.ctx = MockGameContext()
        self.api_controller = GameAPIController(self.ctx)
        self.manager = AIScriptManager()

    def tearDown(self):
        self.manager.stop_all()

    def test_start_and_stop_script_threads(self):
        all_tanks = self.ctx.physics_engine.player_tanks + self.ctx.physics_engine.enemy_tanks
        self.manager.start_scripts(all_tanks, self.api_controller, Path("."))

        # 检查是否为 player_bravo 和 enemy_1 拉起了工作线程
        self.assertIn("player_bravo", self.manager._threads)
        self.assertIn("enemy_1", self.manager._threads)
        # player_1 是可控单位，不应当拉起脚本线程
        self.assertNotIn("player_1", self.manager._threads)

        # 线程正在后台独立运行
        time.sleep(0.1)
        self.assertTrue(self.manager._threads["player_bravo"].is_alive())
        self.assertTrue(self.manager._threads["enemy_1"].is_alive())

        # 优雅终结所有线程
        self.manager.stop_all()
        time.sleep(0.1)
        self.assertEqual(len(self.manager._threads), 0)

    def test_script_sleep_and_stop_condition(self):
        stop_event = threading.Event()
        api = TankScriptAPI("player_bravo", self.api_controller, stop_event)

        # 存活时 should_stop 为 False
        self.assertFalse(api.should_stop())

        # 当 tank 阵亡时，should_stop 自动判定为 True
        self.ctx.p_auto.alive = False
        self.assertTrue(api.should_stop())

        # 测试快速中断睡眠
        t0 = time.time()
        stop_event.set()
        api.sleep(5.0)  # 本应休眠 5 秒，但因 stop_event 瞬间退出
        elapsed = time.time() - t0
        self.assertLess(elapsed, 0.5)

    def test_pause_and_resume_freezes_ai(self):
        self.ctx.ai_script_manager = self.manager
        all_tanks = self.ctx.physics_engine.player_tanks + self.ctx.physics_engine.enemy_tanks
        self.manager.start_scripts(all_tanks, self.api_controller, Path("."))

        # 初始状态未暂停
        self.assertFalse(self.manager.is_paused())

        # 调用 API pause 暂停
        res_pause = json.loads(self.api_controller.handle_request(json.dumps({"action": "api.pause"})))
        self.assertEqual(res_pause.get("status"), "ok")
        self.assertTrue(self.ctx.is_paused)
        self.assertTrue(self.manager.is_paused())

        # 暂停状态下允许执行移动与开火 API，但不立刻生成子弹或物理位移，而是暂存待恢复后立刻执行
        res_move = json.loads(self.api_controller.handle_request(json.dumps({"action": "command_move", "params": {"unit_ids": ["player_1"], "x": 200, "y": 200}})))
        self.assertEqual(res_move.get("status"), "ok")
        self.assertTrue(res_move.get("queued", False))

        res_fire = json.loads(self.api_controller.handle_request(json.dumps({"action": "command_fire", "params": {"unit_ids": ["player_1"]}})))
        self.assertEqual(res_fire.get("status"), "ok")
        self.assertTrue(res_fire.get("queued", False))
        # 暂停中，子弹尚未发射进入物理引擎
        self.assertEqual(len(self.ctx.physics_engine.bullets), 0)

        # 脚本 API 也会感知暂停
        stop_event = threading.Event()
        api = TankScriptAPI("player_bravo", self.api_controller, stop_event, script_manager=self.manager)
        self.assertTrue(api.is_engine_paused())

        # 调用 API resume 恢复
        res_resume = json.loads(self.api_controller.handle_request(json.dumps({"action": "api.resume"})))
        self.assertEqual(res_resume.get("status"), "ok")
        self.assertFalse(self.ctx.is_paused)
        self.assertFalse(self.manager.is_paused())
        self.assertFalse(api.is_engine_paused())

        # 恢复后，暂停期间暂存的开火指令立刻执行完毕
        self.assertEqual(len(self.ctx.physics_engine.bullets), 1)


class TestMissionConfiguration(unittest.TestCase):
    def test_mission_01_loading(self):
        mission_path = Path("missions/mission_01.json")
        mission = MissionLoader.load_from_file(mission_path)

        # 验证 player_bravo 为不可控友军并配置了战术脚本
        bravo = next((p for p in mission.player_units if p.id == "player_bravo"), None)
        self.assertIsNotNone(bravo)
        self.assertFalse(bravo.controllable)
        self.assertEqual(bravo.ai_script, "ai_python/ally_escort.py")

        # 验证敌军单位配置了对应战术脚本
        hunter = next((e for e in mission.enemies if e.id == "e_hunter_1"), None)
        self.assertIsNotNone(hunter)
        self.assertEqual(hunter.ai_script, "ai_python/boss_hunter.py")

        fast = next((e for e in mission.enemies if e.id == "e_fast_1"), None)
        self.assertIsNotNone(fast)
        self.assertEqual(fast.ai_script, "ai_python/charge_assault.py")

        patrol = next((e for e in mission.enemies if e.id == "e_patrol_1"), None)
        self.assertIsNotNone(patrol)
        self.assertEqual(patrol.ai_script, "ai_python/patrol_scout.py")


class TestSmartPathfindingAndBreaching(unittest.TestCase):
    def setUp(self):
        # 构建 10x10 测试地图：
        # 第 5 列 (col=5) 的 0~4 行为砖墙 (BRICK)
        # 5~9 行默认为空地，可供绕行
        self.grid = [[TileType.EMPTY for _ in range(10)] for _ in range(10)]
        for r in range(5):
            self.grid[r][5] = TileType.BRICK
        self.game_map = GameMap(name="breach_test", cols=10, rows=10, tile_size=32, grid=self.grid)

    def test_infinite_ammo_auto_breach(self):
        from command.pathfinder import GridPathfinder
        pf = GridPathfinder(self.game_map)

        # 无限弹药坦克从 (0, 0) 移动到 (9, 0)
        tank = Tank(0, 0, size=32, ammo=-1)
        path, ammo_needed = pf.find_path(0, 0, 9 * 32, 0, tank=tank, limited_ammo_enabled=True)

        # 无限弹药时：自动破障，直接选择炸开 1 块砖的最近直达路径
        self.assertEqual(ammo_needed, 1)
        self.assertTrue(len(path) > 0)

    def test_limited_ammo_saves_ammo_by_detour(self):
        from command.pathfinder import GridPathfinder
        pf = GridPathfinder(self.game_map)

        # 有限弹药坦克 (ammo=5) 从 (0, 0) 移动到 (9, 0)
        tank = Tank(0, 0, size=32, ammo=5)
        path, ammo_needed = pf.find_path(0, 0, 9 * 32, 0, tank=tank, limited_ammo_enabled=True)

        # 有限弹药时：优先寻找最省弹药办法，自动绕过障碍，消耗 0 发弹药
        self.assertEqual(ammo_needed, 0)
        # 路径必定经过没有砖块的下方空地 (row >= 5)
        has_detour = any(py >= 5 * 32 for px, py in path)
        self.assertTrue(has_detour)

    def test_limited_ammo_minimum_breach_when_detour_blocked(self):
        from command.pathfinder import GridPathfinder
        # 将下方绕行空地 (5~9 行) 全部堵上不可摧毁的铁墙 (STEEL)
        for r in range(5, 10):
            self.grid[r][5] = TileType.STEEL
        blocked_map = GameMap(name="blocked_test", cols=10, rows=10, tile_size=32, grid=self.grid)
        pf = GridPathfinder(blocked_map)

        # 此时无法绕行，只能破障：有限弹药坦克自动计算破损砖块绝对最少的方案 (1 块砖)
        tank = Tank(0, 0, size=32, ammo=5)
        path, ammo_needed = pf.find_path(0, 0, 9 * 32, 0, tank=tank, limited_ammo_enabled=True)
        self.assertEqual(ammo_needed, 1)

    def test_zero_ammo_cannot_breach(self):
        from command.pathfinder import GridPathfinder
        for r in range(5, 10):
            self.grid[r][5] = TileType.STEEL
        blocked_map = GameMap(name="blocked_test2", cols=10, rows=10, tile_size=32, grid=self.grid)
        pf = GridPathfinder(blocked_map)

        # 弹药为 0 时，绝不尝试破障
        tank = Tank(0, 0, size=32, ammo=0)
        path, ammo_needed = pf.find_path(0, 0, 9 * 32, 0, tank=tank, limited_ammo_enabled=True)
        self.assertEqual(ammo_needed, 0)

    def test_tank_script_api_find_path(self):
        ctx = MockGameContext()
        api_ctrl = GameAPIController(ctx)
        stop_event = threading.Event()
        api = TankScriptAPI("player_bravo", api_ctrl, stop_event)

        res = api.find_path(200.0, 200.0)
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("waypoints", res)
        self.assertIn("ammo_needed", res)
        self.assertIn("step_count", res)

    def test_move_command_auto_clears_obstacle_in_simulation(self):
        from command.commands import MoveCommand
        # 构建简单通道：坦克位于 (0, 0)，砖块位于 (1, 0)，目标位于 (2*32, 0)
        g = [[TileType.EMPTY for _ in range(5)] for _ in range(5)]
        g[0][1] = TileType.BRICK
        gm = GameMap(name="sim_breach", cols=5, rows=5, tile_size=32, grid=g)
        engine = PhysicsEngine(gm, fog_of_war_enabled=False, limited_ammo_enabled=True)

        tank = Tank(x=0, y=0, size=32, speed=3.0, ammo=-1)  # 无限弹药
        tank.fire_cooldown_max = 5
        tank.fire_cooldown = 0
        engine.add_player_tank(tank)

        cmd = MoveCommand(dest_x=2 * 32, dest_y=0, tolerance=4.0)

        # 模拟运行数帧：坦克开火将砖块摧毁并继续前行
        for _ in range(35):
            cmd.execute(tank, engine, gm)
            engine.update()
            tank.update_cooldown()

        # 砖块应已被成功轰破变为空地
        self.assertEqual(gm.get_tile(1, 0), TileType.EMPTY)
        # 坦克向前推进穿过原砖块区域
        self.assertGreater(tank.x, 10.0)

    def test_continuous_target_annihilation(self):
        """测试 AI 连续歼灭多个目标：歼灭第 1 个目标后，立即接续机动并歼灭第 2 个目标，杜绝原地发呆"""
        from command.dispatcher import CommandDispatcher
        from command.commands import AttackTargetCommand
        from map_loader.loader import MapLoader

        gm = MapLoader.load_from_file("maps/level_01.json")
        engine = PhysicsEngine(gm, fog_of_war_enabled=False, limited_ammo_enabled=False)
        dispatcher = CommandDispatcher()

        # 敌军猎杀者 (无限弹药)
        hunter = Tank(x=0.0, y=0.0, size=36, speed=2.2, camp=Camp.ENEMY, tank_id="e_test_hunter", ammo=-1)
        hunter.fire_cooldown_max = 20
        hunter.fire_cooldown = 0
        engine.add_enemy_tank(hunter)
        dispatcher.register_tank(hunter)

        # 玩家目标 1：雷达塔
        target1 = Tank(x=36.0, y=396.0, size=36, camp=Camp.PLAYER, tank_id="radar_tower", health=2)
        engine.add_player_tank(target1)

        # 玩家目标 2：要塞
        target2 = Tank(x=324.0, y=432.0, size=36, camp=Camp.PLAYER, tank_id="core_supply_base", health=2)
        engine.add_player_tank(target2)

        # 下达攻击目标 1
        dispatcher.issue_attack_target([hunter], target1, engine)

        target1_killed = False
        target2_killed = False

        # 运行模拟循环 (最多 600 帧)
        for frame in range(600):
            dispatcher.update(engine.player_tanks, None, False, engine, gm)
            engine.update()
            if not target1.alive and not target1_killed:
                target1_killed = True
            if not target2.alive:
                target2_killed = True
                break

        self.assertTrue(target1_killed, "目标 1 应已被击毁")
        self.assertTrue(target2_killed, "目标 1 阵亡后，AI 应自动接续并击毁目标 2")

    def test_diagonal_engagement_no_deadlock(self):
        """测试斜向近距对峙时不卡死、主动调整并开火击毁"""
        from command.commands import AttackTargetCommand

        g = [[TileType.EMPTY for _ in range(8)] for _ in range(8)]
        gm = GameMap(name="diagonal_test", cols=8, rows=8, tile_size=36, grid=g)
        engine = PhysicsEngine(gm, fog_of_war_enabled=False, limited_ammo_enabled=False)

        target = Tank(x=4 * 36, y=4 * 36, size=36, camp=Camp.PLAYER, health=1)
        # 放置在斜上方对角线相邻阵位 (非轴向对齐，无初始物理重叠)
        hunter = Tank(x=3 * 36, y=3 * 36, size=36, speed=2.5, camp=Camp.ENEMY)
        hunter.fire_cooldown_max = 10
        hunter.fire_cooldown = 0
        engine.add_player_tank(target)
        engine.add_enemy_tank(hunter)

        cmd = AttackTargetCommand(target)
        for _ in range(60):
            cmd.execute(hunter, engine, gm)
            engine.update()
            if not target.alive:
                break

        self.assertFalse(target.alive, "斜向对峙应主动走位瞄准并击毁目标，杜绝斜角死锁")

    def test_lane_alignment_no_wall_sticking(self):
        """测试坦克在走廊通道中转弯并沿通道行进，连续中心线吸附防止卡入方块边缘"""
        # 构建 L 形单格通道：(0,0)->(0,3)->(3,3)，周围均为钢墙
        g = [[TileType.STEEL for _ in range(5)] for _ in range(5)]
        g[0][0] = TileType.EMPTY
        g[1][0] = TileType.EMPTY
        g[2][0] = TileType.EMPTY
        g[3][0] = TileType.EMPTY
        g[3][1] = TileType.EMPTY
        g[3][2] = TileType.EMPTY
        g[3][3] = TileType.EMPTY

        gm = GameMap(name="corridor_test", cols=5, rows=5, tile_size=36, grid=g)
        engine = PhysicsEngine(gm, fog_of_war_enabled=False, limited_ammo_enabled=True)

        tank = Tank(x=0.0, y=0.0, size=36, speed=2.2, camp=Camp.PLAYER)
        engine.add_player_tank(tank)

        from command.commands import MoveCommand
        cmd = MoveCommand(dest_x=3 * 36, dest_y=3 * 36, tolerance=4.0)

        for _ in range(150):
            finished = cmd.execute(tank, engine, gm)
            engine.update()
            if finished:
                break

        # 验证坦克顺利穿过通道与拐角抵达终点，未卡在拐角砖墙内
        self.assertAlmostEqual(tank.x, 3 * 36, delta=6.0)
        self.assertAlmostEqual(tank.y, 3 * 36, delta=6.0)


class TestUncontrollableFriendlyUnits(unittest.TestCase):
    """
    测试不可控己方单位的完整行为准则：
    1. 能被 list 接口正常列出 (list_current_unit_id / list_allies)；
    2. 在所有需要共享视野的地方（迷雾消除、敌军发现、集火目标探测等）共享视野；
    3. 外部尝试命令它们时不报错 (status='ok')，但命令本身不被执行；
    4. 这些单位自身的独立脚本能自主下达并执行命令。
    """

    def setUp(self):
        self.ctx = MockGameContext()
        self.api_controller = GameAPIController(self.ctx)
        self.stop_event = threading.Event()
        self.script_api = TankScriptAPI("player_bravo", self.api_controller, self.stop_event)

    def test_uncontrollable_units_listed(self):
        """1. 不能被操控的我方单位也能被 list 出来"""
        resp = json.loads(self.api_controller.handle_request(json.dumps({
            "action": "api.list_current_unit_id"
        })))
        self.assertEqual(resp["status"], "ok")
        unit_ids = resp["unit_ids"].split(",")
        self.assertIn("player_bravo", unit_ids)
        self.assertIn("player_1", unit_ids)

        resp_allies = json.loads(self.api_controller.handle_request(json.dumps({
            "action": "api.list_allies",
            "unit_id": "player_1"
        })))
        self.assertEqual(resp_allies["status"], "ok")
        ally_ids = [u["id"] for u in resp_allies["units"]]
        self.assertIn("player_bravo", ally_ids)

    def test_uncontrollable_units_share_vision(self):
        """2. 不可操控我方单位在所有需要共享视野的地方共享视野"""
        # 将迷雾开启
        self.ctx.physics_engine.fog_of_war_enabled = True

        # player_1 在 (100, 100), vision_size=200 -> 视野范围 [0, 200] x [0, 200]
        # player_bravo 在 (150, 100), vision_size=260 -> 视野范围 [20, 280] x [-30, 230]
        # 在 (250, 100) 放置一个敌军：该位置超出 player_1 视野 (100+100=200)，但处于 player_bravo 视野内！
        far_enemy = Tank(x=250, y=100, size=32, speed=2.0, camp=Camp.ENEMY, tank_id="far_enemy", visibility=1.0)
        self.ctx.physics_engine.add_enemy_tank(far_enemy)

        # 帧更新视线
        self.ctx.physics_engine.update_vision_and_stealth()

        # 验证该敌军被 player_bravo 共享的视野探测到
        self.assertTrue(far_enemy.is_spotted)
        self.assertTrue(self.ctx.physics_engine.is_enemy_visible(far_enemy))
        self.assertIn(far_enemy, self.ctx.physics_engine.get_visible_enemies())

        # 验证外部视野 list_enemy_curr 也能通过共享视野探知该敌军
        resp_enemy = json.loads(self.api_controller.handle_request(json.dumps({
            "action": "api.list_enemy_curr"
        })))
        self.assertIn("far_enemy", resp_enemy["unit_ids"])

        # 验证 player_1 (可控单位) 也可以直接集火该共享视野发现的敌军
        cmd_atk = json.loads(self.api_controller.handle_request(json.dumps({
            "action": "api.command_attack",
            "unit_ids": "player_1",
            "target_id": "far_enemy"
        })))
        self.assertEqual(cmd_atk["status"], "ok")
        self.assertIn("player_1", cmd_atk["affected_units"])

    def test_external_command_on_uncontrollable_unit_does_not_execute(self):
        """3. 外部尝试命令不可控单位时不报错，但命令本身不执行"""
        # 3.1 外部下发移动指令给 player_bravo
        res_move = json.loads(self.api_controller.handle_request(json.dumps({
            "action": "api.command_move",
            "unit_ids": "player_bravo",
            "x": 500.0,
            "y": 500.0
        })))
        self.assertEqual(res_move["status"], "ok")
        self.assertEqual(res_move["affected_units"], [])
        self.assertIsNone(self.ctx.command_dispatcher.tank_commands.get("player_bravo"))

        # 3.2 外部下发集火指令给 player_bravo
        res_attack = json.loads(self.api_controller.handle_request(json.dumps({
            "action": "api.command_attack",
            "unit_ids": "player_bravo",
            "target_id": "enemy_1"
        })))
        self.assertEqual(res_attack["status"], "ok")
        self.assertEqual(res_attack["affected_units"], [])
        self.assertIsNone(self.ctx.command_dispatcher.tank_commands.get("player_bravo"))

        # 3.3 外部下发开火指令给 player_bravo
        bullet_count = len(self.ctx.physics_engine.bullets)
        res_fire = json.loads(self.api_controller.handle_request(json.dumps({
            "action": "api.command_fire",
            "unit_ids": "player_bravo"
        })))
        self.assertEqual(res_fire["status"], "ok")
        self.assertEqual(res_fire["fired_units"], [])
        self.assertEqual(len(self.ctx.physics_engine.bullets), bullet_count)

        # 3.4 外部下发战术姿态给 player_bravo
        res_tactic = json.loads(self.api_controller.handle_request(json.dumps({
            "action": "api.command_set_tactic",
            "unit_ids": "player_bravo",
            "tactic": "aggressive"
        })))
        self.assertEqual(res_tactic["status"], "ok")
        self.assertEqual(res_tactic["affected_units"], [])

        # 3.5 外部全选下发指令 (player_1 和 player_bravo)
        res_batch = json.loads(self.api_controller.handle_request(json.dumps({
            "action": "api.command_move",
            "unit_ids": "player_1,player_bravo",
            "x": 300.0,
            "y": 300.0
        })))
        self.assertEqual(res_batch["status"], "ok")
        self.assertEqual(res_batch["affected_units"], ["player_1"])
        # player_1 被下达了指令，player_bravo 没有
        self.assertIsNotNone(self.ctx.command_dispatcher.tank_commands.get("player_1"))
        self.assertIsNone(self.ctx.command_dispatcher.tank_commands.get("player_bravo"))

    def test_own_script_can_command_uncontrollable_unit(self):
        """4. 不可控单位执行自己预定的独立战术脚本"""
        # 由其内部脚本发出的指令正常执行
        res_move = self.script_api.move(350.0, 350.0)
        self.assertEqual(res_move["status"], "ok")
        self.assertEqual(res_move["affected_units"], ["player_bravo"])
        self.assertIsNotNone(self.ctx.command_dispatcher.tank_commands.get("player_bravo"))

        # 由其内部脚本发出的开火指令正常执行
        bullet_count = len(self.ctx.physics_engine.bullets)
        self.ctx.p_auto.fire_cooldown = 0
        self.ctx.p_auto.ammo = 10
        res_fire = self.script_api.fire("UP")
        self.assertEqual(res_fire["status"], "ok")
        self.assertEqual(res_fire["fired_units"], ["player_bravo"])
        self.assertEqual(len(self.ctx.physics_engine.bullets), bullet_count + 1)


if __name__ == "__main__":
    unittest.main()
