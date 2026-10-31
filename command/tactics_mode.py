from enum import Enum

class TacticMode(Enum):
    MANUAL_OR_IDLE = "manual"        # 待命 / 手动微操
    AGGRESSIVE = "aggressive"        # 自由交战 / 主动索敌
    DEFENSIVE = "defensive"          # 坚守阵地 / 原地警戒
    GUARD_UNIT = "guard_unit"        # 跟踪并保卫特定己方单位
