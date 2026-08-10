APP_STYLESHEET = r"""
QMainWindow, QDialog, QScrollArea { background: #f5efe9; }
QWidget { color: #171717; font-family: "Microsoft YaHei UI"; }
QWidget#page { background: #f5efe9; color: #171717; }
QFrame#hero { background: #fff8f3; border: 2px solid #171717; border-radius: 26px; }
QLabel#mouseMascot { background: transparent; border: 0; }
QLabel#eyebrow { color: #df5268; font-size: 11px; font-weight: 800; letter-spacing: 1px; border: 0; }
QLabel#title { font-size: 31px; font-weight: 800; color: #111111; border: 0; }
QLabel#subtitle { font-size: 15px; color: #5e5552; border: 0; }
QLabel#workflowStep, QLabel#workflowActive {
    border: 2px solid #171717; border-radius: 16px; padding: 9px 12px;
    font-size: 12px; font-weight: 700; background: #fffdfb;
}
QLabel#workflowActive { background: #ffd9df; }
QLabel#sectionTitle { font-size: 19px; font-weight: 750; color: #171717; border: 0; }
QLabel#sectionDescription { font-size: 13px; color: #746966; border: 0; }
QLabel#fieldLabel { font-size: 12px; font-weight: 700; color: #5e5552; border: 0; }
QLabel#status { color: #5e5552; padding: 3px 2px; }
QLabel#outputHint { color: #3f3735; background: #fff5f2; border: 1px solid #e7cac5; border-radius: 10px; padding: 10px 12px; }
QFrame#panel {
    background: #fffdfb; border: 2px solid #171717;
    border-radius: 20px;
}
QFrame#historyBar {
    background: #fffdfb; border: 2px solid #171717;
    border-radius: 14px;
}
QLabel#historyLabel { color: #746966; font-size: 12px; border: 0; }
QListWidget, QLineEdit, QComboBox, QSpinBox {
    color: #171717; background: #ffffff; border: 2px solid #171717;
    border-radius: 10px; padding: 9px 11px; min-height: 23px;
    selection-background-color: #ef6f82;
    selection-color: #171717;
}
QListWidget#dropZone { background: #fff4f5; border: 2px dashed #171717;
    border-radius: 16px; padding: 12px; }
QListWidget#dropZone:focus { border: 2px solid #df5268; }
QListWidget::item { color: #171717; background: transparent;
    border-radius: 8px; padding: 9px 10px; margin: 2px 0; }
QListWidget::item:hover { background: #ffe7eb; }
QListWidget::item:selected { color: #171717; background: #ffd2da; }
QComboBox QAbstractItemView {
    color: #171717; background: #ffffff; border: 2px solid #171717;
    border-radius: 10px; padding: 6px; outline: 0;
    selection-color: #171717; selection-background-color: #ffd2da;
}
QComboBox QAbstractItemView::item { color: #171717;
    background: #ffffff; min-height: 30px; padding: 5px 9px; }
QComboBox QAbstractItemView::item:hover,
QComboBox QAbstractItemView::item:selected { color: #171717; background: #ffd2da; }
QComboBox::drop-down { border: 0; width: 34px; }
QTableWidget { color: #1d1d1f; background: #ffffff;
    alternate-background-color: #f5f5f7; gridline-color: #e5e5ea; }
QHeaderView::section { color: #424245; background: #f5f5f7;
    border: 0; border-bottom: 1px solid #d2d2d7; padding: 8px; }
QPushButton {
    background: #ffffff; color: #171717; border: 2px solid #171717; border-radius: 10px;
    padding: 10px 16px; font-weight: 600; min-height: 20px;
}
QPushButton:hover { background: #ffe4e8; }
QPushButton#primary { background: #ef6f82; color: #171717; border-radius: 12px; padding: 13px 20px; font-weight: 800; }
QPushButton#primary:hover { background: #f38293; }
QPushButton#secondary { background: #fffdfb; }
QPushButton#linkButton { color: #c63f55; background: transparent; border: 0; padding: 6px 8px; }
QPushButton#linkButton:hover { color: #a52c40; background: #ffe9ec; }
QPushButton#dangerLinkButton { color: #d70015; background: transparent; padding: 6px 8px; }
QPushButton#dangerLinkButton:hover { color: #b60012; background: #fff0f1; }
QPushButton:disabled { color: #a29a97; background: #e9e2de; border-color: #bdb4b0; }
QCheckBox { color: #424245; spacing: 8px; padding: 3px 0; }
QCheckBox::indicator { width: 17px; height: 17px; }
QProgressBar {
    border: 2px solid #171717; background: #f0e8e4; border-radius: 5px;
    text-align: center; min-height: 8px; max-height: 8px; color: transparent;
}
QProgressBar::chunk { background: #ef6f82; border-radius: 3px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #c7c7cc; border-radius: 5px; min-height: 34px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
