BACKGROUND = "#10131c"
PANEL = "#171b26"
TEXT = "#d9deea"
MUTED = "#8c96ab"
UP = "#24ba9b"
DOWN = "#f36873"
BLUE = "#447bff"

STYLESHEET = """
QWidget { background:#10131c; color:#d9deea; font-size:12px; }
QMainWindow, QDialog { background:#10131c; }
QFrame#panel { background:#171b26; border:1px solid #272e40; border-radius:5px; }
QLabel { background:transparent; }
QFrame#topbar { background:#191e2b; border-bottom:1px solid #2a3244; }
QLabel#brand { font-size:18px; font-weight:800; color:#f1f4fb; letter-spacing:2px; }
QLabel#muted { color:#8c96ab; }
QLabel#section { color:#edf1fa; font-weight:600; font-size:13px; }
QLabel#symbol { font-size:21px; font-weight:700; color:#f1f4fb; }
QLabel#price { font-size:29px; font-weight:600; color:#f1f4fb; }
QLabel#eyebrow { color:#7697ef; font-size:10px; }
QLabel#empty { color:#8c96ab; font-size:13px; padding:24px; }
QPushButton { background:#222a3a; border:1px solid #323e55; border-radius:4px; padding:7px 12px; min-height:17px; }
QPushButton:hover { background:#2c3850; border-color:#4b6089; }
QPushButton:disabled { color:#657087; background:#1c2230; border-color:#282f40; }
QPushButton:checked { background:#273b67; color:#9db9ff; border-color:#447bff; }
QPushButton#primary { background:#356cf0; border-color:#447bff; color:white; font-weight:600; }
QPushButton#primary:hover { background:#487df5; }
QPushButton#buy { background:#159c82; border-color:#24ba9b; color:white; font-weight:600; min-height:25px; }
QPushButton#sell { background:#c95163; border-color:#f36873; color:white; font-weight:600; min-height:25px; }
QPushButton#buy:disabled, QPushButton#sell:disabled, QPushButton#primary:disabled { background:#202737; color:#657087; border-color:#30394c; }
QPushButton#nav { background:transparent; border:0; border-bottom:2px solid transparent; border-radius:0; padding:15px 17px; }
QPushButton#nav:checked { color:#8cadff; background:#202b44; border-bottom:2px solid #5e8bff; }
QPushButton#range { padding:3px 9px; min-height:16px; background:transparent; border-color:transparent; }
QPushButton#range:checked { color:#91b1ff; background:#253653; border-color:#3c5279; }
QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox, QPlainTextEdit, QTextBrowser {
 background:#111622; border:1px solid #30394c; border-radius:4px; padding:6px; selection-background-color:#355ba0;
}
QLineEdit:focus, QPlainTextEdit:focus { border-color:#5c81d5; }
QComboBox QAbstractItemView { background:#1b2332; color:#d9deea; selection-background-color:#2a416e; }
QHeaderView::section { background:#1b2231; color:#8f9cb5; border:0; border-bottom:1px solid #2b3448; padding:7px 5px; font-size:11px; }
QTableView { background:#141925; alternate-background-color:#171d2b; gridline-color:#242d40; border:0; selection-background-color:#273b61; selection-color:#eef3ff; }
QTableView::item { border:0; padding:5px; }
QTableView::item:selected { background:#273b61; }
QTabWidget::pane { border:1px solid #272e40; background:#141925; }
QTabBar::tab { background:#171d2b; color:#8c96ab; padding:9px 16px; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:#d9e6ff; border-bottom:2px solid #5887ff; background:#1d2840; }
QSplitter::handle { background:#242b3b; }
QSplitter::handle:horizontal { width:4px; }
QSplitter::handle:vertical { height:4px; }
QStatusBar { background:#171d2a; color:#8c96ab; border-top:1px solid #2a3244; font-size:11px; }
QStatusBar::item { border:0; }
QMenuBar { background:#151b27; color:#98a4bc; }
QMenuBar::item:selected, QMenu::item:selected { background:#2a3d60; }
QMenu { background:#1b2332; border:1px solid #323f56; }
QScrollBar:vertical { background:#121824; width:8px; }
QScrollBar::handle:vertical { background:#39455e; border-radius:3px; min-height:25px; }
QScrollBar:horizontal { background:#121824; height:8px; }
QScrollBar::handle:horizontal { background:#39455e; border-radius:3px; min-width:25px; }
QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
QCheckBox { spacing:7px; }
QProgressBar { background:#172137; border:0; min-height:3px; max-height:3px; }
QProgressBar::chunk { background:#447bff; }
"""
