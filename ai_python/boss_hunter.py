"""
战术脚本：Boss 重装猎杀者 (Boss Hunter)
全知全能视野：
1. 扫描战局中所有对手单位；
2. 优先猎杀防御塔与残血脆皮单位；
3. 计算距离与走位，持续进行集火追猎与火力压制；
4. 目标阵亡后自适应重新锁定下一高威胁目标。
"""
import math

def run(api):
    logger.info("Boss Hunter script started for %s", api.tank_id)

    while not api.should_stop():
        # 1. 查询自身状态
        me = api.get_status()
        if not me or not me.get("alive", False):
            break

        my_x = me.get("x", 0.0)
        my_y = me.get("y", 0.0)

        # 2. 全知全能获取所有对手
        opponents = api.get_opponents()
        if not opponents:
            # 战局无敌对目标，休眠巡逻
            api.sleep(0.5)
            continue

        # 3. 目标价值打分算法：防御塔权重最高，其次为 HP 较低者，再次为距离最近者
        best_target = None
        best_score = -999999.0

        for opp in opponents:
            ox = opp.get("x", 0.0)
            oy = opp.get("y", 0.0)
            dist = math.hypot(ox - my_x, oy - my_y)
            hp = opp.get("hp", 1)
            is_tower = opp.get("is_tower", False)

            # 评分：防御塔加分 500，低 HP 加分，距离近加分
            score = 1000.0 - (dist * 1.0) - (hp * 50.0)
            if is_tower:
                score += 500.0

            if score > best_score:
                best_score = score
                best_target = opp

        if best_target:
            target_id = best_target.get("id")
            # 4. 下达集火攻击指令
            api.attack(target_id)

            # 5. 计算朝向发射支援炮火
            tx = best_target.get("x", 0.0)
            ty = best_target.get("y", 0.0)
            dx = tx - my_x
            dy = ty - my_y

            # 若大致在同一直线上，果断开火轰击
            if abs(dx) < 32.0:
                fire_dir = "DOWN" if dy > 0 else "UP"
                api.fire(fire_dir)
            elif abs(dy) < 32.0:
                fire_dir = "RIGHT" if dx > 0 else "LEFT"
                api.fire(fire_dir)

        # 战术循环评估节拍
        api.sleep(0.3)
