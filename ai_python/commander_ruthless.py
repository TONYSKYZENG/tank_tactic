"""
敌方冷酷指挥官脚本 (Ruthless Enemy Commander)
运行宿主：敌方核心防御塔 / 重型加农要塞
战术风格：
- 极速心跳（0.5 秒高频决策），绝不留情
- 严格兵种分类：基地车只负责开采与转换暴兵，绝不白白送死冲锋；只挑能攻击的战斗群全军突击
- 宏观经济暴兵：兵力不足时优先利用基地车制造战车（天启重坦与犀牛突击队）；资源不足时自动通过配方转换或开采积累
- 狼群集群齐射：战车群统一进攻姿态 (aggressive)，专注战略斩首与残血歼灭
"""
import math
import logging

logger = logging.getLogger("CommanderRuthless")

def run(api):
    logger.info("Ruthless Commander operational on %s", api.tank_id)

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

        # 2. 宏观经济调控与战车制造暴兵
        res_info = api.get_resources()
        cur_res = res_info.get("resources", {})
        alloy = float(cur_res.get("alloy", 0.0))
        dark_matter = float(cur_res.get("dark_matter", 0.0))

        # 兵力少于 3 辆时强力暴兵
        is_army_insufficient = len(combat_units) < 3

        for builder in builders:
            bid = builder["id"]
            stat = api.report(bid)
            conv_tbl = stat.get("converter_table", [])
            conv_stat = stat.get("converter_status") or {}
            is_converting = conv_stat.get("is_converting", False) or stat.get("is_converting", False)

            # (1) 兵力不足时优先造兵
            if is_army_insufficient and not is_converting and conv_tbl:
                # 生产天启重型主战坦克
                if "recipe_build_apocalypse" in conv_tbl and alloy >= 25.0 and dark_matter >= 18.0:
                    if stat.get("is_harvesting"):
                        api.stop_harvest(bid)
                    api.convert("recipe_build_apocalypse", count=1, unit_id=bid)
                    is_converting = True
                # 生产犀牛极速骚扰坦克
                elif "recipe_build_rhino" in conv_tbl and alloy >= 8.0 and dark_matter >= 4.0:
                    if stat.get("is_harvesting"):
                        api.stop_harvest(bid)
                    api.convert("recipe_build_rhino", count=1, unit_id=bid)
                    is_converting = True
                # 生产标准战车
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

        # (3) 无法造兵或闲置时组织非战斗基地车采矿
        active_harvesters = harvesters if harvesters else [b for b in builders if not (api.report(b["id"]).get("is_converting", False))]
        if active_harvesters:
            blocks = api.get_resource_blocks()
            active_blocks = [b for b in blocks if b.get("current_amount", 0.0) > 0 and b.get("is_exclusive", True)]
            if active_blocks:
                for idx, h in enumerate(active_harvesters):
                    h_stat = api.report(h["id"])
                    if h_stat.get("is_harvesting") and h_stat.get("harvest_state") in ("harvesting", "contested"):
                        continue
                    if h_stat.get("is_converting"):
                        continue

                    # 优先采掘最紧缺资源
                    preferred = active_blocks
                    if alloy < 8.0 and dark_matter >= 4.0:
                        alloy_b = [b for b in active_blocks if b.get("resource_type") == "alloy"]
                        if alloy_b: preferred = alloy_b
                    elif dark_matter < 4.0 and alloy >= 8.0:
                        dm_b = [b for b in active_blocks if b.get("resource_type") == "dark_matter"]
                        if dm_b: preferred = dm_b

                    hx = h_stat.get("x", 0.0)
                    hy = h_stat.get("y", 0.0)
                    target_b = min(preferred, key=lambda b: math.hypot(b["x"] - hx, b["y"] - hy))
                    api.harvest(target_b["col"], target_b["row"], unit_id=h["id"])

        # 3. 狼群战术与弱点斩杀目标选择：只挑能攻击的战斗单位 (combat_units) 冲锋
        if combat_units and opponents:
            combat_ids = [c["id"] for c in combat_units]
            avg_ax = sum(a.get("x", 0.0) for a in combat_units) / len(combat_units)
            avg_ay = sum(a.get("y", 0.0) for a in combat_units) / len(combat_units)

            def score_target(opp):
                ox = opp.get("x", 0.0)
                oy = opp.get("y", 0.0)
                hp = opp.get("hp", 1)
                is_tower = opp.get("is_tower", False)
                dist_to_army = math.hypot(ox - avg_ax, oy - avg_ay)

                score = 1000.0 - dist_to_army * 0.5 - (hp * 120.0)
                if is_tower:
                    score += 1500.0  # 优先斩首防御塔
                return score

            primary_target = max(opponents, key=score_target)
            target_id = primary_target["id"]

            # 设定侵略姿态并狼群集火冲锋
            api.set_tactic("aggressive", unit_ids=combat_ids)
            api.attack(target_id, unit_ids=combat_ids)
        elif combat_units and not opponents:
            guard_ids = [c["id"] for c in combat_units]
            api.set_guard(api.tank_id, unit_ids=guard_ids)

        api.sleep(0.5)
