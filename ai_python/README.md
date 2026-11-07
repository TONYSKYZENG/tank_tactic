# 🧠 Tanks Tactic — AI Python Scripting Subsystem & Developer Guide

Welcome to the **`ai_python`** scripting subsystem for the Tanks Tactic game engine!

This subsystem allows developers to write **fully autonomous, asynchronous tactical scripts** and **high-level AI commanders** in standard Python 3. Scripts can be attached to any unit (friendly or enemy) to control micro maneuvers, manage economy and production, orchestrate multi-tank squads, or script dynamic battlefield events.

---

## 🏗️ Architecture & Core Principles

```
┌────────────────────────────────────────────────────────┐
│               Tanks Tactic Game Engine                 │
│  (PyQt5 / Headless Runner / PhysicsEngine / AI Thread) │
└──────────────────────────┬─────────────────────────────┘
                           │ (Direct in-memory / JSON RPC)
                           ▼
             ┌───────────────────────────┐
             │    GameAPIController      │
             └─────────────┬─────────────┘
                           │ RLock Thread-Safety
                           ▼
             ┌───────────────────────────┐
             │      TankScriptAPI        │  (ai_python/bridge.py)
             └─────────────┬─────────────┘
                           │ Injected instance: `api`
       ┌───────────────────┴───────────────────┐
       ▼                                       ▼
┌───────────────────────┐             ┌───────────────────────┐
│ Worker Thread 1       │             │ Worker Thread 2       │
│ (commander_novice.py) │             │ (grizzly_spawner.py)  │
└───────────────────────┘             └───────────────────────┘
```

1. **Decoupled Thread Architecture**:
   Every AI script executes in its own dedicated background worker thread managed by [`AIScriptManager`](file:///Volumes/data/projects/tank_tactic/ai_python/manager.py). It interacts with the simulation solely via an injected [`TankScriptAPI`](file:///Volumes/data/projects/tank_tactic/ai_python/bridge.py) instance.
2. **Omniscient Telemetry (God-Mode Awareness)**:
   AI scripts are granted full situational awareness. Calls such as `api.get_opponents()` and `api.report()` bypass fog-of-war and camouflage, enabling precise strategic decision-making.
3. **Transparent Pause & Resume Synchronization**:
   When the game is paused (via keypress `P` or network API), `AIScriptManager` automatically freezes all script threads. `api.sleep()` seamlessly suspends and resumes without race conditions or CPU spin-locks.
4. **Resilient Exception Isolation**:
   If an AI script throws an unhandled exception, it is caught and logged under `AI.<tank_id>`. The rest of the game engine continues running without disruption.

---

## 🚀 Quick Start: How to Attach and Run a Script

### Method 1: In Mission Configuration JSON
Specify the relative path in the unit's definition:
```json
{
  "id": "enemy_commander",
  "config_file": "tank_configs/mcv_tank.json",
  "spawn": { "x": 10, "y": 2 },
  "ai_script": "ai_python/commander_intermediate.py"
}
```

### Method 2: In the Built-in Editor (`editor/mission_editor.py`)
In the **Mission & Units Editor (Mode 2)**, select any unit, scroll down to **"★ 战术与自动化控制 (Tactics)"**, and enter the script path (e.g., `ai_python/grizzly_spawner.py`) into the **AI Script** text box.

### Method 3: Dynamically Spawn from Another Script or API
You can dynamically create new armored units with custom AI scripts attached at runtime:
```python
api.create_unit(
    camp="enemy",
    x=400.0,
    y=120.0,
    config_file="enemy_heavy",
    unit_id="boss_vanguard",
    ai_script="ai_python/boss_hunter.py"
)
```

---

## 📝 Writing Your First Tactical AI Script

Create a new file in `ai_python/`, for example `ai_python/my_patrol_bot.py`. The engine looks for a top-level `run(api)` function:

```python
"""
my_patrol_bot.py - Simple scout and intercept script
"""

def run(api):
    logger.info("Bot initialized for host tank: %s", api.tank_id)
    
    # 1. Fetch map boundaries
    mission_info = api.get_mission_info()
    max_x = mission_info.get("max_x", 720.0)
    max_y = mission_info.get("max_y", 576.0)

    patrol_points = [(100.0, 100.0), (max_x - 100.0, 100.0), (max_x - 100.0, max_y - 100.0), (100.0, max_y - 100.0)]
    wp_idx = 0

    # 2. Main operational loop (always check api.should_stop())
    while not api.should_stop():
        me = api.get_status()
        if not me or not me.get("alive", False):
            break

        opponents = api.get_opponents()
        
        # Check for close threats (< 200 pixels)
        target = None
        for opp in opponents:
            dist = math.hypot(opp["x"] - me["x"], opp["y"] - me["y"])
            if dist < 200.0:
                target = opp
                break

        if target:
            # Engage hostile target
            api.attack(target["id"])
            api.fire()
        else:
            # Continue patrol route
            dest_x, dest_y = patrol_points[wp_idx]
            api.move(dest_x, dest_y)
            if math.hypot(dest_x - me["x"], dest_y - me["y"]) < 30.0:
                wp_idx = (wp_idx + 1) % len(patrol_points)

        # Pause-aware sleep (avoids CPU spin-locks)
        api.sleep(0.5)
```

---

## 📚 Complete `TankScriptAPI` Reference

All methods below are available via the `api` parameter passed into `run(api)`.

### 1. Telemetry & Situational Awareness
| Method | Description |
| :--- | :--- |
| `api.tank_id` | String ID of the tank hosting this script. |
| `api.get_status()` | Returns host status dictionary (`x`, `y`, `health`, `ammo`, `speed`, `alive`, `angle`, `is_converting`, etc.). |
| `api.report(unit_id=None)` | Telemetry report of any unit on the field (defaults to host). |
| `api.get_opponents()` | List of dictionaries for all living enemy units. |
| `api.get_allies()` | List of dictionaries for all living friendly allied units. |
| `api.get_mission_info()` | Mission briefing narrative, map grid size (`cols`, `rows`), tile size, and pixel limits (`max_x`, `max_y`). |
| `api.get_game_time()` | Active engine simulation runtime dictionary (`game_time_ms`, `game_time_sec`, `is_paused`). |
| `api.get_time_ms()` | Integer milliseconds of active engine simulation runtime (strictly frozen during pause). |
| `api.is_game_success()` | Returns boolean whether current mission has achieved victory. |

### 2. Tactical Movement & Combat
| Method | Description |
| :--- | :--- |
| `api.move(x, y, unit_ids=None)` | Commands host (or squad `unit_ids`) to pathfind to `(x, y)`. |
| `api.attack(target_id, unit_ids=None)` | Commands units to focus-fire on `target_id`. |
| `api.attack_ground(x, y, unit_ids=None)` | Commands AoE units (`splash_radius > 0`) to bombard ground position `(x, y)`. |
| `api.force_attack_ground(x, y, unit_ids=None)` | Alias for `attack_ground(x, y)`. |
| `api.attack_tile(col, row, unit_ids=None)` | Commands AoE units to bombard grid tile cell `(col, row)`. |
| `api.fire(direction=None, unit_ids=None)` | Orders cannon fire in a cardinal direction or current facing. |
| `api.set_tactic(tactic, guard_target_id=None, unit_ids=None)` | Sets squad tactic (`"patrol"`, `"aggressive"`, `"defensive"`, `"hunter"`, `"stop"`). |
| `api.set_guard(target_id, unit_ids=None)` | Sets bodyguard escort orders protecting `target_id`. |
| `api.find_path(x, y)` | Computes A* any-angle waypoint route and ammo breach cost. |

### 3. Economy, Harvesting & Conversion
| Method | Description |
| :--- | :--- |
| `api.get_resources()` | Returns current resource stockpiles (`dark_matter`, `alloy`, etc.) and income rates. |
| `api.get_resource_blocks()` | Returns all resource deposit blocks, coordinates, remaining reserves, and exclusivity radii. |
| `api.harvest(col, row, unit_id=None)` | Dispatches unit to mine resource block at tile `(col, row)`. |
| `api.harvest_nearest(resource_type=None)` | Convenience helper: finds nearest unoccupied node with resources and starts mining. |
| `api.stop_harvest(unit_id=None)` | Stops mining operations. |
| `api.list_converter()` | Lists all available converter/factory recipe IDs. |
| `api.show_converter(converter_id)` | Returns inputs, costs, build time, and outputs for a recipe. |
| `api.convert(recipe_id, count=1)` | Queues conversion or unit production. |
| `api.terminate_convert()` | Cancels active conversion and clears queue. |

### 4. Dynamic Battlefield Manipulation (God-Mode Intervention)
| Method | Description |
| :--- | :--- |
| `api.edit_attr(unit_ids, attr, value)` | Dynamically modifies attributes (e.g. `speed`, `health`, `ammo`, `controllable`) with auto-type conversion. |
| `api.set_resources(camp="both", resources=None, **kwargs)` | Sets global resource reserves for `"both"`, `"player"`, or `"enemy"`. |
| `api.create_unit(camp="player", x=0, y=0, config_file=None, unit_id=None, **kwargs)` | Dynamically spawns new armored vehicles or towers onto the battlefield. |

### 5. Loop Control & Sleep
| Method | Description |
| :--- | :--- |
| `api.should_stop()` | Returns `True` when the engine is shutting down or the unit has died. |
| `api.sleep(seconds)` | **Crucial**: Pause-aware sleep that freezes during game pause and awakens immediately on unpause. |
| `api.wait_if_paused()` | Explicitly blocks worker thread if simulation is currently paused. |

---

## 💡 Practical AI Design Patterns

### Pattern A: Periodic Reinforcement Spawner
See [`ai_python/grizzly_spawner.py`](file:///Volumes/data/projects/tank_tactic/ai_python/grizzly_spawner.py):
Uses `api.get_time_ms()` to accurately track active simulation elapsed time (freezing during pauses) and calls `api.create_unit()` every 10 seconds.

### Pattern B: Strategic Macro Commander
See [`ai_python/commander_intermediate.py`](file:///Volumes/data/projects/tank_tactic/ai_python/commander_intermediate.py) or [`commander_ruthless.py`](file:///Volumes/data/projects/tank_tactic/ai_python/commander_ruthless.py):
- Monitors resource inflow.
- Balances harvesting vs combat unit production (`api.convert("recipe_build_tank")`).
- Forms attack squads and dispatches offensive strikes once critical mass is reached.

### Pattern C: Escort Bodyguard
See [`ai_python/ally_escort.py`](file:///Volumes/data/projects/tank_tactic/ai_python/ally_escort.py):
- Locates VIP unit (e.g., MCV or Harvester).
- Maintains escort distance and switches to focus-fire whenever the VIP is attacked.

---

## 🛠️ Best Practices & Debugging Tips

1. **Always use `api.sleep(duration)`**: Never use Python's built-in `time.sleep()`. Python's native sleep does not respect the engine's pause state, causing time desyncs.
2. **Always check `api.should_stop()`**: Ensure your main loop checks `not api.should_stop()` so thread cleanup occurs cleanly upon game reset or quit.
3. **Use the injected `logger`**: The execution context automatically injects a pre-configured `logger`. Messages logged with `logger.info(...)` appear with formatted timestamps and the tank's ID in the console.
4. **Pre-imported Globals**: The execution namespace automatically imports `math`, `random`, `time`, and `logger`.
