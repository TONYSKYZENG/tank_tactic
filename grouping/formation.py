import math
from typing import List, Tuple

def calculate_formation_slots(target_x: float, target_y: float, count: int,
                              spacing: float = 40.0) -> List[Tuple[float, float]]:
    """
    根据目标中心点与坦克数量，计算编队槽位坐标（紧凑方阵排列），防止多车重叠挤死。
    """
    if count <= 0:
        return []
    if count == 1:
        return [(target_x, target_y)]

    slots: List[Tuple[float, float]] = []
    # 计算行列数 (尽量接近正方形或矩形)
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)

    start_x = target_x - ((cols - 1) * spacing) / 2.0
    start_y = target_y - ((rows - 1) * spacing) / 2.0

    idx = 0
    for r in range(rows):
        for c in range(cols):
            if idx >= count:
                break
            sx = start_x + c * spacing
            sy = start_y + r * spacing
            slots.append((sx, sy))
            idx += 1

    return slots
