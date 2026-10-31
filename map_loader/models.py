from enum import IntEnum
from dataclasses import dataclass, field
from typing import List

class TileType(IntEnum):
    EMPTY = 0
    BRICK = 1   # 可被摧毁的砖块
    STEEL = 2   # 不可摧毁的铁块
    DARK_MATTER = 3  # 暗物质资源块
    ALLOY = 4        # 合金资源块
    BASE = 9    # 基地

@dataclass
class GameMap:
    name: str
    tile_size: int
    cols: int
    rows: int
    grid: List[List[int]] = field(default_factory=list)

    @property
    def pixel_width(self) -> int:
        return self.cols * self.tile_size

    @property
    def pixel_height(self) -> int:
        return self.rows * self.tile_size

    def get_tile(self, col: int, row: int) -> int:
        if 0 <= col < self.cols and 0 <= row < self.rows:
            return self.grid[row][col]
        return TileType.STEEL  # 地图外默认视为不可穿透

    def set_tile(self, col: int, row: int, tile_type: int) -> None:
        if 0 <= col < self.cols and 0 <= row < self.rows:
            self.grid[row][col] = tile_type

    def destroy_tile(self, col: int, row: int) -> bool:
        """尝试摧毁瓦片，返回是否成功销毁"""
        if 0 <= col < self.cols and 0 <= row < self.rows:
            if self.grid[row][col] in (TileType.BRICK, TileType.BASE):
                self.grid[row][col] = TileType.EMPTY
                return True
        return False
