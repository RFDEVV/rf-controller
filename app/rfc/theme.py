"""Palet warna terang/gelap dan stylesheet aplikasi."""
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont

DARK = dict(
    bg="#0E1319", side="#0A0F14", surface="#151C24", surface2="#1C2530", border="#263241",
    text="#E7EDF4", muted="#8696A8", accent="#4DA3FF", accent_text="#06121F", amber="#FFB84D",
    teal="#3DD6A0", rose="#FF7A9A", danger="#FF6B6B", grid="#202B38", glow=0.55,
)
LIGHT = dict(
    bg="#EEF2F6", side="#E3E9F0", surface="#FFFFFF", surface2="#F3F6FA", border="#D5DEE8",
    text="#17202A", muted="#5B6B7D", accent="#1769E0", accent_text="#FFFFFF", amber="#C77700",
    teal="#0F9A6F", rose="#D6336C", danger="#D6342C", grid="#E3E9F0", glow=0.18,
)

HEAD_FONT = "Bahnschrift"
BODY_FONT = "Segoe UI"


def head_font(px, weight=QFont.DemiBold):
    f = QFont(HEAD_FONT)
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


class Theme(QObject):
    changed = Signal()

    def __init__(self, dark=True):
        super().__init__()
        self.dark = dark
        self.c = dict(DARK if dark else LIGHT)
        self.animations = True

    def set_dark(self, dark):
        self.dark = dark
        self.c = dict(DARK if dark else LIGHT)
        self.changed.emit()

    def col(self, name, alpha=None):
        q = QColor(self.c[name])
        if alpha is not None:
            q.setAlphaF(alpha)
        return q

    def qss(self):
        c = self.c
        return f"""
* {{ font-family: "{BODY_FONT}", "Segoe UI Variable", "Noto Sans", sans-serif; font-size: 13px; color: {c['text']}; }}
QWidget#root, QWidget#page, QStackedWidget {{ background: {c['bg']}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QWidget#side {{ background: {c['side']}; }}
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-family: "{HEAD_FONT}"; font-size: 22px; font-weight: 600; }}
QLabel[role="h2"] {{ font-family: "{HEAD_FONT}"; font-size: 15px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {c['muted']}; }}
QLabel[role="value"] {{ font-family: "{HEAD_FONT}"; font-size: 13px; color: {c['accent']}; }}
QFrame#card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px; }}
QFrame#card QLabel {{ background: transparent; }}
QPushButton {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 9px; padding: 7px 14px; }}
QPushButton:hover {{ border-color: {c['accent']}; }}
QPushButton:pressed {{ background: {c['border']}; }}
QPushButton:disabled {{ color: {c['muted']}; }}
QPushButton[kind="primary"] {{ background: {c['accent']}; border: 1px solid {c['accent']}; color: {c['accent_text']}; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ border-color: {c['text']}; }}
QPushButton[kind="primary"]:disabled {{ background: {c['border']}; border-color: {c['border']}; color: {c['muted']}; }}
QPushButton[kind="ghost"] {{ background: transparent; border: 1px solid transparent; }}
QPushButton[kind="ghost"]:hover {{ background: {c['surface2']}; border-color: {c['border']}; }}
QComboBox, QSpinBox, QLineEdit {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 5px 9px; min-height: 20px; }}
QComboBox:hover, QSpinBox:hover, QLineEdit:focus {{ border-color: {c['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']}; selection-background-color: {c['accent']}; selection-color: {c['accent_text']}; outline: 0; padding: 4px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {c['text']}; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; border: 3px solid {c['accent']}; }}
QSlider::handle:horizontal:hover {{ width: 16px; height: 16px; margin: -7px 0; border-radius: 8px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QListWidget {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 4px; outline: 0; }}
QListWidget::item {{ padding: 9px 10px; border-radius: 7px; }}
QListWidget::item:selected {{ background: {c['accent']}; color: {c['accent_text']}; }}
QPlainTextEdit {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 8px; font-family: Consolas, "DejaVu Sans Mono", monospace; font-size: 12px; }}
QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 5px; }}
QProgressBar {{ background: {c['surface2']}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
"""
