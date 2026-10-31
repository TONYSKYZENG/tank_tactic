"""
敌方适中指挥官脚本 (Intermediate Enemy Commander)
运行宿主：敌方防御塔 / 前哨基地
战术风格：
- 攻守兼备，决策心跳 1.0 秒
- 严格兵种协同：只挑具备攻击能力的战斗战车冲锋，基地车绝对不肉身突击
- 经济暴兵循环：兵力不足时优先利用基地车制造战车；资源不足时自动进行配方转换或采矿
- 梯队出击：战斗群集结后梯队压上集火突击，留兵保卫核心
"""
import math
import logging

logger = logging.getLogger("CommanderIntermediate")

def run(api):
    logger.info("Intermediate Commander operational on %s", api.tank_id)

    while not api.should_stop():
        me = api.get_status()
        if not me or not me.get("alive", False):
            break

        my_x = me.get("x", 0.0)
        my_y = me.get("y", 0.0)

        allies = api.get_allies()
        opponents = api.get_opponents()

        # 1. 严格区分战斗单位与非战斗建造/采集单位 (MCV 禁止冲锋)
        combat_units = [a for a in allies if not a.get("is_tower", False) and a.get("can_attack", True)]
        builders = [a for a in allies if a.get("converter_table")]
        harvesters = [a for a in allies if not a.get("is_tower", False) and not a.get("can_attack", True)]

        # 2. 宏观经济调控：兵力不足 (战斗单位 < 2) 时优先造兵，无法造兵就转换或采矿
        res_info = api.get_resources()
        cur_res = res_info.get("resources", {})
        alloy = float(cur_res.get("alloy", 0.0))
        dark_matter = float(cur_res.get("dark_matter", 0.0))

        is_army_insufficient = len(combat_units) < 2

        for builder in builders:
            bid = builder["id"]
            stat = api.report(bid)
            conv_tbl = stat.get("converter_table", [])
            conv_stat = stat.get("converter_status") or {}
            is_converting = conv_stat.get("is_converting", False) or stat.get("is_converting", False)

            # (1) 兵力不足时优先造兵
            if is_army_insufficient and not is_converting and conv_tbl:
                # 生产天启重坦 (alloy >= 25, dm >= 18)
                if "recipe_build_apocalypse" in conv_tbl and alloy >= 25.0 and dark_matter >= 18.0:
                    if stat.get("is_harvesting"):
                        api.stop_harvest(bid)
                    api.convert("recipe_build_apocalypse", count=1, unit_id=bid)
                    is_converting = True
                # 生产犀牛战车 (alloy >= 8, dm >= 4)
                elif "recipe_build_rhino" in conv_tbl and alloy >= 8.0 and dark_matter >= 4.0:
                    if stat.get("is_harvesting"):
                        api.stop_harvest(bid)
                    api.convert("recipe_build_rhino", count=1, unit_id=bid)
                    is_converting = True
                # 生产标准战车 (alloy >= 15)
                elif "recipe_build_tank" in conv_tbl and alloy >= 15.0:
                    if stat.get("is_harvesting"):
                        api.stop_harvest(bid)
                    api.convert("recipe_build_tank", count=1, unit_id=bid)
                    is_converting = True

                # (2) 无法造兵时：若有配方差额则进行转换
                if not is_converting:
                    # 缺少合金制造犀牛，暗物质充裕 (dm >= 14, alloy < 8) -> 转换为合金
                    if "recipe_dm_to_alloy" in conv_tbl and dark_matter >= 14.0 and alloy < 8.0:
                        if stat.get("is_harvesting"):
                            api.stop_harvest(bid)
                        api.convert("recipe_dm_to_alloy", count=1, unit_id=bid)
                        is_converting = True
                    # 缺少暗物质，合金充裕 (alloy >= 18, dm < 4) -> 转换为暗物质
                    elif "recipe_alloy_to_dm" in conv_tbl and alloy >= 18.0 and dark_matter < 4.0:
                        if stat.get("is_harvesting"):
                            api.stop_harvest(bid)
                        api.convert("recipe_alloy_to_dm", count=1, unit_id=bid)
                        is_converting = True

        # (3) 无法造兵或闲置时：组织采矿 (优先派遣非战斗单位 MCV 采矿)
        active_harvesters = harvesters if harvesters else [b for b in builders if not (api.report(b["id"]).get("is_converting", False))]
        if active_harvesters:
            blocks = api.get_resource_blocks()
            valid_blocks = [b for b in blocks if b.get("current_amount", 0.0) > 0 and b.get("is_exclusive", True)]
            if valid_blocks:
                for h in active_harvesters:
                    h_stat = api.report(h["id"])
                    # 若正在开采有效矿石且未枯竭，保持开采
                    if h_stat.get("is_harvesting") and h_stat.get("harvest_state") in ("harvesting", "contested"):
                        continue
                    # 若在转换中，不打断
                    if h_stat.get("is_converting"):
                        continue

                    # 智能选择急缺资源
                    hx = h_stat.get("x", 0.0)
                    hy = h_stat.get("y", 0.0)
                    preferred_blocks = valid_blocks
                    if alloy < 8.0 and dark_matter >= 4.0:
                        alloy_b = [b for b in valid_blocks if b.get("resource_type") == "alloy"]
                        if alloy_b:
                            preferred_blocks = alloy_b
                    elif dark_matter < 4.0 and alloy >= 8.0:
                        dm_b = [b for b in valid_blocks if b.get("resource_type") == "dark_matter"]
                        if dm_b:
                            preferred_blocks = dm_b

                    nearest_b = min(preferred_blocks, key=lambda b: math.hypot(b["x"] - hx, b["y"] - hy))
                    api.harvest(nearest_b["col"], nearest_b["row"], unit_id=h["id"])

        # 3. 战斗出击决策：只挑能攻击的单位 (combat_units) 冲锋
        if combat_units and opponents:
            # 威胁评估：优先拦截逼近自身防御塔的入侵者 (320 像素警戒圈)，其次残血与高价值目标
            def evaluate_target(opp):
                ox = opp.get("x", 0.0)
                oy = opp.get("y", 0.0)
                d = math.hypot(ox - my_x, oy - my_y)
                hp = opp.get("hp", 1)
                is_tower = opp.get("is_tower", False)
                threat_bonus = 800.0 if d < 320.0 else 0.0
                tower_bonus = 400.0 if is_tower else 0.0
                return threat_bonus + tower_bonus + (1000.0 - d * 0.8 - hp * 80.0)

            best_target = max(opponents, key=evaluate_target)
            target_dist_to_tower = math.hypot(best_target.get("x", 0.0) - my_x, best_target.get("y", 0.0) - my_y)

            # 梯队分工：若有 2 辆以上战斗单位，指派 1 辆离塔最近者护卫自身，其余作为突击编队协同集火
            guard_unit = None
            assault_units = list(combat_units)
            if len(combat_units) >= 2:
                guard_unit = min(combat_units, key=lambda a: math.hypot(a.get("x", 0.0) - my_x, a.get("y", 0.0) - my_y))
                api.set_guard(api.tank_id, unit_ids=[guard_unit["id"]])
                assault_units = [a for a in combat_units if a["id"] != guard_unit["id"]]

            assault_ids = [a["id"] for a in assault_units]
            if assault_ids:
                api.set_tactic("aggressive", unit_ids=assault_ids)
                api.attack(best_target["id"], unit_ids=assault_ids)
            elif guard_unit and target_dist_to_tower < 350.0:
                # 仅 1 辆战斗单位且敌军深度逼近时就地迎击
                api.attack(best_target["id"], unit_ids=[guard_unit["id"]])
            elif guard_unit:
                api.set_guard(api.tank_id, unit_ids=[guard_unit["id"]])
        elif combat_units and not opponents:
            # 无敌人时战斗单位驻守护卫防御塔
            guard_ids = [c["id"] for c in combat_units]
            api.set_guard(api.tank_id, unit_ids=guard_ids)

        api.sleep(1.0)
