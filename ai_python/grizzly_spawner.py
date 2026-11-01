"""
战术脚本：敌方每 10 秒刷新灰熊坦克支援 (Enemy Grizzly Tank Periodic Spawner)

工作原理：
1. 监控活跃引擎时间（api.get_time_ms），在游戏暂停期间严格冻结计时；
2. 每累计 10 秒 (10,000 毫秒) 活跃战局时间，动态为敌军阵营部署一台灰熊坦克 (Grizzly Tank)；
3. 新增的灰熊坦克自动配置 charge_base / hunter 战术，直接向我方防线施加压力；
4. 完美感知线程退出信号与全量暂停机制。
"""
import random
import logging

logger = logging.getLogger("AI.GrizzlySpawner")

def run(api):
    logger.info("Enemy Grizzly Spawner script started for host unit: %s", api.tank_id)

    spawn_interval_ms = 10000  # 10 秒 (10,000 毫秒)
    last_spawn_time_ms = api.get_time_ms()
    spawn_counter = 0

    # 获取地图边界
    mission_info = api.get_mission_info()
    max_x = float(mission_info.get("max_x", 720.0))
    max_y = float(mission_info.get("max_y", 576.0))

    while not api.should_stop():
        # 1. 检查宿主单位状态
        me = api.get_status()
        if not me or not me.get("alive", False):
            logger.info("Host unit is offline or destroyed. Grizzly Spawner terminating.")
            break

        # 2. 查询当前引擎活跃毫秒数 (暂停期间冻结)
        current_time_ms = api.get_time_ms()
        elapsed_ms = current_time_ms - last_spawn_time_ms

        if elapsed_ms >= spawn_interval_ms:
            spawn_counter += 1
            my_x = me.get("x", 200.0)
            my_y = me.get("y", 100.0)

            # 在宿主周围生成随机微小偏移，防止重叠
            offset_x = random.uniform(-45.0, 45.0)
            offset_y = random.uniform(-45.0, 45.0)
            spawn_x = max(36.0, min(max_x - 36.0, my_x + offset_x))
            spawn_y = max(36.0, min(max_y - 36.0, my_y + offset_y))

            unit_id = f"enemy_grizzly_{spawn_counter}"
            resp = api.create_unit(
                camp="enemy",
                config_file="grizzly_tank",
                x=spawn_x,
                y=spawn_y,
                unit_id=unit_id,
                tactic="charge_base"
            )

            if resp.get("status") == "ok":
                logger.info(
                    "★ Successfully spawned enemy Grizzly Tank '%s' at (%.1f, %.1f) [Game Time: %d ms]",
                    unit_id, spawn_x, spawn_y, current_time_ms
                )
            else:
                logger.warning("Failed to spawn Grizzly Tank: %s", resp)

            last_spawn_time_ms = current_time_ms

        # 休眠 0.5 秒（引擎暂停期间自动冻结等待，不空耗 CPU）
        api.sleep(0.5)

if __name__ == "__main__":
    pass
