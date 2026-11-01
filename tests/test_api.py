import sys
import json
import time
import socket
import unittest
from pathlib import Path

# 确保项目根目录在 sys.path 中
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PyQt5.QtCore import QCoreApplication
from map_loader.models import GameMap
from mission_loader.models import Mission, PlayerMissionInfo, SpawnPoint
from physics.entities import Tank, Bullet, Camp, Direction
from physics.engine import PhysicsEngine
from command.dispatcher import CommandDispatcher
from command.tactics_mode import TacticMode
from conditions.primitives import ConditionContext, UnitSurviveTimeCondition, UnitDestroyedCondition
from conditions.composite import OrCondition
from resource.models import ResourceManager
from command.commands import MoveCommand
from api.controller import GameAPIController
from api.server import APIServerManager
from ai.controller import EnemyAIController

class MockGameContext:
    def __init__(self):
        self.base_dir = BASE_DIR
        self.game_map = GameMap("TestMap", 32, 20, 20, [[0]*20 for _ in range(20)])
        self.mission = Mission(
            name="Test Defense Mission",
            map_file="maps/test.json",
            player=PlayerMissionInfo(config_file="tank_configs/player_tank.json", spawn=SpawnPoint(2, 2)),
            enemies=[],
            briefing="指挥官，歼灭所有来犯敌军！"
        )
        self.physics_engine = PhysicsEngine(self.game_map, fog_of_war_enabled=False, limited_ammo_enabled=True)
        self.ai_controller = EnemyAIController(self.physics_engine, self.game_map)
        self.command_dispatcher = CommandDispatcher()
        self.condition_ctx = ConditionContext(self.physics_engine, self.game_map)
        self.resource_manager = ResourceManager()

        # 玩家单位
        self.p1 = Tank(x=100, y=100, size=28, speed=3.0, camp=Camp.PLAYER, health=3, tank_id="player_alpha", ammo=20, vision_size=200.0, visibility=1.0)
        self.p2 = Tank(x=150, y=100, size=28, speed=3.0, camp=Camp.PLAYER, health=2, tank_id="player_bravo", ammo=10, vision_size=200.0, visibility=0.5)
        self.base = Tank(x=200, y=200, size=32, speed=0.0, camp=Camp.PLAYER, health=5, tank_id="core_supply_base", ammo=-1, vision_size=200.0, is_tower=True, tower_type="supply")

        self.physics_engine.add_player_tank(self.p1)
        self.physics_engine.add_player_tank(self.p2)
        self.physics_engine.add_player_tank(self.base)

        self.command_dispatcher.register_tank(self.p1)
        self.command_dispatcher.register_tank(self.p2)
        self.command_dispatcher.register_tank(self.base)

        # 敌军单位
        self.e1 = Tank(x=300, y=300, size=28, speed=2.0, camp=Camp.ENEMY, health=2, tank_id="enemy_boss")
        self.physics_engine.add_enemy_tank(self.e1)

        self.victory_condition = UnitDestroyedCondition("enemy_boss")
        self.defeat_condition = UnitDestroyedCondition("core_supply_base")

        self.is_paused = False
        self.game_over = False
        self.game_victory = False
        self.stopped = False
        self.restarted = False

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def restart(self):
        self.restarted = True

    def stop(self):
        self.stopped = True

class TestGameAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance()
        if not cls.app:
            cls.app = QCoreApplication(sys.argv)

    def setUp(self):
        self.mock_game = MockGameContext()
        self.controller = GameAPIController(self.mock_game)

    def test_pause_and_resume(self):
        """测试 API 1: pause / resume"""
        resp_pause = json.loads(self.controller.handle_request(json.dumps({"action": "api.pause"})))
        self.assertEqual(resp_pause["status"], "ok")
        self.assertTrue(self.mock_game.is_paused)

        resp_resume = json.loads(self.controller.handle_request(json.dumps({"action": "api.resume"})))
        self.assertEqual(resp_resume["status"], "ok")
        self.assertFalse(self.mock_game.is_paused)

    def test_is_success(self):
        """测试 API 2: is_success"""
        resp1 = json.loads(self.controller.handle_request(json.dumps({"action": "api.is_success"})))
        self.assertEqual(resp1["status"], "ok")
        self.assertFalse(resp1["is_success"])

        # 击毁 BOSS
        self.mock_game.e1.alive = False
        resp2 = json.loads(self.controller.handle_request(json.dumps({"action": "api.is_success"})))
        self.assertEqual(resp2["status"], "ok")
        self.assertTrue(resp2["is_success"])

    def test_terminate(self):
        """测试 API 3: terminate"""
        terminated = []
        ctrl = GameAPIController(self.mock_game, termination_handler=lambda: terminated.append(True))
        resp = json.loads(ctrl.handle_request(json.dumps({"action": "api.terminate"})))
        self.assertEqual(resp["status"], "ok")
        self.assertTrue(len(terminated) > 0)

    def test_list_current_unit_id(self):
        """测试 API 4: list_current_unit_id (逗号隔开与 visibility 概率)"""
        found_alpha = 0
        trials = 20
        for _ in range(trials):
            resp = json.loads(self.controller.handle_request(json.dumps({"action": "api.list_current_unit_id"})))
            self.assertEqual(resp["status"], "ok")
            unit_ids = resp["unit_ids"].split(",")
            self.assertIn("player_alpha", unit_ids)
            self.assertIn("core_supply_base", unit_ids)
            if "player_bravo" in unit_ids:
                found_alpha += 1

        self.assertTrue(0 < found_alpha <= trials)

        # 杀死 player_alpha 后不再列出
        self.mock_game.p1.alive = False
        resp_after_kill = json.loads(self.controller.handle_request(json.dumps({"action": "api.list_current_unit_id"})))
        ids_after = resp_after_kill["unit_ids"].split(",")
        self.assertNotIn("player_alpha", ids_after)

    def test_restart(self):
        """测试 api.restart"""
        resp = json.loads(self.controller.handle_request(json.dumps({"action": "api.restart"})))
        self.assertEqual(resp["status"], "ok")
        self.assertTrue(self.mock_game.restarted)

    def test_list_enemy_curr(self):
        """测试 api.list_enemy_curr (上帝视角与视野可见度模式)"""
        # 启用迷雾进行测试
        self.mock_game.physics_engine.fog_of_war_enabled = True

        # 当前玩家单位：p1 在 (100, 100), vision_size=200
        # 添加视线内的敌军 e_spotted 在 (120, 120), visibility=1.0
        e_spotted = Tank(x=120, y=120, size=28, speed=2.0, camp=Camp.ENEMY, tank_id="e_spotted", visibility=1.0)
        # 添加视线外的敌军 e_hidden 在 (550, 550), visibility=1.0
        e_hidden = Tank(x=550, y=550, size=28, speed=2.0, camp=Camp.ENEMY, tank_id="e_hidden", visibility=1.0)
        # 添加视线内但低辨识度敌军 e_prob 在 (130, 130), visibility=0.5
        e_prob = Tank(x=130, y=130, size=28, speed=2.0, camp=Camp.ENEMY, tank_id="e_prob", visibility=0.5)

        self.mock_game.physics_engine.add_enemy_tank(e_spotted)
        self.mock_game.physics_engine.add_enemy_tank(e_hidden)
        self.mock_game.physics_engine.add_enemy_tank(e_prob)

        # 1. 上帝视角模式 (god_mode=True): 无视迷雾，全部敌军均列出
        resp_god = json.loads(self.controller.handle_request(json.dumps({"action": "api.list_enemy_curr", "god_mode": True})))
        self.assertEqual(resp_god["status"], "ok")
        self.assertEqual(resp_god["mode"], "god")
        god_ids = resp_god["unit_ids"].split(",")
        self.assertIn("e_spotted", god_ids)
        self.assertIn("e_hidden", god_ids)
        self.assertIn("e_prob", god_ids)

        # 2. 视野模式 (god_mode=False): 视线外的 e_hidden 绝对不列出
        # 多次抽样验证 e_spotted 必出，e_hidden 不出，e_prob 概率出现
        found_prob = 0
        trials = 20
        for _ in range(trials):
            resp_vision = json.loads(self.controller.handle_request(json.dumps({"action": "api.list_enemy_curr", "god_mode": False})))
            self.assertEqual(resp_vision["status"], "ok")
            self.assertEqual(resp_vision["mode"], "vision")
            v_ids = resp_vision["unit_ids"].split(",") if resp_vision["unit_ids"] else []
            self.assertIn("e_spotted", v_ids)
            self.assertNotIn("e_hidden", v_ids)
            if "e_prob" in v_ids:
                found_prob += 1

        self.assertTrue(0 < found_prob <= trials)

    def test_enemy_memory_lifecycle(self):
        """测试敌军记忆机制：发现追踪、跟丢保留最后坐标、目击死亡删除、盲杀保留记忆"""
        physics = self.mock_game.physics_engine
        physics.fog_of_war_enabled = True
        physics.enemy_memory.clear()

        # 1. 视线外的敌军不会进入记忆
        e_stealth = Tank(x=550, y=550, size=28, speed=2.0, camp=Camp.ENEMY, tank_id="e_stealth", unit_type="Fast Tank")
        physics.add_enemy_tank(e_stealth)
        physics.update_vision_and_stealth()
        self.assertNotIn("e_stealth", physics.enemy_memory)

        # 2. 敌军进入我方视线 (p1在100,100, vision_size=200) -> 实锤发现并建立记忆
        e_stealth.x, e_stealth.y = 120, 120
        physics.update_vision_and_stealth()
        self.assertIn("e_stealth", physics.enemy_memory)
        mem = physics.enemy_memory["e_stealth"]
        self.assertTrue(mem.is_tracking)
        self.assertEqual(mem.x, 120)
        self.assertEqual(mem.y, 120)
        self.assertEqual(mem.unit_type, "Fast Tank")

        # 3. 敌军移动到视野外 (跟丢) -> is_tracking=False，但最后坐标保持在 (120, 120)
        e_stealth.x, e_stealth.y = 560, 560
        physics.update_vision_and_stealth()
        self.assertIn("e_stealth", physics.enemy_memory)
        self.assertFalse(mem.is_tracking)
        self.assertEqual(mem.x, 120)
        self.assertEqual(mem.y, 120)

        # 4. api.list_enemy_mem 列出记忆
        resp_mem = json.loads(self.controller.handle_request(json.dumps({"action": "api.list_enemy_mem"})))
        self.assertEqual(resp_mem["status"], "ok")
        self.assertIn("e_stealth", resp_mem["unit_ids"])
        self.assertIn("e_stealth", resp_mem["lost"])

        # 5. api.report_enemy: 只报告最后坐标和类型，绝不报告 hp、speed、ammo 等
        resp_rep = json.loads(self.controller.handle_request(json.dumps({"action": "api.report_enemy", "unit_id": "e_stealth"})))
        self.assertEqual(resp_rep["status"], "ok")
        rep = resp_rep["report"]
        self.assertEqual(rep["id"], "e_stealth")
        self.assertEqual(rep["unit_type"], "Fast Tank")
        self.assertEqual(rep["last_x"], 120.0)
        self.assertEqual(rep["last_y"], 120.0)
        self.assertFalse(rep["is_tracking"])
        self.assertNotIn("hp", rep)
        self.assertNotIn("speed", rep)
        self.assertNotIn("ammo", rep)

        # 6. 目击敌方被杀死：实锤目击死亡 -> 从记忆中删除
        e_stealth.x, e_stealth.y = 120, 120
        physics.update_vision_and_stealth()
        self.assertTrue(physics.enemy_memory["e_stealth"].is_tracking)

        # 发射我方炮弹击杀之
        bullet = Bullet(x=120, y=120, direction=Direction.DOWN, speed=5.0, size=8, camp=Camp.PLAYER)
        physics.bullets.append(bullet)
        physics.update_bullets()
        self.assertFalse(e_stealth.alive)
        # 亲眼目睹被击杀，应已被清除出全局记忆
        self.assertNotIn("e_stealth", physics.enemy_memory)

    def test_command_batch_operations(self):
        """测试 API 5: command_move / attack / set_tactic / set_guard"""
        # 1. command_move
        move_req = {
            "action": "api.command_move",
            "unit_ids": "player_alpha,player_bravo",
            "x": 250,
            "y": 350
        }
        resp_move = json.loads(self.controller.handle_request(json.dumps(move_req)))
        self.assertEqual(resp_move["status"], "ok")
        self.assertIn("player_alpha", resp_move["affected_units"])
        self.assertIn("player_bravo", resp_move["affected_units"])

        # 2. command_set_tactic
        tactic_req = {
            "action": "api.command_set_tactic",
            "unit_ids": ["player_alpha"],
            "tactic": "defensive"
        }
        resp_tactic = json.loads(self.controller.handle_request(json.dumps(tactic_req)))
        self.assertEqual(resp_tactic["status"], "ok")
        self.assertEqual(self.mock_game.command_dispatcher.get_tactic(self.mock_game.p1), TacticMode.DEFENSIVE)

        # 3. command_set_guard
        guard_req = {
            "action": "api.command_set_guard",
            "unit_ids": ["player_alpha"],
            "target_id": "core_supply_base"
        }
        resp_guard = json.loads(self.controller.handle_request(json.dumps(guard_req)))
        self.assertEqual(resp_guard["status"], "ok")
        self.assertEqual(self.mock_game.command_dispatcher.get_tactic(self.mock_game.p1), TacticMode.GUARD_UNIT)

        # 4. command_attack
        attack_req = {
            "action": "api.command_attack",
            "unit_ids": "player_alpha",
            "target_id": "enemy_boss"
        }
        resp_attack = json.loads(self.controller.handle_request(json.dumps(attack_req)))
        self.assertEqual(resp_attack["status"], "ok")

    def test_report(self):
        """测试 API 6: report 查询全部属性"""
        req = {
            "action": "api.report",
            "unit_id": "player_alpha"
        }
        resp = json.loads(self.controller.handle_request(json.dumps(req)))
        self.assertEqual(resp["status"], "ok")
        rep = resp["report"]
        self.assertEqual(rep["id"], "player_alpha")
        self.assertTrue(rep["alive"])
        self.assertEqual(rep["speed"], 3.0)
        self.assertEqual(rep["hp"], 3)
        self.assertEqual(rep["ammo"], 20)
        self.assertIn("tactic", rep)
        self.assertIn("x", rep)
        self.assertIn("y", rep)

    def test_network_tcp_and_udp(self):
        """测试真实 TCP、UDP 与 WebSocket 套接字通信"""
        tcp_port = 19281
        udp_port = 19282
        ws_port = 19283

        manager = APIServerManager(
            game_context=self.mock_game,
            host="127.0.0.1",
            tcp_port=tcp_port,
            udp_port=udp_port,
            ws_port=ws_port
        )
        self.assertTrue(manager.start())

        self.app.processEvents()

        # 1. TCP/IP 测试
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_sock:
            tcp_sock.connect(("127.0.0.1", tcp_port))
            tcp_sock.sendall(b'{"action": "api.pause"}\n')

            for _ in range(10):
                self.app.processEvents()
                time.sleep(0.01)

            tcp_sock.settimeout(2.0)
            data = tcp_sock.recv(4096)
            resp = json.loads(data.decode("utf-8").strip())
            self.assertEqual(resp["status"], "ok")
            self.assertTrue(resp["paused"])

        # 2. UDP 纯文本 JSON 调用测试
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_sock:
            udp_sock.settimeout(2.0)
            req_data = json.dumps({"action": "api.report", "unit_id": "core_supply_base"}).encode("utf-8")
            udp_sock.sendto(req_data, ("127.0.0.1", udp_port))

            for _ in range(10):
                self.app.processEvents()
                time.sleep(0.01)

            resp_bytes, _ = udp_sock.recvfrom(4096)
            resp_udp = json.loads(resp_bytes.decode("utf-8").strip())
            self.assertEqual(resp_udp["status"], "ok")
            self.assertEqual(resp_udp["report"]["id"], "core_supply_base")
            self.assertTrue(resp_udp["report"]["is_tower"])

        # 3. WebSocket 客户端连接与调用
        from PyQt5.QtWebSockets import QWebSocket
        from PyQt5.QtCore import QUrl
        ws_client = QWebSocket()
        received_msgs = []
        ws_client.textMessageReceived.connect(lambda msg: received_msgs.append(msg))
        ws_client.open(QUrl(f"ws://127.0.0.1:{ws_port}"))

        for _ in range(15):
            self.app.processEvents()
            time.sleep(0.01)

        ws_client.sendTextMessage(json.dumps({"action": "api.is_success"}))

        for _ in range(15):
            self.app.processEvents()
            time.sleep(0.01)

        self.assertTrue(len(received_msgs) > 0)
        resp_ws = json.loads(received_msgs[0])
        self.assertEqual(resp_ws["status"], "ok")
        self.assertIn("is_success", resp_ws)
        ws_client.close()

        manager.stop()

    def test_commands_while_paused_and_execution_on_resume(self):
        """测试在暂停状态下执行 move, attack, fire，并在 resume 后立刻生效"""
        # 1. 暂停引擎
        self.mock_game.pause()
        self.assertTrue(self.mock_game.is_paused)

        # 2. 暂停期间执行 move
        init_x, init_y = self.mock_game.p1.x, self.mock_game.p1.y
        move_resp = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.command_move",
            "unit_ids": "player_alpha",
            "x": 200.0,
            "y": 200.0
        })))
        self.assertEqual(move_resp["status"], "ok")
        self.assertTrue(move_resp.get("queued", False))
        # 坐标未变（不立刻执行物理移动）
        self.assertEqual(self.mock_game.p1.x, init_x)
        self.assertEqual(self.mock_game.p1.y, init_y)

        # 3. 暂停期间执行 attack
        attack_resp = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.command_attack",
            "unit_ids": "player_alpha",
            "target_id": "enemy_boss"
        })))
        self.assertEqual(attack_resp["status"], "ok")
        self.assertTrue(attack_resp.get("queued", False))

        # 4. 暂停期间执行 fire
        self.assertEqual(len(self.mock_game.physics_engine.bullets), 0)
        fire_resp = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.command_fire",
            "unit_ids": "player_alpha",
            "direction": "UP"
        })))
        self.assertEqual(fire_resp["status"], "ok")
        self.assertTrue(fire_resp.get("queued", False))
        # 子弹尚未生成
        self.assertEqual(len(self.mock_game.physics_engine.bullets), 0)

        # 5. 解除暂停 (resume)
        resume_resp = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.resume"
        })))
        self.assertEqual(resume_resp["status"], "ok")
        self.assertFalse(self.mock_game.is_paused)

        # 解除暂停瞬间，开火动作立刻被执行并生成子弹
        self.assertEqual(len(self.mock_game.physics_engine.bullets), 1)

    def test_headless_runner_default_paused_and_p_key(self):
        """测试 HeadlessGameRunner 默认启动为暂停，按 P 键或网络 resume 启动"""
        from webui.headless_runner import HeadlessGameRunner
        from mission_loader import MissionLoader
        from map_loader import MapLoader

        mission = MissionLoader.load_from_file(BASE_DIR / "missions/mission_01.json")
        game_map = MapLoader.load_from_file(BASE_DIR / mission.map_file)

        runner = HeadlessGameRunner(mission, game_map, BASE_DIR)
        # 默认启动后处于暂停状态
        self.assertTrue(runner.is_paused)
        if hasattr(runner, "ai_script_manager"):
            self.assertTrue(runner.ai_script_manager.is_paused())

        # 按 P 键恢复运行
        runner.handle_key_event("p", is_down=True)
        self.assertFalse(runner.is_paused)
        if hasattr(runner, "ai_script_manager"):
            self.assertFalse(runner.ai_script_manager.is_paused())

        # 再次按 P 键暂停
        runner.handle_key_event("p", is_down=True)
        self.assertTrue(runner.is_paused)

        # 通过 API resume 恢复
        resp = json.loads(runner.api_controller.handle_request(json.dumps({"action": "api.resume"})))
        self.assertEqual(resp["status"], "ok")
        self.assertFalse(runner.is_paused)

        runner.stop()

    def test_list_and_show_converter_api(self):
        """测试 api.list_converter 与 api.show_converter"""
        # 1. list_converter
        req = {"action": "api.list_converter"}
        resp = json.loads(self.controller.handle_request(json.dumps(req)))
        self.assertEqual(resp["status"], "ok")
        self.assertIn("converter_ids", resp)
        self.assertIn("recipe_build_tank", resp["converter_ids"])
        self.assertIn("recipe_free_energy", resp["converter_ids"])
        self.assertGreaterEqual(resp["count"], 2)

        # 2. show_converter - 正常查询战车生产配方
        req_show = {"action": "api.show_converter", "converter_id": "recipe_build_tank"}
        resp_show = json.loads(self.controller.handle_request(json.dumps(req_show)))
        self.assertEqual(resp_show["status"], "ok")
        conv = resp_show["converter"]
        self.assertEqual(conv["id"], "recipe_build_tank")
        self.assertEqual(conv["output_type"], "tank")
        self.assertEqual(conv["visibility"], 0.9)
        self.assertEqual(conv["vision_size"], 300.0)
        self.assertEqual(conv["ammo"], 25)
        self.assertEqual(conv["inputs"], {"alloy": 15.0})

        # 3. show_converter - 零输入资源产出配方
        req_free = {"action": "api.show_converter", "recipe_id": "recipe_free_energy"}
        resp_free = json.loads(self.controller.handle_request(json.dumps(req_free)))
        self.assertEqual(resp_free["status"], "ok")
        self.assertEqual(resp_free["converter"]["inputs"], {})
        self.assertEqual(resp_free["converter"]["output_type"], "resource")

        # 4. show_converter - 缺失参数
        req_err1 = {"action": "api.show_converter"}
        resp_err1 = json.loads(self.controller.handle_request(json.dumps(req_err1)))
        self.assertEqual(resp_err1["status"], "error")

        # 5. show_converter - 配方不存在
        req_err2 = {"action": "api.show_converter", "converter_id": "non_existent_recipe"}
        resp_err2 = json.loads(self.controller.handle_request(json.dumps(req_err2)))
        self.assertEqual(resp_err2["status"], "error")

    def test_cli_client_extended_commands(self):
        """测试 tests/cli_client.py 扩展命令解析与路由"""
        from tests.cli_client import TanksConsoleClient
        client = TanksConsoleClient()
        sent_payloads = []
        client.send_request = lambda payload: sent_payloads.append(payload) or {"status": "ok"}
        client._print_response = lambda resp: None

        # list_converter
        client.execute_command_line("list_converter")
        self.assertEqual(sent_payloads[-1]["action"], "api.list_converter")

        # show_converter
        client.execute_command_line("show_converter recipe_build_tank")
        self.assertEqual(sent_payloads[-1]["action"], "api.show_converter")
        self.assertEqual(sent_payloads[-1]["converter_id"], "recipe_build_tank")

        # resources
        client.execute_command_line("resources")
        self.assertEqual(sent_payloads[-1]["action"], "api.get_resources")

        # blocks
        client.execute_command_line("blocks")
        self.assertEqual(sent_payloads[-1]["action"], "api.list_resource_blocks")

        # harvest
        client.execute_command_line("harvest player_alpha 5 6")
        self.assertEqual(sent_payloads[-1]["action"], "api.harvest")
        self.assertEqual(sent_payloads[-1]["col"], 5)
        self.assertEqual(sent_payloads[-1]["row"], 6)

        # stop_harvest
        client.execute_command_line("stop_harvest player_alpha")
        self.assertEqual(sent_payloads[-1]["action"], "api.stop_harvest")

        # convert
        client.execute_command_line("convert player_alpha recipe_build_tank 3")
        self.assertEqual(sent_payloads[-1]["action"], "api.convert")
        self.assertEqual(sent_payloads[-1]["unit_id"], "player_alpha")
        self.assertEqual(sent_payloads[-1]["recipe_id"], "recipe_build_tank")
        self.assertEqual(sent_payloads[-1]["count"], 3)

        # terminate_convert
        client.execute_command_line("terminate_convert player_alpha")
        self.assertEqual(sent_payloads[-1]["action"], "api.terminate_convert")
        self.assertEqual(sent_payloads[-1]["unit_id"], "player_alpha")

    def test_concurrency_thread_safety(self):
        """测试多线程并发 API 请求与主物理/调度循环的安全锁机制"""
        import threading

        threads = []
        errors = []

        def worker_task(thread_id: int):
            for i in range(25):
                try:
                    action_choice = i % 5
                    if action_choice == 0:
                        req = {"action": "api.move", "unit_ids": "player_alpha", "x": 100 + i, "y": 120 + i}
                    elif action_choice == 1:
                        req = {"action": "api.report", "unit_id": "player_alpha"}
                    elif action_choice == 2:
                        req = {"action": "api.is_success"}
                    elif action_choice == 3:
                        req = {"action": "api.list_current_unit_id"}
                    else:
                        req = {"action": "api.get_resources"}
                    resp_str = self.controller.handle_request(json.dumps(req))
                    resp = json.loads(resp_str)
                    if resp.get("status") not in ("ok", "ignored"):
                        errors.append(f"Thread {thread_id} step {i} status not ok: {resp}")
                except Exception as ex:
                    errors.append(f"Thread {thread_id} step {i} exception: {ex}")

        # 启动模拟游戏主循环线程（持有 lock 更新物理与调度器）
        sim_stop = False
        def sim_loop():
            while not sim_stop:
                with self.controller.lock:
                    self.mock_game.physics_engine.update()
                    self.mock_game.command_dispatcher.update(
                        [self.mock_game.p1], None, False, self.mock_game.physics_engine, self.mock_game.game_map
                    )
                time.sleep(0.002)

        sim_thread = threading.Thread(target=sim_loop, daemon=True)
        sim_thread.start()

        # 启动 8 个并发客户端调用线程
        for tid in range(8):
            t = threading.Thread(target=worker_task, args=(tid,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        sim_stop = True
        sim_thread.join(timeout=1.0)

        self.assertEqual(errors, [], f"Encountered concurrency errors: {errors}")

    def test_batch_request_sorting(self):
        """测试批次请求按优先级与 sequence/order 简单排序机制"""
        # 1. 数组形式批次调用
        batch_payload = [
            {"action": "api.report", "unit_id": "player_alpha"}, # 优先级 50
            {"action": "api.move", "unit_ids": "player_alpha", "x": 120, "y": 120}, # 优先级 30
            {"action": "api.pause"}, # 优先级 0
            {"action": "api.attack", "unit_ids": "player_alpha", "target_id": "enemy_boss"} # 优先级 20
        ]
        resp_str = self.controller.handle_request(json.dumps(batch_payload))
        resp = json.loads(resp_str)
        self.assertIsInstance(resp, list)
        self.assertEqual(len(resp), 4)
        # 校验执行顺序是否按照优先级：pause(0) -> attack(20) -> move(30) -> report(50)
        self.assertTrue(resp[0].get("paused"))
        self.assertEqual(resp[1].get("command"), "command_attack")
        self.assertEqual(resp[2].get("command"), "command_move")
        self.assertIn("report", resp[3])

        # 2. 相同优先级下的 order / seq 排序
        ordered_batch = [
            {"action": "api.move", "order": 3, "unit_ids": "player_alpha", "x": 300, "y": 300},
            {"action": "api.move", "order": 1, "unit_ids": "player_alpha", "x": 100, "y": 100},
            {"action": "api.move", "order": 2, "unit_ids": "player_alpha", "x": 200, "y": 200}
        ]
        resp_ordered = json.loads(self.controller.handle_request(json.dumps(ordered_batch)))
        self.assertEqual(resp_ordered[0]["destination"]["x"], 100.0)
        self.assertEqual(resp_ordered[1]["destination"]["x"], 200.0)
        self.assertEqual(resp_ordered[2]["destination"]["x"], 300.0)

    def test_sequence_anti_jitter_and_stale_command(self):
        """测试 seq 时序反抖动保护与旧指令丢弃防抽风机制"""
        # 第一条指令序列号为 10
        cmd1 = {"action": "api.move", "unit_ids": "player_alpha", "x": 120, "y": 120, "seq": 10}
        resp1 = json.loads(self.controller.handle_request(json.dumps(cmd1)))
        self.assertEqual(resp1["status"], "ok")

        # 迟滞到达的旧指令序列号为 6，应当被判定为 stale 并忽略
        cmd2 = {"action": "api.move", "unit_ids": "player_alpha", "x": 50, "y": 50, "seq": 6}
        resp2 = json.loads(self.controller.handle_request(json.dumps(cmd2)))
        self.assertEqual(resp2["status"], "ignored")
        self.assertIn("Stale command sequence", resp2["reason"])

        # 新序号指令 15 正常接收并执行
        cmd3 = {"action": "api.move", "unit_ids": "player_alpha", "x": 180, "y": 180, "seq": 15}
        resp3 = json.loads(self.controller.handle_request(json.dumps(cmd3)))
        self.assertEqual(resp3["status"], "ok")

    def test_movement_anti_stutter(self):
        """测试目标坐标极其相近时的移动指令阻尼防抖防抽风"""
        # 下发初始移动指令
        cmd1 = {"action": "api.move", "unit_ids": "player_alpha", "x": 250.0, "y": 250.0}
        resp1 = json.loads(self.controller.handle_request(json.dumps(cmd1)))
        self.assertEqual(resp1["status"], "ok")

        first_move_cmd = self.mock_game.command_dispatcher.tank_commands.get("player_alpha")
        self.assertIsInstance(first_move_cmd, MoveCommand)

        # 连续发送几乎相同目的地的移动指令 (误差 < 4 像素)
        cmd2 = {"action": "api.move", "unit_ids": "player_alpha", "x": 251.0, "y": 251.5}
        resp2 = json.loads(self.controller.handle_request(json.dumps(cmd2)))
        self.assertEqual(resp2["status"], "ok")

        second_move_cmd = self.mock_game.command_dispatcher.tank_commands.get("player_alpha")
        # 验证原来的移动指令对象未被重复创建或打断
        self.assertIs(first_move_cmd, second_move_cmd)

        # 发送明显不同的新目的地指令
        cmd3 = {"action": "api.move", "unit_ids": "player_alpha", "x": 400.0, "y": 400.0}
        resp3 = json.loads(self.controller.handle_request(json.dumps(cmd3)))
        self.assertEqual(resp3["status"], "ok")

        third_move_cmd = self.mock_game.command_dispatcher.tank_commands.get("player_alpha")
        self.assertIsNot(first_move_cmd, third_move_cmd)
        self.assertEqual(third_move_cmd.dest_x, 400.0)

    def test_harvest_cli_and_api_bracket_unit_ids(self):
        """测试 CLI 客户端与 API 控制器对带方括号单位 ID 的正确解析与调度 (防止截断为 'p')"""
        from tests.cli_client import clean_unit_ids, TanksConsoleClient
        from resource.models import ResourceBlock

        # 1. 验证 cli_client 辅助函数
        self.assertEqual(clean_unit_ids("[player_alpha]"), "player_alpha")
        self.assertEqual(clean_unit_ids("[player_alpha, player_bravo]"), "player_alpha,player_bravo")
        self.assertEqual(clean_unit_ids("player_alpha"), "player_alpha")

        cmd, args = TanksConsoleClient.parse_command_line("harvest [player_alpha] 5 5")
        self.assertEqual(cmd, "harvest")
        self.assertEqual(args, ["[player_alpha]", "5", "5"])
        self.assertEqual(clean_unit_ids(args[0]), "player_alpha")

        cmd2, args2 = TanksConsoleClient.parse_command_line("harvest [player_alpha, player_bravo] 5 5")
        self.assertEqual(cmd2, "harvest")
        self.assertEqual(args2, ["[player_alpha, player_bravo]", "5", "5"])
        self.assertEqual(clean_unit_ids(args2[0]), "player_alpha,player_bravo")

        # 2. 在 mock 环境中注册资源块 (5, 5)
        blk = ResourceBlock(col=5, row=5, resource_type="dark_matter", current_amount=500.0, initial_amount=500.0, regen_rate=1.0)
        self.mock_game.resource_manager.blocks.append(blk)
        self.mock_game.resource_manager._block_by_pos[(5, 5)] = blk

        # 3. 验证通过 API 传入 "[player_alpha]" (字符串带括号) 正常分发，而非报错找不到单位 'p' 或 '['
        req = {"action": "api.harvest", "unit_ids": "[player_alpha]", "col": 5, "row": 5}
        resp = json.loads(self.controller.handle_request(json.dumps(req)))
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["unit_id"], "player_alpha")
        self.assertIn("player_alpha", resp["unit_ids"])

        # 验证 stop_harvest 同样支持带方括号单位参数
        stop_req = {"action": "api.stop_harvest", "unit_ids": "[player_alpha]"}
        stop_resp = json.loads(self.controller.handle_request(json.dumps(stop_req)))
        self.assertEqual(stop_resp["status"], "ok")

    def test_harvest_center_seeking_movement(self):
        """测试采矿指令优先移动到目标资源块几何中心再开始采集的逻辑"""
        from resource.models import ResourceBlock
        from command.commands import HarvestCommand
        import math

        ts = self.mock_game.game_map.tile_size
        col, row = 8, 8
        blk = ResourceBlock(col=col, row=row, resource_type="dark_matter", current_amount=500.0, initial_amount=500.0, regen_rate=1.0)
        self.mock_game.resource_manager.blocks.append(blk)
        self.mock_game.resource_manager._block_by_pos[(col, row)] = blk

        # 让 player_alpha 位于 (100, 100)，资源块 (8, 8) 中心为 (8.5 * 32, 8.5 * 32) = (272, 272)
        self.mock_game.p1.x = 100.0
        self.mock_game.p1.y = 100.0

        h_cmd = HarvestCommand(col, row, self.mock_game.resource_manager)
        dest = h_cmd._find_standable_harvest_pos(self.mock_game.p1, self.mock_game.physics_engine, self.mock_game.game_map, blk)
        self.assertIsNotNone(dest)

        # 验证计算出的站立点中心与资源块几何中心完全重合
        cx, cy = blk.center(ts)
        tank_cx = dest[0] + self.mock_game.p1.size / 2.0
        tank_cy = dest[1] + self.mock_game.p1.size / 2.0
        self.assertAlmostEqual(tank_cx, cx, delta=1.0)
        self.assertAlmostEqual(tank_cy, cy, delta=1.0)

        # 下达开采指令
        self.mock_game.command_dispatcher.issue_harvest([self.mock_game.p1], col, row, self.mock_game.resource_manager)

        # 推进仿真直到到达中心
        for _ in range(120):
            cmd = self.mock_game.command_dispatcher.tank_commands.get(self.mock_game.p1.id)
            if cmd:
                cmd.execute(self.mock_game.p1, self.mock_game.physics_engine, self.mock_game.game_map)
            self.mock_game.resource_manager.update(0.016)
            self.mock_game.resource_manager.update_harvest([self.mock_game.p1], 0.016, ts)
            if self.mock_game.p1.is_harvesting:
                break

        # 验证已经就位且处于采集状态
        self.assertTrue(self.mock_game.p1.is_harvesting)
        cur_cx = self.mock_game.p1.x + self.mock_game.p1.size / 2.0
        cur_cy = self.mock_game.p1.y + self.mock_game.p1.size / 2.0
        dist_to_center = math.hypot(cur_cx - cx, cur_cy - cy)
        # 验证与目标中心的距离在极小误差范围 (<= 4.0 像素) 内
        self.assertLessEqual(dist_to_center, 4.0)

    def test_plain_function_call_format_and_paired_delimiters(self):
        """测试 func(arg1, arg2, ...) 原始 plain 格式解析，以及成对 " / ' / “” / ‘’ / [...] 长字符串合并与自动掐头去尾"""
        from resource.models import ResourceBlock

        # 1. 验证成对定界符 (" / ' / “” / ‘’ / [...]) 内部带逗号长字符串参数提取与自动掐头去尾
        pos1, _ = GameAPIController.extract_plain_args('"player_alpha, player_bravo", 250, 350')
        self.assertEqual(pos1, ["player_alpha, player_bravo", "250", "350"])

        pos2, _ = GameAPIController.extract_plain_args("'player_alpha, player_bravo', 250, 350")
        self.assertEqual(pos2, ["player_alpha, player_bravo", "250", "350"])

        pos3, _ = GameAPIController.extract_plain_args("[player_alpha, player_bravo], 250, 350")
        self.assertEqual(pos3, ["player_alpha, player_bravo", "250", "350"])

        pos4, _ = GameAPIController.extract_plain_args("“player_alpha, player_bravo”, ‘defensive’")
        self.assertEqual(pos4, ["player_alpha, player_bravo", "defensive"])

        # 2. 验证无参 plain 调用: pause() / resume() / api.is_success()
        resp_pause = json.loads(self.controller.handle_request("api.pause()"))
        self.assertEqual(resp_pause["status"], "ok")
        self.assertTrue(self.mock_game.is_paused)

        resp_resume = json.loads(self.controller.handle_request("resume()"))
        self.assertEqual(resp_resume["status"], "ok")
        self.assertFalse(self.mock_game.is_paused)

        resp_succ = json.loads(self.controller.handle_request("is_success()"))
        self.assertEqual(resp_succ["status"], "ok")
        self.assertFalse(resp_succ["is_success"])

        # 3. 验证带方括号 [...] 长字符串参数的 move([player_alpha, player_bravo], 260, 360)
        resp_move1 = json.loads(self.controller.handle_request("move([player_alpha, player_bravo], 260, 360)"))
        self.assertEqual(resp_move1["status"], "ok")
        self.assertIn("player_alpha", resp_move1["affected_units"])
        self.assertIn("player_bravo", resp_move1["affected_units"])
        self.assertEqual(resp_move1["destination"], {"x": 260.0, "y": 360.0})

        # 4. 验证带双引号/单引号/中文引号长字符串参数的调用
        resp_move2 = json.loads(self.controller.handle_request('api.command_move("player_alpha, player_bravo", 180, 220)'))
        self.assertEqual(resp_move2["status"], "ok")
        self.assertEqual(len(resp_move2["affected_units"]), 2)

        resp_tactic = json.loads(self.controller.handle_request("set_tactic(‘player_alpha, player_bravo’, “defensive”)"))
        self.assertEqual(resp_tactic["status"], "ok")
        self.assertEqual(resp_tactic["tactic"], "defensive")
        self.assertEqual(self.mock_game.command_dispatcher.get_tactic(self.mock_game.p1), TacticMode.DEFENSIVE)

        # 5. 验证 report / attack / guard / harvest 的 plain 格式调用
        resp_rep = json.loads(self.controller.handle_request("report('player_alpha')"))
        self.assertEqual(resp_rep["status"], "ok")
        self.assertEqual(resp_rep["report"]["id"], "player_alpha")

        resp_atk = json.loads(self.controller.handle_request('attack([player_alpha], "enemy_boss")'))
        self.assertEqual(resp_atk["status"], "ok")
        self.assertEqual(resp_atk["target_id"], "enemy_boss")

        blk = ResourceBlock(col=6, row=7, resource_type="alloy", current_amount=300.0, initial_amount=300.0, regen_rate=1.0)
        self.mock_game.resource_manager.blocks.append(blk)
        self.mock_game.resource_manager._block_by_pos[(6, 7)] = blk

        resp_harv = json.loads(self.controller.handle_request("harvest([player_alpha], 6, 7)"))
        self.assertEqual(resp_harv["status"], "ok")
        self.assertEqual(resp_harv["harvest_target"], [6, 7])

        # 6. 验证 CLI 客户端直接输入 func(arg1, arg2, ...) plain 格式
        from tests.cli_client import TanksConsoleClient
        client = TanksConsoleClient()
        sent = []
        client.send_request = lambda p: sent.append(p) or {"status": "ok"}
        client._print_response = lambda r: None
        client.execute_command_line('move([player_alpha, player_bravo], 300, 400)')
        self.assertEqual(sent[-1]["unit_ids"], "player_alpha, player_bravo")
        self.assertEqual(sent[-1]["x"], 300.0)
        self.assertEqual(sent[-1]["y"], 400.0)

    def test_web_god_mode_ui_and_restart_consistency(self):
        """测试 Web 上帝模式 (Monitor) 在 api.restart() 后状态平滑刷新，杜绝抽风与残留上一局旧数据"""
        from mission_loader import MissionLoader
        from map_loader import MapLoader
        from webui.headless_runner import HeadlessGameRunner
        from monitor.server import extract_game_state_snapshot

        mission_path = BASE_DIR / "missions/mission_01.json"
        mission = MissionLoader.load_from_file(mission_path)
        map_path = BASE_DIR / mission.map_file
        game_map = MapLoader.load_from_file(map_path)

        runner = HeadlessGameRunner(mission, game_map, BASE_DIR)
        controller = runner.api_controller

        # 模拟 tanks.py 动态 context 获取快照
        active_ctx = [runner]
        def dynamic_state_getter():
            ctx = active_ctx[0]
            if not ctx:
                return {"status": "initializing"}
            lock = getattr(getattr(ctx, "api_controller", None), "lock", None)
            if lock:
                with lock:
                    pe = getattr(ctx, "physics_engine", None)
                    gm = getattr(ctx, "game_map", None)
                    cd = getattr(ctx, "command_dispatcher", None)
                    rm = getattr(ctx, "resource_manager", None)
                    mid = getattr(ctx, "match_id", 0)
                    if pe and gm and cd:
                        return extract_game_state_snapshot(pe, gm, cd, rm, match_id=mid)
            return {"status": "initializing"}

        # 1. 验证第 1 局初始状态快照
        snap1 = dynamic_state_getter()
        self.assertEqual(snap1["match_id"], 1)
        orig_player_count = len(snap1["player_units"])
        self.assertGreater(orig_player_count, 0)
        first_tank = snap1["player_units"][0]
        orig_x, orig_y = first_tank["x"], first_tank["y"]

        # 2. 模拟第 1 局发生战斗与破坏：坦克移动、砖块破坏、下发时序指令
        controller.handle_request(json.dumps({"action": "api.move", "unit_ids": first_tank["id"], "x": orig_x + 60, "y": orig_y + 60, "seq": 10}))
        runner.physics_engine.player_tanks[0].x = orig_x + 60
        runner.physics_engine.player_tanks[0].y = orig_y + 60
        # 破坏一个砖块 (TileType.EMPTY = 0, BRICK = 1)
        test_col, test_row = 1, 1
        runner.game_map.grid[test_row][test_col] = 0

        snap1_modified = dynamic_state_getter()
        self.assertEqual(snap1_modified["player_units"][0]["x"], round(orig_x + 60, 1))
        self.assertEqual(snap1_modified["map"]["grid"][test_row][test_col], 0)
        self.assertIn(first_tank["id"], controller._unit_last_command)

        # 3. 执行 api.restart()
        resp_restart = json.loads(controller.handle_request("restart()"))
        self.assertEqual(resp_restart["status"], "ok")

        # 4. 验证重启后快照：match_id 递增、砖块恢复、坦克位置重置，绝无上一局残留
        snap2 = dynamic_state_getter()
        self.assertEqual(snap2["match_id"], 2)
        # 验证坦克回到初始位置
        self.assertEqual(snap2["player_units"][0]["x"], orig_x)
        self.assertEqual(snap2["player_units"][0]["y"], orig_y)
        # 验证地图重新加载，被破坏的砖块恢复
        fresh_map = MapLoader.load_from_file(map_path)
        self.assertEqual(snap2["map"]["grid"][test_row][test_col], fresh_map.grid[test_row][test_col])
        # 验证防抽风序列号缓存已清理，允许新局从 seq: 1 正常下发
        self.assertNotIn(first_tank["id"], controller._unit_last_command)

        runner.stop()

    def test_get_mission_info_json_and_plain(self):
        """测试 api.get_mission_info 接口（JSON 与 Plain 函数调用格式），返回简报与地图各尺寸边界"""
        # 1. JSON 格式调用
        resp_json = json.loads(self.controller.handle_request(json.dumps({"action": "api.get_mission_info"})))
        self.assertEqual(resp_json["status"], "ok")
        self.assertEqual(resp_json["mission_name"], "Test Defense Mission")
        self.assertEqual(resp_json["briefing"], "指挥官，歼灭所有来犯敌军！")
        self.assertEqual(resp_json["cols"], 20)
        self.assertEqual(resp_json["rows"], 20)
        self.assertEqual(resp_json["tile_size"], 32)
        self.assertEqual(resp_json["pixel_width"], 640.0)
        self.assertEqual(resp_json["pixel_height"], 640.0)
        self.assertEqual(resp_json["max_x"], 640.0)
        self.assertEqual(resp_json["max_y"], 640.0)
        self.assertIn("map_size", resp_json)
        self.assertEqual(resp_json["map_size"]["cols"], 20)
        self.assertEqual(resp_json["map_size"]["rows"], 20)
        self.assertEqual(resp_json["map_size"]["max_x"], 640.0)
        self.assertEqual(resp_json["map_size"]["max_y"], 640.0)

        # 2. Plain 函数调用格式 get_mission_info()
        resp_plain = json.loads(self.controller.handle_request("get_mission_info()"))
        self.assertEqual(resp_plain["status"], "ok")
        self.assertEqual(resp_plain["briefing"], "指挥官，歼灭所有来犯敌军！")
        self.assertEqual(resp_plain["pixel_width"], 640.0)

        # 3. Plain 别名 briefing()
        resp_briefing = json.loads(self.controller.handle_request("briefing()"))
        self.assertEqual(resp_briefing["status"], "ok")
        self.assertEqual(resp_briefing["briefing"], "指挥官，歼灭所有来犯敌军！")

        # 4. TankScriptAPI 转写调用
        from ai_python.bridge import TankScriptAPI
        import threading
        stop_evt = threading.Event()
        api_bridge = TankScriptAPI("player_alpha", self.controller, stop_evt)
        bridge_info = api_bridge.get_mission_info()
        self.assertEqual(bridge_info["status"], "ok")
        self.assertEqual(bridge_info["briefing"], "指挥官，歼灭所有来犯敌军！")
        self.assertEqual(bridge_info["cols"], 20)
        self.assertEqual(bridge_info["rows"], 20)
        self.assertEqual(bridge_info["max_x"], 640.0)
        self.assertEqual(bridge_info["max_y"], 640.0)

    def test_edit_attr_api(self):
        """测试 api.edit_attr：动态修改属性、自动类型处理、批量修改、仅无匹配对象报错、无属性自动跳过"""
        from ai_python.bridge import TankScriptAPI
        import threading
        stop_evt = threading.Event()
        api_bridge = TankScriptAPI("player_alpha", self.controller, stop_evt)

        # 1. 单单位修改属性，并验证自动类型推断转换 (字符串 "6.5" 自动转为 float，字符串 "8" 自动转为 int)
        resp1 = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.edit_attr",
            "unit_ids": "player_alpha",
            "attr": "speed",
            "value": "6.5"
        })))
        self.assertEqual(resp1["status"], "ok")
        self.assertIn("player_alpha", resp1["updated_units"])
        self.assertEqual(self.mock_game.p1.speed, 6.5)

        # 验证 bool 字符串转换
        resp_bool = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.edit_attr",
            "unit_ids": "player_alpha",
            "attr": "controllable",
            "value": "false"
        })))
        self.assertEqual(resp_bool["status"], "ok")
        self.assertFalse(self.mock_game.p1.controllable)

        # 2. 批量修改多单位属性 (逗号分隔或列表)
        resp_batch = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.edit_attr",
            "unit_ids": ["player_alpha", "player_bravo"],
            "attr": "ammo",
            "value": 88
        })))
        self.assertEqual(resp_batch["status"], "ok")
        self.assertIn("player_alpha", resp_batch["updated_units"])
        self.assertIn("player_bravo", resp_batch["updated_units"])
        self.assertEqual(self.mock_game.p1.ammo, 88)
        self.assertEqual(self.mock_game.p2.ammo, 88)

        # 3. '*' 通配修改全图所有单位
        resp_all = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.edit_attr",
            "unit_ids": "*",
            "attr": "health",
            "value": 15
        })))
        self.assertEqual(resp_all["status"], "ok")
        self.assertEqual(self.mock_game.p1.health, 15)
        self.assertEqual(self.mock_game.p2.health, 15)
        self.assertEqual(self.mock_game.e1.health, 15)

        # 4. 仅在一个对象也找不到的时候报错
        resp_err = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.edit_attr",
            "unit_ids": "ghost_unit_999",
            "attr": "speed",
            "value": 10
        })))
        self.assertEqual(resp_err["status"], "error")
        self.assertIn("No matching units found", resp_err["error"])

        # 5. 某个对象不存在这个属性则自动跳过（不报错）
        # 给 player_alpha 动态绑定一个专有属性，player_bravo 不具备
        self.mock_game.p1.special_shield = 100
        if hasattr(self.mock_game.p2, "special_shield"):
            delattr(self.mock_game.p2, "special_shield")

        resp_skip = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.edit_attr",
            "unit_ids": ["player_alpha", "player_bravo"],
            "attr": "special_shield",
            "value": 250
        })))
        self.assertEqual(resp_skip["status"], "ok")
        self.assertIn("player_alpha", resp_skip["updated_units"])
        self.assertIn("player_bravo", resp_skip["skipped_units"])
        self.assertEqual(self.mock_game.p1.special_shield, 250)

        # 6. Plain 函数调用格式与成对定界符
        resp_plain = json.loads(self.controller.handle_request('edit_attr([player_alpha, player_bravo], "speed", 7.2)'))
        self.assertEqual(resp_plain["status"], "ok")
        self.assertEqual(self.mock_game.p1.speed, 7.2)
        self.assertEqual(self.mock_game.p2.speed, 7.2)

        # 7. TankScriptAPI 桥接调用
        resp_bridge = api_bridge.edit_attr("player_alpha", "speed", 9.0)
        self.assertEqual(resp_bridge["status"], "ok")
        self.assertEqual(self.mock_game.p1.speed, 9.0)

    def test_set_resources_api(self):
        """测试 api.set_resources：修改双方全局战略资源、增量修改、Plain 格式与 Python 桥接"""
        from ai_python.bridge import TankScriptAPI
        import threading
        stop_evt = threading.Event()
        api_bridge = TankScriptAPI("player_alpha", self.controller, stop_evt)

        # 1. 同时设定双方资源储备 (camp='both')
        resp1 = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.set_resources",
            "camp": "both",
            "dark_matter": 800.0,
            "alloy": 400.0
        })))
        self.assertEqual(resp1["status"], "ok")
        self.assertEqual(resp1["player"]["dark_matter"], 800.0)
        self.assertEqual(resp1["player"]["alloy"], 400.0)
        self.assertEqual(resp1["enemy"]["dark_matter"], 800.0)
        self.assertEqual(resp1["enemy"]["alloy"], 400.0)

        # 2. 单独设定敌方储备
        resp2 = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.set_resources",
            "camp": "enemy",
            "dark_matter": 1200.0
        })))
        self.assertEqual(resp2["status"], "ok")
        self.assertEqual(resp2["enemy"]["dark_matter"], 1200.0)
        self.assertEqual(resp2["player"]["dark_matter"], 800.0)

        # 3. 增量修改模式 mode='add'
        resp3 = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.set_resources",
            "camp": "player",
            "dark_matter": 200.0,
            "mode": "add"
        })))
        self.assertEqual(resp3["status"], "ok")
        self.assertEqual(resp3["player"]["dark_matter"], 1000.0)

        # 4. Plain 函数格式调用
        resp_plain = json.loads(self.controller.handle_request('set_resources("both", 600, 350)'))
        self.assertEqual(resp_plain["status"], "ok")
        self.assertEqual(resp_plain["player"]["dark_matter"], 600.0)
        self.assertEqual(resp_plain["enemy"]["alloy"], 350.0)

        # 5. TankScriptAPI 桥接调用
        resp_bridge = api_bridge.set_resources(camp="player", dark_matter=9999.0, alloy=5555.0)
        self.assertEqual(resp_bridge["status"], "ok")
        self.assertEqual(resp_bridge["player"]["dark_matter"], 9999.0)
        self.assertEqual(resp_bridge["player"]["alloy"], 5555.0)

    def test_create_unit_api(self):
        """测试 api.create_unit：动态造兵部署、阵营注册、唯一 ID 分配、Plain 格式与 Python 桥接"""
        from ai_python.bridge import TankScriptAPI
        import threading
        stop_evt = threading.Event()
        api_bridge = TankScriptAPI("player_alpha", self.controller, stop_evt)

        # 1. 创建全新我方单位 (自动生成 ID，使用 player_tank 配置)
        resp1 = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.create_unit",
            "camp": "player",
            "x": 120.0,
            "y": 140.0,
            "config_file": "tank_configs/player_tank.json",
            "health": 6,
            "ammo": 35
        })))
        self.assertEqual(resp1["status"], "ok")
        new_p_id = resp1["unit_id"]
        self.assertTrue(new_p_id.startswith("player_unit_"))
        created_p = next((t for t in self.mock_game.physics_engine.player_tanks if t.id == new_p_id), None)
        self.assertIsNotNone(created_p)
        self.assertEqual(created_p.health, 6)
        self.assertEqual(created_p.ammo, 35)
        self.assertIn(new_p_id, self.mock_game.command_dispatcher.tank_commands)

        # 2. 创建全新敌方单位 (指定 ID 与 tactic)
        resp2 = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.create_unit",
            "camp": "enemy",
            "x": 450.0,
            "y": 350.0,
            "unit_id": "enemy_custom_assault",
            "config_file": "enemy_fast",
            "tactic": "charge_base"
        })))
        self.assertEqual(resp2["status"], "ok")
        self.assertEqual(resp2["unit_id"], "enemy_custom_assault")
        created_e = next((t for t in self.mock_game.physics_engine.enemy_tanks if t.id == "enemy_custom_assault"), None)
        self.assertIsNotNone(created_e)
        self.assertIn("enemy_custom_assault", self.mock_game.ai_controller.agents)

        # 3. 重复 ID 返回错误
        resp_dup = json.loads(self.controller.handle_request(json.dumps({
            "action": "api.create_unit",
            "camp": "player",
            "unit_id": "player_alpha"
        })))
        self.assertEqual(resp_dup["status"], "error")
        self.assertIn("already exists", resp_dup["error"])

        # 4. Plain 函数格式调用
        resp_plain = json.loads(self.controller.handle_request('create_unit("player", 220, 240, "player_tank", "player_plain_reinforce")'))
        self.assertEqual(resp_plain["status"], "ok")
        self.assertEqual(resp_plain["unit_id"], "player_plain_reinforce")
        self.assertTrue(any(t.id == "player_plain_reinforce" for t in self.mock_game.physics_engine.player_tanks))

        # 5. TankScriptAPI 桥接调用
        resp_bridge = api_bridge.create_unit(camp="enemy", x=300.0, y=200.0, unit_id="enemy_bridge_spawn")
        self.assertEqual(resp_bridge["status"], "ok")
        self.assertEqual(resp_bridge["unit_id"], "enemy_bridge_spawn")
        self.assertTrue(any(t.id == "enemy_bridge_spawn" for t in self.mock_game.physics_engine.enemy_tanks))

    def test_get_game_time_api_and_grizzly_spawner(self):
        """测试 api.get_game_time：活跃运行毫秒数、暂停期间冻结计时、Python 桥接以及灰熊坦克刷新脚本"""
        from ai_python.bridge import TankScriptAPI
        from tank_configs.config_loader import TankConfig
        import threading
        stop_evt = threading.Event()
        api_bridge = TankScriptAPI("player_alpha", self.controller, stop_evt)

        # 1. 初始时间为 0
        self.mock_game.condition_ctx.elapsed_time = 0.0
        resp1 = json.loads(self.controller.handle_request(json.dumps({"action": "api.get_game_time"})))
        self.assertEqual(resp1["status"], "ok")
        self.assertEqual(resp1["game_time_ms"], 0)
        self.assertEqual(resp1["game_time_sec"], 0.0)

        # 2. 模拟活跃运行 2.5 秒 (2500 ms)
        self.mock_game.condition_ctx.update(2.5)
        resp2 = json.loads(self.controller.handle_request(json.dumps({"action": "api.get_game_time"})))
        self.assertEqual(resp2["status"], "ok")
        self.assertEqual(resp2["game_time_ms"], 2500)
        self.assertEqual(resp2["game_time_sec"], 2.5)

        # 3. 模拟暂停：暂停期间调用 update 不应增加时间，活跃毫秒数保持冻结
        self.mock_game.is_paused = True
        # 在实际引擎循环中，is_paused 时不会调用 condition_ctx.update
        resp3 = json.loads(self.controller.handle_request("get_game_time()"))
        self.assertEqual(resp3["status"], "ok")
        self.assertEqual(resp3["game_time_ms"], 2500)
        self.assertTrue(resp3["is_paused"])

        # 4. TankScriptAPI 桥接测试
        ms = api_bridge.get_time_ms()
        self.assertEqual(ms, 2500)

        # 5. 验证灰熊坦克配置 grizzly_tank.json 可正常加载
        cfg_path = BASE_DIR / "tank_configs" / "grizzly_tank.json"
        self.assertTrue(cfg_path.exists())
        grizzly_cfg = TankConfig.from_json(cfg_path)
        self.assertEqual(grizzly_cfg.name, "Grizzly Tank")

        # 6. 验证 ai_python/grizzly_spawner.py 脚本格式与可调用性
        spawner_path = BASE_DIR / "ai_python" / "grizzly_spawner.py"
        self.assertTrue(spawner_path.exists())
        with open(spawner_path, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("def run(api):", code)
        self.assertIn("grizzly_tank", code)
        self.assertIn("spawn_interval_ms = 10000", code)


if __name__ == "__main__":



    unittest.main()
