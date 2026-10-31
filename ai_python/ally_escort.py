"""
战术脚本：不可控友军自主护航卫士 (Ally Escort Guard)
用于不可由玩家手动操控的我方战车 (controllable = False)：
1. 寻找核心基地 (如 core_supply_base) 或友军旗舰战车 (player_alpha)；
2. 围绕受保护目标实施环形护航与战术警戒；
3. 发现逼近核心的敌军时主动迎击阻击；
4. 弹药匮乏时自动退回补给塔补给范围。
"""
import math

def run(api):
    logger.info("Ally Escort script started for %s", api.tank_id)

    while not api.should_stop():
        me = api.get_status()
        if not me or not me.get("alive", False):
            break

        my_x = me.get("x", 0.0)
        my_y = me.get("y", 0.0)
        ammo = me.get("ammo", -1)

        allies = api.get_allies()
        opponents = api.get_opponents()

        # 1. 寻找核心护送目标（优先核心补给塔，其次为 player_alpha）
        escort_target = None
        for ally in allies:
            if "supply" in ally.get("id", "") or "base" in ally.get("id", ""):
                escort_target = ally
                break
        if not escort_target and allies:
            escort_target = allies[0]

        # 2. 检查是否有逼近保护目标的敌军威胁 (警戒圈 200 像素)
        target_threat = None
        if escort_target:
            tx = escort_target.get("x", 0.0)
            ty = escort_target.get("y", 0.0)

            for opp in opponents:
                ox = opp.get("x", 0.0)
                oy = opp.get("y", 0.0)
                d = math.hypot(ox - tx, oy - ty)
                if d < 220.0:
                    target_threat = opp
                    break

        # 3. 弹药紧急且有补给塔时退守补给
        if 0 <= ammo < 3 and escort_target and escort_target.get("is_tower", False):
            api.move(escort_target.get("x", 0.0), escort_target.get("y", 0.0))
        elif target_threat:
            # 迎击威胁
            api.attack(target_threat.get("id"))
            api.fire()
        elif escort_target:
            # 贴身护航
            api.set_guard(escort_target.get("id"))

        api.sleep(0.3)
