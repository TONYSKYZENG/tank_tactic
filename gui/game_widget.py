from pathlib import Path
from typing import Set, Dict
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

from map_loader.models import GameMap, TileType
from mission_loader.models import Mission
from tank_configs.config_loader import TankConfig
from physics.entities import Tank, Direction, Camp
from physics.engine import PhysicsEngine
from ai.controller import EnemyAIController
from .renderer import PixelRenderer

class GameCanvasWidget(QWidget):
    """游戏主画布：处理键盘按键输入、AI调度、物理刷新、画面渲染"""

    # 状态通知信号 (用于更新顶部/底部状态栏)
    status_updated = pyqtSignal(dict)

    def __init__(self, mission: Mission, game_map: GameMap, base_dir: Path, parent=None):
        super().__init__(parent)
        self.mission = mission
        self.game_map = game_map
        self.base_dir = base_dir

        self.setFixedSize(self.game_map.pixel_width, self.game_map.pixel_height)
        self.setFocusPolicy(Qt.StrongFocus)

        # 物理引擎
        self.physics_engine = PhysicsEngine(self.game_map)

        # AI 控制器
        self.ai_controller = EnemyAIController(self.physics_engine, self.game_map)

        # 按键集合
        self.active_keys: Set[int] = set()

        # 初始化玩家与敌军（含安全空位校验）
        self._setup_mission_entities()

        # 游戏状态
        self.game_over = False
        self.game_victory = False

        # 游戏主循环定时器（~60 FPS）
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._game_loop)
        self.timer.start(16)

    def _setup_mission_entities(self):
        tile_size = self.game_map.tile_size

        # 1. 初始化玩家坦克（带安全空位矫正）
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

        # 2. 从任务中初始化敌军坦克（带安全空位矫正）并注册到 AI
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

    def keyPressEvent(self, event):
        key = event.key()
        if not event.isAutoRepeat():
            self.active_keys.add(key)
            if key == Qt.Key_Space:
                self._fire_bullet()
        event.accept()

    def keyReleaseEvent(self, event):
        if not event.isAutoRepeat():
            self.active_keys.discard(event.key())
        event.accept()

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
        if Qt.Key_Up in self.active_keys or Qt.Key_W in self.active_keys:
            direction = Direction.UP
        elif Qt.Key_Down in self.active_keys or Qt.Key_S in self.active_keys:
            direction = Direction.DOWN
        elif Qt.Key_Left in self.active_keys or Qt.Key_A in self.active_keys:
            direction = Direction.LEFT
        elif Qt.Key_Right in self.active_keys or Qt.Key_D in self.active_keys:
            direction = Direction.RIGHT

        if direction is not None:
            self.physics_engine.move_tank(self.player_tank, direction)

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

        self.status_updated.emit({
            "player_hp": self.player_tank.health if self.player_tank.alive else 0,
            "enemies_left": len(self.physics_engine.enemy_tanks),
            "base_alive": base_alive,
            "game_over": self.game_over,
            "game_victory": self.game_victory
        })

    def _game_loop(self):
        if not self.game_over and not self.game_victory:
            self._process_player_input()
            self.ai_controller.update()
            self.physics_engine.update()
            self._check_game_status()

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # 1. 经典黑底清屏
        painter.fillRect(self.rect(), QColor("#000000"))

        # 2. 绘制地图
        PixelRenderer.draw_map(painter, self.game_map)

        # 3. 绘制玩家品字形坦克
        if self.player_tank and self.player_tank.alive:
            PixelRenderer.draw_tank(painter, self.player_tank)

        # 4. 绘制所有敌军品字形坦克
        for enemy in self.physics_engine.enemy_tanks:
            if enemy.alive:
                PixelRenderer.draw_tank(painter, enemy)

        # 5. 绘制所有品字形炮弹
        for bullet in self.physics_engine.bullets:
            PixelRenderer.draw_bullet(painter, bullet)

        # 6. 游戏结束/胜利提示覆盖层
        if self.game_over:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 160))
            painter.setPen(QPen(QColor("#E74C3C")))
            painter.setFont(QFont("Courier New", 32, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, "GAME OVER")
        elif self.game_victory:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 160))
            painter.setPen(QPen(QColor("#2ECC71")))
            painter.setFont(QFont("Courier New", 32, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, "VICTORY!")

        painter.end()
