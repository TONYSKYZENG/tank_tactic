import os
import sys
import math
import random
import time
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional
from physics.entities import Tank, Camp
from .bridge import TankScriptAPI

logger = logging.getLogger("AIScriptManager")

class AIScriptManager:
    """
    外挂战术 Python 脚本生命周期管理器：
    - 为每个配置了 ai_script 的敌军或不可控我方单位拉起专属的独立执行线程
    - 管理线程生命周期、优雅退出 (stop_event) 与异常隔离
    - 支持全量暂停 (pause) 与恢复 (resume) 机制，实现高级 AI 单位的彻底冻结
    - 支持热重载与游戏重置时的全量终结
    """

    def __init__(self):
        self._threads: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始状态为运行态 (set=运行，clear=暂停冻结)
        self._paused = False
        self._lock = threading.Lock()

    def is_paused(self) -> bool:
        """检查脚本管理器是否处于暂停冻结状态"""
        return self._paused

    def pause(self) -> None:
        """全量冻结所有正在运行的高级 AI 战术脚本线程"""
        with self._lock:
            self._paused = True
            self._pause_event.clear()
            logger.info("AIScriptManager: Paused and froze all AI script threads")

    def resume(self) -> None:
        """全量恢复解冻所有高级 AI 战术脚本线程"""
        with self._lock:
            self._paused = False
            self._pause_event.set()
            logger.info("AIScriptManager: Resumed all AI script threads")

    def start_scripts(self, tanks: List[Tank], api_controller, base_dir: Optional[Path] = None) -> None:
        """
        扫描坦克列表，对配置了 ai_script 且有资格运行（敌军或不可控友军）的单位启动战术脚本线程
        """
        with self._lock:
            for tank in tanks:
                if not tank.alive or not getattr(tank, "ai_script", None):
                    continue

                # 规则过滤：仅对敌军单位 或 不可由玩家操控的己方单位 启用外挂脚本
                is_eligible = (
                    tank.camp == Camp.ENEMY or
                    (tank.camp == Camp.PLAYER and not getattr(tank, "controllable", True))
                )
                if not is_eligible:
                    continue

                if tank.id in self._threads and self._threads[tank.id].is_alive():
                    continue

                script_rel_path = str(tank.ai_script).strip()
                script_path = None
                candidates = [
                    Path(script_rel_path),
                    (base_dir / script_rel_path) if base_dir else None,
                    Path.cwd() / script_rel_path
                ]
                for p in candidates:
                    if p and p.exists() and p.is_file():
                        script_path = p.resolve()
                        break

                if not script_path:
                    logger.error("AI Script file not found for tank '%s': %s", tank.id, script_rel_path)
                    continue

                stop_event = threading.Event()
                self._stop_events[tank.id] = stop_event

                thread = threading.Thread(
                    target=self._run_script_worker,
                    args=(tank.id, script_path, api_controller, stop_event),
                    daemon=True,
                    name=f"AIScript-{tank.id}"
                )
                self._threads[tank.id] = thread
                thread.start()
                logger.info("Started AI script thread for tank '%s' using '%s'", tank.id, script_path.name)

    def _run_script_worker(self, tank_id: str, script_path: Path, api_controller, stop_event: threading.Event) -> None:
        """独立工作线程：执行外部 Python 战术脚本"""
        api = TankScriptAPI(tank_id, api_controller, stop_event, script_manager=self)

        try:
            with open(script_path, "r", encoding="utf-8") as f:
                code_text = f.read()

            # 构建脚本运行沙箱命名空间
            script_globals = {
                "__name__": "__main__",
                "__file__": str(script_path),
                "api": api,
                "math": math,
                "random": random,
                "time": time,
                "logger": logging.getLogger(f"AI.{tank_id}")
            }

            compiled_code = compile(code_text, str(script_path), "exec")
            exec(compiled_code, script_globals)

            # 兼容支持：若脚本定义了 run(api) 或 main(api) 入口函数，则调用执行
            if "run" in script_globals and callable(script_globals["run"]):
                script_globals["run"](api)
            elif "main" in script_globals and callable(script_globals["main"]):
                script_globals["main"](api)

        except Exception as e:
            if not stop_event.is_set():
                logger.exception("Exception in AI script thread for tank '%s': %s", tank_id, e)
        finally:
            logger.info("AI script thread for tank '%s' terminated", tank_id)

    def stop_all(self) -> None:
        """优雅终结所有正在运行的 AI 战术脚本线程"""
        with self._lock:
            for event in self._stop_events.values():
                event.set()

            for tid, thread in self._threads.items():
                if thread.is_alive():
                    thread.join(timeout=0.25)

            self._threads.clear()
            self._stop_events.clear()
            logger.info("All AI script threads stopped and cleared")

    def clean_dead(self) -> None:
        """清理已自然结束的线程对象"""
        with self._lock:
            dead_ids = [tid for tid, th in self._threads.items() if not th.is_alive()]
            for tid in dead_ids:
                del self._threads[tid]
                if tid in self._stop_events:
                    del self._stop_events[tid]
