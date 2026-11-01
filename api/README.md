# 🌐 Tanks Tactic Network API Specification

The Tanks Tactic Game Engine provides an external, programmable remote control and telemetry interface supporting **dual wire formats**:
1. **Standard JSON-RPC** (`{"action": "api.move", "unit_ids": "player_alpha", "x": 250, "y": 380}`)
2. **Plain Function-Call Format** (`func(arg1, arg2, ...)` or `api.func(arg1, arg2, ...)`, e.g. `move([player_alpha, player_bravo], 250, 380)`)

It enables external agents, LLM/VLM controllers, reinforcement learning controllers, automated test harnesses, and third-party dashboards to monitor, pause, resume, dispatch tactical commands, and inspect friendly armor units in real-time.

---

## 📡 Transport Protocols & Port Matrix

By default, the engine starts three network servers simultaneously (all three transparently accept both **JSON** and **Plain `func(arg1, arg2, ...)`** requests):

| Protocol | Default Port | Format & Wire Encoding | Description |
| :--- | :--- | :--- | :--- |
| **WebSocket** | `8090` | RFC 6455 Text Frames (JSON or `func(...)`) | Bi-directional, event-driven web socket stream. |
| **Raw TCP/IP** | `8091` | Newline-delimited (`\n`) JSON or `func(...)` | Raw socket stream for any language or CLI tools (`nc`, `telnet`). |
| **UDP Beacon & RPC** | `8092` | UDP Datagrams (UTF-8 JSON or `func(...)`) | Online broadcast discovery ("我在这里") and connectionless RPC. |

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

The engine natively supports **two request formats** over WebSocket, TCP, UDP, and direct `GameAPIController.handle_request()` calls:

### Format A: Standard JSON Envelope
Every JSON request is a JSON object (or array of objects for batch execution). Both root-level attributes and nested `params` structures are accepted:
```json
{
  "action": "api.report",
  "unit_id": "player_alpha",
  "id": 1001
}
```
*Note: The `"api."` prefix is optional. `"action": "report"` and `"action": "api.report"` are equivalent.*

### Format B: Plain Function-Call Format (`func(arg1, arg2, ...)`)
For concise human CLI usage, LLM tool calls, or lightweight scripts, you can send raw plain-text function calls directly without wrapping them in JSON:
```text
func(arg1, arg2, ...)
api.func(arg1, arg2, ...)
```
#### Plain Format Parsing & Paired Delimiter Rules ("掐头去尾"):
1. **Paired Quotes & Brackets as Single String Arguments**:
   - Whenever an argument is enclosed in paired double quotes `"..."`, single quotes `'...'`, Chinese curly quotes `“...”` / `‘...’`, or square brackets `[...]` / `【...】`, **everything inside the pair (including commas and spaces) is treated as a single long string argument**, and the opening and closing delimiters are **automatically stripped ("掐头去尾")**.
   - Examples:
     - `move([player_alpha, player_bravo], 250, 380)` $\rightarrow$ `unit_ids="player_alpha, player_bravo"`, `x=250.0`, `y=380.0`
     - `move("player_alpha, player_bravo", 250, 380)` $\rightarrow$ `unit_ids="player_alpha, player_bravo"`, `x=250.0`, `y=380.0`
     - `set_tactic(“player_alpha, player_bravo”, ‘defensive’)` $\rightarrow$ `unit_ids="player_alpha, player_bravo"`, `tactic="defensive"`
     - `report('player_alpha')` $\rightarrow$ `unit_id="player_alpha"`
2. **Positional & Keyword Arguments (`key=value`)**:
   - Arguments can be passed positionally according to the endpoint signature, or explicitly via `key=value` (e.g. `list_enemy_curr(god_mode=true)`, `move([player_alpha], x=250, y=380, seq=5)`).
   - Numbers (`int` / `float`) and booleans (`true` / `false`) outside quotes are automatically cast to their native types.
3. **Multi-Command Batching**:
   - Multiple plain calls can be separated by `;` or newlines in a single payload (e.g. `pause(); move([player_alpha], 250, 380); resume()`), or mixed inside a JSON batch array `["pause()", "move([player_alpha], 250, 380)"]`.

### Standard Response Envelope (Always JSON):
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

## 🛡️ Concurrency Safety & Anti-Jitter Architecture

To prevent game stuttering, tank jitter, and race conditions when multiple API clients (WebSocket, TCP, UDP, AI script threads) issue requests simultaneously:

1. **Re-entrant Thread Safety (`RLock`)**:
   - `GameAPIController.lock` guarantees exclusive atomic execution.
   - Simulation loops (`game_widget.py`, `headless_runner.py`) acquire this lock each tick, preventing physics/dispatcher race conditions.

2. **Batch Commands & Priority Sorting**:
   - Accepts batch arrays `[req1, req2, ...]` or `{"action": "batch", "commands": [...]}`.
   - Automatically sorts requests based on priority:
     - **0**: Emergency/System controls (`pause`, `resume`, `terminate`)
     - **10**: Overrides & Stops (`terminate_convert`, `stop_harvest`, `stop`, `guard`, `tactic`)
     - **20**: Combat actions (`attack`)
     - **30**: Movement & Pathfinding (`move`, `path`)
     - **40**: Economy & Production (`convert`, `harvest`)
     - **50**: Queries & Telemetry (`report`, `resources`, `list_*`)
   - Within the same priority, commands can specify `"order": int` or `"seq": int`.

3. **Sequence Anti-Jitter Protection (`seq`)**:
   - Commands can optionally specify `"seq": <integer>`.
   - If network delay causes an older sequence to arrive after a newer one, the controller safely ignores it (`status: "ignored"`), preventing tanks from jittering back and forth.

4. **Movement Anti-Stutter Damping**:
   - High-frequency calls to `move` with a target within 4.0 pixels of the current active waypoint will preserve the current smooth A* path without interrupting the tank.

---

## 📚 API Reference

### 1. `api.pause()` & `api.resume()`

Freezes or unfreezes the game engine's physical simulation, projectile updates, and enemy/friendly AI routines. Rendering, telemetry, and planning APIs continue to function during pause.
- **Default State on Startup**: The game starts in **PAUSED** mode by default to allow initial tactical planning and reconnaissance. Use `api.resume` or press the **P** key in the GUI/WebUI to start the simulation.
- **Pre-Execution Queuing**: Tactical movement, targeting, and firing APIs (`command_move`, `command_attack`, `command_fire`, etc.) can be called during pause. They will be acknowledged and queued, executing immediately as soon as the engine is resumed.

#### Request (Pause — Plain or JSON):
```text
pause()
```
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

#### Request (Resume — Plain or JSON):
```text
resume()
```
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

#### Request (Plain or JSON):
```text
is_success()
```
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

#### Request (Plain or JSON):
```text
terminate()
```
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

#### Request (Plain or JSON):
```text
restart()
```
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

#### Request (Plain or JSON):
```text
list_current_unit_id()
```
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

#### Request (Default Vision Mode — Plain or JSON):
```text
list_enemy_curr()
```
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

#### Request (God Mode — Plain or JSON):
```text
list_enemy_curr(true)
```
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

#### Request (Plain or JSON):
```text
list_enemy_mem()
```
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

#### Request (Plain or JSON):
```text
report_enemy("e_hunter_1")
```
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

Batch operations target units identified by `unit_ids` (a comma-separated string `"id1,id2"`, a JSON array `["id1", "id2"]`, or a paired-delimiter string in Plain format such as `[id1, id2]` / `"id1, id2"` / `'id1, id2'` / `“id1, id2”`).

#### 9.1 `api.command_move` (or `move`)
Directs targeted units to navigate to destination coordinates `(x, y)` in formation along direct any-angle diagonal paths.
```text
move([player_alpha, player_bravo], 250.0, 380.0)
move("player_alpha, player_bravo", 250.0, 380.0)
```
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

#### 9.2 `api.command_attack` (or `attack`)
Orders targeted units to focus fire on a specific enemy tank or location `(x, y)`.
```text
attack([player_alpha], "e_hunter_1")
attack('player_alpha, player_bravo', 320, 240)
```
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

#### 9.3 `api.command_set_tactic` (or `set_tactic` / `tactic`)
Updates the combat posture of targeted units. Supported postures:
- `"aggressive"` / `"1"`: Engage enemies on sight.
- `"defensive"` / `"2"`: Hold position, defend localized perimeter.
- `"guard_unit"` / `"3"`: Escort and protect a specified friendly unit/fortress.
- `"manual"` / `"stop"`: Idle / direct manual micro-control.

```text
set_tactic([player_alpha], 'defensive')
tactic(“player_alpha, player_bravo”, ‘aggressive’)
```
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

#### 9.4 `api.command_set_guard` (or `set_guard` / `guard`)
Assigns targeted units to closely escort and protect a specific friendly unit (e.g., the Supply Fortress).
```text
guard([player_alpha, player_bravo], "core_supply_base")
```
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

#### Request (Plain or JSON):
```text
report("player_alpha")
```
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
    "auto_clear": false,
    "converter_table": ["recipe_dm_to_alloy", "recipe_build_tank"],
    "is_converting": false,
    "converter_status": { "is_converting": false }
  }
}
```

---

### 11. `api.find_path` (or `path`)

Plans an optimal 8-directional A* + Any-Angle String-Pulled path from the unit's current position to target coordinates `(x, y)`. Automatically calculates waypoint nodes and ammo breach costs based on limited/unlimited ammo rules.

#### Request (Plain or JSON):
```text
find_path("player_alpha", 480.0, 320.0)
```
```json
{
  "action": "api.find_path",
  "unit_id": "player_alpha",
  "x": 480.0,
  "y": 320.0
}
```

#### Response:
```json
{
  "status": "ok",
  "unit_id": "player_alpha",
  "start": [224.0, 448.0],
  "goal": [480.0, 320.0],
  "reachable": true,
  "nodes_count": 3,
  "ammo_cost": 2,
  "nodes": [[224.0, 448.0], [256.0, 416.0], [480.0, 320.0]]
}
```

---

### 12. `api.get_resources` (or `resources`)

Queries tactical resource stockpiles (e.g. `dark_matter`, `alloy`) and current real-time harvesting income rates for a given camp.

#### Request (Plain or JSON):
```text
get_resources("player")
```
```json
{
  "action": "api.get_resources",
  "camp": "player"
}
```

#### Response:
```json
{
  "status": "ok",
  "camp": "player",
  "resources": {
    "dark_matter": 120.0,
    "alloy": 65.0
  },
  "rates": {
    "dark_matter": 2.5,
    "alloy": 0.0
  }
}
```

---

### 13. `api.list_resource_blocks` (or `blocks`)

Lists all active natural resource blocks on the map with their tile coordinates, current amount, regeneration speed, harvesting radius, and exclusive occupation radius.

#### Request (Plain or JSON):
```text
list_resource_blocks("player_alpha")
```
```json
{
  "action": "api.list_resource_blocks",
  "unit_id": "player_alpha"
}
```

#### Response:
```json
{
  "status": "ok",
  "count": 2,
  "blocks": [
    {
      "col": 8,
      "row": 12,
      "x": 288.0,
      "y": 432.0,
      "resource_type": "dark_matter",
      "current_amount": 100.0,
      "max_amount": 100.0,
      "regen_rate": 2.0,
      "harvest_radius": 120.0,
      "exclusive_radius": 80.0,
      "in_range": true,
      "is_exclusive": true
    }
  ]
}
```

---

### 14. `api.command_harvest` & `api.command_stop_harvest`

Orders units to begin extracting tactical resources from a designated map tile `(col, row)`, or stops harvesting.

#### Request (Start Harvest — Plain or JSON):
```text
harvest([player_alpha], 8, 12)
```
```json
{
  "action": "api.harvest",
  "unit_ids": ["player_alpha"],
  "col": 8,
  "row": 12
}
```

#### Request (Stop Harvest — Plain or JSON):
```text
stop_harvest([player_alpha])
```
```json
{
  "action": "api.stop_harvest",
  "unit_ids": ["player_alpha"]
}
```

---

### 15. `api.list_converter`

Enumerates all registered converter recipes loaded into the global registry (`converter/` directory), returning recipe IDs and brief metadata.

#### Request (Plain or JSON):
```text
list_converter()
```
```json
{
  "action": "api.list_converter"
}
```

#### Response:
```json
{
  "status": "ok",
  "count": 5,
  "converter_ids": [
    "recipe_alloy_to_dm",
    "recipe_build_tank",
    "recipe_dm_to_alloy",
    "recipe_free_energy",
    "recipe_hyper_fusion"
  ],
  "converters": [
    {
      "id": "recipe_alloy_to_dm",
      "name": "converter.recipe.alloy_to_dm",
      "output_type": "resource",
      "duration": 5.0
    },
    {
      "id": "recipe_build_tank",
      "name": "converter.recipe.build_tank",
      "output_type": "tank",
      "duration": 5.0
    },
    {
      "id": "recipe_free_energy",
      "name": "converter.recipe.free_energy",
      "output_type": "resource",
      "duration": 3.0
    }
  ]
}
```

---

### 16. `api.show_converter`

Fetches detailed parameters of a specific converter recipe by its ID. Supports querying zero-input recipes (free resource generation) and tank-production recipes (containing chassis template, visibility, vision size, and ammo).

#### Request (Plain or JSON):
```text
show_converter("recipe_build_tank")
```
```json
{
  "action": "api.show_converter",
  "converter_id": "recipe_build_tank"
}
```

#### Response:
```json
{
  "status": "ok",
  "converter_id": "recipe_build_tank",
  "converter": {
    "id": "recipe_build_tank",
    "name": "converter.recipe.build_tank",
    "inputs": {
      "alloy": 15.0
    },
    "outputs": "tank",
    "duration": 5.0,
    "output_type": "tank",
    "tank_config": "tank_configs/player_tank.json",
    "visibility": 0.9,
    "vision_size": 300.0,
    "ammo": 25
  }
}
```

---

### 17. `api.convert` & `api.terminate_convert`

Enqueues and starts a conversion or unit production task on an equipped armor unit. While converting, the unit is held stationary and cannot move or fire. When a tank is produced, it automatically receives an ID of `{producer_id}/{sequence}`, is placed on adjacent free terrain, and is registered to the global battle state.

#### Request (Start Conversion / Production — Plain or JSON):
```text
convert("player_alpha", 'recipe_build_tank', 2)
```
```json
{
  "action": "api.convert",
  "unit_id": "player_alpha",
  "recipe_id": "recipe_build_tank",
  "count": 2
}
```

#### Response:
```json
{
  "status": "ok",
  "unit_id": "player_alpha",
  "recipe_id": "recipe_build_tank",
  "count": 2,
  "result": "started",
  "is_converting": true
}
```

#### Request (Terminate Conversion — Plain or JSON):
```text
terminate_convert("player_alpha")
```
```json
{
  "action": "api.terminate_convert",
  "unit_id": "player_alpha"
}
```

---

### 18. `api.get_mission_info` (or `mission_info` / `briefing`)
Query the mission background briefing narrative, linked map name, and map dimension limits (grid columns & rows, tile size, pixel dimensions, coordinate x/y upper limits).

#### Request (Plain or JSON):
```text
get_mission_info()
```
or
```json
{
  "action": "api.get_mission_info"
}
```

#### Response:
```json
{
  "status": "ok",
  "mission_name": "Mission 1: Defense of Eagle Fortress",
  "briefing": "指挥官！敌军先遣部队正在集结并逼近我方老鹰基地。请率领MCV与防御部队固守阵线，利用暗物质与合金资源研发增援，彻底歼灭来犯敌军！",
  "map_name": "Level 1: Industrial Frontier",
  "map_file": "maps/level_01.json",
  "cols": 20,
  "rows": 16,
  "tile_size": 36,
  "pixel_width": 720.0,
  "pixel_height": 576.0,
  "max_x": 720.0,
  "max_y": 576.0,
  "map_size": {
    "cols": 20,
    "rows": 16,
    "grid_width": 20,
    "grid_height": 16,
    "tile_size": 36,
    "pixel_width": 720.0,
    "pixel_height": 576.0,
    "max_x": 720.0,
    "max_y": 576.0,
    "max_col": 20,
    "max_row": 16
  }
}
```

---

### 19. `api.edit_attr` (or `edit_attr`)
Dynamically modify attribute(s) of one or more existing unit objects on the battlefield (supports batch ID lists and `*`). Data types (`int`, `float`, `bool`, `list`, `str`) are inferred and converted automatically.
* **Error handling rule**: Only returns an error if **no target objects can be found**. If a target object does not have the specified attribute, it is automatically skipped.

#### Request (Plain or JSON):
```text
edit_attr([player_alpha, player_bravo], speed, 5.0)
```
or
```json
{
  "action": "api.edit_attr",
  "unit_ids": ["player_alpha", "player_bravo"],
  "attr": "speed",
  "value": 5.0
}
```

#### Response:
```json
{
  "status": "ok",
  "attr": "speed",
  "value": 5.0,
  "updated_units": ["player_alpha", "player_bravo"],
  "skipped_units": []
}
```

---

### 20. `api.set_resources` (or `set_resources` / `modify_resources`)
Modify global strategic resource stockpiles for either or both camps (`"both"`, `"player"`, or `"enemy"`).

#### Request (Plain or JSON):
```text
set_resources("both", 1000.0, 500.0)
```
or
```json
{
  "action": "api.set_resources",
  "camp": "both",
  "dark_matter": 1000.0,
  "alloy": 500.0,
  "mode": "set"
}
```

#### Response:
```json
{
  "status": "ok",
  "mode": "set",
  "stockpiles": {
    "player": {"dark_matter": 1000.0, "alloy": 500.0},
    "enemy": {"dark_matter": 1000.0, "alloy": 500.0}
  },
  "player": {"dark_matter": 1000.0, "alloy": 500.0},
  "enemy": {"dark_matter": 1000.0, "alloy": 500.0}
}
```

---

### 21. `api.create_unit` (or `create_unit` / `spawn_unit`)
Dynamically spawn and deploy a new combat unit or defensive tower onto the live battlefield. Automatically resolves chassis templates, initializes physics entities, and registers the unit with dispatcher and enemy AI controllers.

#### Request (Plain or JSON):
```text
create_unit("player", 150.0, 200.0, "tank_configs/player_tank.json", "reinforcement_alpha")
```
or
```json
{
  "action": "api.create_unit",
  "camp": "player",
  "x": 150.0,
  "y": 200.0,
  "config_file": "tank_configs/player_tank.json",
  "unit_id": "reinforcement_alpha",
  "health": 5,
  "ammo": 40
}
```

#### Response:
```json
{
  "status": "ok",
  "unit_id": "reinforcement_alpha",
  "camp": "player",
  "x": 150.0,
  "y": 200.0,
  "health": 5,
  "ammo": 40,
  "speed": 3.0,
  "unit_type": "Classic Tank",
  "config_file": "tank_configs/player_tank.json"
}
```

---

### 22. `api.get_game_time` (or `game_time` / `time`)
Query active simulation elapsed runtime in milliseconds and seconds.
* **Pause freezing guarantee**: Active runtime accumulation strictly freezes during engine pauses and resumes seamlessly upon unpausing.

#### Request (Plain or JSON):
```text
get_game_time()
```
or
```json
{
  "action": "api.get_game_time"
}
```

#### Response:
```json
{
  "status": "ok",
  "game_time_ms": 14250,
  "game_time_sec": 14.25,
  "is_paused": false
}
```

---

## 💻 Interactive Console CLI (`tests/cli_client.py`)

A built-in interactive console client is provided for quick terminal debugging and manual interaction. It supports both space-separated CLI shortcuts and direct **`func(arg1, arg2, ...)`** plain API calls.

```bash
# Launch interactive REPL
python3 tests/cli_client.py

# Execute one-shot CLI commands
python3 tests/cli_client.py --cmd "list"
python3 tests/cli_client.py --cmd "resources"
python3 tests/cli_client.py --cmd "list_converter"
python3 tests/cli_client.py --cmd "show_converter recipe_build_tank"
python3 tests/cli_client.py --cmd "convert player_alpha recipe_build_tank 1"
python3 tests/cli_client.py --cmd "harvest player_alpha 8 12"

# Or execute raw Plain Function-Call syntax directly
python3 tests/cli_client.py --cmd "move([player_alpha, player_bravo], 250, 380)"
python3 tests/cli_client.py --cmd "set_tactic(“player_alpha, player_bravo”, ‘defensive’)"
python3 tests/cli_client.py --cmd "report('player_alpha')"
```

### CLI Command Summary:
| Command / Plain Call | Description |
| :--- | :--- |
| `pause` / `pause()` | Pause engine simulation loop |
| `resume` / `resume()` | Resume engine simulation loop |
| `restart` / `restart()` | Reset battle & restart simulation |
| `status` / `is_success()` | Check victory & defeat status |
| `time` / `get_game_time()` | Query active simulation runtime in milliseconds (frozen during pause) |
| `mission_info` / `get_mission_info()` | Query mission briefing narrative and map size/limits |
| `list` / `list_current_unit_id()` | List surviving friendly unit IDs |
| `list_enemy [god]` / `list_enemy_curr(true)` | List currently visible enemy IDs (or all if `god`) |
| `list_enemy_mem` / `list_enemy_mem()` | List enemy IDs recorded in global memory (tracked & lost) |
| `report <id>` / `report("id")` | Query comprehensive telemetry of a friendly unit |
| `report_enemy <id>` / `report_enemy("id")` | Query last known coordinates & unit type of enemy in memory |
| `move <ids> <x> <y>` / `move([ids], x, y)` | Dispatch batch movement orders |
| `attack <ids> <enemy_id>` / `attack([ids], "enemy_id")` | Order batch focus fire |
| `tactic <ids> <mode>` / `set_tactic([ids], "mode")` | Set combat tactic (`aggressive`, `defensive`, etc.) |
| `guard <ids> <ally_id>` / `guard([ids], "ally_id")` | Assign bodyguard escort orders |
| `fire <ids> [direction]` / `fire([ids], "direction")` | Order batch cannon fire |
| `path <id> <x> <y>` / `find_path("id", x, y)` | Plan optimal A* path & query ammo breach cost |
| `resources [camp]` / `get_resources("camp")` | Query resource reserves & real-time income rates |
| `blocks [unit_id]` / `list_resource_blocks("id")` | Query active resource blocks and harvest ranges |
| `harvest <ids> <c> <r>` / `harvest([ids], c, r)` | Order units to harvest resource block at tile `(col, row)` |
| `stop_harvest [ids]` / `stop_harvest([ids])` | Stop resource harvesting |
| `list_converter` / `list_converter()` | List all registered converter recipe IDs |
| `show_converter <id>` / `show_converter("id")` | Display detailed parameters of a converter recipe |
| `convert <id> <r_id> [n]` / `convert("id", "r_id", n)` | Enqueue recipe conversion or tank production |
| `terminate_convert [id]` / `terminate_convert("id")` | Terminate active conversion and clear queue |
| `edit_attr <ids> <attr> <val>` / `edit_attr([ids], attr, val)` | Dynamically modify unit attributes with auto type conversion |
| `set_resources <camp> [dm] [al]` / `set_resources(camp, dm, al)` | Modify global strategic resource stockpiles (both/player/enemy) |
| `create_unit <camp> <x> <y> [cfg] [id]` / `create_unit(camp, x, y, cfg, id)` | Dynamically spawn and deploy new units on battlefield |
| `terminate` / `terminate()` | Terminate engine process |
| `raw <json_or_plain>` | Send custom arbitrary JSON or `func(...)` payload |

---

## 🧭 Any-Angle Diagonal A* Pathfinding, Dynamic Obstacle Avoidance & Ammo-Optimized Breaching

The engine features a hybrid **8-directional A* + Any-Angle String Pulling** pathfinder ([`GridPathfinder`](file:///Volumes/data/projects/tank_tactic/command/pathfinder.py)) combined with multi-stage **Context Steering Dynamic Obstacle Avoidance** ([`commands.py`](file:///Volumes/data/projects/tank_tactic/command/commands.py)):

1. **Direct Diagonal & Any-Angle Pathfinding (任意角度斜线直达)**:
   - **8-Direction A* + Octile Heuristic**: Explores all 8 compass directions (`N, S, E, W, NE, NW, SE, SW`) with strict diagonal corner-cutting prevention and oversized chassis clearance checks (`_is_oversized_blocked_at`).
   - **Swept-Box Line-of-Sight String Pulling (`_smooth_path` & `is_segment_passable`)**: Automatically simplifies multi-step grid waypoints into direct Euclidean straight-line segments whenever the tank's swept bounding box is clear of obstacles—allowing tanks to travel directly along any diagonal angle instead of zig-zagging horizontally and vertically.
   - **Full-Vector Physics Displacement**: [`PhysicsEngine.move_tank`](file:///Volumes/data/projects/tank_tactic/physics/engine.py) prioritizes full vector displacement `(vx, vy)` before applying corridor center-line alignment assist, ensuring shallow diagonal trajectories are never pulled back onto orthogonal grid lines.

2. **Multi-Stage Dynamic Obstacle Avoidance (动态避障与防死锁)**:
   - **Minkowski Obstacle Expansion (`_collect_avoid_tiles`)**: Stationary structures, harvesters, converting units, and blocking tanks are dynamically expanded by the moving tank's half-size during A* replanning so paths leave sufficient physical clearance.
   - **Context Steering & Right-Hand Traffic Rule (`_steer_around_obstacle`)**: When another tank enters the proactive lookahead cone, the unit probes a multi-angle steering fan (`±25° ~ ±135°`) biased by a right-hand traffic rule and locks its evasion side (`evade_lock_timer`) to smoothly glide around stationary or oncoming tanks without oscillation or wall-sliding back into the obstacle's center line.
   - **Dynamic Lookahead Shortcutting & Narrow-Corridor Yielding**: Continuously checks line-of-sight to downstream waypoints (`_is_corridor_blocked_by_tank`) to skip intermediate nodes smoothly, and performs side-pocket or reverse yielding when two tanks meet head-on in a single-tile corridor.

3. **Dual-Mode Ammo-Optimized Obstacle Breaching**:
   - **Infinite Ammo Mode (`tank.ammo < 0` or unlimited ammo enabled)**:
     - **Auto-Breaching (自动破障)**: Incurs minimal obstacle breach penalty (`0.8`), actively blasting straight through destructible brick barriers instead of undertaking lengthy detours.
   - **Limited Ammo Mode (`tank.ammo >= 0` and limited ammo enabled)**:
     - **Ammo-Optimized Route (最省弹药破障)**: Imposes a heavy ammo penalty (`100.0`), automatically discovering zero-ammo bypasses around obstacles; if a passage is completely sealed, it computes the mathematically optimal path that breaches the absolute minimum number of brick barriers.
   - **API Access**: Accessible via `api.find_path(x, y)` in `TankScriptAPI` or `find_path(unit_id, x, y)` / `{"action": "api.find_path", ...}` over WebSocket/TCP/UDP.

---

## 🐍 Tactical Python AI Scripts (`ai_python/`)

The engine provides an autonomous tactical script execution layer in `ai_python/`:
- **Threaded Execution**: Each autonomous unit (enemies and uncontrollable friendly units) executes its configured Python script (`ai_script` in mission JSON) within its own dedicated background `threading.Thread`.
- **API Layer Translation**: Scripts interact with the game engine exclusively via `TankScriptAPI` (`ai_python/bridge.py`), which translates Python method invocations (`move`, `attack`, `fire`, `set_guard`, `report`, `get_opponents`, `get_allies`) into standard JSON API requests dispatched to `GameAPIController.handle_request()`.
- **Omniscient Intelligence**: Tactical scripts are omniscient by default (`god_mode=True`), possessing full situational awareness of all units and terrain without fog-of-war restrictions.
- **Friendly Controllability**: Friendly units can be designated as non-controllable (`controllable: false`). Non-controllable units are always listed in `list_current_unit_id` and share vision across the entire team (clearing fog-of-war and spotting enemies for all friendly units). External commands targeting them succeed without error (`status: "ok"`), but are not executed on them, ensuring these units autonomously execute their own predetermined AI scripts.

### Autonomous Commander Scripts (`ai_python/commander_*.py`):
Can be assigned to enemy defensive fortresses or towers to dynamically direct and command friendly battlefield units:
1. **Novice Commander (`commander_novice.py`)**:
   - Slow heartbeat (`2.5s`), passive defensive posture.
   - Dispatches single interceptors only when opponents breach the inner defense perimeter (`< 220px`).
2. **Intermediate Commander (`commander_intermediate.py`)**:
   - Balanced heartbeat (`1.0s`).
   - Delegates dedicated bodyguards to protect the command tower while sending assault groups to focus-fire vulnerable or nearby targets.
   - Commands idle units to harvest nearby tactical resources.
3. **Ruthless Commander (`commander_ruthless.py`)**:
   - High-frequency heartbeat (`0.4s`).
   - Real-time macro-economic coordination: triggers MCVs to produce heavy Apocalypse or fast Rhino tanks.
   - Wolfpack tactics: orders full aggressive focus-fire with priority on decapitating player fortresses and base buildings.

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

### Python (Raw TCP Socket — Plain `func(...)` or JSON)
```python
import socket
import json

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("127.0.0.1", 8091))

# Example 1: Send Plain Function-Call format (with paired brackets/quotes)
s.sendall(b"move([player_alpha, player_bravo], 250, 380)\n")
print("Move Response:", json.loads(s.recv(4096).decode()))

# Example 2: Send newline-terminated JSON
s.sendall(json.dumps({"action": "api.list_current_unit_id"}).encode() + b"\n")
response = json.loads(s.recv(4096).decode())
print("Active Units:", response["unit_ids"])
s.close()
```

### Python (UDP Datagram RPC — Plain `func(...)` or JSON)
```python
import socket
import json

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Plain Function-Call datagram
sock.sendto(b"report('core_supply_base')", ("127.0.0.1", 8092))
data, _ = sock.recvfrom(4096)
print("Telemetry:", json.loads(data.decode()))
sock.close()
```

### Bash (`nc` / Netcat)
```bash
# Using Plain Function-Call format:
echo 'is_success()' | nc 127.0.0.1 8091
echo 'move([player_alpha, player_bravo], 250, 380)' | nc 127.0.0.1 8091

# Or using JSON format:
echo '{"action": "api.is_success"}' | nc 127.0.0.1 8091
```
