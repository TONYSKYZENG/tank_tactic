import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

@dataclass
class ConverterRecipe:
    """多对多资源转换与战车单位制造配方定义"""
    id: str
    name: str  # 可翻译的多语言 key，如 converter.recipe.dm_to_alloy
    inputs: Dict[str, float] = field(default_factory=dict)   # 输入资源需求表，如 {"dark_matter": 10.0}，可为空字典或 None（免消耗）
    outputs: Any = field(default_factory=dict)               # 输出产出表，如 {"alloy": 5.0} 或 "tank"
    duration: float = 4.0                                    # 单次转换所需时间（秒）
    output_type: str = "resource"                            # 产出类型: "resource" (资源) 或 "tank" (战车单位)
    tank_config: Optional[str] = None                        # 若产出为 tank，可指定底盘模板 JSON 路径
    visibility: float = 1.0                                  # 若产出为 tank，新战车的可见性/辨识度
    vision_size: float = 280.0                               # 若产出为 tank，新战车的视野尺寸
    ammo: int = -1                                           # 若产出为 tank，新战车的初始弹药数目 (-1 为无限)

    def __post_init__(self):
        if self.inputs is None:
            self.inputs = {}
        if self.outputs == "tank" or (isinstance(self.outputs, dict) and "tank" in self.outputs) or self.output_type == "tank":
            self.output_type = "tank"
        self.output_type = str(self.output_type).lower()
        self.visibility = float(self.visibility)
        self.vision_size = float(self.vision_size)
        self.ammo = int(self.ammo)
        self.duration = float(self.duration)


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
    搭载于 Tank 实例上的战车级资源转换/制造机：
    - 支持绑定多张转换配方表 (converter_table)
    - 维持转换任务队列 (queue) 与当前活跃任务 (current_task)
    - 在转换活跃期间，通过 is_converting 状态约束单位不可机动、不可开火
    - 支持无 input 凭空产生资源 (inputs 为空或 None)
    - 支持 output 为 tank，自动按生产者 ID 生成子编号并在周边空地生成单位加入全局
    """

    def __init__(self, converter_table: Optional[List[str]] = None, owner: Optional[Any] = None):
        self.converter_table: List[str] = list(converter_table or [])
        self.owner: Optional[Any] = owner
        self.queue: List[ConversionTask] = []
        self.current_task: Optional[ConversionTask] = None
        self.produced_units_count: int = 0

    @property
    def is_converting(self) -> bool:
        return self.current_task is not None

    def supports_recipe(self, recipe_id: str) -> bool:
        return recipe_id in self.converter_table

    def enqueue(self, recipe: ConverterRecipe, count: int, resource_manager: Any, camp: str = "player") -> Tuple[bool, str]:
        """
        向队列追加转换任务：
        若当前无任务正在进行，且资源库满足初始批次消耗（若无需 input 则直接免消耗），则立即启动起跑；
        若已有任务在跑，则加入等待队列。
        """
        if not self.supports_recipe(recipe.id):
            return False, "unsupported_recipe"

        count = max(1, int(count))

        if self.current_task is None:
            # 立即启动首个任务
            if recipe.inputs:
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

    def update(self, dt: float, resource_manager: Any, camp: str = "player",
               physics_engine: Optional[Any] = None, game_map: Optional[Any] = None,
               command_dispatcher: Optional[Any] = None, ai_controller: Optional[Any] = None,
               base_dir: Optional[Any] = None) -> List[Any]:
        """随主循环 tick 推进转换进度，返回本 tick 生产出来的单位列表"""
        spawned_tanks: List[Any] = []

        if self.current_task is None:
            if self.queue:
                next_task = self.queue[0]
                if not next_task.recipe.inputs or resource_manager.has_enough(next_task.recipe.inputs, camp=camp):
                    self.queue.pop(0)
                    if next_task.recipe.inputs:
                        resource_manager.consume(next_task.recipe.inputs, camp=camp)
                    next_task.is_active = True
                    self.current_task = next_task
            return spawned_tanks

        # 推进当前活跃批次
        self.current_task.progress += dt
        if self.current_task.progress >= self.current_task.recipe.duration:
            # 达成单批次产出
            self._complete_batch(self.current_task.recipe, camp, resource_manager,
                                 physics_engine, game_map, command_dispatcher,
                                 ai_controller, base_dir, spawned_tanks)
            self.current_task.completed_count += 1
            self.current_task.progress = 0.0

            if self.current_task.completed_count < self.current_task.total_count:
                # 尝试投入下一批次
                if not self.current_task.recipe.inputs or resource_manager.has_enough(self.current_task.recipe.inputs, camp=camp):
                    if self.current_task.recipe.inputs:
                        resource_manager.consume(self.current_task.recipe.inputs, camp=camp)
                else:
                    # 资源不足无法继续剩余批次，提前结算退出
                    self.current_task = None
            else:
                # 全部批次完成
                self.current_task = None

        return spawned_tanks

    def _complete_batch(self, recipe: ConverterRecipe, camp: str, resource_manager: Any,
                        physics_engine: Optional[Any], game_map: Optional[Any],
                        command_dispatcher: Optional[Any], ai_controller: Optional[Any],
                        base_dir: Optional[Any], spawned_tanks: List[Any]) -> None:
        """处理单批次转换完成时的结算产出（资源注入或战车单位实例化与入场）"""
        if recipe.output_type == "tank":
            self.produced_units_count += 1
            producer_id = self.owner.id if (self.owner and hasattr(self.owner, "id")) else "tank"
            tank_id = f"{producer_id}/{self.produced_units_count}"

            from physics.entities import Camp, Tank, Rect
            from tank_configs.config_loader import TankConfig

            # 确定阵营归属
            if self.owner and hasattr(self.owner, "camp"):
                owner_camp = self.owner.camp
            elif str(camp).lower() in ("enemy", Camp.ENEMY.value):
                owner_camp = Camp.ENEMY
            else:
                owner_camp = Camp.PLAYER

            # 加载模板配置
            cfg = None
            if recipe.tank_config:
                cfg_p = Path(recipe.tank_config)
                if base_dir and (Path(base_dir) / cfg_p).exists():
                    try:
                        cfg = TankConfig.from_json(Path(base_dir) / cfg_p)
                    except Exception:
                        pass
                elif cfg_p.exists():
                    try:
                        cfg = TankConfig.from_json(cfg_p)
                    except Exception:
                        pass

            if cfg is None:
                default_file = "tank_configs/enemy_basic.json" if owner_camp == Camp.ENEMY else "tank_configs/player_tank.json"
                def_p = Path(default_file)
                if base_dir and (Path(base_dir) / def_p).exists():
                    try:
                        cfg = TankConfig.from_json(Path(base_dir) / def_p)
                    except Exception:
                        pass
                elif def_p.exists():
                    try:
                        cfg = TankConfig.from_json(def_p)
                    except Exception:
                        pass
                if cfg is None:
                    cfg = TankConfig(color="#E74C3C" if owner_camp == Camp.ENEMY else "#E69C24")

            # 在生产者周围寻找空地
            producer_x = getattr(self.owner, "x", 0.0)
            producer_y = getattr(self.owner, "y", 0.0)
            producer_size = getattr(self.owner, "size", cfg.size)
            tile_size = 36
            if physics_engine and hasattr(physics_engine, "game_map") and physics_engine.game_map:
                tile_size = getattr(physics_engine.game_map, "tile_size", 36)
            elif game_map:
                tile_size = getattr(game_map, "tile_size", 36)

            spawn_x, spawn_y = producer_x + producer_size, producer_y
            if physics_engine and hasattr(physics_engine, "find_nearest_free_position"):
                spawn_x, spawn_y = physics_engine.find_nearest_free_position(producer_x, producer_y, cfg.size)
                # 严格确保不与生产者自身重合或重叠
                owner_rect = self.owner.rect if (self.owner and hasattr(self.owner, "rect")) else Rect(producer_x, producer_y, producer_size, producer_size)
                if Rect(spawn_x, spawn_y, cfg.size, cfg.size).collides_with(owner_rect):
                    found = False
                    for radius in range(1, 10):
                        for r in range(-radius, radius + 1):
                            for c in range(-radius, radius + 1):
                                test_x = producer_x + c * tile_size
                                test_y = producer_y + r * tile_size
                                dummy = Tank(test_x, test_y, size=cfg.size)
                                if physics_engine.can_move_to(dummy, test_x, test_y) and not Rect(test_x, test_y, cfg.size, cfg.size).collides_with(owner_rect):
                                    spawn_x, spawn_y = test_x, test_y
                                    found = True
                                    break
                            if found:
                                break
                        if found:
                            break

            new_tank = Tank(
                x=spawn_x,
                y=spawn_y,
                size=cfg.size,
                speed=cfg.speed,
                camp=owner_camp,
                color=cfg.color,
                health=cfg.health,
                tank_id=tank_id,
                vision_size=recipe.vision_size,
                ammo=recipe.ammo,
                visibility=recipe.visibility,
                is_tower=cfg.is_tower,
                can_attack=cfg.can_attack,
                tower_type=cfg.tower_type,
                resupply_radius=cfg.resupply_radius,
                resupply_interval=cfg.resupply_interval,
                unit_type=cfg.name,
                controllable=True if owner_camp == Camp.PLAYER else False,
                ai_script=None,
                can_crush_bricks=getattr(cfg, "can_crush_bricks", False),
                crush_speed_factor=getattr(cfg, "crush_speed_factor", 0.5),
                converter_table=getattr(cfg, "converter_table", []),
                harvest_speed=getattr(cfg, "harvest_speed", None)
            )
            new_tank.fire_cooldown_max = cfg.fire_cooldown
            new_tank._config = cfg

            # 将新单位增加到全局状态
            if physics_engine:
                if owner_camp == Camp.ENEMY:
                    if ai_controller:
                        ai_controller.register_enemy(new_tank, cfg, tactic_name="patrol")
                    else:
                        physics_engine.add_enemy_tank(new_tank)
                    if command_dispatcher:
                        command_dispatcher.register_tank(new_tank)
                else:
                    physics_engine.add_player_tank(new_tank)
                    if command_dispatcher:
                        command_dispatcher.register_tank(new_tank)

            spawned_tanks.append(new_tank)

            # 若 outputs 中还声明了附带资源，一并产出
            if resource_manager and isinstance(recipe.outputs, dict):
                extra_res = {k: v for k, v in recipe.outputs.items() if k != "tank"}
                if extra_res:
                    resource_manager.add_resources(extra_res, camp=camp)
        else:
            if resource_manager and isinstance(recipe.outputs, dict):
                resource_manager.add_resources(recipe.outputs, camp=camp)

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
