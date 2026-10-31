from pathlib import Path
from typing import Set, Dict, Optional, Tuple, List
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QPointF

from map_loader.models import GameMap, TileType
from mission_loader.models import Mission
from translations import t
from tank_configs.config_loader import TankConfig
from physics.entities import Tank, Direction, Camp, Rect
from physics.engine import PhysicsEngine
from ai.controller import EnemyAIController
from grouping.selection import SelectionManager
from command.dispatcher import CommandDispatcher
from command.tactics_mode import TacticMode
from conditions import (
    ConditionContext,
    ConditionBuilder,
    AllEnemiesDestroyedCondition,
    AllPlayersDestroyedCondition,
    OrCondition,
    UnitDestroyedCondition
)
from ai_python.manager import AIScriptManager
from api.controller import GameAPIController
from .renderer import PixelRenderer

class GameCanvasWidget(QWidget):
    """
    游戏主画布：
    - RTS 帝国时代风格框选与右键命令
    - 战争迷雾系统：迷雾外敌军不可见且无法被选中或追踪
    - 视线正方形系统：各单位可调边长视线，-1 为全图挂
    - 有限弹药系统：支持有限发弹药与开火消耗
    - 辨识度系统：敌军在视线区内按 visibility 概率显形
    """

    status_updated = pyqtSignal(dict)

    def __init__(self, mission: Mission, game_map: GameMap, base_dir: Path, parent=None):
        super().__init__(parent)
        self.mission = mission
        self.game_map = game_map
        self.base_dir = base_dir

        self.setFixedSize(self.game_map.pixel_width, self.game_map.pixel_height)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        # 物理引擎 (传入迷雾与有限弹药开关)
        self.physics_engine = PhysicsEngine(
            self.game_map,
            fog_of_war_enabled=self.mission.fog_of_war,
            limited_ammo_enabled=self.mission.limited_ammo
        )

        # 敌军 AI 控制器
        self.ai_controller = EnemyAIController(self.physics_engine, self.game_map)

        # 编组管理器与命令调度器
        self.selection_mgr = SelectionManager()
        self.command_dispatcher = CommandDispatcher()

        # 初始化网络 API 控制器与外挂战术脚本管理器
        self.api_controller = GameAPIController(self)
        self.ai_script_manager = AIScriptManager()

        # 键盘与鼠标状态
        self.active_keys: Set[int] = set()
        self.is_dragging_box = False
        self.drag_start = QPointF(0, 0)
        self.drag_current = QPointF(0, 0)

        # 指令标记 (x, y, is_attack, life_frames)
        self.command_marker: Optional[Tuple[float, float, bool, int]] = None

        # 初始化玩家与敌军
        self._setup_mission_entities()

        # 启动外挂 Python 战术脚本线程
        all_tanks = self.physics_engine.player_tanks + self.physics_engine.enemy_tanks
        self.ai_script_manager.start_scripts(all_tanks, self.api_controller, self.base_dir)

        # 初始化胜负判定系统
        self._setup_conditions()

        if self.physics_engine.player_tanks:
            first_tank = self.physics_engine.player_tanks[0]
            self.selection_mgr.select_single(first_tank)

        self.game_over = False
        self.game_victory = False
        self.is_paused = True
        if hasattr(self, "ai_script_manager"):
            self.ai_script_manager.pause()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._game_loop)
        self.timer.start(16)

    def pause(self):
        self.is_paused = True
        if hasattr(self, "ai_script_manager"):
            self.ai_script_manager.pause()

    def resume(self):
        self.is_paused = False
        if hasattr(self, "ai_script_manager"):
            self.ai_script_manager.resume()
        if hasattr(self, "api_controller"):
            self.api_controller.flush_pending_actions()

    def _setup_conditions(self):
        self.condition_ctx = ConditionContext(self.physics_engine, self.game_map)

        # 获胜条件构建
        if self.mission.victory_conditions:
            self.victory_condition = ConditionBuilder.build(self.mission.victory_conditions)
        else:
            self.victory_condition = AllEnemiesDestroyedCondition()

        # 失败条件构建
        if self.mission.defeat_conditions:
            self.defeat_condition = ConditionBuilder.build(self.mission.defeat_conditions)
        else:
            defeat_subs = [AllPlayersDestroyedCondition()]
            for t in self.physics_engine.player_tanks:
                if t.is_tower and t.tower_type == "supply":
                    defeat_subs.append(UnitDestroyedCondition(t.id))
            self.defeat_condition = OrCondition(defeat_subs)

    def restart(self):
        if hasattr(self, "ai_script_manager"):
            self.ai_script_manager.stop_all()

        self.game_over = False
        self.game_victory = False
        self.is_paused = False
        self.active_keys.clear()
        self.is_dragging_box = False
        self.command_marker = None
        if hasattr(self, "api_controller"):
            self.api_controller.pending_actions.clear()
        self.physics_engine = PhysicsEngine(
            self.game_map,
            fog_of_war_enabled=self.mission.fog_of_war,
            limited_ammo_enabled=self.mission.limited_ammo
        )
        self.ai_controller = EnemyAIController(self.physics_engine, self.game_map)
        self.selection_mgr = SelectionManager()
        self.command_dispatcher = CommandDispatcher()
        self._setup_mission_entities()
        self._setup_conditions()

        if hasattr(self, "ai_script_manager") and hasattr(self, "api_controller"):
            all_tanks = self.physics_engine.player_tanks + self.physics_engine.enemy_tanks
            self.ai_script_manager.start_scripts(all_tanks, self.api_controller, self.base_dir)

        if self.physics_engine.player_tanks:
            self.selection_mgr.select_single(self.physics_engine.player_tanks[0])

    def stop(self):
        if hasattr(self, "ai_script_manager"):
            self.ai_script_manager.stop_all()
        if hasattr(self, "timer") and self.timer.isActive():
            self.timer.stop()

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)

    def _setup_mission_entities(self):
        tile_size = self.game_map.tile_size

        # 1. 我方编组坦克
        units_info = self.mission.player_units if self.mission.player_units else [self.mission.player]
        for p_info in units_info:
            cfg_path = self.base_dir / p_info.config_file
            cfg = TankConfig.from_json(cfg_path)

            req_x = p_info.spawn.x * tile_size
            req_y = p_info.spawn.y * tile_size
            sx, sy = self.physics_engine.find_nearest_free_position(req_x, req_y, cfg.size)

            tank = Tank(
                x=sx,
                y=sy,
                size=cfg.size,
                speed=cfg.speed,
                camp=Camp.PLAYER,
                color=cfg.color,
                health=cfg.health,
                tank_id=p_info.id,
                vision_size=p_info.vision_size,
                ammo=p_info.ammo,
                visibility=getattr(p_info, "visibility", 1.0),
                is_tower=cfg.is_tower,
                can_attack=cfg.can_attack,
                tower_type=cfg.tower_type,
                resupply_radius=cfg.resupply_radius,
                resupply_interval=cfg.resupply_interval,
                unit_type=cfg.name,
                controllable=getattr(p_info, "controllable", True),
                ai_script=getattr(p_info, "ai_script", None),
                can_crush_bricks=getattr(cfg, "can_crush_bricks", False),
                crush_speed_factor=getattr(cfg, "crush_speed_factor", 0.5)
            )
            tank.fire_cooldown_max = cfg.fire_cooldown
            tank._config = cfg
            self.physics_engine.add_player_tank(tank)
            self.command_dispatcher.register_tank(tank)

        # 2. 敌军坦克
        for enemy_info in self.mission.enemies:
            cfg_path = self.base_dir / enemy_info.config_file
            cfg = TankConfig.from_json(cfg_path)

            req_ex = enemy_info.spawn.x * tile_size
            req_ey = enemy_info.spawn.y * tile_size
            ex, ey = self.physics_engine.find_nearest_free_position(req_ex, req_ey, cfg.size)

            tank = Tank(
                x=ex,
                y=ey,
                size=cfg.size,
                speed=cfg.speed,
                camp=Camp.ENEMY,
                color=cfg.color,
                health=cfg.health,
                tank_id=enemy_info.id,
                vision_size=enemy_info.vision_size,
                ammo=enemy_info.ammo,
                visibility=enemy_info.visibility,
                is_tower=cfg.is_tower,
                can_attack=cfg.can_attack,
                tower_type=cfg.tower_type,
                resupply_radius=cfg.resupply_radius,
                resupply_interval=cfg.resupply_interval,
                unit_type=cfg.name,
                controllable=getattr(enemy_info, "controllable", False),
                ai_script=getattr(enemy_info, "ai_script", None),
                can_crush_bricks=getattr(cfg, "can_crush_bricks", False),
                crush_speed_factor=getattr(cfg, "crush_speed_factor", 0.5)
            )
            tank.fire_cooldown_max = cfg.fire_cooldown
            tank._config = cfg
            self.ai_controller.register_enemy(tank, cfg, enemy_info.tactic)

    # ================= 鼠标 RTS 框选与命令 =================

    def mousePressEvent(self, event):
        pos = event.pos()
        x, y = pos.x(), pos.y()

        if event.button() == Qt.LeftButton:
            self.is_dragging_box = True
            self.drag_start = QPointF(x, y)
            self.drag_current = QPointF(x, y)
        elif event.button() == Qt.RightButton:
            selected = self.selection_mgr.get_selected()
            if not selected:
                micro = self.selection_mgr.get_micro_tank()
                if micro and micro.alive:
                    selected = [micro]

            if selected:
                # 1. 检查是否右键点击到【己方单位】 -> 下达【跟踪并保卫该单位】指令
                target_friendly = None
                for ally in self.physics_engine.player_tanks:
                    if ally.alive and ally not in selected and ally.rect.collides_with(Rect(x - 6, y - 6, 12, 12)):
                        target_friendly = ally
                        break

                if target_friendly:
                    self.command_dispatcher.issue_guard_unit(selected, target_friendly)
                    self.command_marker = (target_friendly.x + target_friendly.size / 2.0,
                                           target_friendly.y + target_friendly.size / 2.0, False, 20)
                else:
                    # 2. 检查是否右键点击到【可见敌军】 -> 批量集火
                    target_enemy = None
                    for enemy in self.physics_engine.get_visible_enemies():
                        if enemy.alive and enemy.rect.collides_with(Rect(x - 6, y - 6, 12, 12)):
                            target_enemy = enemy
                            break

                    if target_enemy:
                        self.command_dispatcher.issue_attack_target(selected, target_enemy, self.physics_engine)
                        self.command_marker = (target_enemy.x + target_enemy.size / 2.0,
                                               target_enemy.y + target_enemy.size / 2.0, True, 20)
                    else:
                        # 3. 移动到该位置
                        self.command_dispatcher.issue_move(selected, x, y)
                        self.command_marker = (x, y, False, 20)

        event.accept()

    def mouseMoveEvent(self, event):
        if self.is_dragging_box:
            self.drag_current = QPointF(event.pos().x(), event.pos().y())
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_dragging_box:
            self.is_dragging_box = False
            self.drag_current = QPointF(event.pos().x(), event.pos().y())

            x1, y1 = self.drag_start.x(), self.drag_start.y()
            x2, y2 = self.drag_current.x(), self.drag_current.y()
            rw = abs(x2 - x1)
            rh = abs(y2 - y1)

            if rw < 6 and rh < 6:
                clicked_tank = None
                for tank in self.physics_engine.player_tanks:
                    if tank.alive and tank.rect.collides_with(Rect(x1 - 2, y1 - 2, 4, 4)):
                        clicked_tank = tank
                        break
                if clicked_tank:
                    self.selection_mgr.select_single(clicked_tank)
                else:
                    self.selection_mgr.clear_selection()
            else:
                rx = min(x1, x2)
                ry = min(y1, y2)
                box_rect = Rect(rx, ry, rw, rh)
                self.selection_mgr.select_box(box_rect, self.physics_engine.player_tanks)

        event.accept()

    # ================= 键盘操作与微操 =================

    def keyPressEvent(self, event):
        key = event.key()
        if not event.isAutoRepeat():
            self.active_keys.add(key)

            if key == Qt.Key_Tab:
                self.selection_mgr.cycle_micro_tank(self.physics_engine.player_tanks)
            elif key == Qt.Key_Space:
                self._fire_micro_tank()
            elif key in (Qt.Key_1, Qt.Key_Exclam):
                selected = self.selection_mgr.get_selected()
                self.command_dispatcher.issue_tactic(selected, TacticMode.AGGRESSIVE)
            elif key in (Qt.Key_2, Qt.Key_At):
                selected = self.selection_mgr.get_selected()
                self.command_dispatcher.issue_tactic(selected, TacticMode.DEFENSIVE)
            elif key in (Qt.Key_3, Qt.Key_NumberSign):
                selected = self.selection_mgr.get_selected()
                # 寻找核心补给要塞或微操目标作为护卫对象
                core_tower = None
                for t in self.physics_engine.player_tanks:
                    if t.alive and t.is_tower and t.tower_type == "supply":
                        core_tower = t
                        break
                guard_target = core_tower if core_tower else self.selection_mgr.get_micro_tank()
                self.command_dispatcher.issue_tactic(selected, TacticMode.GUARD_UNIT, guard_target=guard_target)
            elif key == Qt.Key_B:
                target_tanks = self.selection_mgr.get_selected()
                if not target_tanks:
                    micro = self.selection_mgr.get_micro_tank()
                    if micro and micro.alive:
                        target_tanks = [micro]
                if target_tanks:
                    self.command_dispatcher.toggle_auto_clear_path(target_tanks)
            elif key == Qt.Key_S:
                selected = self.selection_mgr.get_selected()
                self.command_dispatcher.issue_stop(selected)
            elif key == Qt.Key_P:
                if self.is_paused:
                    self.resume()
                else:
                    self.pause()
            elif key == Qt.Key_R:
                self.restart()

        event.accept()

    def keyReleaseEvent(self, event):
        if not event.isAutoRepeat():
            self.active_keys.discard(event.key())
        event.accept()

    def _fire_micro_tank(self):
        micro = self.selection_mgr.get_micro_tank()
        if micro and micro.alive:
            cfg = getattr(micro, "_config", None)
            b_speed = cfg.bullet_speed if cfg else 6.0
            b_size = cfg.bullet_size if cfg else 12
            b_color = cfg.bullet_color if cfg else "#FFFFFF"
            if self.is_paused:
                if hasattr(self, "api_controller"):
                    self.api_controller.pending_actions.append(
                        lambda: self.physics_engine.spawn_bullet(micro, b_speed, b_size, b_color)
                    )
                return
            self.physics_engine.spawn_bullet(micro, b_speed, b_size, b_color)

    def _process_micro_tank_input(self) -> bool:
        micro = self.selection_mgr.get_micro_tank()
        if not micro or not micro.alive:
            return False

        vx = 0.0
        vy = 0.0
        if Qt.Key_Up in self.active_keys or Qt.Key_W in self.active_keys:
            vy -= 1.0
        if Qt.Key_Down in self.active_keys or Qt.Key_S in self.active_keys:
            vy += 1.0
        if Qt.Key_Left in self.active_keys or Qt.Key_A in self.active_keys:
            vx -= 1.0
        if Qt.Key_Right in self.active_keys or Qt.Key_D in self.active_keys:
            vx += 1.0

        if abs(vx) > 1e-4 or abs(vy) > 1e-4:
            self.physics_engine.move_tank(micro, (vx, vy))
            return True
        return False

    def _check_game_status(self):
        # 核心要塞存活判定 (重制版鹰巢)
        core_tower = None
        for t in self.physics_engine.player_tanks:
            if t.is_tower and t.tower_type == "supply":
                core_tower = t
                break

        base_alive = True
        if core_tower is not None:
            base_alive = core_tower.alive

        alive_players = [t for t in self.physics_engine.player_tanks if t.alive]
        alive_enemies = [e for e in self.physics_engine.enemy_tanks if e.alive]
        visible_enemies = self.physics_engine.get_visible_enemies()

        # 基于条件树求值胜负逻辑
        if self.defeat_condition.evaluate(self.condition_ctx):
            self.game_over = True
        elif self.victory_condition.evaluate(self.condition_ctx):
            self.game_victory = True

        micro = self.selection_mgr.get_micro_tank()
        micro_tactic = self.command_dispatcher.get_tactic(micro) if micro else TacticMode.MANUAL_OR_IDLE
        micro_auto_clear = self.command_dispatcher.is_auto_clear_path(micro) if micro else False

        self.status_updated.emit({
            "alive_players": len(alive_players),
            "total_players": len(self.physics_engine.player_tanks),
            "enemies_left": len(alive_enemies),
            "enemies_spotted": len(visible_enemies),
            "base_alive": base_alive,
            "selected_count": len(self.selection_mgr.get_selected()),
            "micro_tank_id": micro.id if micro else "None",
            "micro_ammo": micro.ammo if micro else -1,
            "micro_max_ammo": micro.max_ammo if micro else -1,
            "micro_tactic": micro_tactic.value,
            "micro_auto_clear": micro_auto_clear,
            "fog_enabled": self.physics_engine.fog_of_war_enabled,
            "limited_ammo_enabled": self.physics_engine.limited_ammo_enabled,
            "game_over": self.game_over,
            "game_victory": self.game_victory,
            "victory_desc": self.victory_condition.get_description(),
            "defeat_desc": self.defeat_condition.get_description()
        })

    def _game_loop(self):
        if not self.game_over and not self.game_victory and not self.is_paused:
            # 推进胜负条件计时上下文 (假设每步按约 16ms 步进)
            self.condition_ctx.update(0.016)

            has_manual_input = self._process_micro_tank_input()
            self.command_dispatcher.update(
                self.physics_engine.player_tanks,
                self.selection_mgr.get_micro_tank(),
                has_manual_input,
                self.physics_engine,
                self.game_map
            )
            self.ai_controller.update()
            self.physics_engine.update()

            if self.command_marker:
                mx, my, is_atk, lf = self.command_marker
                if lf > 1:
                    self.command_marker = (mx, my, is_atk, lf - 1)
                else:
                    self.command_marker = None

            self._check_game_status()

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # 1. 经典黑底
        painter.fillRect(self.rect(), QColor("#000000"))

        # 2. 地图
        PixelRenderer.draw_map(painter, self.game_map)

        # 3. 我方所有坦克
        for tank in self.physics_engine.player_tanks:
            if tank.alive:
                is_sel = self.selection_mgr.is_selected(tank)
                is_micro = self.selection_mgr.is_micro_tank(tank)
                auto_clr = self.command_dispatcher.is_auto_clear_path(tank)
                PixelRenderer.draw_tank(painter, tank, is_selected=is_sel, is_micro=is_micro, auto_clear=auto_clr)

        # 4. 敌军坦克 (只绘制当前可见的！迷雾外敌军绝对不绘制！)
        for enemy in self.physics_engine.enemy_tanks:
            if enemy.alive and self.physics_engine.is_enemy_visible(enemy):
                PixelRenderer.draw_tank(painter, enemy)

        # 5. 炮弹 (属于玩家的均可见；属于敌军的在视野内才可见)
        sight_rects = self.physics_engine.get_player_sight_rects()
        has_full_vision = any(t.vision_size < 0 for t in self.physics_engine.player_tanks if t.alive)

        for bullet in self.physics_engine.bullets:
            if not bullet.alive:
                continue
            if bullet.camp == Camp.PLAYER or not self.physics_engine.fog_of_war_enabled or has_full_vision:
                PixelRenderer.draw_bullet(painter, bullet)
            else:
                # 敌军炮弹飞入视线区才可见
                if any(bullet.rect.collides_with(sr) for sr in sight_rects):
                    PixelRenderer.draw_bullet(painter, bullet)

        # 6. 战争迷雾覆盖层 (若开启迷雾且非全图视野)
        if self.physics_engine.fog_of_war_enabled and not has_full_vision:
            PixelRenderer.draw_fog_of_war(
                painter,
                self.game_map.pixel_width,
                self.game_map.pixel_height,
                sight_rects
            )

        # 7. 跟丢敌军记忆残影 (只标记最后一次发现的坐标，红色虚线框显示)
        for mem in self.physics_engine.enemy_memory.values():
            if not mem.is_tracking:
                PixelRenderer.draw_lost_enemy_memory(painter, mem)

        # 8. 指令标记
        if self.command_marker:
            mx, my, is_atk, _ = self.command_marker
            PixelRenderer.draw_command_marker(painter, mx, my, is_attack=is_atk)

        # 9. 帝国时代拉框矩形
        if self.is_dragging_box:
            PixelRenderer.draw_selection_box(
                painter,
                self.drag_start.x(), self.drag_start.y(),
                self.drag_current.x(), self.drag_current.y()
            )

        # 9. 胜负与暂停提示
        restart_str = t("game.restart_hint")
        if self.game_over:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 160))
            painter.setPen(QPen(QColor("#E74C3C")))
            painter.setFont(QFont("Courier New", 20, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, f"GAME OVER\n[{self.defeat_condition.get_description()}]\n{restart_str}")
        elif self.game_victory:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 160))
            painter.setPen(QPen(QColor("#2ECC71")))
            painter.setFont(QFont("Courier New", 20, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, f"VICTORY!\n[{self.victory_condition.get_description()}]\n{restart_str}")
        elif self.is_paused:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
            painter.setPen(QPen(QColor("#F1C40F")))
            painter.setFont(QFont("Courier New", 22, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, t("game.paused"))

        painter.end()
