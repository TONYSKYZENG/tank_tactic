# 🕹️ Battle City Pixel (小霸王像素风坦克大战)

基于 **Python 3** 与 **PyQt5** 开发的经典老式小霸王（FC）像素风平面方块坦克大战。

本项目结合了**《帝国时代》风格的 RTS 鼠标框选指挥与战术编组调度**、**FC 原汁原味的街机单车微操手感**、**智能“推土机”自动开路破拆战术**、**视线正方形机制与战争迷雾**、**三大防御塔要塞体系与弹药补给机制**，以及全新的 **【全知上帝视角战术监视器 (辅助只读 WebUI)】**。

---

## 🌟 核心特色

- **辅助只读全知 WebUI 监控器 (`monitor/`，永远在线)**：
  - **默认绑定 `0.0.0.0`，默认端口 `8088`（端口与 IP 均可命令行自由配置）**。
  - **只读不可操控 (Read-Only)**：无任何操控按键或点击交互，专门用于第二屏幕实时遥测、观战或数据监视。
  - **全知上帝视角 (无视战争迷雾)**：
    - **全息雷达地图**：透视整张地图瓦片、全部飞行炮弹、全部我方坦克与防御要塞（附带补给光环与视线框）。
    - **敌军全知透视**：无论敌军藏在迷雾多深处，都能实时透视其位置与移动，并清晰标记 `[已侦测]` 或 `[隐蔽]`。
    - **全量实时属性监视器 (Live Inspector)**：实时表格列出全部敌我单位的**绝对坐标 (X,Y)、当前生命值/上限槽、当前弹药数/上限、视野范围、辨识度 (visibility)、当前战术姿态与自动开路状态**。
- **防御塔体系与弹药补给机制 (`tank_configs/tower_*.json`)**：
  - 鹰巢基地全面重制，作为核心防御要塞实体部署，速度为 0（固定不可移动）。
  - **① 纯视野雷达哨所 (`tower_radar.json`)**：超大视野（`vision_size: 560`），穿透迷雾，无火炮。
  - **② 重型加农防御炮台 (`tower_cannon.json`)**：配备重型防卫火炮，自主拦截射程内的敌军。
  - **③ 弹药补给要塞 / 鹰巢重制版 (`tower_supply.json`)**：具备补给有效半径（`resupply_radius`），处于光环内的我方非满弹战车将自动持续补充弹药，头顶浮现绿色 `+AMMO`！
- **战术重构：“跟踪并保卫特定己方单位” (Guard / Escort Unit)**：
  - 快捷键 `3`，或**鼠标右键直接点击友军单位/防御要塞**，选中的战车将紧随被保护目标跟随掩护，遇敌主动拦截迎击，威胁解除后自动归位！
- **视线系统与战争迷雾 (Sight & Fog of War)**：
  - 正方形视界范围（`vision_size`，`-1` 为全图视野），迷雾外的敌军**绝对不可见，且无法被右键选中集火**。
  - **敌军辨识度系统 (`visibility`)**：在任务中指定（0.0 ~ 1.0），进入视线区后按概率侦测显形。
- **有限弹药系统 (Limited Ammo)**：
  - 每辆战车具备独立弹药上限（`-1` 为无限弹药），开火消耗弹药，弹药耗尽需返回补给防御塔光环内进行弹药补充。
- **可选推土机功能：坦克自动开路 (Auto-Breaching)**：
  - 按 `B` 键开关。开启时遇挡路红砖墙不绕道，直接主动开火炸穿捷径！
- **RTS 帝国时代集群指挥 (`command/` + `grouping/`)**：
  - 鼠标左键拉框框选部队；鼠标右键自动方阵编队移动或集火目标；按 `Tab` 键即时循环切换当前直接手动微操的战车（带有金色 `[▼MICRO]` 光标）。
- **双模运行架构（桌面 GUI / 浏览器 Web VNC）**：
  - 支持标准桌面視窗模式与纯后台无头 Web VNC 串流模式。

---

## 📂 项目结构

```text
tanks_tactic/
├── tanks.py                      # 🚀 顶层启动入口 (同时拉起主游戏与辅助监控 WebUI)
├── README.md                     # 📖 项目工程说明文档
├── .gitignore                    # 🙈 Git 忽略规则
│
├── monitor/                      # 📊 辅助只读全知监控 WebUI 模块 (新增)
│   ├── __init__.py
│   ├── server.py                 # 监视服务器 (绑定 0.0.0.0:8088，提供全知遥测 API)
│   └── static/
│       └── index.html            # 全息雷达上帝小地图与全量敌我属性表格
│
├── api/                          # 🌐 网络 API 模块 (WebSocket / Raw TCP / UDP 探针)
│   ├── __init__.py
│   ├── controller.py             # 核心 API 指令调度器 (pause/resume/is_success/report 等)
│   ├── tcp_server.py             # 原始 TCP/IP 纯文本 JSON 协议服务 (默认 8091)
│   ├── ws_server.py              # WebSocket 纯文本 JSON 协议服务 (默认 8090)
│   ├── udp_beacon.py             # UDP 心跳广播 ('我在这里') 与直接纯文本 JSON 响应 (默认 8092)
│   └── server.py                 # 统一 API 管理中枢 (APIServerManager)
│
├── tank_configs/                 # 🛡️ 战车与防御塔配置 (JSON)
│   ├── tower_radar.json          # 🗼 纯视野雷达哨所
│   ├── tower_cannon.json         # 🗼 重型加农防御炮台
│   ├── tower_supply.json         # 🗼 弹药补给要塞 / 鹰巢重制版
│   ├── player_tank.json          # 机动品字坦克
│   ├── enemy_basic.json          # 敌军基础坦克
│   ├── enemy_fast.json           # 敌军突击轻坦
│   └── enemy_heavy.json          # 敌军重装坦克
│
├── conditions/                   # 🎯 获胜与失败条件判定系统 (与或非组合逻辑/原语求值)
│   ├── __init__.py
│   ├── primitives.py             # 核心条件原语 (存活时间/单位被摧毁/区域可见)
│   ├── composite.py              # 逻辑组合节点 (AndCondition/OrCondition/NotCondition)
│   └── builder.py                # JSON 配置递归 AST 构建器
├── grouping/                     # 🛡️ 编组与选择管理模块 (单选/框选/Tab微操切换)
├── command/                      # 📡 指挥调度与战术系统 (GuardUnit 护卫/自动开路)
├── ai/                           # 🤖 敌军战术行为模块
├── gui/                          # 🖥️ 本地 PyQt5 桌面视窗界面
├── webui/                        # 🌐 可操控 Web VNC 模块 (端口 8080)
├── map_loader/                   # 🗺️ 地图加载模块
├── maps/                         # 💾 纯地图存档文件夹 (JSON)
├── mission_loader/               # 📋 任务加载模块
├── missions/                     # 🎯 任务存档文件夹 (JSON)
├── physics/                      # ⚙️ 物理引擎 (防御塔/弹药补给/视线迷雾)
└── tests/                        # 🧪 测试与客户端套件
    ├── __init__.py
    ├── cli_client.py             # 💻 交互式命令行控制台程序 (TCP/IP)
    ├── test_conditions.py        # 胜负条件系统自动化单元测试
    └── test_api.py               # 网络 API 与套接字端到端自动化测试
```

> 📖 **API 纯英文完整文档参见**：[api/README.md](file:///Users/xianzhizeng/Documents/projects/tanks_tactic/api/README.md)

---

## 🌐 端口与多端服务矩阵

启动 `python3 tanks.py` 时，系统将提供以下服务端口：

| 服务类型 | 默认地址与端口 | 性质与功能 |
| :--- | :--- | :--- |
| **全知战术监视器 (辅助 WebUI)** | **`http://0.0.0.0:8088`** | **永远在线、只读不可操控**。上帝视角透视全图、无视迷雾监控全部敌我单位全部位置与全部实时属性。 |
| **操作端 Web VNC (需加 `--web`)** | **`http://localhost:8080`** | **可交互操控**。浏览器端 RTS 鼠标拉框、右键指令与键盘直接微操驾驶。 |
| **WebSocket 网络 API** | **`ws://0.0.0.0:8090`** | **双向 JSON 文本 API**，可编程控制暂停、继续、指令下发、属性报告等。 |
| **Raw TCP/IP 原始网络 API** | **`tcp://0.0.0.0:8091`** | **纯文本换行 JSON 协议**，支持任何编程语言 socket/netcat 直连交互。 |
| **UDP 探针与无连接 API** | **`udp://0.0.0.0:8092`** | **上线广播 '我在这里'**，支持网络自动服务发现与单包无连接纯文本 JSON 请求。 |
| **本地桌面视窗 (默认模式)** | 本地 PyQt5 窗口 | **本地原生视窗**，直接在系统桌面以原生手感游玩。 |

---

## 🚀 启动与配置命令

### 1. 默认启动（本地桌面游戏 + 后台辅助全知监控 WebUI）

```bash
python3 tanks.py
```
终端将自动打印两个界面：
- 本地桌面弹出游戏窗口。
- 在任意设备浏览器打开 **`http://localhost:8088`**（或对应局域网 IP），即可进入**上帝视角全知监视器**！

---

### 2. 纯后台无头模式（操控端 Web VNC + 辅助全知监控 WebUI）

```bash
python3 tanks.py --web
```
- 打开 **`http://localhost:8080`**：操作端，玩家进行战斗操控。
- 打开 **`http://localhost:8088`**：观察端，副屏幕全知监视敌我全部战况与全量属性。

---

### 3. 自定义辅助监控端口与地址

```bash
python3 tanks.py --monitor-host 0.0.0.0 --monitor-port 9999
```
此时辅助监控将在 `http://0.0.0.0:9999` 启动。

---

## 🎯 任务获胜与失败条件配置（与或非组合逻辑）

在 `missions/*.json` 任务配置中，可以通过 `victory_conditions` 与 `defeat_conditions` 字段自由定义胜负判定规则。系统支持递归的 **与 (and)**、**或 (or)**、**非 (not)** 组合逻辑，并提供 3 个核心原语：

1. **特定单位存活超过特定时间 (`unit_survive_time`)**：
   - 字段：`unit_id`（目标单位 ID），`seconds`（存活累计秒数）。单位在达到指定累计存活时间且仍存活时满足。
2. **特定单位被摧毁 (`unit_destroyed`)**：
   - 字段：`unit_id`（目标单位 ID）。该单位死亡或已被消灭时满足。
3. **特定区域可见 (`area_visible`)**：
   - 字段：`tile_x, tile_y, tile_w, tile_h`（瓦片坐标与宽高，自动换算为 32px 网格）或 `area: [x, y, w, h]`（像素坐标矩形）。目标区域与我方单位视线相交或战场迷雾解除时满足。

### 示例配置 (`missions/mission_01.json`)：

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

## 🔌 纯文本 JSON 网络 API 调用规范 (`api/`)

游戏在启动时默认开启三合一网络 API 接口，所有协议均采用**纯文本 JSON** 进行交互：
- **WebSocket**: `ws://0.0.0.0:8090`
- **原始 TCP/IP**: `tcp://0.0.0.0:8091`（发送以 `\n` 分隔的 JSON 字符串）
- **UDP 探针与无连接 API**: `udp://0.0.0.0:8092`
  - 服务上线时将自动向局域网广播上线数据包：`{"service":"tanks_tactic_api","status":"online","message":"我在这里",...}`；
  - 同样支持直接向 UDP 端口发送纯文本 JSON 请求并接收 JSON 应答。

### 核心接口清单：

#### 1. `api.pause()` 与 `api.resume()`
- **功能**：暂停或恢复游戏物理与战术引擎的循环。
  - **默认启动状态**：游戏引擎默认启动后处于 **暂停 (PAUSED)** 状态，以便外部控制器或玩家进行初始战术侦察与指令部署；调用 `api.resume` 或在 GUI / Web 界面按下 **P** 键即可正式开始运转。
  - **暂停期指令预部署**：在暂停状态下允许执行所有的移动 (`move`) 与攻击/开火 (`attack`/`fire`) API。指令将进入就绪队列，在解除暂停瞬间立刻执行。
- **请求格式**：
  ```json
  {"action": "api.pause"}
  ```
- **响应**：`{"status": "ok", "paused": true, "message": "Engine paused"}`

#### 2. `api.is_success()`
- **功能**：判断当前战役是否达成任务中配置的获胜条件并返回。
- **请求格式**：
  ```json
  {"action": "api.is_success"}
  ```
- **响应**：
  ```json
  {
    "status": "ok",
    "is_success": true,
    "game_over": false,
    "victory_desc": "((单位 [core_supply_base] 存活超过 30.0s 且 ...))"
  }
  ```

#### 3. `api.terminate()` 与 `api.restart()`
- **功能**：
  - `api.terminate`：终结所有引擎、网络后台服务并退出应用；
  - `api.restart`：重置战局、重载地图与出生点、重新开始游戏模拟。
- **请求格式**：
  ```json
  {"action": "api.terminate"}
  {"action": "api.restart"}
  ```

#### 4. `api.list_current_unit_id` 与 `api.list_enemy_curr`
- **功能**：
  - `api.list_current_unit_id`：返回当前存活的所有己方单位 ID，以**逗号隔开**（包含不可控己方单位，不可控友军始终必然被列出）；
  - `api.list_enemy_curr`：列出当前存活的敌方单位 ID（以逗号隔开）：
    - **上帝视角模式 (`god_mode: true`)**：无视迷雾透视全图敌军；
    - **我方视野探测模式 (`god_mode: false`)**：仅汇总所有存活我方单位视线（可控与不可控单位全员共享视野），在视线范围内的敌军按其自身辨识度 `visibility` 概率加入列表。
- **请求格式**：
  ```json
  {"action": "api.list_current_unit_id"}
  {"action": "api.list_enemy_curr", "god_mode": false}
  ```
- **响应示例**：
  ```json
  {
    "status": "ok",
    "unit_ids": "e_patrol_1,e_fast_1",
    "count": 2,
    "mode": "vision",
    "total_enemies": 3
  }
  ```

#### 5. `api.list_enemy_mem` 与 `api.report_enemy` (全局敌军记忆系统)
- **记忆机制**：
  - 一旦敌军被我方实锤发现（视线重叠且辨识度判定成功），立即在全局记忆字典建档；
  - 敌军保持在视野内时持续更新最新坐标，`is_tracking` 为 `true`；
  - 敌军脱离视野（跟丢）时停止追踪（`is_tracking = false`），并**在 GUI 画面上以红色虚线方框标记其最后一次被发现的坐标**；
  - **目击消灭删除规则**：**只有当我方亲眼目睹该敌军被击毁时**，才将其从记忆字典中彻底清除。
- **`api.list_enemy_mem`**：只访问当前全局记忆，返回记忆中的敌方单位 ID 串（包含当前正在追踪的与跟丢的）。
- **`api.report_enemy`**：查询记忆体中的敌军状态。**严守安全规则：敌方单位的 HP、速度、弹药等属性永远不可见**，仅报告最后发现坐标与单位类型。
- **请求示例**：
  ```json
  {"action": "api.list_enemy_mem"}
  {"action": "api.report_enemy", "unit_id": "e_fast_1"}
  ```
- **响应示例**：
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
- **功能**：按照指定 `unit_ids` 批量对己方单位下发控制指令。
  - **不可控友军保护机制**：对于不可控己方单位（`controllable=false`），外部尝试命令它们时不会报错（返回 `status: ok`），但指令本身不会被执行，确保这些单位完全受其预定的 AI 战术脚本自主调度。
- **批量移动**：
  ```json
  {"action": "api.command_move", "unit_ids": "player_alpha,player_bravo", "x": 200, "y": 300}
  ```
- **批量集火攻击**：
  ```json
  {"action": "api.command_attack", "unit_ids": ["player_alpha"], "target_id": "e_hunter_1"}
  ```
- **批量设置战术**：
  ```json
  {"action": "api.command_set_tactic", "unit_ids": "player_alpha", "tactic": "defensive"}
  ```
- **批量护卫指定己方单位**：
  ```json
  {"action": "api.command_set_guard", "unit_ids": "player_alpha", "target_id": "core_supply_base"}
  ```

#### 7. `api.report`
- **功能**：令指定 `unit_id` 的己方单位汇报所有属性（战术、弹药、速度、HP、位置等）。
- **请求格式**：
  ```json
  {"action": "api.report", "unit_id": "player_alpha"}
  ```
- **响应**：
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
      "visibility": 1.0,
      "vision_size": 260.0,
      "is_tower": false,
      "auto_clear": false
    }
  }
  ```

---

## 🎮 操作端快捷键指引

| 按键 / 鼠标 | 功能说明 |
| :--- | :--- |
| **`鼠标左键拖拽`** | 帝国时代拉框批量选中单位 |
| **`鼠标右键点击地面`** | 选中的战车方阵排布编队移动 |
| **`鼠标右键点击友军/要塞`** | **选中的战车执行【跟踪并保卫该己方单位】** |
| **`鼠标右键点击敌军`** | 集火锁定攻击该敌军 |
| **`Tab` 键** | 循环切换当前直接微操的战车（带有金色 `[▼MICRO]` 标记） |
| **`B` 键** | 批量开关【自动开路 (Auto-Breaching)】功能 |
| **`方向键 / WASD`** | 直接手动驾驶当前微操战车 |
| **`空格键 (Space)`** | 微操战车开火（消耗弹药） |
| **`1` / `2` / `3`** | 切换战术姿态 (`1` 自由交战 / `2` 坚守阵地 / `3` 护卫特定己方单位) |
| **`S` / `R`** | `S` 就地待命 / `R` 重置战局 |
