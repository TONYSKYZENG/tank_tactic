import json
from typing import Optional, Dict, Any, List, Union, Tuple
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QGroupBox, QSpinBox, QDoubleSpinBox, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QSplitter, QPlainTextEdit, QMessageBox, QTabWidget, QHeaderView, QFrame, QMenu
)
from PyQt5.QtGui import QFont, QColor, QIcon
from PyQt5.QtCore import Qt, pyqtSignal

from conditions.builder import ConditionBuilder
from translations import i18n, t

class ConditionNodeType:
    # 复合逻辑节点
    AND = "and"
    OR = "or"
    NOT = "not"
    # 条件原语
    ALL_ENEMIES_DESTROYED = "all_enemies_destroyed"
    ALL_PLAYERS_DESTROYED = "all_players_destroyed"
    UNIT_DESTROYED = "unit_destroyed"
    UNIT_SURVIVE_TIME = "unit_survive_time"
    AREA_VISIBLE = "area_visible"
    RESOURCE_AMOUNT = "resource_amount"
    CONSTANT = "constant"


class ConditionEditorWidget(QWidget):
    """
    【模式 3：可视化树状结构编辑胜利/失败条件】
    - 使用 QTreeWidget 树形多级层级结构可视化构建与编排胜利与失败判定逻辑
    - 支持 AND (与), OR (或), NOT (非) 多层嵌套逻辑树
    - 支持全歼敌军、指定关键单位存活时长、关键战车击毁、区域侦察侦测等条件原语
    - 动态单位下拉选择、实时参数检视与实时 JSON 语法校验预览
    """

    condition_modified = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.available_unit_ids: List[str] = []
        self._init_ui()
        self.retranslate_ui()

    def retranslate_ui(self):
        self.tab_widget.setTabText(0, t("editor.condition.tab_victory"))
        self.tab_widget.setTabText(1, t("editor.condition.tab_defeat"))

        for tools in (self.victory_tools, self.defeat_tools):
            if "and" in tools:
                tools["and"].setText(t("editor.condition.add_and"))
            if "or" in tools:
                tools["or"].setText(t("editor.condition.add_or"))
            if "not" in tools:
                tools["not"].setText(t("editor.condition.add_not"))
            if "leaf" in tools:
                tools["leaf"].setText(t("editor.condition.add_primitive"))
            if "delete" in tools:
                tools["delete"].setText(t("editor.condition.del_node"))

        self.prop_title.setText(t("editor.condition.node_props"))
        self.lbl_target_unit_tag.setText(t("editor.condition.target_unit"))
        self.lbl_survive_time_tag.setText(t("editor.condition.survive_time"))
        self.json_group.setTitle(t("editor.condition.json_preview"))
        self.btn_validate.setText(t("editor.condition.validate"))

    @property
    def unit_ids(self) -> List[str]:
        return self.available_unit_ids

    def set_unit_ids(self, unit_ids: List[str]):
        """从模式2同步当前任务所有可用单位 ID，用于下拉选择"""
        self.available_unit_ids = unit_ids
        self._refresh_unit_id_dropdown()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 顶部选项卡：切换 🏆 获胜条件 与 💀 失败条件
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabBar::tab { height: 32px; font-weight: bold; }
        """)

        # 获胜条件树页面
        self.victory_page = QWidget()
        self.victory_tree, self.victory_tools = self._create_tree_page("victory")
        self.tab_widget.addTab(self.victory_page, "🏆 获胜条件树 (Victory Conditions)")

        # 失败条件树页面
        self.defeat_page = QWidget()
        self.defeat_tree, self.defeat_tools = self._create_tree_page("defeat")
        self.tab_widget.addTab(self.defeat_page, "💀 失败条件树 (Defeat Conditions)")

        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # 左右分割面板：左边树 + 按钮，右边属性配置与实时 JSON
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.tab_widget)

        # 右侧：属性检视面板 + 实时 JSON
        right_panel = QFrame()
        right_panel.setFixedWidth(380)
        right_panel.setStyleSheet("background-color: #221E19; border: 1px solid #4D3C26; border-radius: 4px;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(12)

        self.prop_title = QLabel("⚙ 条件节点参数配置")
        self.prop_title.setFont(QFont("Palatino", 13, QFont.Bold))
        self.prop_title.setStyleSheet("color: #F1C40F; border: none;")
        right_layout.addWidget(self.prop_title)

        # 节点属性编辑表单
        self.prop_box = QGroupBox("选中节点参数")
        self.prop_box_layout = QVBoxLayout(self.prop_box)

        # 1. 节点类型标签
        self.lbl_node_type = QLabel("当前选中: (未选择节点)")
        self.lbl_node_type.setStyleSheet("color: #E6C66E; font-weight: bold;")
        self.prop_box_layout.addWidget(self.lbl_node_type)

        # 2. 目标单位选择
        self.unit_field_widget = QWidget()
        u_layout = QHBoxLayout(self.unit_field_widget)
        u_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_target_unit_tag = QLabel("目标单位 ID:")
        u_layout.addWidget(self.lbl_target_unit_tag)
        self.combo_target_unit = QComboBox()
        self.combo_target_unit.setEditable(True)
        self.combo_target_unit.currentTextChanged.connect(self._on_prop_input_changed)
        u_layout.addWidget(self.combo_target_unit)
        self.prop_box_layout.addWidget(self.unit_field_widget)

        # 3. 存活秒数
        self.time_field_widget = QWidget()
        t_layout = QHBoxLayout(self.time_field_widget)
        t_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_survive_time_tag = QLabel("存活时长 (秒):")
        t_layout.addWidget(self.lbl_survive_time_tag)
        self.spin_seconds = QDoubleSpinBox()
        self.spin_seconds.setRange(1.0, 3600.0)
        self.spin_seconds.setValue(30.0)
        self.spin_seconds.valueChanged.connect(self._on_prop_input_changed)
        t_layout.addWidget(self.spin_seconds)
        self.prop_box_layout.addWidget(self.time_field_widget)

        # 4. 侦察区域 (Area)
        self.area_field_widget = QWidget()
        a_layout = QVBoxLayout(self.area_field_widget)
        a_layout.setContentsMargins(0, 0, 0, 0)
        a_layout.addWidget(QLabel("侦测目标区域 (瓦片坐标):"))

        grid_a = QHBoxLayout()
        grid_a.addWidget(QLabel("列 X:"))
        self.spin_area_x = QSpinBox()
        self.spin_area_x.setRange(0, 100)
        self.spin_area_x.valueChanged.connect(self._on_prop_input_changed)
        grid_a.addWidget(self.spin_area_x)

        grid_a.addWidget(QLabel("行 Y:"))
        self.spin_area_y = QSpinBox()
        self.spin_area_y.setRange(0, 100)
        self.spin_area_y.valueChanged.connect(self._on_prop_input_changed)
        grid_a.addWidget(self.spin_area_y)
        a_layout.addLayout(grid_a)

        grid_b = QHBoxLayout()
        grid_b.addWidget(QLabel("宽 W:"))
        self.spin_area_w = QSpinBox()
        self.spin_area_w.setRange(1, 20)
        self.spin_area_w.setValue(4)
        self.spin_area_w.valueChanged.connect(self._on_prop_input_changed)
        grid_b.addWidget(self.spin_area_w)

        grid_b.addWidget(QLabel("高 H:"))
        self.spin_area_h = QSpinBox()
        self.spin_area_h.setRange(1, 20)
        self.spin_area_h.setValue(4)
        self.spin_area_h.valueChanged.connect(self._on_prop_input_changed)
        grid_b.addWidget(self.spin_area_h)
        a_layout.addLayout(grid_b)

        self.prop_box_layout.addWidget(self.area_field_widget)

        # 4.5 资源储备达成 (Resource Amount)
        self.resource_field_widget = QWidget()
        r_layout = QVBoxLayout(self.resource_field_widget)
        r_layout.setContentsMargins(0, 0, 0, 0)

        r_sub1 = QHBoxLayout()
        r_sub1.addWidget(QLabel("资源种类:"))
        self.combo_res_type = QComboBox()
        self.combo_res_type.addItem("🔮 暗物质 (dark_matter)", "dark_matter")
        self.combo_res_type.addItem("⚙️ 合金 (alloy)", "alloy")
        self.combo_res_type.currentIndexChanged.connect(self._on_prop_input_changed)
        r_sub1.addWidget(self.combo_res_type)
        r_layout.addLayout(r_sub1)

        r_sub2 = QHBoxLayout()
        r_sub2.addWidget(QLabel("目标储备数量:"))
        self.spin_res_amount = QDoubleSpinBox()
        self.spin_res_amount.setRange(1.0, 999999.0)
        self.spin_res_amount.setValue(100.0)
        self.spin_res_amount.valueChanged.connect(self._on_prop_input_changed)
        r_sub2.addWidget(self.spin_res_amount)
        r_layout.addLayout(r_sub2)

        self.prop_box_layout.addWidget(self.resource_field_widget)

        # 5. 常量说明
        self.desc_field_widget = QWidget()
        d_layout = QHBoxLayout(self.desc_field_widget)
        d_layout.setContentsMargins(0, 0, 0, 0)
        d_layout.addWidget(QLabel("条件描述:"))
        self.edit_description = QLineEdit()
        self.edit_description.textChanged.connect(self._on_prop_input_changed)
        d_layout.addWidget(self.edit_description)
        self.prop_box_layout.addWidget(self.desc_field_widget)

        right_layout.addWidget(self.prop_box)

        # 实时语法校验与 JSON 预览
        self.json_group = QGroupBox("📜 实时条件语法预览 & 校验")
        json_layout = QVBoxLayout(self.json_group)

        self.txt_json_preview = QPlainTextEdit()
        self.txt_json_preview.setReadOnly(True)
        self.txt_json_preview.setStyleSheet("font-family: 'Courier New'; font-size: 11px; background: #12100E; color: #58D68D; border: 1px solid #3E301E;")
        json_layout.addWidget(self.txt_json_preview)

        self.btn_validate = QPushButton("✓ 校验条件语法合法性")
        self.btn_validate.setStyleSheet("background-color: #27AE60; border: 1px solid #A9DFBF; color: #FFFFFF;")
        self.btn_validate.clicked.connect(self._validate_current_conditions)
        json_layout.addWidget(self.btn_validate)

        right_layout.addWidget(self.json_group)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter)
        self._update_prop_panel_visibility(None)

    def _create_tree_page(self, page_type: str) -> Tuple[QTreeWidget, Dict[str, QPushButton]]:
        container = self.victory_page if page_type == "victory" else self.defeat_page
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 工具栏按钮
        tools_layout = QHBoxLayout()

        btn_add_and = QPushButton("＋ 与节点 (AND)")
        btn_add_and.setStyleSheet("background-color: #3E2723; border: 1px solid #8D6E63; color: #FFCCBC;")
        btn_add_and.clicked.connect(lambda: self._add_composite_node(ConditionNodeType.AND))
        tools_layout.addWidget(btn_add_and)

        btn_add_or = QPushButton("＋ 或节点 (OR)")
        btn_add_or.setStyleSheet("background-color: #1A365D; border: 1px solid #2B6CB0; color: #BEE3F8;")
        btn_add_or.clicked.connect(lambda: self._add_composite_node(ConditionNodeType.OR))
        tools_layout.addWidget(btn_add_or)

        btn_add_not = QPushButton("＋ 非节点 (NOT)")
        btn_add_not.setStyleSheet("background-color: #4A1A40; border: 1px solid #8E44AD; color: #E8DAEF;")
        btn_add_not.clicked.connect(lambda: self._add_composite_node(ConditionNodeType.NOT))
        tools_layout.addWidget(btn_add_not)

        btn_add_leaf = QPushButton("＋ 添加条件原语")
        btn_add_leaf.setStyleSheet("background-color: #2E4053; border: 1px solid #5D6D7E; color: #D5D8DC;")
        btn_add_leaf.clicked.connect(self._on_add_primitive_clicked)
        tools_layout.addWidget(btn_add_leaf)

        btn_delete = QPushButton("－ 删除节点")
        btn_delete.clicked.connect(self._delete_selected_node)
        tools_layout.addWidget(btn_delete)

        layout.addLayout(tools_layout)

        # 树状控件
        tree = QTreeWidget()
        tree.setHeaderLabels(["逻辑层级结构 (Logic Tree)", "参数与描述 (Parameters)"])
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        tree.setStyleSheet("background-color: #151310; border: 1px solid #5C482C; font-size: 13px;")
        tree.itemSelectionChanged.connect(self._on_tree_selection_changed)

        layout.addWidget(tree, stretch=1)

        tools = {
            "and": btn_add_and,
            "or": btn_add_or,
            "not": btn_add_not,
            "leaf": btn_add_leaf,
            "del": btn_delete
        }
        return tree, tools

    def _get_active_tree(self) -> QTreeWidget:
        return self.victory_tree if self.tab_widget.currentIndex() == 0 else self.defeat_tree

    # ================= 树节点构造与序列化 =================

    def load_conditions(self, victory_conf: Any, defeat_conf: Any):
        self.victory_tree.clear()
        self.defeat_tree.clear()

        # 加载胜利条件树
        if victory_conf:
            self._parse_config_into_tree(self.victory_tree, victory_conf)
        else:
            # 默认：全歼敌军
            item = QTreeWidgetItem(["全歼敌军 [all_enemies_destroyed]", "消灭战场上所有敌对装甲单位"])
            item.setData(0, Qt.UserRole, {"type": ConditionNodeType.ALL_ENEMIES_DESTROYED})
            item.setForeground(0, QColor("#58D68D"))
            self.victory_tree.addTopLevelItem(item)

        # 加载失败条件树
        if defeat_conf:
            self._parse_config_into_tree(self.defeat_tree, defeat_conf)
        else:
            # 默认：我方全灭
            item = QTreeWidgetItem(["我方全军覆没 [all_players_destroyed]", "己方所有战车与防御设施均被击毁"])
            item.setData(0, Qt.UserRole, {"type": ConditionNodeType.ALL_PLAYERS_DESTROYED})
            item.setForeground(0, QColor("#E74C3C"))
            self.defeat_tree.addTopLevelItem(item)

        self.victory_tree.expandAll()
        self.defeat_tree.expandAll()
        self._update_json_preview()

    def _parse_config_into_tree(self, tree_or_item: Union[QTreeWidget, QTreeWidgetItem], config: Any):
        if config is None:
            return

        if isinstance(config, list):
            # 列表默认视为 AND
            parent_node = self._create_tree_item(ConditionNodeType.AND, tree_or_item)
            for c in config:
                self._parse_config_into_tree(parent_node, c)
            return

        if isinstance(config, str):
            c_str = config.lower().strip()
            self._create_tree_item(c_str, tree_or_item)
            return

        if not isinstance(config, dict):
            return

        # 快捷语法 {"and": [...]}, {"or": [...]}, {"not": {...}}
        if "and" in config:
            node = self._create_tree_item(ConditionNodeType.AND, tree_or_item)
            subs = config["and"] if isinstance(config["and"], list) else [config["and"]]
            for s in subs:
                self._parse_config_into_tree(node, s)
            return

        if "or" in config:
            node = self._create_tree_item(ConditionNodeType.OR, tree_or_item)
            subs = config["or"] if isinstance(config["or"], list) else [config["or"]]
            for s in subs:
                self._parse_config_into_tree(node, s)
            return

        if "not" in config:
            node = self._create_tree_item(ConditionNodeType.NOT, tree_or_item)
            self._parse_config_into_tree(node, config["not"])
            return

        # type 格式
        c_type = config.get("type", "").lower()
        if c_type in (ConditionNodeType.AND, ConditionNodeType.OR):
            node = self._create_tree_item(c_type, tree_or_item)
            child_list = config.get("conditions") or config.get("children", [])
            for c in child_list:
                self._parse_config_into_tree(node, c)
        elif c_type == ConditionNodeType.NOT:
            node = self._create_tree_item(c_type, tree_or_item)
            sub = config.get("condition") or config.get("conditions") or config.get("child")
            self._parse_config_into_tree(node, sub)
        else:
            self._create_tree_item(c_type, tree_or_item, config)

    def _create_tree_item(self, node_type: str, parent: Union[QTreeWidget, QTreeWidgetItem], raw_dict: Optional[Dict] = None) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        data = dict(raw_dict) if raw_dict else {"type": node_type}
        data["type"] = node_type
        item.setData(0, Qt.UserRole, data)

        self._refresh_item_display(item)

        if isinstance(parent, QTreeWidget):
            parent.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    def _refresh_item_display(self, item: QTreeWidgetItem):
        data = item.data(0, Qt.UserRole) or {}
        ntype = data.get("type", "")

        if ntype == ConditionNodeType.AND:
            item.setText(0, "🔀 [逻辑与] AND 节点")
            item.setText(1, "当且仅当所有子条件均达成")
            item.setForeground(0, QColor("#F39C12"))
        elif ntype == ConditionNodeType.OR:
            item.setText(0, "🔀 [逻辑或] OR 节点")
            item.setText(1, "任意一个子条件达成即可")
            item.setForeground(0, QColor("#3498DB"))
        elif ntype == ConditionNodeType.NOT:
            item.setText(0, "⛔ [逻辑非] NOT 节点")
            item.setText(1, "反转子条件的达成判定")
            item.setForeground(0, QColor("#9B59B6"))
        elif ntype == ConditionNodeType.ALL_ENEMIES_DESTROYED:
            item.setText(0, "⚔ 全歼敌军 [all_enemies_destroyed]")
            item.setText(1, "消灭战场全部存活敌方战车与要塞")
            item.setForeground(0, QColor("#2ECC71"))
        elif ntype == ConditionNodeType.ALL_PLAYERS_DESTROYED:
            item.setText(0, "☠ 我方全灭 [all_players_destroyed]")
            item.setText(1, "己方全部存活战车与要塞阵亡")
            item.setForeground(0, QColor("#E74C3C"))
        elif ntype == ConditionNodeType.UNIT_DESTROYED:
            uid = data.get("unit_id", "未指定")
            item.setText(0, f"🎯 摧毁指定单位 [unit_destroyed]")
            item.setText(1, f"目标单位: '{uid}' 阵亡")
            item.setForeground(0, QColor("#E67E22"))
        elif ntype == ConditionNodeType.UNIT_SURVIVE_TIME:
            uid = data.get("unit_id", "未指定")
            sec = data.get("seconds", 30.0)
            item.setText(0, f"⏳ 单位存活计时 [unit_survive_time]")
            item.setText(1, f"确保 '{uid}' 存活达到 {sec} 秒")
            item.setForeground(0, QColor("#F1C40F"))
        elif ntype == ConditionNodeType.AREA_VISIBLE:
            tx = data.get("tile_x", 0)
            ty = data.get("tile_y", 0)
            tw = data.get("tile_w", 4)
            th = data.get("tile_h", 4)
            item.setText(0, "🔭 探索指定区域 [area_visible]")
            item.setText(1, f"侦察瓦片矩形区域 ({tx}, {ty}) 尺寸 {tw}x{th}")
            item.setForeground(0, QColor("#1ABC9C"))
        elif ntype == ConditionNodeType.RESOURCE_AMOUNT:
            res = data.get("resource_type", "dark_matter")
            amt = data.get("amount", 100.0)
            res_display = "暗物质" if res == "dark_matter" else ("合金" if res == "alloy" else res)
            item.setText(0, "💎 资源储备达成 [resource_amount]")
            item.setText(1, f"拥有 [{res_display}] 达到 {amt:g}")
            item.setForeground(0, QColor("#00E5FF"))
        elif ntype == ConditionNodeType.CONSTANT:
            desc = data.get("description", "常量")
            val = data.get("value", True)
            item.setText(0, f"⚙ 常量条件 [constant]")
            item.setText(1, f"状态: {val} | 描述: {desc}")
            item.setForeground(0, QColor("#BDC3C7"))

    def export_conditions(self) -> Tuple[Optional[Any], Optional[Any]]:
        """导出当前树结构为标准 JSON 格式胜利与失败条件字典"""
        vic = self._serialize_tree(self.victory_tree)
        defa = self._serialize_tree(self.defeat_tree)
        return vic, defa

    def _serialize_tree(self, tree: QTreeWidget) -> Optional[Any]:
        if tree.topLevelItemCount() == 0:
            return None
        if tree.topLevelItemCount() == 1:
            return self._serialize_item(tree.topLevelItem(0))

        # 多个顶层节点，默认使用 OR 包含
        children = [self._serialize_item(tree.topLevelItem(i)) for i in range(tree.topLevelItemCount())]
        return {"or": children}

    def _serialize_item(self, item: QTreeWidgetItem) -> Any:
        data = dict(item.data(0, Qt.UserRole) or {})
        ntype = data.get("type", "")

        if ntype in (ConditionNodeType.AND, ConditionNodeType.OR):
            children = [self._serialize_item(item.child(i)) for i in range(item.childCount())]
            return {ntype: children}
        elif ntype == ConditionNodeType.NOT:
            sub = self._serialize_item(item.child(0)) if item.childCount() > 0 else {"type": "constant", "value": False}
            return {"not": sub}
        else:
            return data

    # ================= 节点编辑与操作 =================

    def _add_composite_node(self, c_type: str):
        tree = self._get_active_tree()
        curr_item = tree.currentItem()

        if curr_item and curr_item.data(0, Qt.UserRole).get("type") in (ConditionNodeType.AND, ConditionNodeType.OR, ConditionNodeType.NOT):
            node = self._create_tree_item(c_type, curr_item)
            curr_item.setExpanded(True)
        else:
            node = self._create_tree_item(c_type, tree)

        tree.setCurrentItem(node)
        self._update_json_preview()
        self.condition_modified.emit()

    def _on_add_primitive_clicked(self):
        tree = self._get_active_tree()
        curr_item = tree.currentItem()

        menu = QMenu(self)
        menu.setStyleSheet("background-color: #24201A; color: #E8D8A0; border: 1px solid #6D532C;")

        act_destroy = menu.addAction("🎯 摧毁指定单位 (unit_destroyed)")
        act_survive = menu.addAction("⏳ 单位存活计时 (unit_survive_time)")
        act_area = menu.addAction("🔭 探索指定区域 (area_visible)")
        act_resource = menu.addAction("💎 资源储备达成 (resource_amount)")
        act_all_enemies = menu.addAction("⚔ 全歼敌军 (all_enemies_destroyed)")
        act_all_players = menu.addAction("☠ 我方全灭 (all_players_destroyed)")

        action = menu.exec_(self.cursor().pos())
        if not action:
            return

        default_target = self.available_unit_ids[0] if self.available_unit_ids else "player_alpha"

        if action == act_destroy:
            ntype = ConditionNodeType.UNIT_DESTROYED
            data = {"type": ntype, "unit_id": default_target}
        elif action == act_survive:
            ntype = ConditionNodeType.UNIT_SURVIVE_TIME
            data = {"type": ntype, "unit_id": default_target, "seconds": 30.0}
        elif action == act_area:
            ntype = ConditionNodeType.AREA_VISIBLE
            data = {"type": ntype, "tile_x": 0, "tile_y": 0, "tile_w": 4, "tile_h": 4}
        elif action == act_resource:
            ntype = ConditionNodeType.RESOURCE_AMOUNT
            data = {"type": ntype, "resource_type": "dark_matter", "amount": 100.0}
        elif action == act_all_enemies:
            ntype = ConditionNodeType.ALL_ENEMIES_DESTROYED
            data = {"type": ntype}
        elif action == act_all_players:
            ntype = ConditionNodeType.ALL_PLAYERS_DESTROYED
            data = {"type": ntype}
        else:
            return

        target_parent = tree
        if curr_item and curr_item.data(0, Qt.UserRole).get("type") in (ConditionNodeType.AND, ConditionNodeType.OR, ConditionNodeType.NOT):
            target_parent = curr_item

        item = self._create_tree_item(ntype, target_parent, data)
        tree.setCurrentItem(item)
        self._update_json_preview()
        self.condition_modified.emit()

    def _delete_selected_node(self):
        tree = self._get_active_tree()
        curr = tree.currentItem()
        if not curr:
            return
        parent = curr.parent()
        if parent:
            parent.removeChild(curr)
        else:
            idx = tree.indexOfTopLevelItem(curr)
            tree.takeTopLevelItem(idx)

        self._update_prop_panel_visibility(None)
        self._update_json_preview()
        self.condition_modified.emit()

    def _on_tree_selection_changed(self):
        tree = self._get_active_tree()
        curr = tree.currentItem()
        if not curr:
            self._update_prop_panel_visibility(None)
            return

        data = curr.data(0, Qt.UserRole) or {}
        self._populate_node_properties(data)

    def _populate_node_properties(self, data: Dict[str, Any]):
        ntype = data.get("type", "")
        self.lbl_node_type.setText(f"当前节点: 【{ntype.upper()}】")
        self._update_prop_panel_visibility(ntype)

        self.block_prop_signals(True)

        if ntype in (ConditionNodeType.UNIT_DESTROYED, ConditionNodeType.UNIT_SURVIVE_TIME):
            uid = data.get("unit_id", "")
            self.combo_target_unit.setCurrentText(uid)

        if ntype == ConditionNodeType.UNIT_SURVIVE_TIME:
            self.spin_seconds.setValue(float(data.get("seconds", 30.0)))

        if ntype == ConditionNodeType.AREA_VISIBLE:
            self.spin_area_x.setValue(int(data.get("tile_x", 0)))
            self.spin_area_y.setValue(int(data.get("tile_y", 0)))
            self.spin_area_w.setValue(int(data.get("tile_w", 4)))
            self.spin_area_h.setValue(int(data.get("tile_h", 4)))

        if ntype == ConditionNodeType.RESOURCE_AMOUNT:
            res = data.get("resource_type", "dark_matter")
            idx = 0 if res == "dark_matter" else 1
            self.combo_res_type.setCurrentIndex(idx)
            self.spin_res_amount.setValue(float(data.get("amount", 100.0)))

        if ntype == ConditionNodeType.CONSTANT:
            self.edit_description.setText(data.get("description", ""))

        self.block_prop_signals(False)

    def _update_prop_panel_visibility(self, ntype: Optional[str]):
        if not ntype or ntype in (ConditionNodeType.AND, ConditionNodeType.OR, ConditionNodeType.NOT, ConditionNodeType.ALL_ENEMIES_DESTROYED, ConditionNodeType.ALL_PLAYERS_DESTROYED):
            self.unit_field_widget.setVisible(False)
            self.time_field_widget.setVisible(False)
            self.area_field_widget.setVisible(False)
            self.resource_field_widget.setVisible(False)
            self.desc_field_widget.setVisible(False)
            return

        self.unit_field_widget.setVisible(ntype in (ConditionNodeType.UNIT_DESTROYED, ConditionNodeType.UNIT_SURVIVE_TIME))
        self.time_field_widget.setVisible(ntype == ConditionNodeType.UNIT_SURVIVE_TIME)
        self.area_field_widget.setVisible(ntype == ConditionNodeType.AREA_VISIBLE)
        self.resource_field_widget.setVisible(ntype == ConditionNodeType.RESOURCE_AMOUNT)
        self.desc_field_widget.setVisible(ntype == ConditionNodeType.CONSTANT)

    def block_prop_signals(self, block: bool):
        self.combo_target_unit.blockSignals(block)
        self.spin_seconds.blockSignals(block)
        self.spin_area_x.blockSignals(block)
        self.spin_area_y.blockSignals(block)
        self.spin_area_w.blockSignals(block)
        self.spin_area_h.blockSignals(block)
        self.combo_res_type.blockSignals(block)
        self.spin_res_amount.blockSignals(block)
        self.edit_description.blockSignals(block)

    def _on_prop_input_changed(self):
        tree = self._get_active_tree()
        curr = tree.currentItem()
        if not curr:
            return

        data = curr.data(0, Qt.UserRole) or {}
        ntype = data.get("type", "")

        if ntype in (ConditionNodeType.UNIT_DESTROYED, ConditionNodeType.UNIT_SURVIVE_TIME):
            data["unit_id"] = self.combo_target_unit.currentText().strip()

        if ntype == ConditionNodeType.UNIT_SURVIVE_TIME:
            data["seconds"] = self.spin_seconds.value()

        if ntype == ConditionNodeType.AREA_VISIBLE:
            data["tile_x"] = self.spin_area_x.value()
            data["tile_y"] = self.spin_area_y.value()
            data["tile_w"] = self.spin_area_w.value()
            data["tile_h"] = self.spin_area_h.value()

        if ntype == ConditionNodeType.RESOURCE_AMOUNT:
            data["resource_type"] = self.combo_res_type.currentData() or "dark_matter"
            data["amount"] = self.spin_res_amount.value()

        if ntype == ConditionNodeType.CONSTANT:
            data["description"] = self.edit_description.text().strip()

        curr.setData(0, Qt.UserRole, data)
        self._refresh_item_display(curr)
        self._update_json_preview()
        self.condition_modified.emit()

    def _refresh_unit_id_dropdown(self):
        self.combo_target_unit.blockSignals(True)
        curr = self.combo_target_unit.currentText()
        self.combo_target_unit.clear()
        self.combo_target_unit.addItems(self.available_unit_ids)
        if curr:
            self.combo_target_unit.setCurrentText(curr)
        self.combo_target_unit.blockSignals(False)

    def _on_tab_changed(self):
        self._update_json_preview()
        self._on_tree_selection_changed()

    def _update_json_preview(self):
        tree = self._get_active_tree()
        cond_dict = self._serialize_tree(tree)
        if cond_dict:
            raw_text = json.dumps(cond_dict, indent=2, ensure_ascii=False)
        else:
            raw_text = "(未配置任何胜负判定条件)"
        self.txt_json_preview.setPlainText(raw_text)

    def _validate_current_conditions(self):
        tree = self._get_active_tree()
        cond_dict = self._serialize_tree(tree)
        if not cond_dict:
            QMessageBox.information(
                self,
                t("editor.condition.val_pass_empty_title"),
                t("editor.condition.val_pass_empty_msg")
            )
            return

        try:
            built_condition = ConditionBuilder.build(cond_dict)
            QMessageBox.information(
                self,
                t("editor.condition.val_pass_title"),
                t("editor.condition.val_pass_msg", cls=built_condition.__class__.__name__)
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                t("editor.condition.val_fail_title"),
                t("editor.condition.val_fail_msg", err=str(e))
            )
