# 🕹️ Battle City Pixel (小霸王像素风坦克大战)

基于 **Python 3** 与 **PyQt5** 开发的经典老式小霸王（FC）像素风平面方块坦克大战。

本项目采用高内聚、低耦合的模块化架构设计，将 **GUI 界面渲染**、**纯地图存档**、**任务编排**、**物理引擎**、**战车配置** 与 **敌军战术 AI** 严格隔离至独立文件夹，非常便于二次开发与战术算法扩展。

---

## 🌟 核心特色

- **品字形方块像素风**：
  - **战车造型**：由 3 个像素正方形拼成经典“品”字形（前端突出 1 块为主炮塔，后端 2 块为底座履带），随行进方向自动旋转，前端带有黑色炮口与立体像素高光。
  - **炮弹造型**：采用微型“品”字形正方形组，随射击方向飞行。
- **纯地图与任务分离**：
  - `maps/` 仅保存纯粹地形（红砖墙、白铁墙、基地大本营尺寸网格），不包含任何动态实体。
  - `missions/` 定义关卡任务，配置引用的地图、玩家出生点、各敌军出生点、分配的战车类型及 AI 战术行为。
- **模块化敌军战术 AI (`ai/`)**：
  - `patrol`（巡逻漫游）：保持稳定步长巡逻，智能侧向避障，防抖防抽搐，随机压制开火。
  - `charge_base`（突袭基地）：以地图下方基地大本营为目标突进，遇到砖墙自动开炮强行破路。
  - `hunter`（视线追猎）：锁定玩家位置，水平/垂直轴线视线对齐时果断转向并持续开火。
- **硬核物理与操控体验**：
  - **转向辅助对齐 (Turn Alignment)**：经典 FC 手感，在拐入窄道时自动吸附对齐网格，避免卡角抽搐。
  - **安全出生点检测**：自动纠偏出生点，杜绝坦克出生在墙体内。
  - **经典弹道碰撞**：双方炮弹相撞互相抵消，炮弹可击毁砖墙与基地，被铁墙阻挡。

---

## 📂 项目结构

```text
tanks_tactic/
├── tanks.py                      # 🚀 顶层游戏启动入口
├── README.md                     # 📖 项目工程说明文档
│
├── ai/                           # 🤖 敌军战术行为模块
│   ├── __init__.py
│   ├── tactics.py                # 战术行为实现 (Patrol, ChargeBase, Hunter)
│   └── controller.py             # 敌军 AI 统一生命周期调度器
│
├── gui/                          # 🖥️ PyQt5 图形界面与像素渲染
│   ├── __init__.py
│   ├── renderer.py               # 方块像素渲染 (品字形坦克、品字形炮弹、砖/铁瓦片)
│   ├── game_widget.py            # 游戏主画布、键盘输入捕获与主循环刷新
│   └── main_window.py            # 主窗口容器与复古 HUD 仪表盘 (生命值、残敌数、战局状态)
│
├── map_loader/                   # 🗺️ 地图数据加载模块
│   ├── __init__.py
│   ├── models.py                 # 地图网格模型与瓦片枚举 (EMPTY, BRICK, STEEL, BASE)
│   └── loader.py                 # 地图 JSON 文件加载与保存
│
├── maps/                         # 💾 纯地图存档文件夹 (JSON)
│   └── level_01.json             # 关卡瓦片二维矩阵 (20×16 网格)
│
├── mission_loader/               # 📋 任务编排加载模块
│   ├── __init__.py
│   ├── models.py                 # 任务数据模型 (Mission, SpawnPoint 等)
│   └── loader.py                 # 任务 JSON 解析器
│
├── missions/                     # 🎯 任务存档文件夹 (JSON)
│   └── mission_01.json           # 任务配置 (玩家出生点、各敌军初始坐标与战术行为)
│
├── physics/                      # ⚙️ 物理与碰撞引擎
│   ├── __init__.py
│   ├── entities.py               # 实体类 (Tank, Bullet, Direction, Camp, Rect)
│   └── engine.py                 # AABB 碰撞检测、网格吸附、伤害判定与子弹销毁
│
└── tank_configs/                 # 🛡️ 战车属性配置文件夹 (JSON)
    ├── __init__.py
    ├── config_loader.py          # 战车配置解析器 (TankConfig)
    ├── player_tank.json          # 玩家经典黄色品字坦克
    ├── enemy_basic.json          # 基础银灰品字坦克
    ├── enemy_fast.json           # 红色突击轻坦 (速度极快)
    └── enemy_heavy.json          # 绿色重装装甲坦克 (高血量)
```

---

## 🎮 快速开始

### 1. 环境依赖

确保已安装 **Python 3.8+** 以及 **PyQt5**：

```bash
pip install PyQt5
```

### 2. 运行游戏

在项目根目录下直接运行顶层入口：

```bash
python3 tanks.py
```

### 3. 操作方式

| 按键 | 功能说明 |
| :--- | :--- |
| **`↑` / `↓` / `←` / `→`** | 控制玩家品字形坦克朝对应方向移动并对齐网格 |
| **`W` / `S` / `A` / `D`** | 备用移动控制按键 |
| **`空格键 (Space)`** | 发射品字形炮弹 |

---

## 🛠️ 配置格式详解

### 1. 战车配置 (`tank_configs/*.json`)

控制坦克的运动与开火物理属性：

```json
{
  "name": "Classic Tank",
  "speed": 3.0,              // 坦克移动速度 (像素/帧)
  "size": 36,                // 坦克外接正方形大小
  "color": "#E69C24",        // 品字形方块主色调
  "track_color": "#4A6B2F",  // 履带附色
  "bullet_speed": 6.0,       // 炮弹飞行速度
  "bullet_size": 12,         // 品字形炮弹尺寸
  "bullet_color": "#FFFFFF", // 炮弹颜色
  "fire_cooldown": 15,       // 开火冷却帧数 (~60 FPS 下 15 帧约 0.25 秒)
  "health": 3                // 生命值
}
```

### 2. 纯地图配置 (`maps/*.json`)

纯粹的地形定义，数值含义：`0`: 空地, `1`: 红砖墙, `2`: 白铁墙, `9`: 鹰巢基地。

```json
{
  "name": "Battle City - Stage 1",
  "tile_size": 36,
  "cols": 20,
  "rows": 16,
  "grid": [
    [0, 0, 0, 0, 0, 0, 0, 0, ...],
    [0, 1, 1, 0, 1, 1, 0, 2, ...]
  ]
}
```

### 3. 任务定义 (`missions/*.json`)

将地图、玩家与敌军战术绑定在一起：

```json
{
  "name": "Mission 1: Defense of Eagle Base",
  "map_file": "maps/level_01.json",
  "player": {
    "config_file": "tank_configs/player_tank.json",
    "spawn": { "x": 6, "y": 14 }
  },
  "enemies": [
    {
      "id": "e_patrol_1",
      "config_file": "tank_configs/enemy_basic.json",
      "spawn": { "x": 0, "y": 0 },
      "tactic": "patrol"
    },
    {
      "id": "e_fast_1",
      "config_file": "tank_configs/enemy_fast.json",
      "spawn": { "x": 9, "y": 0 },
      "tactic": "charge_base"
    },
    {
      "id": "e_hunter_1",
      "config_file": "tank_configs/enemy_heavy.json",
      "spawn": { "x": 19, "y": 0 },
      "tactic": "hunter"
    }
  ]
}
```

---

## 🧩 扩展指南

### 如何新增自定义敌军战术行为？

1. 在 `ai/tactics.py` 中继承 `BaseTactic`：
   ```python
   class FlankTactic(BaseTactic):
       def decide(self, tank, physics_engine, game_map):
           # 返回 (Direction, should_fire: bool)
           return Direction.LEFT, True
   ```
2. 在 `ai/controller.py` 的 `TACTIC_REGISTRY` 中注册该策略名称：
   ```python
   TACTIC_REGISTRY["flank"] = FlankTactic
   ```
3. 在 `missions/*.json` 中的敌人 `tactic` 字段指定 `"flank"` 即可立即生效！
