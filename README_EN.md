[中文](README.md) | [English](README_EN.md)

# 🕹️ Battle City Pixel (Tactical Tank Warfare)

A tactical retro-arcade pixel tank warfare game based on **Python 3** and **PyQt5**, reimagining the classic NES/FC Battle City with deep modern RTS tactics.

This project combines **Age of Empires-style RTS marquee selection and tactical grouping**, **authentic arcade-feel micro control**, **360° free continuous rotation and omnidirectional maneuvering**, **heavy clearing tanks with physical brick crushing**, **smart "bulldozer" auto-breaching**, **line-of-sight & square fog-of-war**, **three specialized fortress towers & ammo resupply mechanics**, **an Age of Empires II-style All-in-One scenario & map editor**, **instant zero-latency GUI internationalization (i18n)**, and an **Omniscient God-View Tactical Monitor (Auxiliary Read-Only WebUI)**.

---

## 🌟 Core Features

- **🏰 Age of Empires II-Style All-in-One Scenario Editor (`editor/`)**:
  - **Mode 1: Map Editor Mode**: Interactive grid terrain editor with real-time crosshair coordinate tracking (Tile & Pixel). Supports **single-cell click painting / right-click clearing** and **drag-and-drop marquee box fill** for fast terrain layout. Dynamically configure map dimensions; full terrain brush palette (Empty, Red Brick, Steel Wall, Water, Bush/Grass, Ice).
  - **Mode 2: Mission & Unit Editor Mode**: Create new missions or load existing maps/scenarios. Visually place Player, Enemy, and Tower fortress entities on canvas with drag-and-drop repositioning. Features a **Scrollable Property Inspector** to modify team, angle (0°-360°), max HP, ammo capacity, speed, vision size, visibility, player controllability, and brick crushing capability.
  - **Mode 3: Victory/Defeat Condition Logic Tree Editor**: Classic AoE2 trigger-inspired **hierarchical condition editor**. Visually construct nested AND / OR / NOT logic nodes and insert core primitives (survival duration, unit destroyed, area visible, all players eliminated) with live JSON preview and syntax validation.
- **🌐 Internationalization & Dual-Language System (`translations/`)**:
  - Both Game GUI (`gui/`) and Editor GUI (`editor/`) feature an instant language switcher dropdown (`[🌐 中文 | 🌐 English]`).
  - Powered by clean YAML definitions (`zh.yml`, `en.yml`). Zero restart needed; all buttons, labels, menus, and inspector panels retranslate on the fly.
- **🔄 360° Free Rotation & Omnidirectional Movement**:
  - Replaces rigid 4-cardinal direction constraints (UP/DOWN/LEFT/RIGHT) with continuous floating-point angular orientation (0°-360°) and smooth directional acceleration, complete with independent hull and turret rotation.
- **🚜 Clearing Tank & Physical Brick Crushing (`tank_configs/clearing_tank.json`)**:
  - Heavy engineering tanks equipped with `can_crush_bricks` can directly bulldoze and crush normal red brick obstacles on contact without wasting ammo! Includes physical speed decay during crushing.
  - Smart A* pathfinding accounts for this capability: clearing tanks treat destructible bricks as traversable routes, optimizing tactical breakthrough paths.
- **📊 Auxiliary Omniscient Read-Only WebUI Monitor (`monitor/`, Always Online)**:
  - **Default bind `0.0.0.0`, default port `8088` (IP and port configurable via CLI)**.
  - **Read-Only**: Zero interactive controls or click events, specifically designed for secondary-screen telemetry, live spectating, and AI monitoring.
  - **God-View (Pierces Fog of War)**:
    - **Holographic Radar Map**: Renders all map tiles, flying projectiles, friendly tanks, and defensive fortresses (with resupply halos and sight boxes).
    - **Full Enemy Telemetry**: Tracks enemy tanks regardless of fog depth, clearly labeled as `[DETECTED]` or `[CONCEALED]`.
    - **Live Property Inspector**: Real-time table displaying absolute coordinates (X, Y), HP / Max HP bars, Ammo / Max Ammo, Vision Size, Visibility, Tactical Stance, and Auto-Breaching status.
- **🗼 Fortress Defense Towers & Ammo Supply Mechanics (`tank_configs/tower_*.json`)**:
  - The classic Eagle Base is reimagined into defensive fortresses with speed 0 (immobile).
  - **① Radar Outpost (`tower_radar.json`)**: Massive vision range (`vision_size: 560`), penetrates fog, unarmed.
  - **② Heavy Defense Cannon (`tower_cannon.json`)**: Equipped with heavy artillery to autonomously engage targets within range.
  - **③ Supply Fortress / Enhanced Eagle (`tower_supply.json`)**: Projects an active resupply radius (`resupply_radius`). Friendly tanks inside the aura continuously regenerate ammo with floating green `+AMMO` indicators!
- **🛡️ Tactical Stance: "Escort & Guard Unit" (Guard / Escort Unit)**:
  - Hotkey `3`, or **right-click directly on friendly units or fortresses**. Selected tanks form an escort perimeter, intercept approaching threats, and return to formation once danger is resolved.
- **🌫️ Sight System & Fog of War**:
  - Square field-of-view (`vision_size`, `-1` for full map). Enemies outside the fog are **completely invisible and cannot be targeted**.
  - **Enemy Visibility Index (`visibility`)**: Configured per unit (0.0 to 1.0). Once inside visual range, units are revealed based on detection probability.
- **🔋 Limited Ammo System**:
  - Each vehicle has an ammo capacity (`-1` for infinite). Firing consumes rounds; depleted units must return to a Supply Tower aura to rearm.
- **💣 Optional Bulldozer Mode: Auto-Breaching**:
  - Toggle via `B` key. When active, tanks encountering blocking brick walls fire directly to blast shortcuts instead of taking long detours.
- **⚔️ Age of Empires RTS Group Control (`command/` + `grouping/`)**:
  - Left-click drag to marquee select units; right-click for formation movement or focus-fire; press `Tab` to cycle the active micro-control tank (marked with a golden `[▼MICRO]` indicator).
- **🖥️ Dual Execution Architecture (Desktop GUI / Browser Web VNC)**:
  - Native PyQt5 desktop window or headless Web VNC streaming mode.

---

## 📦 Installation & Dependency Management

Supports Python 3.9 through 3.13.

### Method 1: Install Dependencies Directly

```bash
pip install -r requirements.txt
```

### Method 2: Editable Package Install (Recommended for Development)

```bash
pip install -e .
```
This registers two global CLI commands in your environment:
- `tanks-game`: Launches the main game;
- `tanks-editor`: Launches the Age of Empires II-style All-in-One Editor.

---

## 📂 Project Structure

```text
tanks_tactic/
├── tanks.py                      # 🚀 Game entrypoint (launches game + telemetry WebUI)
├── editor.py                     # 🏰 All-in-One scenario & map editor shortcut
├── requirements.txt              # 📦 Dependencies (PyQt5, PyYAML)
├── pyproject.toml                # ⚙️ PEP 517/621 project configuration & CLI scripts
├── setup.py                      # 🔧 Classic setup script (backward compatibility)
├── README.md                     # 📖 Chinese Documentation
├── README_EN.md                  # 📖 English Documentation
├── .gitignore                    # 🙈 Git ignore rules
│
├── editor/                       # 🏰 Age of Empires II All-in-One Editor
│   ├── main.py                   # Editor launcher
│   ├── editor_window.py          # Unified tabbed window interface
│   ├── map_editor.py             # Mode 1: Terrain painting & marquee box fill
│   ├── mission_editor.py         # Mode 2: Mission layout & scrollable property inspector
│   ├── condition_editor.py       # Mode 3: Logic tree victory/defeat condition editor
│   ├── canvas.py                 # Double-buffered interactive canvas & coordinate display
│   └── theme.py                  # Retro AoE2 dark visual style
│
├── translations/                 # 🌐 Internationalization (i18n) resources
│   ├── __init__.py
│   ├── i18n.py                   # Singleton i18n localization engine
│   ├── zh.yml                    # Simplified Chinese dictionary
│   └── en.yml                    # English dictionary
│
├── monitor/                      # 📊 Auxiliary Omniscient WebUI Monitor
│   ├── __init__.py
│   ├── server.py                 # Monitor HTTP server (binds 0.0.0.0:8088)
│   └── static/
│       └── index.html            # Holographic radar minimap & live property table
│
├── api/                          # 🌐 Network API Module (WebSocket / Raw TCP / UDP Beacon)
│   ├── __init__.py
│   ├── controller.py             # Core API dispatcher (pause/resume/is_success/report/etc.)
│   ├── tcp_server.py             # Raw TCP newline-delimited JSON server (default 8091)
│   ├── ws_server.py              # WebSocket JSON server (default 8090)
│   ├── udp_beacon.py             # UDP broadcast heartbeat & connectionless JSON (default 8092)
│   └── server.py                 # Unified server manager (APIServerManager)
│
├── tank_configs/                 # 🛡️ Tank and Fortress JSON Templates
│   ├── clearing_tank.json        # 🚜 Clearing tank (crushes normal brick walls)
│   ├── tower_radar.json          # 🗼 Radar outpost (high vision, unarmed)
│   ├── tower_cannon.json         # 🗼 Heavy defense cannon tower
│   ├── tower_supply.json         # 🗼 Ammo supply fortress
│   ├── player_tank.json          # Standard player tank
│   ├── enemy_basic.json          # Basic enemy tank
│   ├── enemy_fast.json           # Fast scout enemy tank
│   └── enemy_heavy.json          # Heavy armored enemy tank
│
├── conditions/                   # 🎯 Victory & Defeat condition evaluator (AST engine)
│   ├── __init__.py
│   ├── primitives.py             # Core condition primitives (survival time, destroyed, visible)
│   ├── composite.py              # Logical composite nodes (AndCondition/OrCondition/NotCondition)
│   └── builder.py                # Recursive JSON AST builder
├── grouping/                     # 🛡️ Unit grouping and selection management
├── command/                      # 📡 Command dispatch and tactical systems
├── ai/                           # 🤖 Tactical AI behaviors
├── gui/                          # 🖥️ Desktop PyQt5 GUI
├── webui/                        # 🌐 Web VNC client (port 8080)
├── map_loader/                   # 🗺️ Map JSON loader
├── maps/                         # 💾 Map definition files (JSON)
├── mission_loader/               # 📋 Mission JSON loader
├── missions/                     # 🎯 Mission scenarios (JSON)
├── physics/                      # ⚙️ Physics and kinematics engine (360° rotation/crushing)
└── tests/                        # 🧪 Test suite and client utilities
    ├── __init__.py
    ├── cli_client.py             # 💻 Interactive TCP CLI console client
    ├── test_conditions.py        # Automated test suite for conditions
    └── test_api.py               # Automated end-to-end API and socket tests
```

> 📖 **For dedicated network API documentation, see**: [api/README.md](file:///Users/xianzhizeng/Documents/projects/tanks_tactic/api/README.md)

---

## 🌐 Ports & Multi-Endpoint Matrix

When executing `python3 tanks.py`, the following services are initialized:

| Service | Address & Port | Mode & Purpose |
| :--- | :--- | :--- |
| **Tactical Monitor (Auxiliary WebUI)** | **`http://0.0.0.0:8088`** | **Always online, read-only**. God-view telemetry, pierces fog-of-war, live unit inspection. |
| **Operator Web VNC (via `--web`)** | **`http://localhost:8080`** | **Interactive control**. In-browser RTS marquee selection, right-click orders, and micro driving. |
| **WebSocket Network API** | **`ws://0.0.0.0:8090`** | **Bidirectional JSON API** for automated control, pause/resume, orders, and telemetry queries. |
| **Raw TCP/IP Network API** | **`tcp://0.0.0.0:8091`** | **Newline-delimited JSON protocol**, compatible with socket/netcat from any language. |
| **UDP Beacon & Connectionless API**| **`udp://0.0.0.0:8092`** | **Heartbeat broadcast ('I am here')**, network service discovery, and one-shot request-response. |
| **Desktop GUI Window (Default)** | Native PyQt5 Window | **Native desktop application** with full arcade response feel. |

---

## 🚀 Startup & Execution Guide

### 1. Launching the Game

#### Option A: Native Desktop GUI + Auxiliary Telemetry WebUI (Default)
```bash
python3 tanks.py
# Or via global CLI script:
tanks-game
```
- The desktop game window opens immediately.
- Open **`http://localhost:8088`** in any browser (or LAN IP) to view the **God-View Tactical Monitor**!

#### Option B: Headless Web VNC Mode (Remote Operator + Auxiliary Monitor)
```bash
python3 tanks.py --web
```
- Visit **`http://localhost:8080`**: Operator client for interactive tactical play.
- Visit **`http://localhost:8088`**: Observer client for secondary-screen telemetry and analysis.

#### Option C: Customizing Telemetry Host and Port
```bash
python3 tanks.py --monitor-host 0.0.0.0 --monitor-port 9999
```

---

### 2. Launching the Scenario & Map Editor

```bash
python3 editor.py
# Or as a module:
python3 -m editor.main
# Or via global CLI script:
tanks-editor
```

The Editor provides three integrated workflow tabs:
1. **Mode 1: Map Editor**
   - Palette toolbar to pick terrain types: Empty, Red Brick, Steel Wall, Water, Bush/Grass, Ice.
   - Status bar reports live cursor coordinates: **Tile (grid coordinates) and Pixel (absolute coordinates)**.
   - **Controls**:
     - Left-click: Paint selected terrain brush.
     - Right-click: Clear tile back to empty ground.
     - Click-and-drag: **Marquee box-fill** entire rectangular regions upon release.
   - Dynamic map dimensions (default 26×26); easily create new maps, load existing ones, and save to JSON.
2. **Mode 2: Mission & Unit Editor**
   - Create new missions or load existing missions and maps.
   - Visually place Blue (Player/Ally), Red (Enemy), and Tower entities on canvas.
   - Click units to **drag and reposition** freely, or press Delete / sidebar button to remove.
   - **Scrollable Property Inspector** allows real-time adjustment of:
     - Unit ID, Team (`player` / `enemy`), Unit template, Initial pixel position (X, Y).
     - Heading angle (0° to 360° via interactive slider and spinbox).
     - Max HP, Speed, Ammo capacity, Vision size (`vision_size`), Visibility (`visibility`).
     - Player controllability (`controllable`) and Brick crushing capability (`can_crush_bricks`).
3. **Mode 3: Victory & Defeat Condition Editor**
   - Age of Empires II-style hierarchical condition tree.
   - Freely add and nest logic composite nodes (**AND / OR / NOT**).
   - Insert evaluation primitives:
     - **Unit Survival Duration (`unit_survive_time`)**: Target unit ID and minimum survival seconds.
     - **Unit Destroyed (`unit_destroyed`)**: Target unit ID.
     - **Area Visible (`area_visible`)**: Target rectangular tile coordinates (X, Y, W, H).
     - **All Players Destroyed (`all_players_destroyed`)**.
   - Right-side panel features **bidirectional live JSON preview and syntax validation**, guaranteeing ready-to-run mission configs.

---

## 🎯 Victory & Defeat Condition Configuration

Inside `missions/*.json`, the `victory_conditions` and `defeat_conditions` sections define objective triggers. The engine evaluates recursive **AND**, **OR**, and **NOT** logical trees using core primitives:

1. **Unit Survival Time (`unit_survive_time`)**:
   - Fields: `unit_id` (string), `seconds` (float). Satisfied when the unit has survived for at least the specified duration.
2. **Unit Destroyed (`unit_destroyed`)**:
   - Fields: `unit_id` (string). Satisfied once the target unit is destroyed or dead.
3. **Area Visible (`area_visible`)**:
   - Fields: `tile_x, tile_y, tile_w, tile_h` (grid coordinates, 32px per tile) or `area: [x, y, w, h]` (pixel coordinates). Satisfied when any friendly line of sight overlaps the designated zone.
4. **All Players Destroyed (`all_players_destroyed`)**:
   - Satisfied when all player-controllable combat tanks are destroyed.

### Example Configuration (`missions/mission_01.json`):

```json
{
  "victory_conditions": {
    "or": [
      {
        "and": [
          {
            "type": "unit_survive_time",
            "unit_id": "core_supply_base",
            "seconds": 30.0
          },
          {
            "type": "area_visible",
            "tile_x": 0,
            "tile_y": 0,
            "tile_w": 4,
            "tile_h": 4
          }
        ]
      },
      {
        "and": [
          {
            "type": "unit_destroyed",
            "unit_id": "e_hunter_1"
          },
          {
            "type": "unit_destroyed",
            "unit_id": "e_fast_1"
          },
          {
            "not": {
              "type": "unit_destroyed",
              "unit_id": "player_alpha"
            }
          }
        ]
      }
    ]
  },
  "defeat_conditions": {
    "or": [
      {
        "type": "unit_destroyed",
        "unit_id": "core_supply_base"
      },
      {
        "type": "all_players_destroyed"
      }
    ]
  }
}
```

---

## 🔌 Plaintext JSON Network API (`api/`)

The game exposes three network endpoints communicating via **plaintext JSON**:
- **WebSocket**: `ws://0.0.0.0:8090`
- **Raw TCP/IP**: `tcp://0.0.0.0:8091` (Newline `\n` delimited JSON strings)
- **UDP Beacon**: `udp://0.0.0.0:8092`
  - Broadcasts on startup: `{"service":"tanks_tactic_api","status":"online","message":"I am here",...}`.
  - Also accepts connectionless one-shot JSON requests and returns responses.

### Core Endpoints:

#### 1. `api.pause` and `api.resume`
- **Function**: Pause or resume the physics and simulation loop.
  - **Initial State**: The engine starts in **PAUSED** mode to allow external controllers or players to inspect the map and queue initial orders. Call `api.resume` or press **P** to unpause.
  - **Command Pre-deployment**: Movement (`move`) and combat (`attack`/`fire`) APIs are fully accepted while paused; queued orders execute instantly when unpaused.
- **Request**:
  ```json
  {"action": "api.pause"}
  ```
- **Response**: `{"status": "ok", "paused": true, "message": "Engine paused"}`

#### 2. `api.is_success`
- **Function**: Evaluates current victory and defeat conditions.
- **Request**:
  ```json
  {"action": "api.is_success"}
  ```
- **Response**:
  ```json
  {
    "status": "ok",
    "is_success": true,
    "game_over": false,
    "victory_desc": "((Unit [core_supply_base] survived > 30.0s AND ...))"
  }
  ```

#### 3. `api.terminate` and `api.restart`
- **Function**:
  - `api.terminate`: Shuts down physics loop, closes network sockets, and exits the application.
  - `api.restart`: Resets game state, reloads map and spawn configurations, and restarts simulation.
- **Request**:
  ```json
  {"action": "api.terminate"}
  {"action": "api.restart"}
  ```

#### 4. `api.list_current_unit_id` and `api.list_enemy_curr`
- **Function**:
  - `api.list_current_unit_id`: Returns comma-separated IDs of all living friendly units (including uncontrollable friendly units).
  - `api.list_enemy_curr`: Returns comma-separated IDs of currently living enemies:
    - **God-Mode (`god_mode: true`)**: Pierces fog to return all living enemy IDs.
    - **Vision Mode (`god_mode: false`)**: Aggregates sight from all friendly units and applies unit `visibility` probability.
- **Request**:
  ```json
  {"action": "api.list_current_unit_id"}
  {"action": "api.list_enemy_curr", "god_mode": false}
  ```
- **Response**:
  ```json
  {
    "status": "ok",
    "unit_ids": "e_patrol_1,e_fast_1",
    "count": 2,
    "mode": "vision",
    "total_enemies": 3
  }
  ```

#### 5. `api.list_enemy_mem` and `api.report_enemy` (Global Memory System)
- **Memory Rules**:
  - Once an enemy is detected (sight overlap + visibility test passed), it is logged into the memory registry.
  - While visible, coordinates update continuously (`is_tracking = true`).
  - When tracking is lost (`is_tracking = false`), a red dashed box marks its last known location on the GUI.
  - **Confirmed Kill Rule**: An enemy is removed from memory **only when its destruction is witnessed by a friendly unit**.
- **`api.list_enemy_mem`**: Returns all unit IDs currently stored in memory.
- **`api.report_enemy`**: Reports last known coordinates and unit type. **Safety rule: Enemy HP, ammo, and speed are never leaked**.
- **Request**:
  ```json
  {"action": "api.list_enemy_mem"}
  {"action": "api.report_enemy", "unit_id": "e_fast_1"}
  ```
- **Response**:
  ```json
  {
    "status": "ok",
    "report": {
      "id": "e_fast_1",
      "unit_type": "Enemy Fast Tank",
      "last_x": 384.0,
      "last_y": 192.0,
      "is_tracking": false,
      "last_seen_time": 1730349120.45
    }
  }
  ```

#### 6. `api.command_move` / `attack` / `set_tactic` / `set_guard`
- **Function**: Dispatches orders to specific units by `unit_ids`.
  - **Uncontrollable Friend Protection**: Orders sent to `controllable=false` units return `status: ok` without executing, ensuring autonomous AI scripting is undisturbed.
- **Batch Move**:
  ```json
  {"action": "api.command_move", "unit_ids": "player_alpha,player_bravo", "x": 200, "y": 300}
  ```
- **Focus Fire Attack**:
  ```json
  {"action": "api.command_attack", "unit_ids": ["player_alpha"], "target_id": "e_hunter_1"}
  ```
- **Set Tactical Stance**:
  ```json
  {"action": "api.command_set_tactic", "unit_ids": "player_alpha", "tactic": "defensive"}
  ```
- **Escort / Guard Unit**:
  ```json
  {"action": "api.command_set_guard", "unit_ids": "player_alpha", "target_id": "core_supply_base"}
  ```

#### 7. `api.report`
- **Function**: Retrieves comprehensive telemetry for a specified friendly `unit_id`.
- **Request**:
  ```json
  {"action": "api.report", "unit_id": "player_alpha"}
  ```
- **Response**:
  ```json
  {
    "status": "ok",
    "report": {
      "id": "player_alpha",
      "alive": true,
      "tactic": "guard_unit",
      "ammo": 20,
      "max_ammo": 20,
      "speed": 3.0,
      "hp": 2,
      "max_hp": 2,
      "x": 224.0,
      "y": 448.0,
      "direction": "UP",
      "angle": 270.0,
      "visibility": 1.0,
      "vision_size": 260.0,
      "is_tower": false,
      "auto_clear": false,
      "can_crush_bricks": false
    }
  }
  ```

---

## 🎮 Operator Hotkeys & Controls

| Key / Mouse Action | Description |
| :--- | :--- |
| **`Left Mouse Drag`** | RTS Marquee box selection of combat tanks |
| **`Right Mouse on Ground`** | Move selected units to target in formation |
| **`Right Mouse on Friendly/Tower`** | **Selected units execute [Escort and Guard this Unit]** |
| **`Right Mouse on Enemy`** | Focus fire and engage target |
| **`Tab` Key** | Cycle active micro-control tank (marked with golden `[▼MICRO]`) |
| **`B` Key** | Toggle [Auto-Breaching (Bulldozer)] mode |
| **`Arrow Keys / WASD`** | Directly steer the active micro tank (360° smooth turning) |
| **`Spacebar`** | Fire main cannon (consumes ammo) |
| **`1` / `2` / `3`** | Switch tactical stance (`1` Free Combat / `2` Hold Ground / `3` Escort Target) |
| **`P` Key** | Pause / Resume physics and game simulation |
| **`S` / `R`** | `S` Halt in place / `R` Restart scenario |
