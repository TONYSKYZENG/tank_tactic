import time
import json
import threading
from pathlib import Path
from typing import Callable, Optional, Dict, Any
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

def extract_game_state_snapshot(physics_engine, game_map, command_dispatcher) -> Dict[str, Any]:
    """
    从物理引擎、地图与调度器中抓取【全知上帝视角】的完整遥测快照
    包含处于迷雾内部不可见的敌军坐标与全部属性
    """
    # 1. 地图信息
    map_data = {
        "name": game_map.name,
        "cols": game_map.cols,
        "rows": game_map.rows,
        "tile_size": game_map.tile_size,
        "width": game_map.pixel_width,
        "height": game_map.pixel_height,
        "grid": game_map.grid
    }

    # 2. 我方全部单位
    player_units = []
    for t in physics_engine.player_tanks:
        if t.alive:
            tactic = command_dispatcher.get_tactic(t) if command_dispatcher else None
            auto_clr = command_dispatcher.is_auto_clear_path(t) if command_dispatcher else False
            cmd = command_dispatcher.tank_commands.get(t.id) if command_dispatcher else None

            player_units.append({
                "id": t.id,
                "camp": "player",
                "x": round(t.x, 1),
                "y": round(t.y, 1),
                "size": t.size,
                "direction": t.direction.name,
                "speed": t.speed,
                "health": t.health,
                "max_health": t.max_health,
                "ammo": t.ammo,
                "max_ammo": t.max_ammo,
                "vision_size": t.vision_size,
                "is_tower": t.is_tower,
                "tower_type": t.tower_type,
                "resupply_radius": t.resupply_radius,
                "tactic": tactic.value if tactic else "manual",
                "command": cmd.__class__.__name__ if cmd else "None",
                "auto_clear": auto_clr,
                "color": t.color
            })

    # 3. 敌方全部单位 (上帝全知透视，包含迷雾中隐匿的敌军)
    enemy_units = []
    for e in physics_engine.enemy_tanks:
        if e.alive:
            cfg = getattr(e, "_config", None)
            enemy_units.append({
                "id": e.id,
                "camp": "enemy",
                "name": cfg.name if cfg else "Enemy Tank",
                "x": round(e.x, 1),
                "y": round(e.y, 1),
                "size": e.size,
                "direction": e.direction.name,
                "speed": e.speed,
                "health": e.health,
                "max_health": e.max_health,
                "ammo": e.ammo,
                "max_ammo": e.max_ammo,
                "vision_size": e.vision_size,
                "visibility": round(e.visibility, 2),
                "is_spotted": bool(e.is_spotted),
                "tactic": getattr(e, "tactic_name", "ai"),
                "color": e.color
            })

    # 4. 当前飞行中炮弹
    bullets = []
    for b in physics_engine.bullets:
        if b.alive:
            bullets.append({
                "x": round(b.x, 1),
                "y": round(b.y, 1),
                "direction": b.direction.name,
                "camp": b.camp.value,
                "speed": b.speed
            })

    # 5. 战局胜负
    alive_players = len(player_units)
    alive_enemies = len(enemy_units)
    core_alive = any(u["is_tower"] and u["tower_type"] == "supply" for u in player_units)

    return {
        "timestamp": time.time(),
        "map": map_data,
        "status": {
            "alive_players": alive_players,
            "alive_enemies": alive_enemies,
            "core_alive": core_alive,
            "game_over": (alive_players == 0 or not core_alive),
            "game_victory": (alive_enemies == 0)
        },
        "player_units": player_units,
        "enemy_units": enemy_units,
        "bullets": bullets
    }


class MonitorServer:
    """
    辅助只读上帝观察 WebUI 服务器：
    - 绑定 0.0.0.0 (支持远程局域网/公网读取)
    - 端口可配置 (默认 8088)
    - 永远打开，只读无控制
    - 提供全量全知遥测数据与上帝视角战术小地图
    """

    def __init__(self, state_getter: Callable[[], dict], host: str = "0.0.0.0", port: int = 8088):
        self.state_getter = state_getter
        self.host = host
        self.port = port
        self.static_dir = Path(__file__).resolve().parent / "static"
        self.httpd: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        static_dir = self.static_dir
        state_getter = self.state_getter

        class MonitorHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(static_dir), **kwargs)

            def do_GET(self):
                if self.path == "/api/state":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()

                    try:
                        state_data = state_getter()
                        resp_bytes = json.dumps(state_data, ensure_ascii=False).encode("utf-8")
                    except Exception as e:
                        resp_bytes = json.dumps({"error": str(e)}).encode("utf-8")

                    self.wfile.write(resp_bytes)
                else:
                    super().do_GET()

            def log_message(self, format, *args):
                pass

        try:
            self.httpd = ThreadingHTTPServer((self.host, self.port), MonitorHandler)
            self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.thread.start()
            print("=" * 64)
            print("📊  【全知战术监视器 (只读)】辅助 WebUI 已启动 (永远在线)")
            print(f"🌐  监控地址: http://{self.host}:{self.port} (本地: http://localhost:{self.port})")
            print("👁️  上帝视角实时透视：显示全部敌我单位位置、迷雾内部、属性与弹药")
            print("=" * 64)
        except Exception as e:
            print(f"[Warning] 监视器 WebUI 启动失败 (端口 {self.port}): {e}")

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
