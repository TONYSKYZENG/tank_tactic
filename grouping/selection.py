from typing import List, Optional, Set
from physics.entities import Tank, Rect, Camp

class SelectionManager:
    """
    编组与选择管理器：
    - 支持单选、帝国时代风格的矩形框选
    - 管理当前具体微操的坦克 (Micro-control Tank)
    - 提供切换/循环微操坦克的 API
    """

    def __init__(self):
        self.selected_tanks: List[Tank] = []
        self.micro_tank: Optional[Tank] = None

    def clean_dead_tanks(self):
        """清除已阵亡的坦克"""
        self.selected_tanks = [t for t in self.selected_tanks if t.alive]
        if self.micro_tank and not self.micro_tank.alive:
            self.micro_tank = self.selected_tanks[0] if self.selected_tanks else None

    def select_single(self, tank: Tank):
        """单选某一坦克，并将其设为当前微操坦克"""
        if not tank.alive or tank.camp != Camp.PLAYER:
            return
        self.selected_tanks = [tank]
        self.micro_tank = tank

    def select_box(self, box_rect: Rect, player_tanks: List[Tank]):
        """
        帝国时代矩形框选：
        选中与 box_rect 相交或被其包含的所有存活我方坦克
        """
        matched = []
        for tank in player_tanks:
            if tank.alive and tank.camp == Camp.PLAYER:
                if box_rect.collides_with(tank.rect):
                    matched.append(tank)

        if matched:
            self.selected_tanks = matched
            # 如果当前微操坦克不在新选中的坦克中，则默认将第 1 辆设为微操坦克
            if self.micro_tank not in self.selected_tanks:
                self.micro_tank = self.selected_tanks[0]
        else:
            self.clear_selection()

    def select_all(self, player_tanks: List[Tank]):
        """全选我方所有存活坦克"""
        self.selected_tanks = [t for t in player_tanks if t.alive and t.camp == Camp.PLAYER]
        if self.selected_tanks:
            if self.micro_tank not in self.selected_tanks:
                self.micro_tank = self.selected_tanks[0]
        else:
            self.micro_tank = None

    def clear_selection(self):
        """清空当前选择"""
        self.selected_tanks.clear()
        self.micro_tank = None

    def set_micro_tank(self, tank: Tank):
        """指定具体的微操坦克"""
        if tank.alive and tank.camp == Camp.PLAYER:
            self.micro_tank = tank
            if tank not in self.selected_tanks:
                self.selected_tanks.append(tank)

    def cycle_micro_tank(self, all_player_tanks: List[Tank]) -> Optional[Tank]:
        """
        循环切换当前具体微操的坦克（按 Tab 键触发）：
        - 如果当前有选中的坦克组，在选中的坦克组内循环切换
        - 如果当前未选中坦克，在我方所有存活坦克中循环切换
        """
        self.clean_dead_tanks()
        candidates = self.selected_tanks if self.selected_tanks else [t for t in all_player_tanks if t.alive]

        if not candidates:
            self.micro_tank = None
            return None

        if self.micro_tank not in candidates:
            self.micro_tank = candidates[0]
        else:
            idx = candidates.index(self.micro_tank)
            next_idx = (idx + 1) % len(candidates)
            self.micro_tank = candidates[next_idx]

        # 确保微操坦克包含在选中列表中
        if self.micro_tank not in self.selected_tanks:
            self.selected_tanks = [self.micro_tank]

        return self.micro_tank

    def is_selected(self, tank: Tank) -> bool:
        return tank in self.selected_tanks

    def is_micro_tank(self, tank: Tank) -> bool:
        return self.micro_tank is not None and tank == self.micro_tank

    def get_selected(self) -> List[Tank]:
        self.clean_dead_tanks()
        return self.selected_tanks

    def get_micro_tank(self) -> Optional[Tank]:
        self.clean_dead_tanks()
        return self.micro_tank
