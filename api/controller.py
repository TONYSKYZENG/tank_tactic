import json
import random
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from command.tactics_mode import TacticMode

logger = logging.getLogger("GameAPI")

class GameAPIController:
    """
    网络 API 核心控制器：
    负责解析外部 JSON 协议，调用物理引擎、编组与战术调度器执行控制与查询。
    """

    def __init__(self, game_context, termination_handler: Optional[Callable] = None):
        """
        :param game_context: 游戏主上下文（MainWindow.canvas 或 HeadlessGameRunner），
                             提供 physics_engine, command_dispatcher, condition_ctx,
                             victory_condition, defeat_condition 等对象
        :param termination_handler: 外部终结引擎回调
        """
        self.game_context = game_context
        self.termination_handler = termination_handler
        self.pending_actions: List[Callable[[], None]] = []

    def handle_request(self, raw_data: str) -> str:
        """接收纯文本 JSON 请求并返回纯文本 JSON 响应"""
        if not raw_data or not raw_data.strip():
            return json.dumps({"status": "error", "error": "Empty request"}, ensure_ascii=False)

        try:
            payload = json.loads(raw_data)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Invalid JSON format: {str(e)}"}, ensure_ascii=False)

        if not isinstance(payload, dict):
            return json.dumps({"status": "error", "error": "Request payload must be a JSON object"}, ensure_ascii=False)

        # 提取操作指令 (兼容 action, method, cmd 等字段)
        action = payload.get("action") or payload.get("method") or payload.get("cmd") or ""
        action = str(action).strip().lower()

        # 规范化：去除 "api." 前缀
        if action.startswith("api."):
            action = action[4:]

        params = payload.get("params")
        if not isinstance(params, dict):
            # 若未提供 params 对象，将顶层 payload 本身作为参数字典
            params = payload

        req_id = payload.get("id")

        try:
            result = self._dispatch_action(action, params)
            if req_id is not None:
                result["id"] = req_id
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.exception("Error executing API action: %s", action)
            err_resp = {"status": "error", "error": str(e)}
            if req_id is not None:
                err_resp["id"] = req_id
            return json.dumps(err_resp, ensure_ascii=False)

    def _dispatch_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        # 1. 暂停 / 继续引擎
        if action == "pause":
            return self.pause(params)
        elif action == "resume":
            return self.resume(params)
        elif action in ("is_paused", "paused"):
            return self.is_paused(params)

        # 2. 判断胜利条件
        elif action in ("is_success", "is_victory", "success"):
            return self.is_success(params)

        # 3. 终结引擎与后台
        elif action in ("terminate", "quit", "exit", "shutdown"):
            return self.terminate(params)
        elif action in ("restart", "reset", "reload"):
            return self.restart(params)

        # 4. 列出当前存活己方单位 ID (逗号隔开，带辨识度 visibility 概率过滤)
        elif action in ("list_current_unit_id", "list_units", "list_player_units"):
            return self.list_current_unit_id(params)
        elif action in ("list_enemy_curr", "list_enemies", "list_enemy"):
            return self.list_enemy_curr(params)
        elif action in ("list_enemy_mem", "enemy_mem", "list_memory", "memory"):
            return self.list_enemy_mem(params)
        elif action in ("report_enemy", "enemy_report"):
            return self.report_enemy(params)

        # 5. 批量指令操作
        elif action in ("command_move", "move"):
            return self.command_move(params)
        elif action in ("command_attack", "attack"):
            return self.command_attack(params)
        elif action in ("command_fire", "fire"):
            return self.command_fire(params)
        elif action in ("command_set_tactic", "set_tactic", "tactic"):
            return self.command_set_tactic(params)
        elif action in ("command_set_guard", "set_guard", "guard"):
            return self.command_set_guard(params)

        # 6. 查询单位完整属性报告与全知情报
        elif action in ("report", "unit_report", "get_status"):
            return self.report(params)
        elif action in ("list_opponents", "opponents", "get_opponents"):
            return self.list_opponents(params)
        elif action in ("list_allies", "allies", "get_allies"):
            return self.list_allies(params)
        elif action in ("find_path", "path"):
            return self.find_path(params)

        # 7. 经济系统、配方转换与资源开采
        elif action in ("list_converter", "list_converters", "list_recipes", "list_converter_id", "list_converter_ids"):
            return self.list_converter(params)
        elif action in ("show_converter", "get_converter", "show_recipe", "get_recipe", "converter_detail"):
            return self.show_converter(params)
        elif action in ("convert", "start_convert"):
            return self.convert(params)
        elif action in ("terminate_convert", "cancel_convert", "clear_convert"):
            return self.terminate_convert(params)
        elif action in ("get_resources", "resources", "list_resources"):
            return self.get_resources(params)
        elif action in ("harvest", "start_harvest", "command_harvest"):
            return self.command_harvest(params)
        elif action in ("stop_harvest", "command_stop_harvest", "cancel_harvest"):
            return self.command_stop_harvest(params)
        elif action in ("list_resource_blocks", "get_resource_blocks", "resource_blocks"):
            return self.list_resource_blocks(params)

        # 辅助探针
        elif action in ("ping", "hello"):
            return {"status": "ok", "message": "pong"}
        elif action in ("discovery", "whoami"):
            return {"status": "ok", "message": "我在这里"}

        else:
            return {"status": "error", "error": f"Unknown action: '{action}'"}

    # ================= 1. api.pause() / api.resume() =================

    def pause(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """暂停引擎运行，同时全量冻结所有高级 AI 战术脚本线程"""
        if hasattr(self.game_context, "pause"):
            self.game_context.pause()
        elif hasattr(self.game_context, "is_paused"):
            self.game_context.is_paused = True

        mgr = getattr(self.game_context, "ai_script_manager", None)
        if mgr and hasattr(mgr, "pause"):
            mgr.pause()

        return {"status": "ok", "paused": True, "message": "Engine and all AI scripts paused"}

    def resume(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """恢复引擎运行，同时全量解冻所有高级 AI 战术脚本线程，并立刻执行暂停期间暂存的动作"""
        if hasattr(self.game_context, "resume"):
            self.game_context.resume()
        elif hasattr(self.game_context, "is_paused"):
            self.game_context.is_paused = False

        mgr = getattr(self.game_context, "ai_script_manager", None)
        if mgr and hasattr(mgr, "resume"):
            mgr.resume()

        # 立刻执行暂停期间积累的动作（如 command_fire 等）
        self.flush_pending_actions()

        return {"status": "ok", "paused": False, "message": "Engine and all AI scripts resumed"}

    def flush_pending_actions(self) -> None:
        """执行暂停期间积累的动作（开火等）"""
        if not self.pending_actions:
            return
        actions = list(self.pending_actions)
        self.pending_actions.clear()
        for act in actions:
            try:
                act()
            except Exception as e:
                logger.exception("Error executing pending action: %s", e)

    def is_paused(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """查询引擎当前是否处于暂停状态"""
        is_p = bool(getattr(self.game_context, "is_paused", False))
        return {"status": "ok", "paused": is_p}

    # ================= 2. api.is_success() =================

    def is_success(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """判断是否达成获胜条件并返回"""
        condition_ctx = getattr(self.game_context, "condition_ctx", None)
        victory_cond = getattr(self.game_context, "victory_condition", None)
        defeat_cond = getattr(self.game_context, "defeat_condition", None)

        is_succ = False
        if victory_cond and condition_ctx:
            is_succ = victory_cond.evaluate(condition_ctx)

        game_over = getattr(self.game_context, "game_over", False)
        game_victory = getattr(self.game_context, "game_victory", False) or is_succ

        return {
            "status": "ok",
            "is_success": game_victory,
            "game_over": game_over,
            "victory_desc": victory_cond.get_description() if victory_cond else "全歼敌军",
            "defeat_desc": defeat_cond.get_description() if defeat_cond else "我方部队覆灭"
        }

    # ================= 3. api.terminate() =================

    def terminate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """终结所有的引擎和后台"""
        if self.termination_handler:
            self.termination_handler()
        elif hasattr(self.game_context, "stop"):
            self.game_context.stop()

        return {"status": "ok", "message": "Terminating all engines and background services..."}

    def restart(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """重置战局并重新启动游戏引擎"""
        self.pending_actions.clear()
        if hasattr(self.game_context, "restart"):
            self.game_context.restart()
            return {"status": "ok", "message": "Game restarted successfully"}
        return {"status": "error", "error": "Game context does not support restart"}

    # ================= 4. api.list_current_unit_id / api.list_enemy_curr =================

    def list_current_unit_id(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        返回当前还存活的所有己方单位 ID，以逗号隔开。
        包含可操控与不可操控的所有己方单位（不能被操控的我方单位始终必然被列出，其余单位受 visibility 影响）。
        """
        physics = getattr(self.game_context, "physics_engine", None)
        if not physics:
            return {"status": "error", "error": "Physics engine not available"}

        god_mode = bool(params.get("god_mode", False) or params.get("all", False))
        visible_ids = []
        for tank in physics.player_tanks:
            if tank.alive:
                vis = getattr(tank, "visibility", 1.0)
                is_uncontrollable = not getattr(tank, "controllable", True)
                # 辨识度判定：不能被操控的我方单位始终必然被列出；其他单位在 god_mode、vis>=1.0 或按概率列出
                if is_uncontrollable or god_mode or vis >= 1.0 or random.random() < vis:
                    visible_ids.append(tank.id)

        unit_ids_str = ",".join(visible_ids)
        return {
            "status": "ok",
            "unit_ids": unit_ids_str,
            "count": len(visible_ids)
        }

    def list_enemy_curr(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        列出当前存活敌军单位 ID（以逗号隔开）：
        - 上帝视角模式 (god_mode=True 或 mode='god'):
          无视战争迷雾与视野限制，直接列出全部存活敌军 ID。
        - 我方视野汇总模式 (god_mode=False，默认模式):
          汇总当前所有存活我方单位的视线范围 (正方形视界)；
          若敌军处于任一我方单位视线范围内，再根据敌军的 visibility (辨识度) 概率决定是否添加进 list。
        """
        physics = getattr(self.game_context, "physics_engine", None)
        if not physics:
            return {"status": "error", "error": "Physics engine not available"}

        # 检查是否开启上帝视角模式
        mode_param = str(params.get("mode", "")).lower().strip()
        god_mode = bool(
            params.get("god_mode", False) or
            params.get("all", False) or
            mode_param in ("god", "all", "cheat")
        )

        alive_enemies = [e for e in physics.enemy_tanks if e.alive]

        # 1. 上帝视角：直接列出全部存活敌军
        if god_mode:
            enemy_ids = [e.id for e in alive_enemies]
            return {
                "status": "ok",
                "unit_ids": ",".join(enemy_ids),
                "count": len(enemy_ids),
                "mode": "god",
                "total_enemies": len(alive_enemies)
            }

        # 2. 视野与迷雾探测模式
        has_full_vision = any(t.vision_size < 0 for t in physics.player_tanks if t.alive)
        fog_enabled = getattr(physics, "fog_of_war_enabled", True)
        sight_rects = physics.get_player_sight_rects() if (fog_enabled and not has_full_vision) else []

        spotted_enemy_ids = []
        for enemy in alive_enemies:
            # 判定是否在任一存活我方单位视线内
            if not fog_enabled or has_full_vision:
                in_sight = True
            else:
                in_sight = any(enemy.rect.collides_with(sr) for sr in sight_rects)

            if in_sight:
                vis = getattr(enemy, "visibility", 1.0)
                # 按照视野中敌方单位的可见度随机判定是否添加进 list
                if vis >= 1.0 or random.random() < vis:
                    spotted_enemy_ids.append(enemy.id)

        return {
            "status": "ok",
            "unit_ids": ",".join(spotted_enemy_ids),
            "count": len(spotted_enemy_ids),
            "mode": "vision",
            "total_enemies": len(alive_enemies)
        }

    # ================= api.list_enemy_mem / api.report_enemy =================

    def list_enemy_mem(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        只访问当前全局记忆列出记忆中的敌方单位 ID (以逗号隔开)。
        包括当前追踪中 (tracked) 与跟丢了的 (lost) 记忆项目。
        """
        physics = getattr(self.game_context, "physics_engine", None)
        if not physics:
            return {"status": "error", "error": "Physics engine not available"}

        memory = getattr(physics, "enemy_memory", {})
        mem_ids = list(memory.keys())
        tracked = [mid for mid, entry in memory.items() if entry.is_tracking]
        lost = [mid for mid, entry in memory.items() if not entry.is_tracking]

        return {
            "status": "ok",
            "unit_ids": ",".join(mem_ids),
            "count": len(mem_ids),
            "tracked": tracked,
            "lost": lost
        }

    def report_enemy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据提供的 ID 查找敌军记忆体。
        严格限制安全边界：敌方单位的 HP、速度、弹药等属性永远不可见，
        只能报告其最后一次更新的坐标和单位类型。
        """
        physics = getattr(self.game_context, "physics_engine", None)
        if not physics:
            return {"status": "error", "error": "Physics engine not available"}

        unit_id = str(params.get("unit_id") or params.get("id") or "").strip()
        if not unit_id:
            return {"status": "error", "error": "Missing 'unit_id' parameter"}

        memory = getattr(physics, "enemy_memory", {})
        if unit_id not in memory:
            return {"status": "error", "error": f"Enemy unit '{unit_id}' not found in memory"}

        entry = memory[unit_id]
        return {
            "status": "ok",
            "report": {
                "id": entry.enemy_id,
                "unit_type": entry.unit_type,
                "last_x": round(entry.x, 2),
                "last_y": round(entry.y, 2),
                "is_tracking": entry.is_tracking,
                "last_seen_time": round(entry.last_seen_time, 2)
            }
        }

    # ================= 5. api.command_* 批量指令 =================

    def _get_target_tanks(self, unit_ids_param: Any) -> List[Any]:
        physics = getattr(self.game_context, "physics_engine", None)
        if not physics:
            return []

        all_player_tanks = [t for t in physics.player_tanks if t.alive]
        all_enemy_tanks = [t for t in physics.enemy_tanks if t.alive]
        all_tanks = all_player_tanks + all_enemy_tanks

        if not unit_ids_param:
            return all_player_tanks

        if isinstance(unit_ids_param, str):
            ids = [i.strip() for i in unit_ids_param.split(",") if i.strip()]
        elif isinstance(unit_ids_param, (list, tuple)):
            ids = [str(i).strip() for i in unit_ids_param if str(i).strip()]
        else:
            ids = [str(unit_ids_param).strip()]

        if "*" in ids or "all" in ids:
            return all_player_tanks

        target_set = set(ids)
        matched = [t for t in all_tanks if t.id in target_set]

        # 若调度器中未注册该坦克，自动注册
        dispatcher = getattr(self.game_context, "command_dispatcher", None)
        if dispatcher:
            for t in matched:
                if t.id not in dispatcher.tank_commands:
                    dispatcher.register_tank(t)

        return matched

    # 保持向后兼容
    _get_target_player_tanks = _get_target_tanks

    def _can_execute_command(self, tank: Any, params: Dict[str, Any]) -> bool:
        """
        判断指定坦克是否允许执行该控制指令：
        - 若单位为可操控单位 (controllable=True)，始终允许执行外部与内部指令；
        - 若单位为不可操控单位 (controllable=False)：
          仅当该指令是由该单位自身的战术脚本 (TankScriptAPI) 内部发起时才允许执行；
          外部指令（如玩家/网络 API/测试下发的指令）被安全静默忽略（不报错，亦不覆盖其预定脚本的自主决策）。
        """
        if getattr(tank, "controllable", True):
            return True

        caller_id = params.get("_caller_unit_id") or params.get("caller") or params.get("sender")
        if caller_id and str(caller_id).strip() == str(tank.id).strip():
            return True

        return False

    def command_move(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """按照 ID 批量移动单位到 (x, y)"""
        dispatcher = getattr(self.game_context, "command_dispatcher", None)
        if not dispatcher:
            return {"status": "error", "error": "Command dispatcher not available"}

        tanks = self._get_target_tanks(params.get("unit_ids"))
        if not tanks:
            return {"status": "error", "error": "No matching alive units found"}

        try:
            x = float(params.get("x", 0.0))
            y = float(params.get("y", 0.0))
        except (ValueError, TypeError):
            return {"status": "error", "error": "Invalid x, y coordinates"}

        executable_tanks = [t for t in tanks if self._can_execute_command(t, params)]
        if executable_tanks:
            dispatcher.issue_move(executable_tanks, x, y)

        is_p = bool(getattr(self.game_context, "is_paused", False))
        res = {
            "status": "ok",
            "command": "command_move",
            "destination": {"x": x, "y": y},
            "affected_units": [t.id for t in executable_tanks],
            "count": len(executable_tanks)
        }
        if is_p and executable_tanks:
            res["queued"] = True
            res["message"] = "Move command issued while paused, will execute immediately upon resume"
        return res

    def command_attack(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """按照 ID 批量攻击指定目标"""
        dispatcher = getattr(self.game_context, "command_dispatcher", None)
        physics = getattr(self.game_context, "physics_engine", None)
        if not dispatcher or not physics:
            return {"status": "error", "error": "Engine or dispatcher not available"}

        tanks = self._get_target_tanks(params.get("unit_ids"))
        if not tanks:
            return {"status": "error", "error": "No matching alive units found"}

        target_id = params.get("target_id")
        target_tank = None
        all_active = physics.player_tanks + physics.enemy_tanks
        if target_id:
            for t in all_active:
                if t.id == target_id and t.alive:
                    target_tank = t
                    break

        if not target_tank:
            # 若提供了坐标 (x, y)，寻找该坐标附近的单位
            if "x" in params and "y" in params:
                tx = float(params["x"])
                ty = float(params["y"])
                for t in all_active:
                    if t.alive and abs(t.x - tx) < 40 and abs(t.y - ty) < 40:
                        target_tank = t
                        break

        if not target_tank:
            return {"status": "error", "error": f"Target unit '{target_id}' not found or destroyed"}

        executable_tanks = [t for t in tanks if self._can_execute_command(t, params)]
        if executable_tanks:
            god_mode = bool(params.get("god_mode", False) or params.get("ignore_vision", False))
            dispatcher.issue_attack_target(executable_tanks, target_tank, physics, ignore_vision=god_mode)

        is_p = bool(getattr(self.game_context, "is_paused", False))
        res = {
            "status": "ok",
            "command": "command_attack",
            "target_id": target_tank.id,
            "affected_units": [t.id for t in executable_tanks],
            "count": len(executable_tanks)
        }
        if is_p and executable_tanks:
            res["queued"] = True
            res["message"] = "Attack command issued while paused, will execute immediately upon resume"
        return res

    def command_fire(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """按照 ID 批量让坦克向指定或当前朝向开火"""
        physics = getattr(self.game_context, "physics_engine", None)
        if not physics:
            return {"status": "error", "error": "Physics engine not available"}

        from physics.entities import Direction, Camp
        tanks = self._get_target_tanks(params.get("unit_ids"))
        if not tanks:
            return {"status": "error", "error": "No matching alive units found"}

        executable_tanks = [t for t in tanks if self._can_execute_command(t, params)]
        if not executable_tanks:
            return {
                "status": "ok",
                "command": "command_fire",
                "fired_units": [],
                "count": 0
            }

        dir_str = params.get("direction")
        angle_param = params.get("angle")
        unit_ids = [t.id for t in executable_tanks]

        # 若处于暂停状态，不立刻开火，暂存到 pending_actions，解除暂停后立刻执行
        if getattr(self.game_context, "is_paused", False):
            if angle_param is not None:
                for tank in executable_tanks:
                    tank.angle = float(angle_param)
            elif dir_str:
                d_name = str(dir_str).upper()
                if hasattr(Direction, d_name):
                    for tank in executable_tanks:
                        tank.direction = getattr(Direction, d_name)

            def execute_fire():
                curr_tanks = self._get_target_tanks(unit_ids)
                curr_executable = [t for t in curr_tanks if self._can_execute_command(t, params)]
                for tank in curr_executable:
                    if not tank.alive:
                        continue
                    if angle_param is not None:
                        tank.angle = float(angle_param)
                    elif dir_str:
                        d_name = str(dir_str).upper()
                        if hasattr(Direction, d_name):
                            tank.direction = getattr(Direction, d_name)
                    if tank.can_fire(physics.limited_ammo_enabled):
                        cfg = getattr(tank, "_config", None)
                        b_speed = cfg.bullet_speed if cfg else 6.0
                        b_size = cfg.bullet_size if cfg else 12
                        b_color = cfg.bullet_color if cfg else ("#E69C24" if tank.camp == Camp.PLAYER else "#E63946")
                        physics.spawn_bullet(tank, b_speed, b_size, b_color)

            self.pending_actions.append(execute_fire)
            return {
                "status": "ok",
                "command": "command_fire",
                "fired_units": unit_ids,
                "count": len(unit_ids),
                "queued": True,
                "message": "Fire command queued while paused, will execute immediately upon resume"
            }

        fired_units = []
        for tank in executable_tanks:
            if not tank.alive:
                continue
            if angle_param is not None:
                tank.angle = float(angle_param)
            elif dir_str:
                d_name = str(dir_str).upper()
                if hasattr(Direction, d_name):
                    tank.direction = getattr(Direction, d_name)

            if tank.can_fire(physics.limited_ammo_enabled):
                cfg = getattr(tank, "_config", None)
                b_speed = cfg.bullet_speed if cfg else 6.0
                b_size = cfg.bullet_size if cfg else 12
                b_color = cfg.bullet_color if cfg else ("#E69C24" if tank.camp == Camp.PLAYER else "#E63946")
                physics.spawn_bullet(tank, b_speed, b_size, b_color)
                fired_units.append(tank.id)

        return {
            "status": "ok",
            "command": "command_fire",
            "fired_units": fired_units,
            "count": len(fired_units)
        }

    def command_set_tactic(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """按照 ID 批量设置单位的战术姿态"""
        dispatcher = getattr(self.game_context, "command_dispatcher", None)
        physics = getattr(self.game_context, "physics_engine", None)
        if not dispatcher or not physics:
            return {"status": "error", "error": "Engine or dispatcher not available"}

        tanks = self._get_target_tanks(params.get("unit_ids"))
        if not tanks:
            return {"status": "error", "error": "No matching alive units found"}

        tactic_str = str(params.get("tactic", "aggressive")).lower().strip()
        guard_target = None
        all_active = physics.player_tanks + physics.enemy_tanks

        if tactic_str in ("aggressive", "attack", "1"):
            tactic_mode = TacticMode.AGGRESSIVE
        elif tactic_str in ("defensive", "defense", "2"):
            tactic_mode = TacticMode.DEFENSIVE
        elif tactic_str in ("guard", "guard_unit", "3"):
            tactic_mode = TacticMode.GUARD_UNIT
            gt_id = params.get("guard_target_id")
            if gt_id:
                for ally in all_active:
                    if ally.id == gt_id and ally.alive:
                        guard_target = ally
                        break
        elif tactic_str in ("stop", "idle", "manual"):
            tactic_mode = TacticMode.MANUAL_OR_IDLE
        else:
            return {"status": "error", "error": f"Unknown tactic '{tactic_str}'"}

        executable_tanks = [t for t in tanks if self._can_execute_command(t, params)]
        if executable_tanks:
            dispatcher.issue_tactic(executable_tanks, tactic_mode, guard_target=guard_target)
        return {
            "status": "ok",
            "command": "command_set_tactic",
            "tactic": tactic_mode.value,
            "guard_target": guard_target.id if guard_target else None,
            "affected_units": [t.id for t in executable_tanks],
            "count": len(executable_tanks)
        }

    def command_set_guard(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """按照 ID 批量让单位去跟踪并保卫特定单位"""
        dispatcher = getattr(self.game_context, "command_dispatcher", None)
        physics = getattr(self.game_context, "physics_engine", None)
        if not dispatcher or not physics:
            return {"status": "error", "error": "Engine or dispatcher not available"}

        tanks = self._get_target_tanks(params.get("unit_ids"))
        if not tanks:
            return {"status": "error", "error": "No matching alive units found"}

        all_active = physics.player_tanks + physics.enemy_tanks
        target_id = params.get("target_id") or params.get("guard_target_id")
        guard_target = None
        if target_id:
            for ally in all_active:
                if ally.id == target_id and ally.alive:
                    guard_target = ally
                    break

        if not guard_target:
            # 默认寻找核心补给要塞
            for ally in physics.player_tanks:
                if ally.alive and ally.is_tower and ally.tower_type == "supply":
                    guard_target = ally
                    break

        if not guard_target:
            return {"status": "error", "error": f"Guard target '{target_id}' not found"}

        executable_tanks = [t for t in tanks if self._can_execute_command(t, params)]
        if executable_tanks:
            dispatcher.issue_guard_unit(executable_tanks, guard_target)
        return {
            "status": "ok",
            "command": "command_set_guard",
            "guard_target": guard_target.id,
            "affected_units": [t.id for t in executable_tanks],
            "count": len(executable_tanks)
        }

    # ================= 6. api.report / 全知情报 =================

    def report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """报告特定 ID 单位的详细属性（战术、弹药、速度、HP、位置等）"""
        physics = getattr(self.game_context, "physics_engine", None)
        dispatcher = getattr(self.game_context, "command_dispatcher", None)
        if not physics:
            return {"status": "error", "error": "Physics engine not available"}

        unit_id = str(params.get("unit_id") or params.get("id") or "").strip()
        if not unit_id:
            return {"status": "error", "error": "Missing 'unit_id' parameter"}

        target_tank = None
        for t in physics.player_tanks + physics.enemy_tanks:
            if t.id == unit_id:
                target_tank = t
                break

        if not target_tank:
            return {"status": "error", "error": f"Unit with ID '{unit_id}' not found"}

        tactic = dispatcher.get_tactic(target_tank) if dispatcher else None
        auto_clr = dispatcher.is_auto_clear_path(target_tank) if dispatcher else False

        report_data = {
            "id": target_tank.id,
            "camp": target_tank.camp.value,
            "alive": target_tank.alive,
            "tactic": tactic.value if tactic else "manual",
            "ammo": target_tank.ammo,
            "max_ammo": target_tank.max_ammo,
            "speed": target_tank.speed,
            "hp": target_tank.health,
            "max_hp": target_tank.max_health,
            "x": round(target_tank.x, 2),
            "y": round(target_tank.y, 2),
            "size": target_tank.size,
            "direction": target_tank.direction.name,
            "angle": round(target_tank.angle, 1),
            "visibility": getattr(target_tank, "visibility", 1.0),
            "vision_size": target_tank.vision_size,
            "is_tower": target_tank.is_tower,
            "tower_type": target_tank.tower_type,
            "resupply_radius": target_tank.resupply_radius,
            "can_crush_bricks": getattr(target_tank, "can_crush_bricks", False),
            "auto_clear": auto_clr,
            "controllable": getattr(target_tank, "controllable", True),
            "ai_script": getattr(target_tank, "ai_script", None),
            "converter_table": list(getattr(target_tank, "converter_table", [])),
            "is_converting": getattr(target_tank, "is_converting", False),
            "converter_status": target_tank.converter.get_status_dict() if getattr(target_tank, "converter", None) else None,
            "harvest_speed": dict(getattr(target_tank, "harvest_speed", {})),
            "is_harvesting": getattr(target_tank, "is_harvesting", False),
            "harvest_target": getattr(target_tank, "harvest_target", None),
            "harvest_state": getattr(target_tank, "harvest_state", "idle")
        }

        return {
            "status": "ok",
            "report": report_data
        }

    def list_opponents(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """列出指定单位或阵营的全部敌对存活单位（全知全能上帝视角）"""
        physics = getattr(self.game_context, "physics_engine", None)
        if not physics:
            return {"status": "error", "error": "Physics engine not available"}

        from physics.entities import Camp
        unit_id = str(params.get("unit_id") or "").strip()
        camp = None
        if unit_id:
            for t in physics.player_tanks + physics.enemy_tanks:
                if t.id == unit_id:
                    camp = t.camp
                    break
        if not camp:
            camp_str = str(params.get("camp", "enemy")).lower()
            camp = Camp.ENEMY if "enemy" in camp_str else Camp.PLAYER

        opp_tanks = physics.player_tanks if camp == Camp.ENEMY else physics.enemy_tanks
        units = []
        for t in opp_tanks:
            if t.alive:
                units.append({
                    "id": t.id,
                    "camp": t.camp.value,
                    "x": round(t.x, 2),
                    "y": round(t.y, 2),
                    "hp": t.health,
                    "max_hp": t.max_health,
                    "unit_type": getattr(t, "unit_type", "tank"),
                    "is_tower": getattr(t, "is_tower", False),
                    "tower_type": getattr(t, "tower_type", "general"),
                    "speed": t.speed
                })

        return {
            "status": "ok",
            "units": units,
            "unit_ids": ",".join([u["id"] for u in units]),
            "count": len(units)
        }

    def list_allies(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """列出指定单位或阵营的全部友方存活单位"""
        physics = getattr(self.game_context, "physics_engine", None)
        if not physics:
            return {"status": "error", "error": "Physics engine not available"}

        from physics.entities import Camp
        unit_id = str(params.get("unit_id") or "").strip()
        camp = None
        if unit_id:
            for t in physics.player_tanks + physics.enemy_tanks:
                if t.id == unit_id:
                    camp = t.camp
                    break
        if not camp:
            camp_str = str(params.get("camp", "player")).lower()
            camp = Camp.ENEMY if "enemy" in camp_str else Camp.PLAYER

        ally_tanks = physics.enemy_tanks if camp == Camp.ENEMY else physics.player_tanks
        units = []
        for t in ally_tanks:
            if t.alive and t.id != unit_id:
                units.append({
                    "id": t.id,
                    "camp": t.camp.value,
                    "x": round(t.x, 2),
                    "y": round(t.y, 2),
                    "hp": t.health,
                    "max_hp": t.max_health,
                    "unit_type": getattr(t, "unit_type", "tank"),
                    "is_tower": getattr(t, "is_tower", False),
                    "tower_type": getattr(t, "tower_type", "general"),
                    "speed": t.speed
                })

        return {
            "status": "ok",
            "units": units,
            "unit_ids": ",".join([u["id"] for u in units]),
            "count": len(units)
        }

    def find_path(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """计算单位到目标点的最优路径及最省弹药破障数"""
        physics = getattr(self.game_context, "physics_engine", None)
        game_map = getattr(self.game_context, "game_map", None)
        if not physics or not game_map:
            return {"status": "error", "error": "Game engine or map not available"}

        unit_id = params.get("unit_id")
        tanks = self._get_target_tanks(unit_id)
        tank = tanks[0] if tanks else None

        from command.pathfinder import GridPathfinder
        pf = GridPathfinder(game_map)
        start_x = tank.x if tank else float(params.get("start_x", 0.0))
        start_y = tank.y if tank else float(params.get("start_y", 0.0))
        dest_x = float(params.get("x", params.get("dest_x", 0.0)))
        dest_y = float(params.get("y", params.get("dest_y", 0.0)))

        path, ammo_needed = pf.find_path(
            start_x, start_y, dest_x, dest_y,
            tank=tank,
            limited_ammo_enabled=physics.limited_ammo_enabled
        )

        return {
            "status": "ok",
            "waypoints": [{"x": px, "y": py} for px, py in path],
            "ammo_needed": ammo_needed,
            "step_count": len(path)
        }

    # ================= 7. 经济系统与转换器 API =================

    def convert(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        开始或向指定单位追加配方转换任务
        :param unit_id: 单位 ID (必填)
        :param recipe_id: 配方 ID (必填)
        :param count: 转换批次数 (选填，默认 1)
        """
        unit_id = str(params.get("unit_id", "")).strip()
        recipe_id = str(params.get("recipe_id", "")).strip()
        count = int(params.get("count", 1))

        if not unit_id:
            return {"status": "error", "error": "Missing 'unit_id' parameter"}
        if not recipe_id:
            return {"status": "error", "error": "Missing 'recipe_id' parameter"}

        physics = getattr(self.game_context, "physics_engine", None)
        if not physics:
            return {"status": "error", "error": "Physics engine not available"}

        tank = None
        for t in physics.player_tanks + physics.enemy_tanks:
            if t.id == unit_id:
                tank = t
                break

        if tank is None or not tank.alive:
            return {"status": "error", "error": f"Unit '{unit_id}' not found or is dead"}

        if not getattr(tank, "converter", None):
            return {"status": "error", "error": f"Unit '{unit_id}' has no converter equipped"}

        from converter.loader import RecipeRegistry
        recipe = RecipeRegistry.get(recipe_id)
        if recipe is None:
            return {"status": "error", "error": f"Recipe '{recipe_id}' does not exist"}

        if not tank.converter.supports_recipe(recipe_id):
            return {"status": "error", "error": f"Unit '{unit_id}' does not support recipe '{recipe_id}'"}

        res_mgr = getattr(self.game_context, "resource_manager", None)
        if not res_mgr:
            return {"status": "error", "error": "No resource manager available"}

        camp_str = tank.camp.value if hasattr(tank.camp, "value") else str(tank.camp)
        ok, reason = tank.converter.enqueue(recipe, count, res_mgr, camp=camp_str)
        if not ok:
            return {"status": "error", "error": f"Failed to enqueue conversion: {reason}"}

        return {
            "status": "ok",
            "unit_id": unit_id,
            "recipe_id": recipe_id,
            "count": count,
            "result": reason,
            "is_converting": tank.is_converting
        }

    def terminate_convert(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        终止并清空转换队列
        :param unit_id: 可选。指定单位 ID 则仅终止该单位；缺省则清空全员所有转换队列
        """
        physics = getattr(self.game_context, "physics_engine", None)
        if not physics:
            return {"status": "error", "error": "Physics engine not available"}

        unit_id = params.get("unit_id")
        if unit_id:
            unit_id = str(unit_id).strip()
            found = False
            for t in physics.player_tanks + physics.enemy_tanks:
                if t.id == unit_id:
                    if t.converter:
                        t.converter.terminate()
                    found = True
                    break
            if not found:
                return {"status": "error", "error": f"Unit '{unit_id}' not found"}
            return {"status": "ok", "message": f"Conversion terminated for unit '{unit_id}'"}
        else:
            for t in physics.player_tanks + physics.enemy_tanks:
                if t.converter:
                    t.converter.terminate()
            return {"status": "ok", "message": "All conversion queues terminated"}

    def list_converter(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        展示全局所有已注册的转换器配方 ID 及概要信息
        """
        from converter.loader import RecipeRegistry
        recipes = RecipeRegistry.get_all()
        if not recipes:
            base_dir = getattr(self.game_context, "base_dir", None)
            if base_dir:
                recipes = RecipeRegistry.load_recipes(Path(base_dir) / "converter")
            else:
                recipes = RecipeRegistry.load_recipes()

        converter_ids = list(recipes.keys())
        items = []
        for r in recipes.values():
            items.append({
                "id": r.id,
                "name": r.name,
                "output_type": r.output_type,
                "duration": r.duration
            })

        return {
            "status": "ok",
            "converter_ids": converter_ids,
            "count": len(converter_ids),
            "converters": items
        }

    def show_converter(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        读取特定 ID 的转换器配方详细配置
        :param converter_id / recipe_id / id: 配方唯一 ID (必填)
        """
        converter_id = str(params.get("converter_id") or params.get("recipe_id") or params.get("id") or "").strip()
        if not converter_id:
            return {"status": "error", "error": "Missing 'converter_id' or 'recipe_id' parameter"}

        from converter.loader import RecipeRegistry
        recipe = RecipeRegistry.get(converter_id)
        if not recipe:
            base_dir = getattr(self.game_context, "base_dir", None)
            if base_dir:
                recipes = RecipeRegistry.load_recipes(Path(base_dir) / "converter")
            else:
                recipes = RecipeRegistry.load_recipes()
            recipe = recipes.get(converter_id)

        if not recipe:
            return {"status": "error", "error": f"Converter recipe '{converter_id}' not found"}

        converter_info = {
            "id": recipe.id,
            "name": recipe.name,
            "inputs": dict(recipe.inputs) if isinstance(recipe.inputs, dict) else {},
            "outputs": dict(recipe.outputs) if isinstance(recipe.outputs, dict) else recipe.outputs,
            "duration": float(recipe.duration),
            "output_type": str(recipe.output_type),
            "tank_config": recipe.tank_config,
            "visibility": float(recipe.visibility),
            "vision_size": float(recipe.vision_size),
            "ammo": int(recipe.ammo)
        }

        return {
            "status": "ok",
            "converter_id": recipe.id,
            "converter": converter_info,
            "recipe": converter_info
        }

    def get_resources(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """查询当前拥有的所有各类资源储备及每秒产出速率（支持按阵营查询）"""
        res_mgr = getattr(self.game_context, "resource_manager", None)
        if not res_mgr:
            return {"status": "ok", "resources": {}, "rates": {}, "all_camps": {}}

        camp = params.get("camp", "player")
        caller_id = params.get("_caller_unit_id")
        if caller_id and "camp" not in params:
            physics = getattr(self.game_context, "physics_engine", None)
            if physics:
                for t in physics.player_tanks + physics.enemy_tanks:
                    if t.id == caller_id:
                        camp = t.camp.value if hasattr(t.camp, "value") else str(t.camp)
                        break

        return {
            "status": "ok",
            "camp": str(camp),
            "resources": res_mgr.get_all_resources(camp=camp),
            "rates": res_mgr.get_rates(),
            "all_camps": res_mgr.get_both_stockpiles()
        }

    def command_harvest(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        命令指定单位开始开采地图上的资源块
        :param unit_id: 单位 ID (若缺省则使用调用方 _caller_unit_id)
        :param col: 资源块列号 (或由 x 像素自动换算)
        :param row: 资源块行号 (或由 y 像素自动换算)
        """
        physics = getattr(self.game_context, "physics_engine", None)
        if not physics:
            return {"status": "error", "error": "Physics engine not available"}

        unit_id = params.get("unit_id") or params.get("_caller_unit_id")
        if not unit_id:
            unit_ids = params.get("unit_ids", [])
            unit_id = unit_ids[0] if unit_ids else None

        if not unit_id:
            return {"status": "error", "error": "Missing 'unit_id' parameter"}

        target_tank = None
        for t in physics.player_tanks + physics.enemy_tanks:
            if t.id == unit_id:
                target_tank = t
                break

        if not target_tank or not target_tank.alive:
            return {"status": "error", "error": f"Unit '{unit_id}' not found or is dead"}

        game_map = getattr(self.game_context, "game_map", None)
        tile_size = game_map.tile_size if game_map else 32

        if "col" in params and "row" in params:
            col = int(params["col"])
            row = int(params["row"])
        elif "x" in params and "y" in params:
            px, py = float(params["x"]), float(params["y"])
            col = int(px // tile_size)
            row = int(py // tile_size)
        else:
            return {"status": "error", "error": "Missing 'col'/'row' or 'x'/'y' parameters for target resource block"}

        res_mgr = getattr(self.game_context, "resource_manager", None)
        block = res_mgr.get_block_at(col, row) if res_mgr else None
        if not block:
            return {"status": "error", "error": f"No resource block found at ({col}, {row})"}

        all_tanks = physics.player_tanks + physics.enemy_tanks
        in_range = block.is_in_harvest_range(target_tank, tile_size)
        is_excl = block.is_exclusive(target_tank.camp, all_tanks, tile_size)

        target_tank.start_harvest(col, row)

        return {
            "status": "ok",
            "unit_id": unit_id,
            "harvest_target": [col, row],
            "resource_type": block.resource_type,
            "in_range": in_range,
            "is_exclusive": is_excl
        }

    def command_stop_harvest(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """停止单位的资源开采动作"""
        physics = getattr(self.game_context, "physics_engine", None)
        if not physics:
            return {"status": "error", "error": "Physics engine not available"}

        unit_id = params.get("unit_id") or params.get("_caller_unit_id")
        if unit_id:
            for t in physics.player_tanks + physics.enemy_tanks:
                if t.id == unit_id:
                    t.stop_harvest()
                    return {"status": "ok", "message": f"Harvest stopped for unit '{unit_id}'"}
            return {"status": "error", "error": f"Unit '{unit_id}' not found"}
        else:
            for t in physics.player_tanks + physics.enemy_tanks:
                t.stop_harvest()
            return {"status": "ok", "message": "Harvest stopped for all units"}

    def list_resource_blocks(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """列出地图上所有活跃资源块信息、储量与排他检测"""
        res_mgr = getattr(self.game_context, "resource_manager", None)
        if not res_mgr:
            return {"status": "ok", "blocks": []}

        physics = getattr(self.game_context, "physics_engine", None)
        game_map = getattr(self.game_context, "game_map", None)
        tile_size = game_map.tile_size if game_map else 32
        all_tanks = (physics.player_tanks + physics.enemy_tanks) if physics else []

        caller_id = params.get("unit_id") or params.get("_caller_unit_id")
        caller_tank = None
        if caller_id and physics:
            for t in all_tanks:
                if t.id == caller_id:
                    caller_tank = t
                    break

        blocks_data = []
        for b in res_mgr.blocks:
            item = {
                "col": b.col,
                "row": b.row,
                "x": round((b.col + 0.5) * tile_size, 1),
                "y": round((b.row + 0.5) * tile_size, 1),
                "resource_type": b.resource_type,
                "current_amount": round(b.current_amount, 2),
                "initial_amount": b.initial_amount,
                "max_amount": b.max_amount,
                "regen_rate": b.regen_rate,
                "harvest_radius": b.harvest_radius,
                "exclusive_radius": b.exclusive_radius
            }
            if caller_tank:
                item["in_range"] = b.is_in_harvest_range(caller_tank, tile_size)
                item["is_exclusive"] = b.is_exclusive(caller_tank.camp, all_tanks, tile_size)
            blocks_data.append(item)

        return {"status": "ok", "blocks": blocks_data}
