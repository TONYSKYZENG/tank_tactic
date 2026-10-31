import unittest
import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtWidgets import QApplication

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from translations import i18n, t, tr, I18nManager
from editor.editor_window import EditorMainWindow
from gui.main_window import MainWindow
from map_loader.loader import MapLoader
from mission_loader.loader import MissionLoader


class TestI18nSystem(unittest.TestCase):
    def setUp(self):
        # 默认恢复中文
        i18n.set_language("zh")

    def test_yaml_files_loaded(self):
        langs = i18n.get_available_languages()
        self.assertIn("zh", langs)
        self.assertIn("en", langs)

    def test_translation_lookups(self):
        i18n.set_language("zh")
        self.assertEqual(t("editor.modes.map"), "⚔ 模式 1：地图建造")
        self.assertEqual(t("game.base_safe"), "安全")

        i18n.set_language("en")
        self.assertEqual(t("editor.modes.map"), "⚔ Mode 1: Terrain")
        self.assertEqual(t("game.base_safe"), "Safe")

    def test_formatting_and_fallback(self):
        i18n.set_language("zh")
        formatted = t("game.ammo_count", ammo=25)
        self.assertEqual(formatted, "弹药:25")

        i18n.set_language("en")
        formatted_en = t("game.ammo_count", ammo=25)
        self.assertEqual(formatted_en, "Ammo:25")

        # Unknown key fallback
        fallback = t("non_existent.nested.key", default="DefaultVal")
        self.assertEqual(fallback, "DefaultVal")

    def test_signal_emission(self):
        emitted = []
        i18n.language_changed.connect(lambda lang: emitted.append(lang))
        i18n.set_language("en")
        self.assertIn("en", emitted)
        i18n.set_language("zh")
        self.assertIn("zh", emitted)

    def test_editor_gui_language_switch(self):
        i18n.set_language("zh")
        win = EditorMainWindow()
        self.assertIn("地图建造", win.btn_mode_map.text())
        self.assertIn("单格画笔", win.map_editor.btn_brush.text())
        self.assertIn("我方单位", win.mission_editor.btn_add_player.text())

        # Switch to EN
        win.combo_lang.setCurrentIndex(1)
        self.assertEqual(i18n.get_language(), "en")
        self.assertIn("Terrain", win.btn_mode_map.text())
        self.assertIn("Brush", win.map_editor.btn_brush.text())
        self.assertIn("Allied Unit", win.mission_editor.btn_add_player.text())

        # Switch back to ZH
        win.combo_lang.setCurrentIndex(0)
        self.assertEqual(i18n.get_language(), "zh")
        self.assertIn("地图建造", win.btn_mode_map.text())
        self.assertIn("单格画笔", win.map_editor.btn_brush.text())

    def test_game_gui_language_switch(self):
        gmap = MapLoader.load_from_file(BASE_DIR / "maps/level_01.json")
        mission = MissionLoader.load_from_file(BASE_DIR / "missions/mission_01.json")
        win_game = MainWindow(mission, gmap, BASE_DIR)

        i18n.set_language("zh")
        self.assertIn("框选", win_game.help_label.text())

        win_game.combo_lang.setCurrentIndex(1)
        self.assertEqual(i18n.get_language(), "en")
        self.assertIn("Controls", win_game.help_label.text())
        self.assertIn("Battle City", win_game.windowTitle())

        win_game.combo_lang.setCurrentIndex(0)
        self.assertEqual(i18n.get_language(), "zh")
        self.assertIn("框选", win_game.help_label.text())


if __name__ == "__main__":
    unittest.main()
