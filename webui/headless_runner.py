from pathlib import Path
from typing import Set, Dict, Callable, Optional
from PyQt5.QtCore import QObject, QTimer, QBuffer, QIODevice, pyqtSignal
from PyQt5.QtGui import QImage, QPainter, QColor, QFont, QPen
from PyQt5.QtCore import Qt

from map_loader.models import GameMap, TileType
from mission_loader.models import Mission
from tank_configs.config_loader import TankConfig
from physics.entities import Tank, Direction, Camp
from physics.engine import PhysicsEngine
from ai.controller import EnemyAIController
from gui.renderer import PixelRenderer

class HeadlessGameRunner(QObject):
    """
    后台无头游戏运行器：
    脱离桌面 GUI 窗口运行，以 60 FPS 驱动物理与 AI，
    通过 QImage 离屏渲染游戏画面，并通过信号向 Web 端输出实时 JPEG 帧与状态数据。
    """

    frame_ready = pyqtSignal(bytes, dict)

    def __init__(self, mission: Mission, game_map: GameMap, base_dir: Path, parent=None):
        super().__init__(parent)
        self.mission = mission
        self.game_map = game_map
        self.base_dir = base_dir

        self.width = self.game_map.pixel_width
        self.height = self.game_map.pixel_height

        # 离屏渲染缓冲区
        self.render_image = QImage(self.width, self.height, QImage.Format_RGB32)

        # 物理与 AI
        self.physics_engine = PhysicsEngine(self.game_map)
        self.ai_controller = EnemyAIController(self.physics_engine, self.game_map)

        # 键盘按键跟踪集合 (支持 Web 端传入的标准键名或 keyCode)
        self.active_keys: Set[str] = set()

        # 状态
        self.game_over = False
        self.game_victory = False

        self._setup_mission_entities()

        # 60 FPS 定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._step)

    def start(self):
        self.timer.start(16)

    def stop(self):
        self.timer.stop()

    def _setup_mission_entities(self):
        tile_size = self.game_map.tile_size

        # 1. 玩家坦克
        player_cfg_path = self.base_dir / self.mission.player.config_file
        self.player_config = TankConfig.from_json(player_cfg_path)

        req_px = self.mission.player.spawn.x * tile_size
        req_py = self.mission.player.spawn.y * tile_size
        spawn_x, spawn_y = self.physics_engine.find_nearest_free_position(req_px, req_py, self.player_config.size)

        self.player_tank = Tank(
            x=spawn_x,
            y=spawn_y,
            size=self.player_config.size,
            speed=self.player_config.speed,
            camp=Camp.PLAYER,
            color=self.player_config.color,
            health=self.player_config.health,
            tank_id="player"
        )
        self.player_tank.fire_cooldown_max = self.player_config.fire_cooldown
        self.physics_engine.set_player_tank(self.player_tank)

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
                tank_id=enemy_info.id
            )
            tank.fire_cooldown_max = cfg.fire_cooldown
            self.ai_controller.register_enemy(tank, cfg, enemy_info.tactic)

    def handle_key_event(self, key_name: str, is_down: bool):
        """处理来自 Web 端的键盘事件"""
        norm_key = key_name.lower()
        if is_down:
            self.active_keys.add(norm_key)
            if norm_key in ("space", " "):
                self._fire_bullet()
            elif norm_key in ("r", "keyr") and (self.game_over or self.game_victory):
                self.restart()
        else:
            self.active_keys.discard(norm_key)

    def _fire_bullet(self):
        if self.player_tank and self.player_tank.alive:
            self.physics_engine.spawn_bullet(
                tank=self.player_tank,
                bullet_speed=self.player_config.bullet_speed,
                bullet_size=self.player_config.bullet_size,
                color=self.player_config.bullet_color
            )

    def _process_player_input(self):
        if not self.player_tank or not self.player_tank.alive:
            return

        direction = None
        if "arrowup" in self.active_keys or "w" in self.active_keys or "up" in self.active_keys:
            direction = Direction.UP
        elif "arrowdown" in self.active_keys or "s" in self.active_keys or "down" in self.active_keys:
            direction = Direction.DOWN
        elif "arrowleft" in self.active_keys or "a" in self.active_keys or "left" in self.active_keys:
            direction = Direction.LEFT
        elif "arrowright" in self.active_keys or "d" in self.active_keys or "right" in self.active_keys:
            direction = Direction.RIGHT

        if direction is not None:
            self.physics_engine.move_tank(self.player_tank, direction)

    def restart(self):
        """重置任务"""
        self.game_over = False
        self.game_victory = False
        self.active_keys.clear()
        self.physics_engine = PhysicsEngine(self.game_map)
        self.ai_controller = EnemyAIController(self.physics_engine, self.game_map)
        self._setup_mission_entities()

    def _check_game_status(self):
        base_alive = False
        for row in range(self.game_map.rows):
            for col in range(self.game_map.cols):
                if self.game_map.get_tile(col, row) == TileType.BASE:
                    base_alive = True
                    break
            if base_alive:
                break

        if not self.player_tank.alive or not base_alive:
            self.game_over = True
        elif len(self.physics_engine.enemy_tanks) == 0:
            self.game_victory = True

        return {
            "player_hp": self.player_tank.health if self.player_tank.alive else 0,
            "enemies_left": len(self.physics_engine.enemy_tanks),
            "base_alive": base_alive,
            "game_over": self.game_over,
            "game_victory": self.game_victory,
            "mission_name": self.mission.name
        }

    def _render_frame(self) -> bytes:
        """执行离屏像素绘制并输出 JPEG 图像字节"""
        painter = QPainter(self.render_image)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # 1. 经典黑底
        painter.fillRect(self.render_image.rect(), QColor("#000000"))

        # 2. 地图
        PixelRenderer.draw_map(painter, self.game_map)

        # 3. 玩家品字形坦克
        if self.player_tank and self.player_tank.alive:
            PixelRenderer.draw_tank(painter, self.player_tank)

        # 4. 敌军品字形坦克
        for enemy in self.physics_engine.enemy_tanks:
            if enemy.alive:
                PixelRenderer.draw_tank(painter, enemy)

        # 5. 品字形炮弹
        for bullet in self.physics_engine.bullets:
            PixelRenderer.draw_bullet(painter, bullet)

        # 6. 游戏结束/胜利覆层
        if self.game_over:
            painter.fillRect(self.render_image.rect(), QColor(0, 0, 0, 160))
            painter.setPen(QPen(QColor("#E74C3C")))
            painter.setFont(QFont("Courier New", 32, QFont.Bold))
            painter.drawText(self.render_image.rect(), Qt.AlignCenter, "GAME OVER\n[Press R to Restart]")
        elif self.game_victory:
            painter.fillRect(self.render_image.rect(), QColor(0, 0, 0, 160))
            painter.setPen(QPen(QColor("#2ECC71")))
            painter.setFont(QFont("Courier New", 32, QFont.Bold))
            painter.drawText(self.render_image.rect(), Qt.AlignCenter, "VICTORY!\n[Press R to Restart]")

        painter.end()

        # 编码为 JPEG
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        self.render_image.save(buffer, "JPEG", 70)
        return bytes(buffer.data())

    def _step(self):
        if not self.game_over and not self.game_victory:
            self._process_player_input()
            self.ai_controller.update()
            self.physics_engine.update()

        status = self._check_game_status()
        frame_bytes = self._render_frame()
        self.frame_ready.emit(frame_bytes, status)
