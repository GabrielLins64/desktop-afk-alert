"""Matrix-inspired application styling."""

BACKGROUND = "#0D0208"
GREEN = "#00FF41"
TEAL = "#00D4C7"

STYLESHEET = """
QWidget {
    background: #0D0208; color: #CEEFDC;
    font-family: "DejaVu Sans Mono", "Liberation Mono", monospace;
    font-size: 13px;
}
QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget { background: #0D0208; }
QScrollArea { border: 0; }
QFrame#card { background: #101A14; border: 1px solid #213F2B; border-radius: 14px; }
QFrame#card QLabel, QWidget#cardContent { background: transparent; }
QLabel#brand { color: #00FF41; font-size: 25px; font-weight: bold; }
QLabel#eyebrow { color: #00D4C7; font-size: 11px; font-weight: bold; }
QLabel#sectionTitle { color: #E0FFEA; font-size: 16px; font-weight: bold; }
QLabel#muted { color: #91AD9A; font-size: 12px; }
QLabel#error { color: #FFACAC; font-size: 12px; }
QLabel#badge { color: #00FF41; background: #003B00; border-radius: 8px; padding: 5px 10px; font-size: 11px; font-weight: bold; }
QLabel#status { color: #A6C3B0; font-size: 12px; }
QLabel#warning { color: #E4C975; font-size: 12px; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {
    background: #090E0B; border: 1px solid #31543D; border-radius: 7px;
    padding: 9px 11px; color: #D9FFE6; selection-background-color: #003B00;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #00D4C7; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: #597061; border-color: #22372A; }
QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"], QComboBox[invalid="true"], QSpinBox[invalid="true"] { border-color: #FFACAC; }
QComboBox::drop-down { border: 0; width: 26px; }
QComboBox QAbstractItemView { background: #101A14; color: #D9FFE6; selection-background-color: #003B00; padding: 4px; }
QSpinBox { min-width: 105px; }
QSpinBox QLineEdit { background: transparent; border: 0; padding: 0 11px; }
/* Hide buttons through styling so Qt preserves the spin box editor's width. */
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: 0; }
QPushButton {
    background: #192E20; color: #BCF2CD; border: 1px solid #31543D;
    border-radius: 7px; padding: 9px 15px; font-weight: bold;
}
QPushButton:hover { background: #23432C; border-color: #008F11; }
QPushButton:focus { border-color: #00D4C7; }
QPushButton:disabled { color: #597061; background: #132019; border-color: #22372A; }
QPushButton#activate { background: #00FF41; color: #08150B; border: 0; padding: 13px 26px; font-size: 14px; }
QPushButton#activate:hover { background: #73FF97; }
QPushButton#activate:disabled { background: #1F5530; color: #7FA68C; }
QPushButton#secondary { color: #00D4C7; }
QFrame#footer { background: #101A14; border-top: 1px solid #213F2B; }
QFrame#footer QLabel { background: transparent; }
QFrame#passwordPanel { background: #101A14; border: 1px solid #008F11; border-radius: 12px; }
QFrame#passwordPanel QWidget { background: transparent; }
QFrame#passwordPanel QLineEdit { background: #090E0B; font-size: 21px; padding: 12px; }
QScrollBar:vertical { background: #0D0208; width: 8px; margin: 3px; }
QScrollBar::handle:vertical { background: #31543D; border-radius: 3px; min-height: 32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #101A14; color: #CEEFDC; border: 1px solid #008F11; padding: 5px; }
"""
