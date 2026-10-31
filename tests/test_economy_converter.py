import unittest
from pathlib import Path

from map_loader.models import GameMap, TileType
from physics.entities import Tank, Camp
from physics.engine import PhysicsEngine
from resource import ResourceType, ResourceBlockConfig, ResourceBlock, ResourceManager, ResourceLoader
from converter import ConverterRecipe, ConversionTask, UnitConverter, RecipeRegistry
from conditions import ConditionContext, ConditionBuilder, ResourceAmountCondition
from api.controller import GameAPIController

class MockGameContext:
    def __init__(self, physics_engine, game_map, resource_manager):
        self.physics_engine = physics_engine
        self.game_map = game_map
        self.resource_manager = resource_manager
        self.command_dispatcher = None
        self.is_paused = False


class TestEconomyAndConverter(unittest.TestCase):

    def setUp(self):
        # 建立测试地图 (包含空地、暗物质资源块、合金资源块、红砖)
        self.game_map = GameMap(name="TestMap", cols=10, rows=10, tile_size=32,
                                grid=[[TileType.EMPTY for _ in range(10)] for _ in range(10)])
        self.game_map.set_tile(2, 2, TileType.DARK_MATTER)
        self.game_map.set_tile(4, 4, TileType.ALLOY)

        self.physics = PhysicsEngine(self.game_map, fog_of_war_enabled=False, limited_ammo_enabled=True)
        self.res_mgr = ResourceManager(initial_resources={
            ResourceType.DARK_MATTER: 100.0,
            ResourceType.ALLOY: 50.0
        })
        self.res_mgr.init_from_map(self.game_map)

        # 注册配方
        RecipeRegistry.load_recipes()

    def test_resource_blocks_and_regen(self):
        """测试地图资源块注册、数值与周期再生供货"""
        # 应该解析出 2 个资源块
        self.assertEqual(len(self.res_mgr.blocks), 2)
        dm_blocks = [b for b in self.res_mgr.blocks if b.resource_type == ResourceType.DARK_MATTER]
        alloy_blocks = [b for b in self.res_mgr.blocks if b.resource_type == ResourceType.ALLOY]
        self.assertEqual(len(dm_blocks), 1)
        self.assertEqual(len(alloy_blocks), 1)

        # 初始存量
        self.assertEqual(self.res_mgr.get_amount(ResourceType.DARK_MATTER), 100.0)
        self.assertEqual(self.res_mgr.get_amount(ResourceType.ALLOY), 50.0)

        # 推进 5 秒时间
        rates = self.res_mgr.get_rates()
        self.assertGreater(rates[ResourceType.DARK_MATTER], 0.0)
        self.assertGreater(rates[ResourceType.ALLOY], 0.0)

        # 消耗部分资源块后测试其自身再生递增
        dm_blocks[0].current_amount = 200.0
        self.res_mgr.update(5.0)
        self.assertGreater(dm_blocks[0].current_amount, 200.0)

    def test_converter_recipes_and_lifecycle(self):
        """测试配方加载、多批次转换与输入扣除输出产出"""
        recipe = RecipeRegistry.get("recipe_dm_to_alloy")
        self.assertIsNotNone(recipe, "应成功加载暗物质合成合金配方")
        self.assertIn("dark_matter", recipe.inputs)
        self.assertIn("alloy", recipe.outputs)

        # 创建搭载转换机的战车
        tank = Tank(x=0, y=0, size=32, speed=3.0, camp=Camp.PLAYER, tank_id="p1",
                    converter_table=["recipe_dm_to_alloy", "recipe_alloy_to_dm"])
        self.physics.add_player_tank(tank)

        self.assertIsNotNone(tank.converter)
        self.assertFalse(tank.is_converting)

        # 启动转换任务：2 批次
        ok, reason = tank.converter.enqueue(recipe, count=2, resource_manager=self.res_mgr)
        self.assertTrue(ok)
        self.assertEqual(reason, "started")
        self.assertTrue(tank.is_converting)

        # 检查首批输入已扣除 (10 暗物质)
        self.assertEqual(self.res_mgr.get_amount(ResourceType.DARK_MATTER), 90.0)

        # 推进时间刚好到达 1 批次完成 (duration = 4.0s)
        tank.converter.update(4.0, self.res_mgr)
        # 应获得第 1 批产出 (5 合金) 且开始第 2 批 (再次扣除 10 暗物质)
        self.assertEqual(self.res_mgr.get_amount(ResourceType.ALLOY), 55.0)
        self.assertEqual(self.res_mgr.get_amount(ResourceType.DARK_MATTER), 80.0)
        self.assertTrue(tank.is_converting)

        # 推进第 2 批次完成
        tank.converter.update(4.0, self.res_mgr)
        self.assertEqual(self.res_mgr.get_amount(ResourceType.ALLOY), 60.0)
        # 任务已全部完成
        self.assertFalse(tank.is_converting)

    def test_unit_immobile_and_cannot_fire_while_converting(self):
        """测试核心要求 5：执行转换时，单位不可机动也不可开火，取消后恢复"""
        tank = Tank(x=0, y=0, size=32, speed=3.0, camp=Camp.PLAYER, tank_id="p1",
                    converter_table=["recipe_dm_to_alloy"], ammo=10)
        self.physics.add_player_tank(tank)

        # 转换前：正常机动与开火
        self.assertTrue(tank.can_fire())
        moved = self.physics.move_tank(tank, (1, 0))
        self.assertTrue(moved)
        self.assertGreater(tank.x, 0.0)

        bullet = self.physics.spawn_bullet(tank, bullet_speed=6.0, bullet_size=8)
        self.assertIsNotNone(bullet)

        # 开启转换
        recipe = RecipeRegistry.get("recipe_dm_to_alloy")
        tank.converter.enqueue(recipe, count=1, resource_manager=self.res_mgr)
        self.assertTrue(tank.is_converting)

        # 转换中：禁止开火与机动
        self.assertFalse(tank.can_fire())
        bullet2 = self.physics.spawn_bullet(tank, bullet_speed=6.0, bullet_size=8)
        self.assertIsNone(bullet2, "转换中的单位不得发射炮弹")

        old_x, old_y = tank.x, tank.y
        moved_while_converting = self.physics.move_tank(tank, (1, 0))
        self.assertFalse(moved_while_converting, "转换中的单位不可移动")
        self.assertEqual(tank.x, old_x)
        self.assertEqual(tank.y, old_y)

        # 取消转换
        tank.converter.terminate()
        self.assertFalse(tank.is_converting)
        tank.fire_cooldown = 0

        # 恢复机动与开火
        self.assertTrue(tank.can_fire())
        moved_after_term = self.physics.move_tank(tank, (1, 0))
        self.assertTrue(moved_after_term)

    def test_api_convert_and_terminate(self):
        """测试要求 4：api.convert() 与 api.terminate_convert()"""
        tank = Tank(x=0, y=0, size=32, speed=3.0, camp=Camp.PLAYER, tank_id="p1",
                    converter_table=["recipe_dm_to_alloy"])
        self.physics.add_player_tank(tank)

        ctx = MockGameContext(self.physics, self.game_map, self.res_mgr)
        api = GameAPIController(ctx)

        # 1. 尝试对无权配方报错
        resp_err = api.convert({"unit_id": "p1", "recipe_id": "invalid_recipe", "count": 1})
        self.assertEqual(resp_err["status"], "error")

        # 2. 正常发起转换
        resp = api.convert({"unit_id": "p1", "recipe_id": "recipe_dm_to_alloy", "count": 3})
        self.assertEqual(resp["status"], "ok")
        self.assertTrue(tank.is_converting)

        # 3. report 接口验证
        rep_resp = api.report({"unit_id": "p1"})
        rep = rep_resp["report"]
        self.assertTrue(rep["is_converting"])
        self.assertIn("recipe_dm_to_alloy", rep["converter_table"])

        # 4. api.terminate_convert 清空
        term_resp = api.terminate_convert({"unit_id": "p1"})
        self.assertEqual(term_resp["status"], "ok")
        self.assertFalse(tank.is_converting)

        # 5. api.get_resources
        res_resp = api.get_resources({})
        self.assertEqual(res_resp["status"], "ok")
        self.assertIn("dark_matter", res_resp["resources"])

    def test_resource_amount_victory_condition(self):
        """测试要求 6：将资源数目增添到胜利条件 (ResourceAmountCondition)"""
        cond = ResourceAmountCondition("dark_matter", 150.0)
        ctx = ConditionContext(self.physics, self.game_map, self.res_mgr)

        # 初始 100.0，未达到 150.0
        self.assertFalse(cond.evaluate(ctx))

        # 补充到 160.0
        self.res_mgr.add_resource("dark_matter", 60.0)
        self.assertTrue(cond.evaluate(ctx))

        # 通过 ConditionBuilder AST 构建测试
        builder_cond = ConditionBuilder.build({
            "type": "resource_amount",
            "resource_type": "alloy",
            "amount": 80.0
        })
        self.assertFalse(builder_cond.evaluate(ctx))
        self.res_mgr.add_resource("alloy", 40.0)
        self.assertTrue(builder_cond.evaluate(ctx))

    def test_harvest_mechanics_radius_and_exclusivity(self):
        """测试核心要求 1：不同资源不同采集速度、采集半径与排他半径独占机制"""
        # 创建位于暗物质块 (2, 2) 旁边的我方战车 (坐标 2*32=64, 2*32=64，中心重合)
        tank = Tank(x=64, y=64, size=32, speed=3.0, camp=Camp.PLAYER, tank_id="p_harvester",
                    harvest_speed={"dark_matter": 4.0, "alloy": 2.0})
        self.physics.add_player_tank(tank)

        dm_block = self.res_mgr.get_block_at(2, 2)
        self.assertIsNotNone(dm_block)
        dm_block.current_amount = 500.0

        # 1. 距离在采集半径 (64.0) 内
        self.assertTrue(dm_block.is_in_harvest_range(tank, tile_size=32))

        # 2. 初始状态下无敌军，排他性满足
        self.assertTrue(dm_block.is_exclusive(tank.camp, [tank], tile_size=32))

        # 启动开采
        tank.start_harvest(2, 2)
        self.assertTrue(tank.is_harvesting)

        # 推进 2 秒时间：4.0 * 2 = 8.0 暗物质开采
        initial_stockpile = self.res_mgr.get_amount(ResourceType.DARK_MATTER, camp="player")
        self.res_mgr.update_harvest([tank], dt=2.0, tile_size=32)

        self.assertEqual(tank.harvest_state, "harvesting")
        self.assertEqual(dm_block.current_amount, 492.0)
        self.assertEqual(self.res_mgr.get_amount(ResourceType.DARK_MATTER, camp="player"), initial_stockpile + 8.0)

        # 3. 超出采集半径测试
        tank.x = 300.0
        tank.y = 300.0
        self.assertFalse(dm_block.is_in_harvest_range(tank, tile_size=32))
        self.res_mgr.update_harvest([tank], dt=2.0, tile_size=32)
        self.assertEqual(tank.harvest_state, "out_of_range")
        # 储量未发生变化
        self.assertEqual(dm_block.current_amount, 492.0)

        # 4. 核心排他性争夺测试：敌方进入排他半径 (96.0) 内
        tank.x = 64.0
        tank.y = 64.0
        # 敌军出现在距离资源块中心 80px 处 (小于 exclusive_radius 96.0)
        enemy = Tank(x=64.0 + 80.0, y=64.0, size=32, camp=Camp.ENEMY, tank_id="e1")
        self.physics.add_enemy_tank(enemy)

        self.assertFalse(dm_block.is_exclusive(tank.camp, [tank, enemy], tile_size=32))
        self.res_mgr.update_harvest([tank, enemy], dt=2.0, tile_size=32)
        # 产生争夺阻滞，只有排他的时候可以采集！
        self.assertEqual(tank.harvest_state, "contested")
        self.assertEqual(dm_block.current_amount, 492.0)

        # 5. 摧毁或移出敌军后，排他性恢复，采集正常继续
        enemy.alive = False
        self.assertTrue(dm_block.is_exclusive(tank.camp, [tank, enemy], tile_size=32))
        self.res_mgr.update_harvest([tank, enemy], dt=1.0, tile_size=32)
        self.assertEqual(tank.harvest_state, "harvesting")
        self.assertEqual(dm_block.current_amount, 488.0)

    def test_both_camps_harvesting_and_stockpiles(self):
        """测试敌我双方各自采集并存入各自独立的战备库"""
        alloy_block = self.res_mgr.get_block_at(4, 4)
        alloy_block.current_amount = 300.0

        enemy_harvester = Tank(x=4 * 32, y=4 * 32, size=32, camp=Camp.ENEMY, tank_id="e_harvester",
                               harvest_speed={"alloy": 5.0})
        self.physics.add_enemy_tank(enemy_harvester)

        enemy_harvester.start_harvest(4, 4)
        self.res_mgr.update_harvest([enemy_harvester], dt=3.0, tile_size=32)

        # 敌方战略库增加 15.0 合金
        self.assertEqual(self.res_mgr.get_amount(ResourceType.ALLOY, camp="enemy"), 15.0)
        # 我方战略库保持不变
        self.assertEqual(self.res_mgr.get_amount(ResourceType.ALLOY, camp="player"), 50.0)

    def test_api_and_ai_python_harvest_integration(self):
        """测试 API 控制器与 AI Python 脚本桥接开采"""
        tank = Tank(x=64, y=64, size=32, camp=Camp.PLAYER, tank_id="p_script")
        self.physics.add_player_tank(tank)
        mock_ctx = MockGameContext(self.physics, self.game_map, self.res_mgr)
        api = GameAPIController(mock_ctx)

        # 1. API 资源块列表查询
        blocks_resp = api.list_resource_blocks({"unit_id": "p_script"})
        self.assertEqual(blocks_resp["status"], "ok")
        self.assertEqual(len(blocks_resp["blocks"]), 2)

        # 2. API 下达采集指令
        h_resp = api.command_harvest({"unit_id": "p_script", "col": 2, "row": 2})
        self.assertEqual(h_resp["status"], "ok")
        self.assertTrue(tank.is_harvesting)
        self.assertEqual(tank.harvest_target, (2, 2))

        # 3. report 状态验证
        rep_resp = api.report({"unit_id": "p_script"})
        self.assertTrue(rep_resp["report"]["is_harvesting"])
        self.assertEqual(rep_resp["report"]["harvest_target"], (2, 2))

        # 4. API 停止采集
        stop_resp = api.command_stop_harvest({"unit_id": "p_script"})
        self.assertEqual(stop_resp["status"], "ok")
        self.assertFalse(tank.is_harvesting)

        # 5. AI Python Bridge 集成测试
        import threading
        from ai_python.bridge import TankScriptAPI
        stop_ev = threading.Event()
        bridge = TankScriptAPI("p_script", api, stop_ev)

        bridge_blocks = bridge.get_resource_blocks()
        self.assertEqual(len(bridge_blocks), 2)

        res_h = bridge.harvest(2, 2)
        self.assertEqual(res_h["status"], "ok")
        self.assertTrue(tank.is_harvesting)

        bridge.stop_harvest()
        self.assertFalse(tank.is_harvesting)

    def test_harvest_rates_and_hud_stockpile_consistency(self):
        """测试用户反馈问题：杜绝凭空显示 +4.0/s，实际开采时速率与总量严格同步更新"""
        # 初始状态下无坦克采集：开采流入速率应为 0.0，绝不凭空出现 +4.0/s
        player_harvest_rates = self.res_mgr.get_harvest_rates("player")
        self.assertEqual(player_harvest_rates.get("dark_matter", 0.0), 0.0)
        self.assertEqual(player_harvest_rates.get("alloy", 0.0), 0.0)

        # 自然再生总速率仍然正确统计实体资源块
        block_regen = self.res_mgr.get_block_regen_rates()
        self.assertGreater(block_regen.get("dark_matter", 0.0), 0.0)

        # 部署一辆位于暗物质块旁的战车 (采集速度 2.5)
        tank = Tank(x=64, y=64, size=32, camp=Camp.PLAYER, tank_id="p_tester",
                    harvest_speed={"dark_matter": 2.5, "alloy": 1.0})
        self.physics.add_player_tank(tank)

        from command.dispatcher import CommandDispatcher
        dispatcher = CommandDispatcher()
        dispatcher.register_tank(tank)

        # 通过调度器下达采集命令
        dispatcher.issue_harvest([tank], target_col=2, target_row=2, resource_manager=self.res_mgr)

        # 推进一帧调度与开采循环
        dispatcher.update([tank], micro_tank=None, has_manual_input=False, physics_engine=self.physics, game_map=self.game_map)
        self.assertTrue(tank.is_harvesting)

        # 推进 2 秒开采
        self.res_mgr.update_harvest([tank], dt=2.0, tile_size=32)

        # 此时采集速率应精确为 2.5/s，总量从 100 增至 105.0
        cur_rates = self.res_mgr.get_harvest_rates("player")
        self.assertEqual(cur_rates.get("dark_matter"), 2.5)
        self.assertEqual(self.res_mgr.get_amount("dark_matter", camp="player"), 105.0)

        # 当下达移动指令到其他空地时，开采动作被自动取消，开采速率归零
        dispatcher.issue_move([tank], target_x=200, target_y=200)
        self.assertFalse(tank.is_harvesting)
        self.res_mgr.update_harvest([tank], dt=1.0, tile_size=32)
        cur_rates_stopped = self.res_mgr.get_harvest_rates("player")
        self.assertEqual(cur_rates_stopped.get("dark_matter", 0.0), 0.0)
        # 总量保持在 105.0 不再无故增加
        self.assertEqual(self.res_mgr.get_amount("dark_matter", camp="player"), 105.0)


if __name__ == "__main__":
    unittest.main()
