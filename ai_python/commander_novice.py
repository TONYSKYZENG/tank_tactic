"""
敌方新手指挥官脚本 (Novice Enemy Commander)
运行宿主：敌方防御塔 / 前哨基地
战术风格：
- 反应迟缓（2.0 秒决策间隔）
- 保守防御，只挑能攻击的战斗战车在敌军深度侵入警戒圈时阻击，基地车禁止肉身冲锋
- 具备基础自保意识：无战斗单位时基地车采矿积攒资源制造基础防御战车
"""
import math
import logging

logger = logging.getLogger("CommanderNovice")

def run(api):
    logger.info("Novice Commander operational on %s", api.tank_id)

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

        # 2. 宏观调控：若无战斗单位则优先造兵，无法造兵则转换或采矿
        res_info = api.get_resources()
        cur_res = res_info.get("resources", {})
        alloy = float(cur_res.get("alloy", 0.0))
        dark_matter = float(cur_res.get("dark_matter", 0.0))

        for builder in builders:
            bid = builder["id"]
            stat = api.report(bid)
            conv_tbl = stat.get("converter_table", [])
            conv_stat = stat.get("converter_status") or {}
            is_converting = conv_stat.get("is_converting", False) or stat.get("is_converting", False)

            # (1) 兵力不足时优先造兵
            if not combat_units and not is_converting and conv_tbl:
                if "recipe_build_rhino" in conv_tbl and alloy >= 8.0 and dark_matter >= 4.0:
                    if stat.get("is_harvesting"):
                        api.stop_harvest(bid)
                    api.convert("recipe_build_rhino", count=1, unit_id=bid)
                    is_converting = True
                elif "recipe_build_tank" in conv_tbl and alloy >= 15.0:
                    if stat.get("is_harvesting"):
                        api.stop_harvest(bid)
                    api.convert("recipe_build_tank", count=1, unit_id=bid)
                    is_converting = True

                # (2) 无法造兵时通过配方转换弥补短缺
                if not is_converting:
                    if "recipe_dm_to_alloy" in conv_tbl and dark_matter >= 14.0 and alloy < 8.0:
                        if stat.get("is_harvesting"):
                            api.stop_harvest(bid)
                        api.convert("recipe_dm_to_alloy", count=1, unit_id=bid)
                        is_converting = True
                    elif "recipe_alloy_to_dm" in conv_tbl and alloy >= 18.0 and dark_matter < 4.0:
                        if stat.get("is_harvesting"):
                            api.stop_harvest(bid)
                        api.convert("recipe_alloy_to_dm", count=1, unit_id=bid)
                        is_converting = True

            # (3) 无法造兵或闲置时基地车进行基础采矿
            if not is_converting:
                if not (stat.get("is_harvesting") and stat.get("harvest_state") in ("harvesting", "contested")):
                    blocks = api.get_resource_blocks()
                    valid_blocks = [b for b in blocks if b.get("current_amount", 0.0) > 0 and b.get("is_exclusive", True)]
                    if valid_blocks:
                        hx = stat.get("x", 0.0)
                        hy = stat.get("y", 0.0)
                        nearest_b = min(valid_blocks, key=lambda b: math.hypot(b["x"] - hx, b["y"] - hy))
                        api.harvest(nearest_b["col"], nearest_b["row"], unit_id=bid)

        # 3. 战斗拦截：只挑能攻击的战斗单位阻击入侵者
        intruder = None
        min_dist_to_tower = 999999.0
        for opp in opponents:
            ox = opp.get("x", 0.0)
            oy = opp.get("y", 0.0)
            d = math.hypot(ox - my_x, oy - my_y)
            if d < 220.0 and d < min_dist_to_tower:
                min_dist_to_tower = d
                intruder = opp

        if intruder and combat_units:
            ix = intruder.get("x", 0.0)
            iy = intruder.get("y", 0.0)
            defender = min(combat_units, key=lambda a: math.hypot(a.get("x", 0.0) - ix, a.get("y", 0.0) - iy))
            api.attack(intruder["id"], unit_ids=[defender["id"]])

            idle_combats = [a["id"] for a in combat_units if a["id"] != defender["id"]]
            if idle_combats:
                api.set_tactic("defensive", unit_ids=idle_combats)
        elif not intruder and combat_units:
            ally_ids = [a["id"] for a in combat_units]
            api.set_tactic("defensive", unit_ids=ally_ids)

        api.sleep(2.0)
