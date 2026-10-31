# 🌐 Tanks Tactic Network API Specification

The Tanks Tactic Game Engine provides an external, programmable remote control and telemetry interface based on a lightweight, plain-text **JSON-RPC** protocol.

It enables external agents, reinforcement learning controllers, automated test harnesses, and third-party dashboards to monitor, pause, resume, dispatch tactical commands, and inspect friendly armor units in real-time.

---

## 📡 Transport Protocols & Port Matrix

By default, the engine starts three network servers simultaneously:

| Protocol | Default Port | Format & Wire Encoding | Description |
| :--- | :--- | :--- | :--- |
| **WebSocket** | `8090` | RFC 6455 Text Frames (JSON) | Bi-directional, event-driven web socket stream. |
| **Raw TCP/IP** | `8091` | Newline-delimited (`\n`) JSON | Raw socket stream for any language or CLI tools (`nc`, `telnet`). |
| **UDP Beacon & RPC** | `8092` | UDP Datagrams (UTF-8 JSON) | Online broadcast discovery ("我在这里") and connectionless RPC. |

*All ports and host bindings can be customized using command-line arguments (e.g. `--api-host`, `--api-ws-port`, `--api-tcp-port`, `--api-udp-port`).*

---

## 📢 UDP Service Discovery Beacon ("我在这里")

Immediately upon launching, the game engine broadcasts a discovery datagram over UDP (to `255.255.255.255` and `127.0.0.1` on port `8092`) indicating that the service is online:

```json
{
  "service": "tanks_tactic_api",
  "status": "online",
  "message": "我在这里",
  "udp_port": 8092,
  "tcp_port": 8091,
  "ws_port": 8090,
  "timestamp": 1730347890.123
}
```

The beacon continues to broadcast every 5 seconds. Clients can also send a datagram `{"action": "discovery"}` or `{"action": "ping"}` to receive an immediate response.

---

## 📐 Wire Protocol & Request Structure

Every request must be a valid JSON object. Both root-level attributes and nested `params` structures are accepted.

### Standard Request Envelope:
```json
{
  "action": "api.report",
  "unit_id": "player_alpha",
  "id": 1001
}
```
*Note: The `"api."` prefix is optional. `"action": "report"` and `"action": "api.report"` are equivalent.*

### Standard Response Envelope:
```json
{
  "status": "ok",
  "report": { ... },
  "id": 1001
}
```

### Error Response Envelope:
```json
{
  "status": "error",
  "error": "Error description details",
  "id": 1001
}
```

---

## 📚 API Reference

### 1. `api.pause()` & `api.resume()`

Freezes or unfreezes the game engine's physical simulation, projectile updates, and enemy/friendly AI routines. Rendering, telemetry, and planning APIs continue to function during pause.
- **Default State on Startup**: The game starts in **PAUSED** mode by default to allow initial tactical planning and reconnaissance. Use `api.resume` or press the **P** key in the GUI/WebUI to start the simulation.
- **Pre-Execution Queuing**: Tactical movement, targeting, and firing APIs (`command_move`, `command_attack`, `command_fire`, etc.) can be called during pause. They will be acknowledged and queued, executing immediately as soon as the engine is resumed.

#### Request (Pause):
```json
{"action": "api.pause"}
```
#### Response:
```json
{
  "status": "ok",
  "paused": true,
  "message": "Engine paused"
}
```

#### Request (Resume):
```json
{"action": "api.resume"}
```
#### Response:
```json
{
  "status": "ok",
  "paused": false,
  "message": "Engine resumed"
}
```

---

### 2. `api.is_success()`

Evaluates whether the victory condition configured in the active mission (`missions/*.json`) has been satisfied.

#### Request:
```json
{"action": "api.is_success"}
```
#### Response:
```json
{
  "status": "ok",
  "is_success": false,
  "game_over": false,
  "victory_desc": "((单位 [core_supply_base] 存活超过 30.0s 且 侦测到指定区域 (0,0,128x128)) 或 (...))",
  "defeat_desc": "(特定单位 [core_supply_base] 被摧毁 或 我方所有装甲部队覆灭)"
}
```

---

### 3. `api.terminate()`

Gracefully shuts down the game engine, closes all network listeners, stops background loops, and exits the application process.

#### Request:
```json
{"action": "api.terminate"}
```
#### Response:
```json
{
  "status": "ok",
  "message": "Terminating all engines and background services..."
}
```

---

### 4. `api.restart()`

Resets the battle, reinitializes entity positions, reloads maps/mission configurations, and restarts the game simulation loop.

#### Request:
```json
{"action": "api.restart"}
```
#### Response:
```json
{
  "status": "ok",
  "message": "Game restarted successfully"
}
```

---

### 5. `api.list_current_unit_id`

Retrieves a **comma-separated string** of IDs for all currently surviving friendly units.

> [!IMPORTANT]
> **Probabilistic Visibility Filter**: Friendly units also participate in the visibility mechanism. If a unit's `visibility` attribute is less than `1.0` (e.g. `0.7`), there is a probabilistic chance (`1 - visibility`) that the unit will not be detected or reported in that query tick. Units with `visibility: 1.0` are guaranteed to be listed as long as they are alive.

#### Request:
```json
{"action": "api.list_current_unit_id"}
```
#### Response:
```json
{
  "status": "ok",
  "unit_ids": "core_supply_base,radar_tower,player_alpha,player_bravo",
  "count": 4
}
```

---

### 6. `api.list_enemy_curr`

Lists currently active enemy tank IDs (comma-separated). Supports two operational modes:

1. **God Mode (`god_mode: true` / `mode: "god"`)**:
   - Omniscient god's-eye perspective. Ignores fog of war and player line-of-sight; directly returns all currently alive enemy IDs across the entire map.
2. **Vision Mode (`god_mode: false`, default)**:
   - Aggregates the field of view (square sight viewports) of all surviving friendly units.
   - For every enemy within line-of-sight, checks the enemy's `visibility` attribute (0.0 ~ 1.0) probabilistically. Only enemies that pass the roll are included in the returned list. Enemies outside friendly vision are never returned.

#### Request (Default Vision Mode):
```json
{
  "action": "api.list_enemy_curr",
  "god_mode": false
}
```
#### Response:
```json
{
  "status": "ok",
  "unit_ids": "e_patrol_1,e_fast_1",
  "count": 2,
  "mode": "vision",
  "total_enemies": 3
}
```

#### Request (God Mode):
```json
{
  "action": "api.list_enemy_curr",
  "god_mode": true
}
```
#### Response:
```json
{
  "status": "ok",
  "unit_ids": "e_patrol_1,e_fast_1,e_hunter_1",
  "count": 3,
  "mode": "god",
  "total_enemies": 3
}
```

---

### 7. `api.list_enemy_mem`

Accesses the **Global Enemy Memory** registry.

> [!NOTE]
> **Enemy Memory Mechanism**:
> - **Spotting & Memory Creation**: Whenever an enemy unit is legitimately detected in real-time by any surviving friendly unit (both line-of-sight and visibility probability check succeeded), a persistent memory record is established.
> - **Continuous Tracking**: While the enemy remains visible in friendly sight, its coordinate is continuously refreshed, and `is_tracking` is set to `true`.
> - **Lost Tracking**: When the enemy slips away into fog-of-war or escapes line-of-sight, `is_tracking` switches to `false`. Its **last known coordinates** remain frozen in memory. In GUI / headless stream, lost enemies are rendered as a **dashed bounding box** marking their last confirmed location.
> - **Witnessed Death Deletion Rule**: An enemy is removed from the memory registry **ONLY IF** friendly units witness its destruction (i.e. it is visible to friendly forces at the exact moment of its elimination). Enemies destroyed unseen in fog remain in memory until scouted.

#### Request:
```json
{"action": "api.list_enemy_mem"}
```

#### Response:
```json
{
  "status": "ok",
  "unit_ids": "e_patrol_1,e_hunter_1",
  "count": 2,
  "tracked": ["e_patrol_1"],
  "lost": ["e_hunter_1"]
}
```

---

### 8. `api.report_enemy`

Retrieves intelligence regarding a specific enemy unit stored in the memory registry.

> [!CAUTION]
> **Strict Operational Security**:
> Enemy internal combat statistics—such as **HP, max HP, movement speed, fire cooldown, and ammunition—are strictly classified and NEVER revealed**. Only the last known coordinates, unit type, and tracking state are reported.

#### Request:
```json
{
  "action": "api.report_enemy",
  "unit_id": "e_hunter_1"
}
```

#### Response:
```json
{
  "status": "ok",
  "report": {
    "id": "e_hunter_1",
    "unit_type": "Enemy Heavy Tank",
    "last_x": 420.5,
    "last_y": 180.0,
    "is_tracking": false,
    "last_seen_time": 1730349120.45
  }
}
```

---

### 9. Tactical Command APIs

Batch operations target units identified by `unit_ids` (either a comma-separated string `"id1,id2"` or a JSON array `["id1", "id2"]`).

#### 9.1 `api.command_move`
Directs targeted units to navigate to destination coordinates `(x, y)` in formation.
```json
{
  "action": "api.command_move",
  "unit_ids": "player_alpha,player_bravo",
  "x": 250.0,
  "y": 380.0
}
```
**Response:**
```json
{
  "status": "ok",
  "command": "command_move",
  "destination": {"x": 250.0, "y": 380.0},
  "affected_units": ["player_alpha", "player_bravo"],
  "count": 2
}
```

#### 9.2 `api.command_attack`
Orders targeted units to focus fire on a specific enemy tank or location.
```json
{
  "action": "api.command_attack",
  "unit_ids": "player_alpha",
  "target_id": "e_hunter_1"
}
```
**Response:**
```json
{
  "status": "ok",
  "command": "command_attack",
  "target_id": "e_hunter_1",
  "affected_units": ["player_alpha"],
  "count": 1
}
```

#### 9.3 `api.command_set_tactic`
Updates the combat posture of targeted units. Supported postures:
- `"aggressive"` / `"1"`: Engage enemies on sight.
- `"defensive"` / `"2"`: Hold position, defend localized perimeter.
- `"guard_unit"` / `"3"`: Escort and protect a specified friendly unit/fortress.
- `"manual"` / `"stop"`: Idle / direct manual micro-control.

```json
{
  "action": "api.command_set_tactic",
  "unit_ids": "player_alpha",
  "tactic": "defensive"
}
```
**Response:**
```json
{
  "status": "ok",
  "command": "command_set_tactic",
  "tactic": "defensive",
  "affected_units": ["player_alpha"],
  "count": 1
}
```

#### 9.4 `api.command_set_guard`
Assigns targeted units to closely escort and protect a specific friendly unit (e.g., the Supply Fortress).
```json
{
  "action": "api.command_set_guard",
  "unit_ids": "player_alpha,player_bravo",
  "target_id": "core_supply_base"
}
```
**Response:**
```json
{
  "status": "ok",
  "command": "command_set_guard",
  "guard_target": "core_supply_base",
  "affected_units": ["player_alpha", "player_bravo"],
  "count": 2
}
```

---

### 10. `api.report`

Requests a complete telemetry and status report for a specific friendly unit.

#### Request:
```json
{
  "action": "api.report",
  "unit_id": "player_alpha"
}
```

#### Response:
```json
{
  "status": "ok",
  "report": {
    "id": "player_alpha",
    "alive": true,
    "tactic": "guard_unit",
    "ammo": 18,
    "max_ammo": 20,
    "speed": 3.0,
    "hp": 2,
    "max_hp": 2,
    "x": 224.0,
    "y": 448.0,
    "direction": "UP",
    "visibility": 1.0,
    "vision_size": 260.0,
    "is_tower": false,
    "tower_type": "general",
    "resupply_radius": 0.0,
    "auto_clear": false
  }
}
```

---

## 💻 Interactive Console CLI (`tests/cli_client.py`)

A built-in interactive console client is provided for quick terminal debugging and manual interaction.

```bash
# Launch interactive REPL
python3 tests/cli_client.py

# Or execute a one-shot command
python3 tests/cli_client.py --cmd "list"
python3 tests/cli_client.py --cmd "list_enemy"
python3 tests/cli_client.py --cmd "list_enemy god"
python3 tests/cli_client.py --cmd "report player_alpha"
python3 tests/cli_client.py --cmd "move player_alpha 200 300"
```

### CLI Command Summary:
| Command | Description |
| :--- | :--- |
| `pause` | Pause engine simulation loop |
| `resume` | Resume engine simulation loop |
| `restart` | Reset battle & restart simulation |
| `status` | Check victory & defeat status |
| `list` | List surviving friendly unit IDs |
| `list_enemy [god]` | List currently visible enemy IDs (or all if `god`) |
| `list_enemy_mem` | List enemy IDs recorded in global memory (tracked & lost) |
| `report <id>` | Query comprehensive telemetry of a friendly unit |
| `report_enemy <id>` | Query last known coordinates & unit type of enemy in memory |
| `move <ids> <x> <y>` | Dispatch batch movement orders |
| `attack <ids> <enemy_id>` | Order batch focus fire |
| `tactic <ids> <mode>` | Set combat tactic (`aggressive`, `defensive`, etc.) |
| `guard <ids> <ally_id>` | Assign bodyguard escort orders |
| `terminate` | Terminate engine process |
| `fire <ids> [direction]` | Order batch cannon fire |
| `path <id> <x> <y>` | Plan optimal A* path & query ammo breach cost |
| `raw <json>` | Send custom arbitrary JSON payload |

---

## 🧭 Intelligent A* Pathfinding & Ammo-Optimized Obstacle Breaching

The engine features a dual-mode A* pathfinding algorithm ([`GridPathfinder`](file:///Users/xianzhizeng/Documents/projects/tanks_tactic/command/pathfinder.py)):
- **Infinite Ammo Mode (`tank.ammo < 0` or unlimited ammo enabled)**:
  - **Auto-Breaching (自动破障)**: Incurs minimal obstacle breach penalty (`0.8`), actively blasting straight through destructible brick barriers instead of undertaking lengthy detours.
- **Limited Ammo Mode (`tank.ammo >= 0` and limited ammo enabled)**:
  - **Ammo-Optimized Route (最省弹药破障)**: Imposes a heavy ammo penalty (`100.0`), automatically discovering zero-ammo bypasses around obstacles; if a passage is completely sealed, it computes the mathematically optimal path that breaches the absolute minimum number of brick barriers.
- **API Access**: Accessible via `api.find_path(x, y)` in `TankScriptAPI` or `api.find_path` over WebSocket/TCP/UDP.

---

## 🐍 Tactical Python AI Scripts (`ai_python/`)

The engine provides an autonomous tactical script execution layer in `ai_python/`:
- **Threaded Execution**: Each autonomous unit (enemies and uncontrollable friendly units) executes its configured Python script (`ai_script` in mission JSON) within its own dedicated background `threading.Thread`.
- **API Layer Translation**: Scripts interact with the game engine exclusively via `TankScriptAPI` (`ai_python/bridge.py`), which translates Python method invocations (`move`, `attack`, `fire`, `set_guard`, `report`, `get_opponents`, `get_allies`) into standard JSON API requests dispatched to `GameAPIController.handle_request()`.
- **Omniscient Intelligence**: Tactical scripts are omniscient by default (`god_mode=True`), possessing full situational awareness of all units and terrain without fog-of-war restrictions.
- **Friendly Controllability**: Friendly units can be designated as non-controllable (`controllable: false`). Non-controllable units are always listed in `list_current_unit_id` and share vision across the entire team (clearing fog-of-war and spotting enemies for all friendly units). External commands targeting them succeed without error (`status: "ok"`), but are not executed on them, ensuring these units autonomously execute their own predetermined AI scripts.

### Example Tactical Python Script (`ai_python/boss_hunter.py`):
```python
import math

def run(api):
    while not api.should_stop():
        me = api.get_status()
        opponents = api.get_opponents()
        if opponents:
            # Omniscient target selection: prioritize defense towers or lowest HP
            target = min(opponents, key=lambda o: o.get("hp", 1))
            api.attack(target["id"])
            api.fire()
        api.sleep(0.3)
```

---

## 🛠️ Code Examples

### Python (Raw TCP Socket)
```python
import socket
import json

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("127.0.0.1", 8091))

# Send newline-terminated JSON
s.sendall(json.dumps({"action": "api.list_current_unit_id"}).encode() + b"\n")

# Receive newline-terminated JSON
response = json.loads(s.recv(4096).decode())
print("Active Units:", response["unit_ids"])
s.close()
```

### Python (UDP Datagram RPC)
```python
import socket
import json

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
req = json.dumps({"action": "api.report", "unit_id": "core_supply_base"}).encode()
sock.sendto(req, ("127.0.0.1", 8092))

data, _ = sock.recvfrom(4096)
print("Telemetry:", json.loads(data.decode()))
sock.close()
```

### Bash (`nc` / Netcat)
```bash
echo '{"action": "api.is_success"}' | nc 127.0.0.1 8091
```
