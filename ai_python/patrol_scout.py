"""
战术脚本：巡逻侦察兵 (Patrol Scout)
全知全能视野：
1. 预设巡逻路径航点 (Waypoints)；
2. 状态机驱动：[PATROL 巡航状态] <---> [INTERCEPT 拦截歼敌状态]；
3. 当侦测到对手单位侵入防线（距离小于 220 像素）时，立即切换为拦截并集火；
4. 当威胁解除或目标摧毁后，返回巡逻航点继续巡防。
"""
import math

def run(api):
    logger.info("Patrol Scout script started for %s", api.tank_id)

    # 预设巡航航点 (世界坐标)
    waypoints = [
        (80.0, 80.0),
        (560.0, 80.0),
        (560.0, 320.0),
        (80.0, 320.0)
    ]
    current_wp_idx = 0
    state = "PATROL"
    intercept_target_id = None

    while not api.should_stop():
        me = api.get_status()
        if not me or not me.get("alive", False):
            break

        my_x = me.get("x", 0.0)
        my_y = me.get("y", 0.0)

        opponents = api.get_opponents()

        # 检查周边是否有威胁目标 (警戒半径 220.0)
        nearby_threat = None
        min_dist = 99999.0
        for opp in opponents:
            ox = opp.get("x", 0.0)
            oy = opp.get("y", 0.0)
            d = math.hypot(ox - my_x, oy - my_y)
            if d < 220.0 and d < min_dist:
                min_dist = d
                nearby_threat = opp

        # 状态切换逻辑
        if nearby_threat:
            state = "INTERCEPT"
            intercept_target_id = nearby_threat.get("id")
        else:
            state = "PATROL"
            intercept_target_id = None

        if state == "INTERCEPT" and intercept_target_id:
            api.attack(intercept_target_id)
            api.fire()
        else:
            # 执行巡逻航点导航
            dest_x, dest_y = waypoints[current_wp_idx]
            dist_to_wp = math.hypot(dest_x - my_x, dest_y - my_y)
            if dist_to_wp < 35.0:
                current_wp_idx = (current_wp_idx + 1) % len(waypoints)
                dest_x, dest_y = waypoints[current_wp_idx]

            api.move(dest_x, dest_y)

        api.sleep(0.3)
