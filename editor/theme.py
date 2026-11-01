"""
Age of Empires II (帝国时代2) 风格主题样式与调色板
经典中世纪羊皮纸/古铜/深铁风格，带高对比度金色与雕刻按钮质感。
"""

AOE2_STYLE = """
/* 全局基础设置 */
QMainWindow, QDialog, QWidget {
    background-color: #1A1815;
    color: #E2D9C8;
    font-family: "Cinzel", "Palatino", "Georgia", "SimSun", "Microsoft YaHei", serif;
    font-size: 13px;
}

/* 顶部菜单栏与工具栏 */
QMenuBar {
    background-color: #24201B;
    border-bottom: 2px solid #5A472A;
    color: #DCCBA8;
    font-weight: bold;
    padding: 3px;
}

QMenuBar::item {
    background: transparent;
    padding: 6px 14px;
    border-radius: 2px;
}

QMenuBar::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4E3B1C, stop:1 #2C210E);
    border: 1px solid #C8A048;
    color: #FFF2C6;
}

QMenu {
    background-color: #24201B;
    border: 2px solid #6C5531;
    color: #E2D9C8;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px;
}

QMenu::item:selected {
    background-color: #4E3B1C;
    border: 1px solid #C8A048;
    color: #FFF2C6;
}

/* 帝国时代2风格大模式切换按钮栏 */
QToolBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2C261F, stop:1 #1C1814);
    border-top: 1px solid #6A5534;
    border-bottom: 2px solid #503E24;
    spacing: 6px;
    padding: 5px;
}

/* 经典帝国时代古铜刻印质感按钮 */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3D3325, stop:0.5 #2C2419, stop:1 #201A12);
    border: 2px solid #685233;
    border-top-color: #8C6E44;
    border-left-color: #7D633D;
    border-radius: 3px;
    color: #E6C66E;
    font-weight: bold;
    padding: 6px 14px;
    min-height: 22px;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #574834, stop:0.5 #3F3323, stop:1 #2E2519);
    border: 2px solid #C8A048;
    color: #FFF3BD;
}

QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A140E, stop:0.5 #221B13, stop:1 #352B1E);
    border: 2px solid #4A3A23;
    color: #B59850;
}

QPushButton:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6B231D, stop:0.5 #4D1814, stop:1 #330F0C);
    border: 2px solid #E69C24;
    color: #FFEA9F;
}

QPushButton:disabled {
    background-color: #24201B;
    border: 1px solid #3F3628;
    color: #6C6251;
}

/* 模式大选项卡按钮 */
QTabBar::tab {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #322A20, stop:1 #1F1A13);
    border: 2px solid #59452B;
    border-bottom: none;
    color: #CDB580;
    font-size: 13px;
    font-weight: bold;
    padding: 8px 20px;
    margin-right: 4px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #54442F, stop:0.5 #382D1F, stop:1 #271F15);
    border: 2px solid #C8A048;
    border-bottom: 2px solid #271F15;
    color: #FFF2C6;
}

QTabBar::tab:hover:!selected {
    background: #41372A;
    color: #EADBAC;
}

QTabWidget::pane {
    border: 2px solid #6C5531;
    background-color: #1F1B16;
}

/* 分组框与面板 */
QGroupBox {
    border: 2px solid #5C482C;
    border-radius: 4px;
    margin-top: 18px;
    font-weight: bold;
    color: #E6C66E;
    padding-top: 10px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    background-color: #1A1815;
}

/* 输入框与选择器 */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #151310;
    border: 1px solid #5C482C;
    border-radius: 2px;
    color: #E2D9C8;
    padding: 4px 6px;
    selection-background-color: #8C6E44;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #C8A048;
    background-color: #1A1713;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #5C482C;
}

QComboBox QAbstractItemView {
    background-color: #24201B;
    border: 1px solid #6C5531;
    selection-background-color: #4E3B1C;
    selection-color: #FFF2C6;
}

/* 列表与树状视图 (Mode 3 条件树专属) */
QTreeWidget, QListWidget, QTableWidget {
    background-color: #151310;
    border: 1px solid #4E3C24;
    color: #E2D9C8;
    alternate-background-color: #1A1713;
}

QTreeWidget::item, QListWidget::item {
    padding: 5px;
    border-bottom: 1px solid #282218;
}

QTreeWidget::item:selected, QListWidget::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4E3B1C, stop:1 #322510);
    border: 1px solid #C8A048;
    color: #FFF2C6;
}

QHeaderView::section {
    background-color: #2B241A;
    border: 1px solid #4E3C24;
    color: #E6C66E;
    font-weight: bold;
    padding: 5px;
}

/* 滚动条 (AoE2 古铜滑块) */
QScrollBar:vertical {
    background: #181512;
    width: 14px;
    margin: 16px 0 16px 0;
    border: 1px solid #3A2F1E;
}

QScrollBar::handle:vertical {
    background: #473B28;
    border: 1px solid #6D5638;
    min-height: 24px;
    border-radius: 2px;
}

QScrollBar::handle:vertical:hover {
    background: #645339;
    border: 1px solid #C8A048;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    background: #2A2318;
    border: 1px solid #4E3C24;
    height: 14px;
    subcontrol-origin: margin;
}

QScrollBar:horizontal {
    background: #181512;
    height: 14px;
    margin: 0 16px 0 16px;
    border: 1px solid #3A2F1E;
}

QScrollBar::handle:horizontal {
    background: #473B28;
    border: 1px solid #6D5638;
    min-width: 24px;
    border-radius: 2px;
}

/* 底部状态栏 */
QStatusBar {
    background: #14120F;
    border-top: 1px solid #4A3A23;
    color: #C6AA6F;
    font-size: 12px;
    font-weight: bold;
}

QStatusBar QLabel {
    padding: 2px 10px;
}

/* 提示与 CheckBox */
QCheckBox {
    spacing: 8px;
    color: #E2D9C8;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    background-color: #151310;
    border: 1px solid #685233;
    border-radius: 2px;
}

QCheckBox::indicator:checked {
    background-color: #8C6E44;
    border: 1px solid #FFD97D;
}
"""

from PyQt5.QtCore import QObject, QEvent, Qt
from PyQt5.QtWidgets import QApplication, QScrollArea, QWidget, QAbstractSpinBox, QComboBox


class SidebarWheelFilter(QObject):
    """
    让侧边工具栏内的 SpinBox / DoubleSpinBox / ComboBox 在未主动聚焦时不劫持鼠标滚轮事件，
    而是将滚轮事件转发给所属 QScrollArea 的垂直滚动条，保证侧边工具栏页面上下滚轮顺畅滚动。
    """

    def __init__(self, scroll_area: QScrollArea, parent: QObject = None):
        super().__init__(parent or scroll_area)
        self.scroll_area = scroll_area

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Wheel:
            if isinstance(obj, QWidget) and not obj.hasFocus():
                if self.scroll_area is not None and self.scroll_area.verticalScrollBar() is not None:
                    QApplication.sendEvent(self.scroll_area.verticalScrollBar(), event)
                    return True
        return super().eventFilter(obj, event)


def install_sidebar_wheel_guard(scroll_area: QScrollArea, container: QWidget) -> SidebarWheelFilter:
    """为可滚动侧边栏内的所有数值框与下拉框安装滚轮穿透保护"""
    wheel_filter = SidebarWheelFilter(scroll_area, container)
    for w in container.findChildren((QAbstractSpinBox, QComboBox)):
        w.setFocusPolicy(Qt.StrongFocus)
        w.installEventFilter(wheel_filter)
    scroll_area._wheel_filter = wheel_filter
    return wheel_filter

