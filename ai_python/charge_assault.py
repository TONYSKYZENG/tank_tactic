"""
战术脚本：强袭突击队 (Charge Assault)
全知全能视野：
1. 锁定玩家核心要塞（如 core_supply_base）或主要防线；
2. 保持高速移动向前推进突防；
3. 行进途中沿途持续发射火炮清除障碍与阻拦部队。
"""
import math

def run(api):
    logger.info("Charge Assault script started for %s", api.tank_id)

    while not api.should_stop():
        me = api.get_status()
        if not me or not me.get("alive", False):
            break

        opponents = api.get_opponents()
        if not opponents:
            api.sleep(0.5)
            continue

        # 优先寻找核心要塞或基座防御塔
        core_target = None
        for opp in opponents:
            if opp.get("is_tower", False) or "supply" in opp.get("id", "") or "base" in opp.get("id", ""):
                core_target = opp
                break

        # 若无核心要塞，锁定最近的对手
        if not core_target:
            my_x = me.get("x", 0.0)
            my_y = me.get("y", 0.0)
            core_target = min(
                opponents,
                key=lambda o: (o.get("x", 0) - my_x)**2 + (o.get("y", 0) - my_y)**2
            )

        if core_target:
            api.attack(core_target.get("id"))
            # 持续发射压制火力
            api.fire()

        api.sleep(0.25)
