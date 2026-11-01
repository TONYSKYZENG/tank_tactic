#!/usr/bin/env python3
"""
Tanks Tactic Game Engine Interactive Console CLI Client
Supports real-time bidirectional TCP/IP JSON command-line communication with the game engine.
"""

import sys
import json
import socket
import argparse
from typing import Optional, List, Tuple, Any

def clean_unit_ids(val: Any) -> str:
    """清理并规整输入的单位 ID 参数（去除首尾成对引号/方括号、统一逗号分割）"""
    if not val:
        return ""
    strip_chars = "[]【】'\"“”‘’ \t\r\n"
    if isinstance(val, (list, tuple)):
        return ",".join(str(v).strip(strip_chars) for v in val if str(v).strip(strip_chars))
    s = str(val).strip(strip_chars)
    parts = [p.strip(strip_chars) for p in s.replace(",", " ").split() if p.strip(strip_chars)]
    return ",".join(parts)


class TanksConsoleClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8091, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None

    @staticmethod
    def parse_command_line(line: str) -> Tuple[str, List[str]]:
        """智能解析命令行，保持方括号内的单位列表 [unit_a, unit_b] 为整体 token"""
        line = line.strip()
        tokens = []
        current = []
        in_bracket = False
        for char in line:
            if char == '[':
                in_bracket = True
                current.append(char)
            elif char == ']':
                in_bracket = False
                current.append(char)
            elif char.isspace() and not in_bracket:
                if current:
                    tokens.append("".join(current))
                    current = []
            else:
                current.append(char)
        if current:
            tokens.append("".join(current))

        if not tokens:
            return "", []
        return tokens[0].lower(), tokens[1:]

    def connect(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.host, self.port))
            return True
        except Exception as e:
            print(f"❌ Failed to connect to {self.host}:{self.port} - {e}")
            self.sock = None
            return False

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send_request(self, payload: dict) -> dict:
        if not self.sock:
            if not self.connect():
                return {"status": "error", "error": "Not connected to game engine"}

        try:
            raw_data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
            self.sock.sendall(raw_data)

            # 接收响应
            response_chunks = []
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                response_chunks.append(chunk)
                if b"\n" in chunk:
                    break

            raw_resp = b"".join(response_chunks).decode("utf-8").strip()
            if not raw_resp:
                return {"status": "error", "error": "Empty response from engine"}
            return json.loads(raw_resp)
        except Exception as e:
            self.close()
            return {"status": "error", "error": f"Communication error: {e}"}

    def print_help(self):
        print("""
================================================================================
🎮 Available Commands:
--------------------------------------------------------------------------------
  pause                          - Pause game physics & AI loop
  resume                         - Resume game physics & AI loop
  restart                        - Reset battle & restart game engine
  status / is_success            - Check victory / defeat condition status
  list / units                   - List currently alive friendly unit IDs
  list_enemy [god] / enemies     - List currently visible enemy IDs (or all if 'god')
  list_enemy_mem / memory        - List enemies recorded in global memory (tracked & lost)
  report <unit_id>               - Report all attributes of a friendly unit
  report_enemy <enemy_id>        - Report last known position & unit type of enemy in memory
  move <ids> <x> <y>             - Move unit(s) to destination (x, y)
  attack <ids> <target_enemy_id> - Focus fire attack on target enemy
  tactic <ids> <mode>            - Set tactic (aggressive | defensive | manual | guard)
  guard <ids> <friendly_target>  - Escort & guard a friendly unit/tower
  fire <ids> [direction]         - Order unit(s) to fire cannon
  path <id> <x> <y>              - Plan optimal A* path & query ammo breach cost
  resources / res                - Query current resource stockpiles & income rates
  harvest <ids> <col> <row>      - Order units to harvest resource block at tile (col, row)
  stop_harvest [ids]             - Stop resource harvesting
  blocks / resource_blocks       - List active resource blocks on map
  list_converter / converters    - List all registered converter recipe IDs
  show_converter <recipe_id>     - Display detailed parameters of a converter recipe
  convert <id> <recipe_id> [cnt] - Enqueue recipe conversion/production task
  terminate_convert [unit_id]    - Terminate active conversion and clear queue
  terminate                      - Terminate all engines and shutdown
  ping                           - Ping server
  raw <json>                     - Send arbitrary raw JSON payload
  help                           - Show this help message
  exit / quit                    - Exit console client
================================================================================
Examples:
  tanks> list
  tanks> report player_alpha
  tanks> resources
  tanks> list_converter
  tanks> show_converter recipe_build_tank
  tanks> convert player_alpha recipe_build_tank 2
  tanks> harvest player_alpha 2 3
  tanks> move player_alpha,player_bravo 200 300
  tanks> tactic player_alpha defensive
  tanks> guard player_alpha core_supply_base
  tanks> attack player_alpha e_hunter_1
================================================================================
""")

    def execute_command_line(self, line: str) -> bool:
        line = line.strip()
        if not line:
            return True

        if line.lower() in ("exit", "quit", "q"):
            print("👋 Bye!")
            return False

        if line.lower() in ("help", "h", "?"):
            self.print_help()
            return True

        # 如果直接输入了 JSON
        if line.startswith("{") and line.endswith("}"):
            try:
                payload = json.loads(line)
            except Exception as e:
                print(f"❌ Invalid JSON: {e}")
                return True
            resp = self.send_request(payload)
            self._print_response(resp)
            return True

        # 如果输入了 func(arg1, arg2, ...) 原始 plain 函数调用格式
        if "(" in line and (line.endswith(")") or line.endswith(");")):
            from api.controller import GameAPIController
            plain_payload = GameAPIController.parse_plain_api_call(line)
            if plain_payload is not None:
                resp = self.send_request(plain_payload)
                self._print_response(resp)
                return True

        cmd, args = self.parse_command_line(line)
        if not cmd:
            return True

        payload = None

        if cmd in ("pause", "api.pause"):
            payload = {"action": "api.pause"}
        elif cmd in ("resume", "api.resume"):
            payload = {"action": "api.resume"}
        elif cmd in ("restart", "reset", "api.restart"):
            payload = {"action": "api.restart"}
        elif cmd in ("status", "is_success", "api.is_success"):
            payload = {"action": "api.is_success"}
        elif cmd in ("time", "game_time", "get_game_time", "api.get_game_time"):
            payload = {"action": "api.get_game_time"}
        elif cmd in ("mission_info", "get_mission_info", "briefing", "api.get_mission_info"):
            payload = {"action": "api.get_mission_info"}
        elif cmd in ("list", "units", "list_current_unit_id", "api.list_current_unit_id"):
            payload = {"action": "api.list_current_unit_id"}
        elif cmd in ("list_enemy", "list_enemies", "enemies", "list_enemy_curr", "api.list_enemy_curr"):
            god_mode = len(args) > 0 and args[0].lower() in ("god", "--god", "-g", "all", "true")
            payload = {"action": "api.list_enemy_curr", "god_mode": god_mode}
        elif cmd in ("list_enemy_mem", "enemy_mem", "memory", "list_memory", "api.list_enemy_mem"):
            payload = {"action": "api.list_enemy_mem"}
        elif cmd in ("report_enemy", "enemy_report", "api.report_enemy"):
            if not args:
                print("❌ Usage: report_enemy <enemy_id>")
                return True
            payload = {"action": "api.report_enemy", "unit_id": clean_unit_ids(args[0])}
        elif cmd in ("terminate", "api.terminate"):
            payload = {"action": "api.terminate"}
        elif cmd in ("ping", "api.ping"):
            payload = {"action": "api.ping"}
        elif cmd == "report":
            if not args:
                print("❌ Usage: report <unit_id>")
                return True
            payload = {"action": "api.report", "unit_id": clean_unit_ids(args[0])}
        elif cmd == "move":
            if len(args) < 3:
                print("❌ Usage: move <unit_ids> <x> <y>")
                return True
            try:
                x = float(args[1])
                y = float(args[2])
            except ValueError:
                print("❌ x and y must be numbers")
                return True
            payload = {"action": "api.command_move", "unit_ids": clean_unit_ids(args[0]), "x": x, "y": y}
        elif cmd == "attack":
            if len(args) < 2:
                print("❌ Usage: attack <unit_ids> <target_enemy_id>")
                return True
            payload = {"action": "api.command_attack", "unit_ids": clean_unit_ids(args[0]), "target_id": clean_unit_ids(args[1])}
        elif cmd in ("tactic", "set_tactic"):
            if len(args) < 2:
                print("❌ Usage: tactic <unit_ids> <aggressive|defensive|manual|guard>")
                return True
            payload = {"action": "api.command_set_tactic", "unit_ids": clean_unit_ids(args[0]), "tactic": args[1]}
        elif cmd in ("guard", "set_guard"):
            if len(args) < 2:
                print("❌ Usage: guard <unit_ids> <target_friendly_id>")
                return True
            payload = {"action": "api.command_set_guard", "unit_ids": clean_unit_ids(args[0]), "target_id": clean_unit_ids(args[1])}
        elif cmd in ("fire", "command_fire"):
            unit_ids = clean_unit_ids(args[0]) if len(args) > 0 else "*"
            direction = args[1] if len(args) > 1 else None
            payload = {"action": "api.command_fire", "unit_ids": unit_ids}
            if direction:
                payload["direction"] = direction
        elif cmd in ("path", "find_path"):
            if len(args) < 3:
                print("❌ Usage: path <unit_id> <x> <y>")
                return True
            payload = {"action": "api.find_path", "unit_id": clean_unit_ids(args[0]), "x": float(args[1]), "y": float(args[2])}
        elif cmd in ("resources", "res", "get_resources", "api.get_resources"):
            camp = args[0] if len(args) > 0 else "player"
            payload = {"action": "api.get_resources", "camp": camp}
        elif cmd in ("blocks", "resource_blocks", "list_resource_blocks", "api.list_resource_blocks"):
            unit_id = clean_unit_ids(args[0]) if len(args) > 0 else None
            payload = {"action": "api.list_resource_blocks"}
            if unit_id:
                payload["unit_id"] = unit_id
        elif cmd in ("harvest", "command_harvest", "api.harvest"):
            if len(args) < 3:
                print("❌ Usage: harvest <unit_ids> <col> <row>")
                return True
            try:
                col = int(args[1])
                row = int(args[2])
            except ValueError:
                print("❌ col and row must be integer tile coordinates")
                return True
            payload = {"action": "api.harvest", "unit_ids": clean_unit_ids(args[0]), "col": col, "row": row}
        elif cmd in ("stop_harvest", "command_stop_harvest", "cancel_harvest", "api.stop_harvest"):
            unit_ids = clean_unit_ids(args[0]) if len(args) > 0 else "*"
            payload = {"action": "api.stop_harvest", "unit_ids": unit_ids}
        elif cmd in ("list_converter", "list_converters", "converters", "recipes", "list_recipes", "api.list_converter"):
            payload = {"action": "api.list_converter"}
        elif cmd in ("show_converter", "show_recipe", "recipe", "converter", "api.show_converter"):
            if not args:
                print("❌ Usage: show_converter <recipe_id>")
                return True
            payload = {"action": "api.show_converter", "converter_id": args[0]}
        elif cmd in ("convert", "start_convert", "api.convert"):
            if len(args) < 2:
                print("❌ Usage: convert <unit_id> <recipe_id> [count]")
                return True
            count = int(args[2]) if len(args) > 2 else 1
            payload = {"action": "api.convert", "unit_id": clean_unit_ids(args[0]), "recipe_id": args[1], "count": count}
        elif cmd in ("terminate_convert", "cancel_convert", "clear_convert", "api.terminate_convert"):
            unit_id = clean_unit_ids(args[0]) if len(args) > 0 else None
            payload = {"action": "api.terminate_convert"}
            if unit_id:
                payload["unit_id"] = unit_id
        elif cmd in ("edit_attr", "modify_attr", "api.edit_attr"):
            if len(args) < 3:
                print("❌ Usage: edit_attr <unit_ids> <attr> <value>")
                return True
            payload = {"action": "api.edit_attr", "unit_ids": clean_unit_ids(args[0]), "attr": args[1], "value": args[2]}
        elif cmd in ("set_resources", "modify_resources", "edit_resources", "api.set_resources"):
            if not args:
                print("❌ Usage: set_resources <camp: player/enemy/both> [dark_matter] [alloy]")
                return True
            camp = args[0]
            payload = {"action": "api.set_resources", "camp": camp}
            if len(args) >= 2:
                try:
                    payload["dark_matter"] = float(args[1])
                except ValueError:
                    pass
            if len(args) >= 3:
                try:
                    payload["alloy"] = float(args[2])
                except ValueError:
                    pass
        elif cmd in ("create_unit", "spawn_unit", "api.create_unit"):
            if len(args) < 3:
                print("❌ Usage: create_unit <camp: player/enemy> <x> <y> [config_file] [unit_id]")
                return True
            camp = args[0]
            x = float(args[1])
            y = float(args[2])
            payload = {"action": "api.create_unit", "camp": camp, "x": x, "y": y}
            if len(args) >= 4:
                payload["config_file"] = args[3]
            if len(args) >= 5:
                payload["unit_id"] = args[4]
        elif cmd == "raw":
            raw_str = " ".join(args)
            try:
                payload = json.loads(raw_str)
            except Exception as e:
                print(f"❌ Invalid JSON format: {e}")
                return True
        else:
            print(f"❌ Unknown command: '{cmd}'. Type 'help' for guidance.")
            return True

        resp = self.send_request(payload)
        self._print_response(resp)
        return True

    def _print_response(self, resp: dict):
        if resp.get("status") == "ok":
            print("✅ Response:")
            print(json.dumps(resp, indent=2, ensure_ascii=False))
        else:
            print(f"⚠️ Error: {resp.get('error', 'Unknown error')}")
            print(json.dumps(resp, indent=2, ensure_ascii=False))

    def run_repl(self):
        print("=" * 64)
        print(f"🎮 Tanks Tactic Game Engine Interactive Console (TCP://{self.host}:{self.port})")
        print("Connecting to game engine...")

        if not self.connect():
            print("⚠️ Could not establish initial connection. You can still type commands to retry.")
        else:
            print("✅ Connected successfully!")

        print("Type 'help' for available commands, or 'exit' to quit.")
        print("=" * 64)

        try:
            while True:
                try:
                    line = input("tanks> ").strip()
                except EOFError:
                    break
                except KeyboardInterrupt:
                    print("\n👋 Exiting...")
                    break

                if not self.execute_command_line(line):
                    break
        finally:
            self.close()

def main():
    parser = argparse.ArgumentParser(description="Tanks Tactic Engine Interactive Console CLI")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Target API host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8091, help="Target Raw TCP API port (default: 8091)")
    parser.add_argument("--cmd", type=str, default=None, help="Execute single command non-interactively")
    args = parser.parse_args()

    client = TanksConsoleClient(host=args.host, port=args.port)

    if args.cmd:
        if not client.connect():
            sys.exit(1)
        client.execute_command_line(args.cmd)
        client.close()
    else:
        client.run_repl()

if __name__ == "__main__":
    main()
