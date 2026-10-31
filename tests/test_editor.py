import unittest
import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Set offscreen for headless testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtWidgets import QApplication

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from map_loader.models import GameMap, TileType
from mission_loader.models import Mission, PlayerMissionInfo, EnemyMissionInfo, SpawnPoint
from editor.canvas import EditorCanvas, EditorMode, TerrainTool
from editor.map_editor import MapEditorWidget
from editor.mission_editor import MissionEditorWidget
from editor.condition_editor import ConditionEditorWidget, ConditionNodeType
from editor.editor_window import EditorMainWindow
from conditions.builder import ConditionBuilder


class TestEditorComponents(unittest.TestCase):
    def setUp(self):
        self.game_map = GameMap(
            name="TestMap",
            tile_size=32,
            cols=10,
            rows=10,
            grid=[[TileType.EMPTY for _ in range(10)] for _ in range(10)]
        )

    def test_canvas_draw_and_box_fill(self):
        canvas = EditorCanvas(self.game_map)
        
        # Test single tile painting
        canvas.set_tile_type(TileType.BRICK)
        canvas.set_tool(TerrainTool.BRUSH)
        canvas.apply_brush_at_pixel(0, 0)
        self.assertEqual(canvas.game_map.grid[0][0], TileType.BRICK)

        # Test hover coordinate calculation
        coord_events = []
        canvas.hover_coord_changed.connect(lambda c, r, x, y, t: coord_events.append((c, r, x, y, t)))
        canvas._handle_mouse_move(40, 70)  # col 1, row 2
        self.assertTrue(len(coord_events) > 0)
        col, row, px, py, tile_val = coord_events[-1]
        self.assertEqual(col, 1)
        self.assertEqual(row, 2)
        self.assertEqual(px, 40)
        self.assertEqual(py, 70)

        # Test box fill
        canvas.set_tile_type(TileType.STEEL)
        canvas.apply_box_fill(2, 2, 4, 4)
        for r in range(2, 5):
            for c in range(2, 5):
                self.assertEqual(canvas.game_map.grid[r][c], TileType.STEEL)

        # Test Dark Matter and Alloy resource tile painting
        canvas.set_tile_type(TileType.DARK_MATTER)
        canvas.apply_brush_at_pixel(32, 32)
        self.assertEqual(canvas.game_map.grid[1][1], TileType.DARK_MATTER)

        canvas.set_tile_type(TileType.ALLOY)
        canvas.apply_brush_at_pixel(64, 64)
        self.assertEqual(canvas.game_map.grid[2][2], TileType.ALLOY)

    def test_map_editor_widget(self):
        canvas = EditorCanvas(self.game_map)
        map_widget = MapEditorWidget(canvas)
        self.assertIsNotNone(map_widget.canvas)
        
        # Test resizing map via spin boxes and apply button
        map_widget.spin_cols.setValue(15)
        map_widget.spin_rows.setValue(12)
        map_widget.spin_tile_size.setValue(32)
        map_widget.edit_name.setText("ResizedMap")
        map_widget._apply_map_resize()

        self.assertEqual(canvas.game_map.cols, 15)
        self.assertEqual(canvas.game_map.rows, 12)
        self.assertEqual(canvas.game_map.name, "ResizedMap")

    def test_mission_editor_widget(self):
        canvas = EditorCanvas(self.game_map)
        mission_widget = MissionEditorWidget(canvas, BASE_DIR)
        
        # Check that property inspector is in a QScrollArea (user requirement: scrollable property inspector)
        self.assertIsNotNone(mission_widget.prop_scroll_area)
        self.assertTrue(mission_widget.prop_scroll_area.widgetResizable())

        # Add player unit
        mission_widget._on_add_player_clicked()
        self.assertEqual(len(mission_widget.player_units), 1)
        player_unit = mission_widget.player_units[0]
        self.assertEqual(player_unit.id, "player_1")

        # Add enemy unit
        mission_widget._on_add_enemy_clicked()
        self.assertEqual(len(mission_widget.enemy_units), 1)
        enemy_unit = mission_widget.enemy_units[0]
        self.assertEqual(enemy_unit.id, "enemy_1")

        # Select player unit and modify properties via inspector
        mission_widget._select_unit(player_unit)
        mission_widget.edit_id.setText("player_alpha")
        mission_widget._on_prop_changed()
        self.assertEqual(player_unit.id, "player_alpha")

        mission_widget.chk_controllable.setChecked(False)
        mission_widget._on_prop_changed()
        self.assertFalse(player_unit.controllable)

        # Export mission data
        data = mission_widget.get_mission_data()
        self.assertEqual(data["name"], mission_widget.edit_mission_name.text())
        self.assertEqual(len(data["player_units"]), 1)
        self.assertEqual(data["player_units"][0]["id"], "player_alpha")
        self.assertFalse(data["player_units"][0]["controllable"])

        # Test creating new mission
        new_m = mission_widget.create_new_mission(map_file="maps/custom.json", mission_name="Brand New Mission")
        self.assertEqual(new_m.name, "Brand New Mission")
        self.assertEqual(new_m.map_file, "maps/custom.json")
        self.assertEqual(mission_widget.edit_mission_name.text(), "Brand New Mission")
        self.assertEqual(mission_widget.edit_map_file.text(), "maps/custom.json")
        self.assertEqual(len(mission_widget.player_units), 1)
        self.assertEqual(len(mission_widget.enemies), 1)

    def test_condition_editor_widget(self):
        cond_widget = ConditionEditorWidget()

        # Load condition dictionaries into tree
        vic_config = {
            "type": "and",
            "children": [
                {"type": "all_enemies_destroyed"},
                {"type": "unit_survive_time", "unit_id": "player_1", "duration": 30.0},
                {"type": "resource_amount", "resource_type": "dark_matter", "amount": 250.0}
            ]
        }
        def_config = {
            "type": "all_players_destroyed"
        }
        cond_widget.load_conditions(vic_config, def_config)

        # Serialize back from tree
        exported_vic, exported_def = cond_widget.export_conditions()
        self.assertIn("and", exported_vic)
        self.assertEqual(len(exported_vic["and"]), 3)
        self.assertEqual(exported_vic["and"][0]["type"], "all_enemies_destroyed")
        self.assertEqual(exported_vic["and"][1]["type"], "unit_survive_time")
        self.assertEqual(exported_vic["and"][1]["duration"], 30.0)
        self.assertEqual(exported_vic["and"][2]["type"], "resource_amount")
        self.assertEqual(exported_vic["and"][2]["amount"], 250.0)
        self.assertEqual(exported_def["type"], "all_players_destroyed")

        # Validate with game's ConditionBuilder
        built_vic = ConditionBuilder.build(exported_vic)
        built_def = ConditionBuilder.build(exported_def)
        self.assertIsNotNone(built_vic)
        self.assertIsNotNone(built_def)

    def test_main_editor_window(self):
        window = EditorMainWindow()
        self.assertIsNotNone(window.map_editor)
        self.assertIsNotNone(window.mission_editor)
        self.assertIsNotNone(window.condition_editor)

        # Test mode switching (Mode 1: 地形, Mode 2: 任务/单位, Mode 3: 胜负条件)
        window.switch_mode(0)
        self.assertEqual(window.stack.currentIndex(), 0)
        window.switch_mode(1)
        self.assertEqual(window.stack.currentIndex(), 1)
        window.switch_mode(2)
        self.assertEqual(window.stack.currentIndex(), 2)

        # Ensure unit list is synchronized to condition editor when switching to Mode 3
        window.mission_editor._on_add_player_clicked()
        window.mission_editor._on_add_enemy_clicked()
        p_id = window.mission_editor.player_units[-1].id
        e_id = window.mission_editor.enemies[-1].id
        window.switch_mode(2)
        unit_ids = window.condition_editor.unit_ids
        self.assertIn(p_id, unit_ids)
        self.assertIn(e_id, unit_ids)

        # Test triggering new mission in window
        window._on_new_mission()
        self.assertIsNone(window.current_mission_path)
        self.assertEqual(window.stack.currentIndex(), 1)  # Automatically jumps to Mission Mode
        self.assertEqual(window.mission_editor.edit_mission_name.text(), "New Campaign Mission")

    def test_dynamic_resource_palette_and_initial_resources_dropdown(self):
        """测试要求 2 & 3：地图编辑器从 JSON 动态读取资源块，以及任务编辑器敌我双方初始资源下拉编辑"""
        canvas = EditorCanvas(self.game_map)
        map_widget = MapEditorWidget(canvas)

        # 1. 验证地图编辑器瓦片面板并非写死，而是动态包含 resource/*.json 中定义的所有资源
        resource_types_in_palette = [info[2] for info in map_widget.tiles_info]
        self.assertIn("dark_matter", resource_types_in_palette)
        self.assertIn("alloy", resource_types_in_palette)
        self.assertIn("brick", resource_types_in_palette)
        self.assertIn("steel", resource_types_in_palette)

        # 2. 任务编辑器初始资源下拉列表编辑验证
        mission_widget = MissionEditorWidget(canvas)
        mission_widget.create_new_mission()

        # 初始我方资源
        self.assertEqual(mission_widget.player_initial_resources.get("dark_matter"), 100.0)
        self.assertEqual(mission_widget.player_initial_resources.get("alloy"), 50.0)

        # 切换到敌方 (索引 1) 并修改暗物质
        mission_widget.combo_res_camp.setCurrentIndex(1)  # 敌方
        # 选择 dark_matter
        dm_idx = mission_widget.combo_res_type.findData("dark_matter")
        if dm_idx != -1:
            mission_widget.combo_res_type.setCurrentIndex(dm_idx)
        mission_widget.spin_res_amount.setValue(250.0)

        self.assertEqual(mission_widget.enemy_initial_resources.get("dark_matter"), 250.0)

        # 切换回我方 (索引 0) 并修改合金
        mission_widget.combo_res_camp.setCurrentIndex(0)
        alloy_idx = mission_widget.combo_res_type.findData("alloy")
        if alloy_idx != -1:
            mission_widget.combo_res_type.setCurrentIndex(alloy_idx)
        mission_widget.spin_res_amount.setValue(320.0)

        self.assertEqual(mission_widget.player_initial_resources.get("alloy"), 320.0)

        # 导出任务数据检验
        m_data = mission_widget.get_mission_data()
        self.assertEqual(m_data["player_initial_resources"]["alloy"], 320.0)
        self.assertEqual(m_data["enemy_initial_resources"]["dark_matter"], 250.0)


if __name__ == "__main__":
    unittest.main()
