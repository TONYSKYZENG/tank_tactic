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
from physics.entities import Tank, Bullet, Camp, Direction
from physics.engine import PhysicsEngine
from command.dispatcher import CommandDispatcher
from command.tactics_mode import TacticMode
from conditions.primitives import ConditionContext, UnitSurviveTimeCondition, UnitDestroyedCondition
from conditions.composite import OrCondition
from api.controller import GameAPIController
from api.server import APIServerManager

class MockGameContext:
    def __init__(self):
        self.game_map = GameMap("TestMap", 32, 20, 20, [[0]*20 for _ in range(20)])
        self.physics_engine = PhysicsEngine(self.game_map, fog_of_war_enabled=False, limited_ammo_enabled=True)
        self.command_dispatcher = CommandDispatcher()
        self.condition_ctx = ConditionContext(self.physics_engine, self.game_map)

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

if __name__ == "__main__":
    unittest.main()
