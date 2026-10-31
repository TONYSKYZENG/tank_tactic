from pathlib import Path
from typing import Set, Dict, Optional, Tuple, List
from PyQt5.QtCore import QObject, QTimer, QBuffer, QIODevice, pyqtSignal, QPointF
from PyQt5.QtGui import QImage, QPainter, QColor, QFont, QPen
from PyQt5.QtCore import Qt

from map_loader.models import GameMap, TileType
from mission_loader.models import Mission
from tank_configs.config_loader import TankConfig
from physics.entities import Tank, Direction, Camp, Rect
from physics.engine import PhysicsEngine
from ai.controller import EnemyAIController
from grouping.selection import SelectionManager
from command.dispatcher import CommandDispatcher
from command.tactics_mode import TacticMode
from gui.renderer import PixelRenderer
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
from resource import ResourceManager, ResourceLoader
from converter import RecipeRegistry

class HeadlessGameRunner(QObject):
    """
    后台无头游戏运行器：
    支持战争迷雾、视线正方形、有限弹药、敌军辨识度探测与 Web VNC 离屏推流
    """

    frame_ready = pyqtSignal(bytes, dict)

    def __init__(self, mission: Mission, game_map: GameMap, base_dir: Path, parent=None):
        super().__init__(parent)
        self.mission = mission
        self.game_map = game_map
        self.base_dir = base_dir

        self.width = self.game_map.pixel_width
        self.height = self.game_map.pixel_height

        self.render_image = QImage(self.width, self.height, QImage.Format_RGB32)

        self.physics_engine = PhysicsEngine(
            self.game_map,
            fog_of_war_enabled=self.mission.fog_of_war,
            limited_ammo_enabled=self.mission.limited_ammo
        )
        self.ai_controller = EnemyAIController(self.physics_engine, self.game_map)
        self.selection_mgr = SelectionManager()
        self.command_dispatcher = CommandDispatcher()

        # 初始化 API 控制器与外挂战术脚本管理器
        self.api_controller = GameAPIController(self)
        self.ai_script_manager = AIScriptManager()

        self.active_keys: Set[str] = set()

        self.preview_box: Optional[Tuple[float, float, float, float]] = None
        self.command_marker: Optional[Tuple[float, float, bool, int]] = None

        self.game_over = False
        self.game_victory = False
        self.is_paused = True

        # 经济系统
        self.resource_loader = ResourceLoader()
        self.resource_configs = self.resource_loader.load_configs(self.base_dir / "resource")
        self.resource_manager = ResourceManager(
            initial_resources=getattr(self.mission, "initial_resources", None),
            player_initial_resources=getattr(self.mission, "player_initial_resources", None),
            enemy_initial_resources=getattr(self.mission, "enemy_initial_resources", None)
        )
        self.resource_manager.init_from_map(self.game_map, self.resource_configs)
        RecipeRegistry.load_recipes(self.base_dir / "converter")

        self._setup_mission_entities()

        # 启动战术脚本线程
        all_tanks = self.physics_engine.player_tanks + self.physics_engine.enemy_tanks
        self.ai_script_manager.start_scripts(all_tanks, self.api_controller, self.base_dir)
        self.ai_script_manager.pause()

        self._setup_conditions()

        if self.physics_engine.player_tanks:
            self.selection_mgr.select_single(self.physics_engine.player_tanks[0])

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._step)

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
        self.condition_ctx = ConditionContext(self.physics_engine, self.game_map, self.resource_manager)

        if self.mission.victory_conditions:
            self.victory_condition = ConditionBuilder.build(self.mission.victory_conditions)
        else:
            self.victory_condition = AllEnemiesDestroyedCondition()

        if self.mission.defeat_conditions:
            self.defeat_condition = ConditionBuilder.build(self.mission.defeat_conditions)
        else:
            defeat_subs = [AllPlayersDestroyedCondition()]
            for t in self.physics_engine.player_tanks:
                if t.is_tower and t.tower_type == "supply":
                    defeat_subs.append(UnitDestroyedCondition(t.id))
            self.defeat_condition = OrCondition(defeat_subs)

    def start(self):
        self.timer.start(16)

    def stop(self):
        if hasattr(self, "ai_script_manager"):
            self.ai_script_manager.stop_all()
        self.timer.stop()

    def _setup_mission_entities(self):
        tile_size = self.game_map.tile_size

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
                crush_speed_factor=getattr(cfg, "crush_speed_factor", 0.5),
                converter_table=p_info.converter_table if getattr(p_info, "converter_table", None) is not None else getattr(cfg, "converter_table", []),
                harvest_speed=getattr(cfg, "harvest_speed", None)
            )
            tank.fire_cooldown_max = cfg.fire_cooldown
            tank._config = cfg
            self.physics_engine.add_player_tank(tank)
            self.command_dispatcher.register_tank(tank)

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
                crush_speed_factor=getattr(cfg, "crush_speed_factor", 0.5),
                converter_table=enemy_info.converter_table if getattr(enemy_info, "converter_table", None) is not None else getattr(cfg, "converter_table", []),
                harvest_speed=getattr(cfg, "harvest_speed", None)
            )
            tank.fire_cooldown_max = cfg.fire_cooldown
            tank._config = cfg
            self.ai_controller.register_enemy(tank, cfg, enemy_info.tactic)

    def handle_mouse_event(self, data: dict):
        ev_type = data.get("type")
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))

        if ev_type == "box_drag":
            x1, y1 = float(data.get("x1", 0)), float(data.get("y1", 0))
            x2, y2 = float(data.get("x2", 0)), float(data.get("y2", 0))
            self.preview_box = (x1, y1, x2, y2)
        elif ev_type == "box_select":
            self.preview_box = None
            x1, y1 = float(data.get("x1", 0)), float(data.get("y1", 0))
            x2, y2 = float(data.get("x2", 0)), float(data.get("y2", 0))
            rw = abs(x2 - x1)
            rh = abs(y2 - y1)
            if rw < 8 and rh < 8:
                clicked = None
                for t in self.physics_engine.player_tanks:
                    if t.alive and t.rect.collides_with(Rect(x1 - 3, y1 - 3, 6, 6)):
                        clicked = t
                        break
                if clicked:
                    self.selection_mgr.select_single(clicked)
                else:
                    self.selection_mgr.clear_selection()
            else:
                rx = min(x1, x2)
                ry = min(y1, y2)
                self.selection_mgr.select_box(Rect(rx, ry, rw, rh), self.physics_engine.player_tanks)

        elif ev_type == "context_cmd":
            selected = self.selection_mgr.get_selected()
            if not selected:
                micro = self.selection_mgr.get_micro_tank()
                if micro and micro.alive:
                    selected = [micro]

            if selected:
                # 1. 检查是否右键友军 -> 护卫该友军
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
                    # 2. 检查是否右键可见敌军 -> 集火
                    target_enemy = None
                    for e in self.physics_engine.get_visible_enemies():
                        if e.alive and e.rect.collides_with(Rect(x - 6, y - 6, 12, 12)):
                            target_enemy = e
                            break

                    if target_enemy:
                        self.command_dispatcher.issue_attack_target(selected, target_enemy, self.physics_engine)
                        self.command_marker = (target_enemy.x + target_enemy.size / 2.0,
                                               target_enemy.y + target_enemy.size / 2.0, True, 20)
                    else:
                        ts = self.game_map.tile_size
                        click_col = int(x // ts)
                        click_row = int(y // ts)
                        target_res_block = self.resource_manager.get_block_at(click_col, click_row)
                        if target_res_block:
                            self.command_dispatcher.issue_harvest(selected, click_col, click_row, self.resource_manager)
                            self.command_marker = ((click_col + 0.5) * ts, (click_row + 0.5) * ts, False, 20)
                        else:
                            # 3. 移动
                            self.command_dispatcher.issue_move(selected, x, y)
                            self.command_marker = (x, y, False, 20)

    def handle_key_event(self, key_name: str, is_down: bool):
        norm_key = key_name.lower()
        if is_down:
            self.active_keys.add(norm_key)

            if norm_key == "tab":
                self.selection_mgr.cycle_micro_tank(self.physics_engine.player_tanks)
            elif norm_key in ("space", " "):
                self._fire_micro_tank()
            elif norm_key == "1":
                self.command_dispatcher.issue_tactic(self.selection_mgr.get_selected(), TacticMode.AGGRESSIVE)
            elif norm_key == "2":
                self.command_dispatcher.issue_tactic(self.selection_mgr.get_selected(), TacticMode.DEFENSIVE)
            elif norm_key == "3":
                selected = self.selection_mgr.get_selected()
                core_tower = None
                for t in self.physics_engine.player_tanks:
                    if t.alive and t.is_tower and t.tower_type == "supply":
                        core_tower = t
                        break
                guard_target = core_tower if core_tower else self.selection_mgr.get_micro_tank()
                self.command_dispatcher.issue_tactic(selected, TacticMode.GUARD_UNIT, guard_target=guard_target)
            elif norm_key == "b":
                target_tanks = self.selection_mgr.get_selected()
                if not target_tanks:
                    micro = self.selection_mgr.get_micro_tank()
                    if micro and micro.alive:
                        target_tanks = [micro]
                if target_tanks:
                    self.command_dispatcher.toggle_auto_clear_path(target_tanks)
            elif norm_key == "s":
                self.command_dispatcher.issue_stop(self.selection_mgr.get_selected())
            elif norm_key == "p":
                if self.is_paused:
                    self.resume()
                else:
                    self.pause()
            elif norm_key == "r":
                self.restart()
        else:
            self.active_keys.discard(norm_key)

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
        if "arrowup" in self.active_keys or "w" in self.active_keys or "up" in self.active_keys:
            vy -= 1.0
        if "arrowdown" in self.active_keys or "s" in self.active_keys or "down" in self.active_keys:
            vy += 1.0
        if "arrowleft" in self.active_keys or "a" in self.active_keys or "left" in self.active_keys:
            vx -= 1.0
        if "arrowright" in self.active_keys or "d" in self.active_keys or "right" in self.active_keys:
            vx += 1.0

        if abs(vx) > 1e-4 or abs(vy) > 1e-4:
            self.physics_engine.move_tank(micro, (vx, vy))
            return True
        return False

    def restart(self):
        if hasattr(self, "ai_script_manager"):
            self.ai_script_manager.stop_all()

        self.game_over = False
        self.game_victory = False
        self.is_paused = False
        self.active_keys.clear()
        self.preview_box = None
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

    def _check_game_status(self):
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

        # 胜负条件动态求值
        if self.defeat_condition.evaluate(self.condition_ctx):
            self.game_over = True
        elif self.victory_condition.evaluate(self.condition_ctx):
            self.game_victory = True

        micro = self.selection_mgr.get_micro_tank()
        micro_tactic = self.command_dispatcher.get_tactic(micro) if micro else TacticMode.MANUAL_OR_IDLE
        micro_auto_clear = self.command_dispatcher.is_auto_clear_path(micro) if micro else False

        return {
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
            "resources": self.resource_manager.get_all_resources(camp="player"),
            "resource_rates": self.resource_manager.get_harvest_rates(camp="player"),
            "game_over": self.game_over,
            "game_victory": self.game_victory,
            "victory_desc": self.victory_condition.get_description(),
            "defeat_desc": self.defeat_condition.get_description(),
            "mission_name": self.mission.name
        }

    def _render_frame(self) -> bytes:
        painter = QPainter(self.render_image)
        painter.setRenderHint(QPainter.Antialiasing, False)

        painter.fillRect(self.render_image.rect(), QColor("#000000"))
        PixelRenderer.draw_map(painter, self.game_map)

        for tank in self.physics_engine.player_tanks:
            if tank.alive:
                is_sel = self.selection_mgr.is_selected(tank)
                is_micro = self.selection_mgr.is_micro_tank(tank)
                auto_clr = self.command_dispatcher.is_auto_clear_path(tank)
                PixelRenderer.draw_tank(painter, tank, is_selected=is_sel, is_micro=is_micro, auto_clear=auto_clr)

        for enemy in self.physics_engine.enemy_tanks:
            if enemy.alive and self.physics_engine.is_enemy_visible(enemy):
                PixelRenderer.draw_tank(painter, enemy)

        sight_rects = self.physics_engine.get_player_sight_rects()
        has_full_vision = any(t.vision_size < 0 for t in self.physics_engine.player_tanks if t.alive)

        for bullet in self.physics_engine.bullets:
            if not bullet.alive:
                continue
            if bullet.camp == Camp.PLAYER or not self.physics_engine.fog_of_war_enabled or has_full_vision:
                PixelRenderer.draw_bullet(painter, bullet)
            else:
                if any(bullet.rect.collides_with(sr) for sr in sight_rects):
                    PixelRenderer.draw_bullet(painter, bullet)

        if self.physics_engine.fog_of_war_enabled and not has_full_vision:
            PixelRenderer.draw_fog_of_war(
                painter,
                self.game_map.pixel_width,
                self.game_map.pixel_height,
                sight_rects
            )

        # 跟丢敌军记忆残影 (虚线框标记最后一次坐标)
        for mem in self.physics_engine.enemy_memory.values():
            if not mem.is_tracking:
                PixelRenderer.draw_lost_enemy_memory(painter, mem)

        if self.command_marker:
            mx, my, is_atk, _ = self.command_marker
            PixelRenderer.draw_command_marker(painter, mx, my, is_attack=is_atk)

        if self.preview_box:
            bx1, by1, bx2, by2 = self.preview_box
            PixelRenderer.draw_selection_box(painter, bx1, by1, bx2, by2)

        if self.game_over:
            painter.fillRect(self.render_image.rect(), QColor(0, 0, 0, 160))
            painter.setPen(QPen(QColor("#E74C3C")))
            painter.setFont(QFont("Courier New", 20, QFont.Bold))
            painter.drawText(self.render_image.rect(), Qt.AlignCenter, f"GAME OVER\n[{self.defeat_condition.get_description()}]\n[按 R 重新挑战]")
        elif self.game_victory:
            painter.fillRect(self.render_image.rect(), QColor(0, 0, 0, 160))
            painter.setPen(QPen(QColor("#2ECC71")))
            painter.setFont(QFont("Courier New", 20, QFont.Bold))
            painter.drawText(self.render_image.rect(), Qt.AlignCenter, f"VICTORY!\n[{self.victory_condition.get_description()}]\n[按 R 重新挑战]")
        elif self.is_paused:
            painter.fillRect(self.render_image.rect(), QColor(0, 0, 0, 110))
            painter.setPen(QPen(QColor("#F1C40F")))
            painter.setFont(QFont("Courier New", 22, QFont.Bold))
            painter.drawText(self.render_image.rect(), Qt.AlignCenter, "PAUSED\n(全部单位与高阶 AI 已冻结)")

        painter.end()

        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        self.render_image.save(buffer, "JPEG", 70)
        return bytes(buffer.data())

    def _step(self):
        if not self.game_over and not self.game_victory and not self.is_paused:
            self.condition_ctx.update(0.016)

            # 推进经济系统与转换机
            self.resource_manager.update(0.016)
            all_tanks = self.physics_engine.player_tanks + self.physics_engine.enemy_tanks
            self.resource_manager.update_harvest(all_tanks, 0.016, self.game_map.tile_size)
            for t in all_tanks:
                if t.alive and t.converter:
                    camp_str = t.camp.value if hasattr(t.camp, "value") else str(t.camp)
                    t.converter.update(
                        0.016,
                        self.resource_manager,
                        camp=camp_str,
                        physics_engine=self.physics_engine,
                        game_map=self.game_map,
                        command_dispatcher=self.command_dispatcher,
                        ai_controller=self.ai_controller,
                        base_dir=self.base_dir
                    )

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

        status = self._check_game_status()
        frame_bytes = self._render_frame()
        self.frame_ready.emit(frame_bytes, status)
