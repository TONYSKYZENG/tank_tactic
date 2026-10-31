import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

@dataclass
class ConverterRecipe:
    """多对多资源转换配方定义"""
    id: str
    name: str  # 可翻译的多语言 key，如 converter.recipe.dm_to_alloy
    inputs: Dict[str, float]   # 输入资源需求表，如 {"dark_matter": 10.0}
    outputs: Dict[str, float]  # 输出产出表，如 {"alloy": 5.0}
    duration: float = 4.0      # 单次转换所需时间（秒）


@dataclass
class ConversionTask:
    """转换队列中的任务实例"""
    recipe: ConverterRecipe
    total_count: int
    completed_count: int = 0
    progress: float = 0.0  # 当前批次已运行秒数 (0.0 ~ recipe.duration)
    is_active: bool = False

    @property
    def progress_percentage(self) -> float:
        if self.recipe.duration <= 0:
            return 100.0
        return min(100.0, (self.progress / self.recipe.duration) * 100.0)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.recipe.duration - self.progress)


class UnitConverter:
    """
    搭载于 Tank 实例上的战车级资源转换器：
    - 支持绑定多张转换配方表 (converter_table)
    - 维持转换任务队列 (queue) 与当前活跃任务 (current_task)
    - 在转换活跃期间，通过 is_converting 状态约束单位不可机动、不可开火
    """

    def __init__(self, converter_table: Optional[List[str]] = None):
        self.converter_table: List[str] = list(converter_table or [])
        self.queue: List[ConversionTask] = []
        self.current_task: Optional[ConversionTask] = None

    @property
    def is_converting(self) -> bool:
        return self.current_task is not None

    def supports_recipe(self, recipe_id: str) -> bool:
        return recipe_id in self.converter_table

    def enqueue(self, recipe: ConverterRecipe, count: int, resource_manager: Any, camp: str = "player") -> Tuple[bool, str]:
        """
        向队列追加转换任务：
        若当前无任务正在进行，且资源库满足初始批次消耗，则立即扣费起跑；
        若已有任务在跑，则加入等待队列。
        """
        if not self.supports_recipe(recipe.id):
            return False, "unsupported_recipe"

        count = max(1, int(count))

        if self.current_task is None:
            # 立即启动首个任务
            if not resource_manager.has_enough(recipe.inputs, camp=camp):
                return False, "insufficient_resources"
            resource_manager.consume(recipe.inputs, camp=camp)
            self.current_task = ConversionTask(recipe=recipe, total_count=count, is_active=True)
            return True, "started"
        else:
            # 加入等待队列
            self.queue.append(ConversionTask(recipe=recipe, total_count=count, is_active=False))
            return True, "queued"

    def terminate(self) -> None:
        """清空所有转换队列并立即终止当前转换，恢复机动与开火能力"""
        self.current_task = None
        self.queue.clear()

    def update(self, dt: float, resource_manager: Any, camp: str = "player") -> None:
        """随主循环 tick 推进转换进度"""
        if self.current_task is None:
            if self.queue:
                next_task = self.queue[0]
                if resource_manager.has_enough(next_task.recipe.inputs, camp=camp):
                    self.queue.pop(0)
                    resource_manager.consume(next_task.recipe.inputs, camp=camp)
                    next_task.is_active = True
                    self.current_task = next_task
            return

        # 推进当前活跃批次
        self.current_task.progress += dt
        if self.current_task.progress >= self.current_task.recipe.duration:
            # 达成单批次产出
            resource_manager.add_resources(self.current_task.recipe.outputs, camp=camp)
            self.current_task.completed_count += 1
            self.current_task.progress = 0.0

            if self.current_task.completed_count < self.current_task.total_count:
                # 尝试投入下一批次
                if resource_manager.has_enough(self.current_task.recipe.inputs, camp=camp):
                    resource_manager.consume(self.current_task.recipe.inputs, camp=camp)
                else:
                    # 资源不足无法继续剩余批次，提前结算退出
                    self.current_task = None
            else:
                # 全部批次完成
                self.current_task = None

    def get_status_dict(self) -> Dict[str, Any]:
        """获取序列化转换状态字典，用于 UI 渲染与 API report"""
        if not self.is_converting or self.current_task is None:
            return {
                "is_converting": False,
                "current_recipe_id": None,
                "current_recipe_name": None,
                "progress_percentage": 0.0,
                "remaining_seconds": 0.0,
                "completed_count": 0,
                "total_count": 0,
                "queue_length": len(self.queue)
            }
        task = self.current_task
        return {
            "is_converting": True,
            "current_recipe_id": task.recipe.id,
            "current_recipe_name": task.recipe.name,
            "progress_percentage": round(task.progress_percentage, 1),
            "remaining_seconds": round(task.remaining_seconds, 1),
            "completed_count": task.completed_count,
            "total_count": task.total_count,
            "queue_length": len(self.queue)
        }
