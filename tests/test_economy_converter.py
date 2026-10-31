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

    def test_free_recipe_without_inputs(self):
        """测试要求 1：接受没有 input、直接凭空产生资源的配方"""
        free_recipe = ConverterRecipe(
            id="recipe_vacuum_energy",
            name="converter.recipe.vacuum_energy",
            inputs={},
            outputs={"dark_matter": 7.5},
            duration=2.0
        )
        self.res_mgr.stockpiles["player"]["dark_matter"] = 0.0
        tank = Tank(x=0, y=0, size=32, camp=Camp.PLAYER, tank_id="harvester_alpha",
                    converter_table=["recipe_vacuum_energy"])
        self.physics.add_player_tank(tank)

        # 即使没有任何暗物质输入，也允许启动 2 批次
        ok, reason = tank.converter.enqueue(free_recipe, count=2, resource_manager=self.res_mgr)
        self.assertTrue(ok)
        self.assertEqual(reason, "started")
        self.assertTrue(tank.is_converting)

        # 推进 2.0s，第 1 批完成
        tank.converter.update(2.0, self.res_mgr)
        self.assertEqual(self.res_mgr.get_amount("dark_matter"), 7.5)
        self.assertTrue(tank.is_converting)

        # 推进 2.0s，第 2 批完成
        tank.converter.update(2.0, self.res_mgr)
        self.assertEqual(self.res_mgr.get_amount("dark_matter"), 15.0)
        self.assertFalse(tank.is_converting)

    def test_tank_production_auto_id_and_global_spawn(self):
        """测试要求 2, 3, 4, 5：output 为 tank，携带可见性、视野、初始弹药，ID 为 生产者/序号，在周围空地生成并加入全局"""
        tank_recipe = ConverterRecipe(
            id="recipe_produce_fighter",
            name="converter.recipe.produce_fighter",
            inputs={"alloy": 10.0},
            outputs="tank",
            duration=3.0,
            output_type="tank",
            visibility=0.75,
            vision_size=310.0,
            ammo=25
        )
        self.res_mgr.stockpiles["player"]["alloy"] = 30.0

        builder = Tank(x=64, y=64, size=32, camp=Camp.PLAYER, tank_id="builder_prime",
                      converter_table=["recipe_produce_fighter"])
        self.physics.add_player_tank(builder)

        from command.dispatcher import CommandDispatcher
        dispatcher = CommandDispatcher()
        dispatcher.register_tank(builder)

        self.assertEqual(len(self.physics.player_tanks), 1)

        # 启动 2 批次建造
        ok, reason = builder.converter.enqueue(tank_recipe, count=2, resource_manager=self.res_mgr)
        self.assertTrue(ok)
        self.assertEqual(self.res_mgr.get_amount("alloy"), 20.0)

        # 推进 3.0s 生产出第 1 辆战车
        spawned1 = builder.converter.update(
            3.0, self.res_mgr, camp="player",
            physics_engine=self.physics, game_map=self.game_map,
            command_dispatcher=dispatcher
        )
        self.assertEqual(len(spawned1), 1)
        tank1 = spawned1[0]

        # 校验 4: 自动生成 ID 为 生产者/序号
        self.assertEqual(tank1.id, "builder_prime/1")

        # 校验 3: 可见性、视野、初始弹药
        self.assertAlmostEqual(tank1.visibility, 0.75)
        self.assertAlmostEqual(tank1.vision_size, 310.0)
        self.assertEqual(tank1.ammo, 25)

        # 校验 5: 增加到全局 (physics_engine 及 command_dispatcher)
        self.assertIn(tank1, self.physics.player_tanks)
        self.assertIn(tank1.id, dispatcher.tank_tactics)

        # 校验 5: 自动在生产者周围空地生成（不与生产者重合碰撞）
        self.assertFalse(tank1.rect.collides_with(builder.rect))
        self.assertTrue(self.physics.can_move_to(tank1, tank1.x, tank1.y))

        # 推进第 2 批次完成
        spawned2 = builder.converter.update(
            3.0, self.res_mgr, camp="player",
            physics_engine=self.physics, game_map=self.game_map,
            command_dispatcher=dispatcher
        )
        self.assertEqual(len(spawned2), 1)
        tank2 = spawned2[0]
        self.assertEqual(tank2.id, "builder_prime/2")
        self.assertIn(tank2, self.physics.player_tanks)
        self.assertFalse(tank2.rect.collides_with(builder.rect))
        self.assertFalse(tank2.rect.collides_with(tank1.rect))
        self.assertEqual(len(self.physics.player_tanks), 3)

    def test_enemy_tank_production_auto_id_and_ai(self):
        """测试敌军生产战车：自动分配 enemy 专属 ID，并注册至 AI 控制器与全局"""
        enemy_recipe = ConverterRecipe(
            id="recipe_enemy_spawn",
            name="converter.recipe.enemy_spawn",
            inputs={},
            outputs="tank",
            duration=1.0,
            output_type="tank",
            visibility=0.9,
            vision_size=200.0,
            ammo=10
        )
        enemy_factory = Tank(x=128, y=128, size=32, camp=Camp.ENEMY, tank_id="e_factory",
                             converter_table=["recipe_enemy_spawn"])
        self.physics.add_enemy_tank(enemy_factory)

        from ai.controller import EnemyAIController
        ai_ctrl = EnemyAIController(self.physics, self.game_map)

        ok, _ = enemy_factory.converter.enqueue(enemy_recipe, count=1, resource_manager=self.res_mgr, camp="enemy")
        self.assertTrue(ok)

        spawned = enemy_factory.converter.update(
            1.0, self.res_mgr, camp="enemy",
            physics_engine=self.physics, game_map=self.game_map,
            ai_controller=ai_ctrl
        )
        self.assertEqual(len(spawned), 1)
        new_enemy = spawned[0]
        self.assertEqual(new_enemy.id, "e_factory/1")
        self.assertEqual(new_enemy.camp, Camp.ENEMY)
        self.assertIn(new_enemy, self.physics.enemy_tanks)
        self.assertIn(new_enemy.id, ai_ctrl.agents)
        self.assertFalse(new_enemy.rect.collides_with(enemy_factory.rect))

    def test_recipe_registry_and_api_integration(self):
        """测试从 JSON 载入零输入配方与战车制造配方，并通过 API 下达建造"""
        from converter.loader import RecipeRegistry
        from api.controller import GameAPIController

        recipes = RecipeRegistry.load_recipes()
        self.assertIn("recipe_free_energy", recipes)
        self.assertIn("recipe_build_tank", recipes)

        r_free = recipes["recipe_free_energy"]
        self.assertEqual(r_free.inputs, {})
        self.assertEqual(r_free.output_type, "resource")

        r_tank = recipes["recipe_build_tank"]
        self.assertEqual(r_tank.output_type, "tank")
        self.assertEqual(r_tank.visibility, 0.9)
        self.assertEqual(r_tank.vision_size, 300.0)
        self.assertEqual(r_tank.ammo, 25)

        # 模拟通过 API 控制器触发转换
        factory = Tank(x=32, y=32, size=32, camp=Camp.PLAYER, tank_id="api_factory",
                       converter_table=["recipe_free_energy", "recipe_build_tank"])
        self.physics.add_player_tank(factory)

        class MockGameCtx:
            def __init__(self, physics, res_mgr):
                self.physics_engine = physics
                self.resource_manager = res_mgr

        api = GameAPIController(MockGameCtx(self.physics, self.res_mgr))
        resp = api.convert({"unit_id": "api_factory", "recipe_id": "recipe_free_energy", "count": 1})
        self.assertEqual(resp["status"], "ok")
        self.assertTrue(factory.is_converting)

    def test_new_and_modified_tank_types_balance(self):
        """测试新增/修改的三类单位平衡性与特性定义：犀牛坦克、基地车、天启坦克"""
        from tank_configs.config_loader import TankConfig
        from converter.loader import RecipeRegistry

        # 1. 犀牛坦克：可采集，不可建造其他单位，不可转化，廉价跑得快的报纸壳壳，可被建造
        cfg_rhino = TankConfig.from_json("tank_configs/rhino_tank.json")
        self.assertEqual(cfg_rhino.name, "Rhino Tank")
        self.assertGreaterEqual(cfg_rhino.speed, 3.8)      # 跑得快
        self.assertEqual(cfg_rhino.health, 1)             # 报纸壳壳
        self.assertFalse(cfg_rhino.can_crush_bricks)      # 不可破障
        self.assertEqual(cfg_rhino.converter_table, [])   # 不可转化、不可建造其他单位
        self.assertIn("dark_matter", cfg_rhino.harvest_speed)  # 可采集
        self.assertIn("alloy", cfg_rhino.harvest_speed)

        # 检查可被建造配方
        recipes = RecipeRegistry.load_recipes()
        self.assertIn("recipe_build_rhino", recipes)
        r_rhino = recipes["recipe_build_rhino"]
        self.assertEqual(r_rhino.output_type, "tank")
        self.assertEqual(r_rhino.tank_config, "tank_configs/rhino_tank.json")
        self.assertLessEqual(r_rhino.duration, 3.0)       # 建造极快且廉价

        # 2. 基地车：可采集，可建造，可被建造，可转化，可破障，跑得慢
        cfg_mcv = TankConfig.from_json("tank_configs/mcv_tank.json")
        self.assertEqual(cfg_mcv.name, "Mobile Construction Vehicle")
        self.assertLessEqual(cfg_mcv.speed, 1.8)          # 跑得慢
        self.assertGreaterEqual(cfg_mcv.health, 8)        # 高生命值重型单位
        self.assertTrue(cfg_mcv.can_crush_bricks)         # 可破障
        self.assertIn("dark_matter", cfg_mcv.harvest_speed)   # 可采集
        self.assertIn("alloy", cfg_mcv.harvest_speed)
        # 可转化：包含资源转换配方
        self.assertIn("recipe_dm_to_alloy", cfg_mcv.converter_table)
        self.assertIn("recipe_hyper_fusion", cfg_mcv.converter_table)
        # 可建造：包含单位生产配方
        self.assertIn("recipe_build_rhino", cfg_mcv.converter_table)
        self.assertIn("recipe_build_apocalypse", cfg_mcv.converter_table)
        self.assertIn("recipe_build_mcv", cfg_mcv.converter_table)

        # 检查可被建造配方
        self.assertIn("recipe_build_mcv", recipes)
        r_mcv = recipes["recipe_build_mcv"]
        self.assertEqual(r_mcv.output_type, "tank")
        self.assertEqual(r_mcv.tank_config, "tank_configs/mcv_tank.json")
        self.assertGreaterEqual(r_mcv.duration, 8.0)      # 基地车建造成本与时间高

        # 3. 天启坦克：可采集，不可建造其他单位，可被建造，能破障和转化，速度一般
        cfg_apoc = TankConfig.from_json("tank_configs/apocalypse_tank.json")
        self.assertEqual(cfg_apoc.name, "Apocalypse Tank")
        self.assertTrue(2.0 <= cfg_apoc.speed <= 2.8)     # 速度一般
        self.assertGreaterEqual(cfg_apoc.health, 5)       # 重装甲
        self.assertTrue(cfg_apoc.can_crush_bricks)        # 能破障
        self.assertIn("dark_matter", cfg_apoc.harvest_speed)  # 可采集
        # 能转化：包含资源转换配方
        self.assertIn("recipe_dm_to_alloy", cfg_apoc.converter_table)
        # 不可建造其他单位：严格不包含任何以 recipe_build_ 为前缀的建造配方
        build_recipes = [r_id for r_id in cfg_apoc.converter_table if "build" in r_id]
        self.assertEqual(build_recipes, [])

        # 检查可被建造配方
        self.assertIn("recipe_build_apocalypse", recipes)
        r_apoc = recipes["recipe_build_apocalypse"]
        self.assertEqual(r_apoc.output_type, "tank")
        self.assertEqual(r_apoc.tank_config, "tank_configs/apocalypse_tank.json")

        # 4. 实机生产验证：基地车生产天启坦克和犀牛坦克
        mcv_tank = Tank(x=100, y=100, size=cfg_mcv.size, camp=Camp.PLAYER, tank_id="mcv_01",
                        converter_table=cfg_mcv.converter_table)
        self.physics.add_player_tank(mcv_tank)
        self.res_mgr.stockpiles["player"]["alloy"] = 100.0
        self.res_mgr.stockpiles["player"]["dark_matter"] = 100.0

        # 基地车生产犀牛坦克
        ok, reason = mcv_tank.converter.enqueue(r_rhino, count=1, resource_manager=self.res_mgr)
        self.assertTrue(ok)
        spawned = mcv_tank.converter.update(
            r_rhino.duration, self.res_mgr, camp="player",
            physics_engine=self.physics, game_map=self.game_map
        )
        self.assertEqual(len(spawned), 1)
        rhino_spawned = spawned[0]
        self.assertEqual(rhino_spawned.id, "mcv_01/1")
        self.assertEqual(rhino_spawned.speed, 4.0)
        self.assertEqual(rhino_spawned.health, 1)
        self.assertEqual(rhino_spawned.converter_table, [])
        self.assertFalse(rhino_spawned.can_crush_bricks)
        self.assertIn(rhino_spawned, self.physics.player_tanks)
        self.assertFalse(rhino_spawned.rect.collides_with(mcv_tank.rect))

    def test_mcv_harvest_movement_and_collection(self):
        """测试大型基地车 (MCV, size=44 > tile_size=36) 前往并开采资源块全流程"""
        from command.dispatcher import CommandDispatcher
        from tank_configs.config_loader import TankConfig
        from api.controller import GameAPIController
        from map_loader.loader import MapLoader
        from mission_loader.loader import MissionLoader

        m = MissionLoader.load_from_file('missions/mission_01.json')
        gmap = MapLoader.load_from_file(m.map_file)
        pe = PhysicsEngine(gmap, fog_of_war_enabled=False)
        dispatcher = CommandDispatcher()
        res_mgr = ResourceManager(initial_resources={"dark_matter": 0.0, "alloy": 0.0})
        res_mgr.init_from_map(gmap)

        mcv_cfg = TankConfig.from_json('tank_configs/mcv_tank.json')
        mcv = Tank(
            x=8 * 36, y=14 * 36, size=mcv_cfg.size, speed=mcv_cfg.speed,
            camp=Camp.PLAYER, tank_id="player_mcv",
            can_crush_bricks=mcv_cfg.can_crush_bricks,
            harvest_speed=mcv_cfg.harvest_speed
        )
        pe.add_player_tank(mcv)
        dispatcher.register_tank(mcv)

        # 1. 验证可为大型基地车成功计算站位坐标，不返回 None
        target_block = res_mgr.get_block_at(3, 12)
        self.assertIsNotNone(target_block)
        from command.commands import HarvestCommand
        harvest_cmd = HarvestCommand(3, 12, res_mgr)
        stand_pos = harvest_cmd._find_standable_harvest_pos(mcv, pe, gmap, target_block)
        self.assertIsNotNone(stand_pos)
        self.assertTrue(pe.can_move_to(mcv, stand_pos[0], stand_pos[1]))

        # 2. 下达采集指令并推进仿真
        dispatcher.issue_harvest([mcv], 3, 12, res_mgr)
        for _ in range(160):
            cmd = dispatcher.tank_commands.get(mcv.id)
            if cmd:
                cmd.execute(mcv, pe, gmap)
            res_mgr.update(0.016)
            res_mgr.update_harvest([mcv], 0.016, gmap.tile_size)

        # 3. 校验基地车已就位并展开开采
        self.assertTrue(mcv.is_harvesting)
        self.assertEqual(mcv.harvest_state, "harvesting")
        self.assertGreater(res_mgr.get_amount("dark_matter", "player"), 0.0)

        # 4. 校验 API 停止采集
        class MockGameCtx:
            def __init__(self, physics, disp, rm, gm):
                self.physics_engine = physics
                self.command_dispatcher = disp
                self.resource_manager = rm
                self.game_map = gm

        ctx = MockGameCtx(pe, dispatcher, res_mgr, gmap)
        api = GameAPIController(ctx)
        import json
        stop_resp = json.loads(api.handle_request(json.dumps({"action": "api.stop_harvest", "unit_id": "player_mcv"})))
        self.assertEqual(stop_resp["status"], "ok")
        self.assertFalse(mcv.is_harvesting)
        self.assertIsNone(dispatcher.tank_commands.get("player_mcv"))


if __name__ == "__main__":
    unittest.main()
