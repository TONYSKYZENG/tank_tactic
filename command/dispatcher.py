import math
from typing import Dict, List, Optional
from physics.entities import Tank, Direction, Camp
from map_loader.models import GameMap, TileType
from grouping.formation import calculate_formation_slots
from .tactics_mode import TacticMode
from .commands import BaseCommand, MoveCommand, AttackTargetCommand, HoldCommand, GuardUnitCommand

class CommandDispatcher:
    """
    命令下发与战术执行调度器：
    - 支持批量下达移动目的地 (排布阵型避免重叠)
    - 支持【可选的自动开路功能 (Auto-Breaching)】
    - 支持批量下达集火攻击目标
    - 支持【跟踪并保卫特定己方单位 (Guard Unit)】战术
    - 支持批量下达战术姿态 (AGGRESSIVE, DEFENSIVE, GUARD_UNIT, MANUAL)
    - 防御塔自主防空与火炮拦截
    """

    def __init__(self):
        self.tank_commands: Dict[str, Optional[BaseCommand]] = {}
        self.tank_tactics: Dict[str, TacticMode] = {}
        self.tank_auto_clear: Dict[str, bool] = {}
        # 记录每辆坦克要保卫的目标单位 ID
        self.guard_targets: Dict[str, str] = {}

    def register_tank(self, tank: Tank, default_tactic: TacticMode = TacticMode.MANUAL_OR_IDLE):
        self.tank_commands[tank.id] = None
        self.tank_tactics[tank.id] = default_tactic
        self.tank_auto_clear[tank.id] = False

    def get_tactic(self, tank: Tank) -> TacticMode:
        return self.tank_tactics.get(tank.id, TacticMode.MANUAL_OR_IDLE)

    def is_auto_clear_path(self, tank: Tank) -> bool:
        return self.tank_auto_clear.get(tank.id, False)

    def set_auto_clear_path(self, tanks: List[Tank], enabled: bool):
        for tank in tanks:
            self.tank_auto_clear[tank.id] = enabled
            curr_cmd = self.tank_commands.get(tank.id)
            if isinstance(curr_cmd, MoveCommand):
                curr_cmd.auto_clear_path = enabled

    def toggle_auto_clear_path(self, tanks: List[Tank]) -> bool:
        if not tanks:
            return False
        new_val = not self.is_auto_clear_path(tanks[0])
        self.set_auto_clear_path(tanks, new_val)
        return new_val

    def issue_move(self, tanks: List[Tank], target_x: float, target_y: float):
        valid_tanks = [t for t in tanks if t.alive and not t.is_tower]
        if not valid_tanks:
            return

        slots = calculate_formation_slots(target_x, target_y, len(valid_tanks), spacing=42.0)
        for tank, (sx, sy) in zip(valid_tanks, slots):
            clear_path = self.is_auto_clear_path(tank)
            self.tank_commands[tank.id] = MoveCommand(dest_x=sx, dest_y=sy, auto_clear_path=clear_path)

    def issue_attack_target(self, tanks: List[Tank], target_tank: Tank, physics_engine=None, ignore_vision: bool = False):
        if not target_tank.alive:
            return
        is_omniscient = ignore_vision or any(getattr(t, "ai_script", None) for t in tanks)
        if physics_engine and not is_omniscient and not physics_engine.is_enemy_visible(target_tank):
            self.issue_move(tanks, target_tank.x, target_tank.y)
            return

        for tank in tanks:
            if tank.alive:
                clear_path = self.is_auto_clear_path(tank)
                curr_cmd = self.tank_commands.get(tank.id)
                # 若已在追击该相同存活目标，保持现有寻路与行军子命令，避免高频打断抽搐
                # 若当前攻击指令严重受阻卡死 (>30 帧)，则允许刷新重设
                if isinstance(curr_cmd, AttackTargetCommand) and curr_cmd.target_tank == target_tank and target_tank.alive:
                    if getattr(curr_cmd, "stuck_attack_frames", 0) < 30:
                        continue
                self.tank_commands[tank.id] = AttackTargetCommand(target_tank, auto_clear_path=clear_path)

    def _auto_acquire_next_target(self, tank: Tank, physics_engine, exclude_target: Optional[Tank] = None) -> None:
        """当当前目标被歼灭或路径受阻卡死时，自动为战斗/战术单位接续锁定下一个高威胁目标，确保连续作战不发呆"""
        if not tank.alive or tank.is_tower:
            return

        clear_path = self.is_auto_clear_path(tank)
        tactic = self.tank_tactics.get(tank.id, TacticMode.MANUAL_OR_IDLE)
        has_script = getattr(tank, "ai_script", None) is not None

        if tank.camp == Camp.ENEMY or has_script:
            opp_list = physics_engine.player_tanks if tank.camp == Camp.ENEMY else physics_engine.enemy_tanks
            alive_opps = [t for t in opp_list if t.alive and (exclude_target is None or t != exclude_target)]
            if not alive_opps and exclude_target is not None and exclude_target.alive:
                alive_opps = [exclude_target]
            if alive_opps:
                best_target = min(
                    alive_opps,
                    key=lambda t: (0 if t.is_tower else 1, (t.x - tank.x)**2 + (t.y - tank.y)**2)
                )
                self.tank_commands[tank.id] = AttackTargetCommand(best_target, auto_clear_path=clear_path)
        elif tactic == TacticMode.AGGRESSIVE:
            visible_enemies = [e for e in physics_engine.get_visible_enemies() if (exclude_target is None or e != exclude_target)]
            if not visible_enemies and exclude_target is not None and exclude_target.alive and physics_engine.is_enemy_visible(exclude_target):
                visible_enemies = [exclude_target]
            if visible_enemies:
                nearest_enemy = min(
                    visible_enemies,
                    key=lambda e: (e.x - tank.x)**2 + (e.y - tank.y)**2
                )
                self.tank_commands[tank.id] = AttackTargetCommand(nearest_enemy, auto_clear_path=clear_path)

    def issue_guard_unit(self, tanks: List[Tank], target_to_guard: Tank):
        """批量下发：跟踪并保卫特定己方单位"""
        if not target_to_guard.alive:
            return
        for tank in tanks:
            if tank.alive and tank != target_to_guard:
                self.tank_tactics[tank.id] = TacticMode.GUARD_UNIT
                self.guard_targets[tank.id] = target_to_guard.id
                self.tank_commands[tank.id] = GuardUnitCommand(target_to_guard)

    def issue_tactic(self, tanks: List[Tank], tactic_mode: TacticMode, guard_target: Optional[Tank] = None):
        """批量设置战术姿态"""
        for tank in tanks:
            if tank.alive:
                self.tank_tactics[tank.id] = tactic_mode
                if tactic_mode == TacticMode.DEFENSIVE:
                    self.tank_commands[tank.id] = HoldCommand()
                elif tactic_mode == TacticMode.GUARD_UNIT and guard_target:
                    self.guard_targets[tank.id] = guard_target.id
                    self.tank_commands[tank.id] = GuardUnitCommand(guard_target)

    def issue_stop(self, tanks: List[Tank]):
        for tank in tanks:
            self.tank_commands[tank.id] = None
            self.tank_tactics[tank.id] = TacticMode.MANUAL_OR_IDLE

    def update(self, player_tanks: List[Tank], micro_tank: Optional[Tank],
               has_manual_input: bool, physics_engine, game_map: GameMap):
        alive_player_tanks = [t for t in player_tanks if t.alive]
        # 兼容独立战术脚本驱动的敌军坦克或其他已被下发指令的活动单位
        enemy_cmd_tanks = [t for t in getattr(physics_engine, "enemy_tanks", [])
                           if t.alive and (self.tank_commands.get(t.id) is not None or self.tank_tactics.get(t.id))]
        alive_tanks = alive_player_tanks + [t for t in enemy_cmd_tanks if t not in alive_player_tanks]
        visible_enemies = physics_engine.get_visible_enemies()

        # 核心防御塔（若有）
        core_tower = None
        for t in alive_tanks:
            if t.is_tower and t.tower_type == "supply":
                core_tower = t
                break

        for tank in alive_tanks:
            # 微操坦克手动控制优先
            if tank == micro_tank and has_manual_input:
                continue

            # 防御塔自主防空火炮：若处于空闲状态且有射界内可见敌军，自主开火轰击
            if tank.is_tower and tank.can_attack and visible_enemies:
                cmd = self.tank_commands.get(tank.id)
                if cmd is None:
                    # 寻找视野内最近敌军
                    center_x = tank.x + tank.size / 2.0
                    center_y = tank.y + tank.size / 2.0
                    in_range_enemies = []
                    sight_half = tank.vision_size / 2.0 if tank.vision_size > 0 else 9999.0
                    for e in visible_enemies:
                        e_cx = e.x + e.size / 2.0
                        e_cy = e.y + e.size / 2.0
                        if abs(e_cx - center_x) <= sight_half and abs(e_cy - center_y) <= sight_half:
                            in_range_enemies.append((math.hypot(e_cx - center_x, e_cy - center_y), e))
                    if in_range_enemies:
                        in_range_enemies.sort(key=lambda x: x[0])
                        self.tank_commands[tank.id] = AttackTargetCommand(in_range_enemies[0][1])

            cmd = self.tank_commands.get(tank.id)
            if cmd is not None:
                if isinstance(cmd, AttackTargetCommand):
                    # 若目标已阵亡，由 cmd.execute() 判定为 finished 并触发自动接续转火
                    if not cmd.target_tank.alive:
                        pass
                    # 若为我方受限迷雾视野普通单位且目标失联，则取消追踪
                    elif tank.camp == Camp.PLAYER and getattr(tank, "ai_script", None) is None:
                        if not physics_engine.is_enemy_visible(cmd.target_tank):
                            self.tank_commands[tank.id] = None
                            cmd = None

                if cmd is not None:
                    finished = cmd.execute(tank, physics_engine, game_map)
                    if finished:
                        self.tank_commands[tank.id] = None
                        target = getattr(cmd, "target_tank", None)
                        exclude = target if (target and target.alive) else None
                        cmd = None
                        self._auto_acquire_next_target(tank, physics_engine, exclude_target=exclude)
                    continue

            tactic = self.tank_tactics.get(tank.id, TacticMode.MANUAL_OR_IDLE)
            clear_path = self.is_auto_clear_path(tank)

            if tactic == TacticMode.AGGRESSIVE and visible_enemies:
                nearest_enemy = min(
                    visible_enemies,
                    key=lambda e: (e.x - tank.x)**2 + (e.y - tank.y)**2
                )
                self.tank_commands[tank.id] = AttackTargetCommand(nearest_enemy, auto_clear_path=clear_path)
            elif tactic == TacticMode.GUARD_UNIT:
                # 跟踪并保卫特定己方单位
                target_id = self.guard_targets.get(tank.id)
                target_unit = None
                if target_id:
                    for cand in alive_tanks:
                        if cand.id == target_id:
                            target_unit = cand
                            break

                # 默认保卫核心防御塔或微操坦克
                if not target_unit:
                    target_unit = core_tower if core_tower and core_tower != tank else (micro_tank if micro_tank and micro_tank != tank else None)

                if target_unit and target_unit.alive:
                    self.tank_commands[tank.id] = GuardUnitCommand(target_unit)
