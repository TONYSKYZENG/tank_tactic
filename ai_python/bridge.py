import time
import json
import logging
import threading
from typing import Dict, Any, List, Optional

logger = logging.getLogger("TankScriptAPI")

class TankScriptAPI:
    """
    战术 Python 脚本与引擎的桥接转写 API：
    严格遵守“用 api 层的转写和引擎交互”，每一个战术动作与情报查询均转写为
    标准的 JSON 请求，分发给 GameAPIController 执行，并解析 JSON 响应返回。
    具备全知全能特性（god_mode=True），无视战争迷雾与视线遮挡。
    """

    def __init__(self, tank_id: str, api_controller, stop_event: threading.Event, script_manager=None):
        self.tank_id = tank_id
        self.api_controller = api_controller
        self.stop_event = stop_event
        self.script_manager = script_manager

    def is_engine_paused(self) -> bool:
        """检查引擎或 AI 脚本管理器是否处于暂停状态"""
        if self.script_manager and hasattr(self.script_manager, "is_paused"):
            if self.script_manager.is_paused():
                return True
        ctx = getattr(self.api_controller, "game_context", None)
        if ctx and getattr(ctx, "is_paused", False):
            return True
        return False

    def wait_if_paused(self) -> None:
        """若处于暂停状态，彻底阻塞当前战术线程，直到引擎恢复运行或收到退出信号"""
        while not self.stop_event.is_set():
            if not self.is_engine_paused():
                break
            if self.script_manager and hasattr(self.script_manager, "_pause_event"):
                self.script_manager._pause_event.wait(timeout=0.05)
            else:
                time.sleep(0.05)

    def _call(self, action: str, **params) -> Dict[str, Any]:
        """将 Python 方法调用转写为标准 JSON 协议字符串，与 GameAPIController 交互"""
        if self.stop_event.is_set():
            return {"status": "error", "error": "Script thread stopping"}

        # 标记本次 API 指令是由本车内部独立战术脚本发起的，享有本车动作执行权限
        params["_caller_unit_id"] = self.tank_id

        payload = {
            "action": action,
            "params": params
        }
        raw_json = json.dumps(payload, ensure_ascii=False)
        response_str = self.api_controller.handle_request(raw_json)
        try:
            return json.loads(response_str)
        except Exception as e:
            logger.error("API response parsing failed for %s: %s", action, e)
            return {"status": "error", "error": str(e)}

    # ================= 运行控制与睡眠 =================

    def should_stop(self) -> bool:
        """检查脚本线程是否应当终止（引擎停止、重置或坦克阵亡）"""
        if self.stop_event.is_set():
            return True
        # 若处于暂停态，阻塞等待
        self.wait_if_paused()
        if self.stop_event.is_set():
            return True
        status = self.get_status()
        return not status.get("alive", False)

    def sleep(self, seconds: float) -> None:
        """
        具备暂停感知与中断响应的安全睡眠：
        若引擎处于暂停 (pause) 状态，休眠计时器暂停累计；
        只有在非暂停时间里，才递减剩余秒数；
        收到 stop_event 瞬间终止退出。
        """
        remaining = max(0.0, float(seconds))
        while remaining > 0 and not self.stop_event.is_set():
            self.wait_if_paused()
            if self.stop_event.is_set():
                break
            t0 = time.time()
            step = min(0.05, remaining)
            time.sleep(step)
            # 只有在非暂停状态下消耗倒计时
            if not self.is_engine_paused():
                remaining -= (time.time() - t0)

    # ================= 状态与属性查询 (全知全能) =================

    def get_status(self) -> Dict[str, Any]:
        """查询本车最新完整状态（HP、坐标、速度、朝向、弹药等）"""
        resp = self._call("report", unit_id=self.tank_id)
        return resp.get("report", {})

    def report(self, unit_id: Optional[str] = None) -> Dict[str, Any]:
        """查询任意单位（无论敌我）的最新详细状态"""
        target = unit_id or self.tank_id
        resp = self._call("report", unit_id=target)
        return resp.get("report", {})

    def get_opponents(self) -> List[Dict[str, Any]]:
        """全知全能获取当前所有存活对手单位信息列表（含坐标、HP、类型等）"""
        resp = self._call("list_opponents", unit_id=self.tank_id, god_mode=True)
        return resp.get("units", [])

    def get_allies(self) -> List[Dict[str, Any]]:
        """全知全能获取当前所有存活友军单位信息列表"""
        resp = self._call("list_allies", unit_id=self.tank_id, god_mode=True)
        return resp.get("units", [])

    def is_game_success(self) -> bool:
        """查询是否达成通关胜败条件"""
        resp = self._call("is_success")
        return resp.get("is_success", False)

    def find_path(self, x: float, y: float) -> Dict[str, Any]:
        """
        计算本车到达目标坐标 (x, y) 的最优 A* 路径及所需消耗的弹药数（破障数）：
        - 无限弹药时：优先直线自动破障开辟近道；
        - 有限弹药时：自动计算最省弹药破障路线（优先零耗弹绕过障碍）。
        """
        return self._call("find_path", unit_id=self.tank_id, x=x, y=y)

    # ================= 战术动作命令下发 =================

    def move(self, x: float, y: float) -> Dict[str, Any]:
        """移动本车到目标世界坐标 (x, y)"""
        return self._call("command_move", unit_ids=[self.tank_id], x=x, y=y)

    def attack(self, target_id: str) -> Dict[str, Any]:
        """集火攻击目标单位（全知全能视角定位并追击目标）"""
        return self._call("command_attack", unit_ids=[self.tank_id], target_id=target_id, god_mode=True)

    def fire(self, direction: Optional[str] = None) -> Dict[str, Any]:
        """
        向指定方向或当前朝向发射炮弹
        :param direction: 可选 'UP', 'DOWN', 'LEFT', 'RIGHT'
        """
        params = {"unit_ids": [self.tank_id]}
        if direction:
            params["direction"] = direction
        return self._call("command_fire", **params)

    def set_tactic(self, tactic: str, guard_target_id: Optional[str] = None) -> Dict[str, Any]:
        """
        设置战术姿态
        :param tactic: 'aggressive', 'defensive', 'guard', 'stop'
        :param guard_target_id: 当 tactic 为 'guard' 时的保护目标 ID
        """
        params = {"unit_ids": [self.tank_id], "tactic": tactic}
        if guard_target_id:
            params["guard_target_id"] = guard_target_id
        return self._call("command_set_tactic", **params)

    def set_guard(self, target_id: str) -> Dict[str, Any]:
        """贴身保卫并护航目标单位"""
        return self._call("command_set_guard", unit_ids=[self.tank_id], target_id=target_id)

    # ================= 资源经济与配方转换 =================

    def convert(self, recipe_id: str, count: int = 1, unit_id: Optional[str] = None) -> Dict[str, Any]:
        """
        开始或向队列追加配方转换任务
        :param recipe_id: 配方 ID (如 'recipe_dm_to_alloy')
        :param count: 转换批次数 (默认 1)
        :param unit_id: 执行转换的目标单位 ID (缺省默认为本车 self.tank_id)
        """
        target = unit_id or self.tank_id
        return self._call("convert", unit_id=target, recipe_id=recipe_id, count=count)

    def terminate_convert(self, unit_id: Optional[str] = None) -> Dict[str, Any]:
        """
        终止并清空转换队列
        :param unit_id: 指定单位 ID 则终止该车；缺省则清空全员转换队列
        """
        params = {}
        if unit_id is not None:
            params["unit_id"] = unit_id
        return self._call("terminate_convert", **params)

    def get_resources(self) -> Dict[str, Any]:
        """查询当前拥有的所有各类资源储备及每秒产出速率"""
        return self._call("get_resources")

    def harvest(self, col: int, row: int, unit_id: Optional[str] = None) -> Dict[str, Any]:
        """
        命令指定单位（缺省默认为本车）采集地图目标瓦片 (col, row) 的资源块
        若距离超出 harvest_radius 或有敌军在 exclusive_radius 内，引擎将标记对应争夺/超距状态
        """
        target = unit_id or self.tank_id
        return self._call("harvest", unit_id=target, col=col, row=row)

    def stop_harvest(self, unit_id: Optional[str] = None) -> Dict[str, Any]:
        """停止当前资源采集动作"""
        target = unit_id or self.tank_id
        return self._call("stop_harvest", unit_id=target)

    def get_resource_blocks(self) -> List[Dict[str, Any]]:
        """全知全能查询地图上所有活跃资源块信息、当前存量、排他判定与可采集范围"""
        resp = self._call("list_resource_blocks", unit_id=self.tank_id)
        return resp.get("blocks", [])

    def harvest_nearest(self, resource_type: Optional[str] = None, unit_id: Optional[str] = None) -> Dict[str, Any]:
        """
        便捷战术动作：自动定位全图距离最近、具备存量且无敌方争夺的资源块并展开开采
        若未到达可采集半径，自动下达移动并锁定目标开采
        """
        target_uid = unit_id or self.tank_id
        my_status = self.report(target_uid)
        my_x, my_y = my_status.get("x", 0.0), my_status.get("y", 0.0)

        blocks = self.get_resource_blocks()
        if resource_type:
            blocks = [b for b in blocks if b.get("resource_type") == resource_type]

        # 筛选尚有存量的资源块
        valid_blocks = [b for b in blocks if b.get("current_amount", 0.0) > 0]
        if not valid_blocks:
            valid_blocks = blocks

        if not valid_blocks:
            return {"status": "error", "error": "No available resource blocks found"}

        # 按像素欧氏距离排序
        import math
        valid_blocks.sort(key=lambda b: math.hypot(b["x"] - my_x, b["y"] - my_y))
        best_block = valid_blocks[0]

        # 若不在采集范围内，先下达移动
        if not best_block.get("in_range", False):
            self.move(best_block["x"], best_block["y"])

        return self.harvest(best_block["col"], best_block["row"], unit_id=target_uid)
