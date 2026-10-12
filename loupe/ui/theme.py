"""Theme, typography scale, palette, and styling for Loupe Workstation."""

import os
from PySide6.QtGui import QFont, QFontDatabase, QPalette, QColor
from PySide6.QtWidgets import QApplication

# Color Palette: Dark graphite darkroom workstation with warm amber accent
COLOR_BG_BASE = "#101113"
COLOR_BG_SURFACE = "#17191C"
COLOR_BG_ELEVATED = "#202327"
COLOR_BG_HOVER = "#2A2E35"
COLOR_BG_ACTIVE = "#32373F"

COLOR_BORDER_SUBTLE = "#282C33"
COLOR_BORDER_DISTINCT = "#3B414B"
COLOR_BORDER_FOCUS = "#E59533"  # Warm amber keyboard focus ring

COLOR_TEXT_PRIMARY = "#EDEFEA"
COLOR_TEXT_SECONDARY = "#9DA4AE"
COLOR_TEXT_MUTED = "#5E6672"

COLOR_ACCENT = "#E59533"        # Warm Darkroom Amber
COLOR_ACCENT_HOVER = "#F0A342"
COLOR_ACCENT_PRESSED = "#CF8024"

COLOR_STATUS_KEPT = "#3EA66A"       # Forest Sage
COLOR_STATUS_REJECTED = "#D44747"   # Cinnabar Red
COLOR_STATUS_PENDING = "#727B88"

# Fonts loaded dynamically
_DISPLAY_FONT_FAMILY = "Space Grotesk"
_BODY_FONT_FAMILY = "Plus Jakarta Sans"
_MONO_FONT_FAMILY = "IBM Plex Mono"

def setup_dark_palette(app: QApplication):
    """Enforce a dark palette on QApplication so Windows light theme does not force black text."""
    palette = QPalette()
    bg_base = QColor(COLOR_BG_BASE)
    bg_surf = QColor(COLOR_BG_SURFACE)
    bg_elev = QColor(COLOR_BG_ELEVATED)
    text_pri = QColor(COLOR_TEXT_PRIMARY)
    text_mut = QColor(COLOR_TEXT_MUTED)
    accent = QColor(COLOR_ACCENT)

    palette.setColor(QPalette.ColorRole.Window, bg_base)
    palette.setColor(QPalette.ColorRole.WindowText, text_pri)
    palette.setColor(QPalette.ColorRole.Base, bg_surf)
    palette.setColor(QPalette.ColorRole.AlternateBase, bg_elev)
    palette.setColor(QPalette.ColorRole.ToolTipBase, bg_elev)
    palette.setColor(QPalette.ColorRole.ToolTipText, text_pri)
    palette.setColor(QPalette.ColorRole.Text, text_pri)
    palette.setColor(QPalette.ColorRole.Button, bg_elev)
    palette.setColor(QPalette.ColorRole.ButtonText, text_pri)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Link, accent)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#0A0B0D"))

    # Disabled text
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, text_mut)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_mut)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, text_mut)
    
    app.setPalette(palette)

def load_application_fonts():
    """Load bundled characterful display and body fonts into QFontDatabase."""
    global _DISPLAY_FONT_FAMILY, _BODY_FONT_FAMILY, _MONO_FONT_FAMILY
    
    base_dir = os.path.dirname(os.path.dirname(__file__))
    fonts_dir = os.path.join(base_dir, "resources", "fonts")
    
    if os.path.exists(fonts_dir):
        for font_file in os.listdir(fonts_dir):
            if font_file.endswith(".ttf") or font_file.endswith(".otf"):
                full_path = os.path.join(fonts_dir, font_file)
                font_id = QFontDatabase.addApplicationFont(full_path)
                if font_id >= 0:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        fname = families[0]
                        if "Space" in fname:
                            _DISPLAY_FONT_FAMILY = fname
                        elif "Jakarta" in fname:
                            _BODY_FONT_FAMILY = fname
                        elif "Mono" in fname:
                            _MONO_FONT_FAMILY = fname

def get_display_font(size: int = 15, bold: bool = True) -> QFont:
    f = QFont(_DISPLAY_FONT_FAMILY, size)
    f.setBold(bold)
    return f

def get_body_font(size: int = 13, bold: bool = False) -> QFont:
    f = QFont(_BODY_FONT_FAMILY, size)
    f.setBold(bold)
    return f

def get_mono_font(size: int = 12, bold: bool = False) -> QFont:
    f = QFont(_MONO_FONT_FAMILY, size)
    f.setBold(bold)
    return f

def get_application_stylesheet() -> str:
    """Returns the comprehensive stylesheet with distinct states and high typographic utility."""
    return f"""
    * {{
        color: {COLOR_TEXT_PRIMARY};
        font-family: "{_BODY_FONT_FAMILY}", "Segoe UI", sans-serif;
        font-size: 13px;
        outline: none;
    }}

    QWidget {{
        color: {COLOR_TEXT_PRIMARY};
    }}

    QLabel {{
        color: {COLOR_TEXT_PRIMARY};
    }}

    QMainWindow, QDialog, QWidget#centralWidget {{
        background-color: {COLOR_BG_BASE};
        color: {COLOR_TEXT_PRIMARY};
    }}

    QMessageBox, QInputDialog {{
        background-color: {COLOR_BG_SURFACE};
        color: {COLOR_TEXT_PRIMARY};
    }}

    QMessageBox QLabel, QInputDialog QLabel {{
        color: {COLOR_TEXT_PRIMARY};
    }}

    QListWidget {{
        background-color: transparent;
        color: {COLOR_TEXT_PRIMARY};
    }}

    QListWidget::item {{
        color: {COLOR_TEXT_PRIMARY};
    }}

    /* Global Scrollbars */
    QScrollBar:vertical {{
        background: {COLOR_BG_BASE};
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {COLOR_BG_ELEVATED};
        min-height: 24px;
        border-radius: 2px;
        border: 1px solid {COLOR_BORDER_SUBTLE};
    }}
    QScrollBar::handle:vertical:hover {{
        background: {COLOR_BG_HOVER};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    /* Buttons */
    QPushButton {{
        background-color: {COLOR_BG_ELEVATED};
        color: {COLOR_TEXT_PRIMARY};
        border: 1px solid {COLOR_BORDER_DISTINCT};
        border-radius: 2px;
        padding: 7px 14px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {COLOR_BG_HOVER};
        border-color: {COLOR_TEXT_SECONDARY};
    }}
    QPushButton:pressed {{
        background-color: {COLOR_BG_ACTIVE};
    }}
    QPushButton:focus {{
        border: 1px solid {COLOR_BORDER_FOCUS};
    }}
    QPushButton:disabled {{
        background-color: {COLOR_BG_SURFACE};
        color: {COLOR_TEXT_MUTED};
        border-color: {COLOR_BORDER_SUBTLE};
    }}

    /* Accent Button */
    QPushButton#accentButton {{
        background-color: #D97706;
        color: #FFFFFF;
        font-weight: 700;
        border: 1px solid #F59E0B;
        border-radius: 3px;
        padding: 7px 16px;
    }}
    QPushButton#accentButton:hover {{
        background-color: #F59E0B;
        color: #FFFFFF;
        border-color: #FBBF24;
    }}
    QPushButton#accentButton:pressed {{
        background-color: #B45309;
        color: #FFFFFF;
    }}
    QPushButton#accentButton:focus {{
        border: 2px solid #FFFFFF;
    }}

    /* Card Primary Action Button (High Contrast Amber) */
    QPushButton#resumeCullButton {{
        background-color: #2D2214;
        color: #FFAE42;
        border: 1px solid #E59533;
        border-radius: 2px;
        padding: 7px 16px;
        font-weight: 600;
        font-size: 13px;
    }}
    QPushButton#resumeCullButton:hover {{
        background-color: #E59533;
        color: #FFFFFF;
        border: 1px solid #FFAE42;
    }}
    QPushButton#resumeCullButton:pressed {{
        background-color: #C87D20;
        color: #FFFFFF;
    }}

    /* Keep (W) Button */
    QPushButton#keepButton {{
        background-color: #1A3323;
        color: #7BE4A2;
        border: 1px solid {COLOR_STATUS_KEPT};
        font-weight: 600;
        padding: 9px 18px;
    }}
    QPushButton#keepButton:hover {{
        background-color: #244631;
        color: #A3F3C0;
    }}
    QPushButton#keepButton:pressed {{
        background-color: #162B1D;
    }}
    QPushButton#keepButton:focus {{
        border: 2px solid #7BE4A2;
    }}

    /* Reject (S) Button */
    QPushButton#rejectButton {{
        background-color: #381B1B;
        color: #F87171;
        border: 1px solid {COLOR_STATUS_REJECTED};
        font-weight: 600;
        padding: 9px 18px;
    }}
    QPushButton#rejectButton:hover {{
        background-color: #4D2525;
        color: #FCA5A5;
    }}
    QPushButton#rejectButton:pressed {{
        background-color: #2E1515;
    }}
    QPushButton#rejectButton:focus {{
        border: 2px solid #F87171;
    }}

    /* Line Edits & Inputs */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
        background-color: {COLOR_BG_SURFACE};
        color: {COLOR_TEXT_PRIMARY};
        border: 1px solid {COLOR_BORDER_DISTINCT};
        border-radius: 2px;
        padding: 6px 10px;
        selection-background-color: {COLOR_ACCENT};
        selection-color: #000000;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus {{
        border: 1px solid {COLOR_BORDER_FOCUS};
    }}
    QLineEdit:disabled, QComboBox:disabled {{
        background-color: {COLOR_BG_BASE};
        color: {COLOR_TEXT_MUTED};
        border-color: {COLOR_BORDER_SUBTLE};
    }}

    /* Dropdowns */
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {COLOR_BG_SURFACE};
        border: 1px solid {COLOR_BORDER_DISTINCT};
        selection-background-color: {COLOR_BG_HOVER};
        selection-color: {COLOR_TEXT_PRIMARY};
    }}

    /* Checkboxes & Radios */
    QCheckBox, QRadioButton {{
        spacing: 8px;
        color: {COLOR_TEXT_PRIMARY};
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {COLOR_BORDER_DISTINCT};
        border-radius: 2px;
        background-color: {COLOR_BG_SURFACE};
    }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
        border-color: {COLOR_TEXT_SECONDARY};
    }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background-color: {COLOR_ACCENT};
        border-color: {COLOR_ACCENT};
    }}
    QCheckBox::indicator:focus, QRadioButton::indicator:focus {{
        border-color: {COLOR_BORDER_FOCUS};
    }}

    /* Sliders */
    QSlider::groove:horizontal {{
        height: 4px;
        background: {COLOR_BORDER_DISTINCT};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {COLOR_ACCENT};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {COLOR_TEXT_PRIMARY};
        border: 1px solid {COLOR_BORDER_DISTINCT};
        width: 14px;
        margin-top: -5px;
        margin-bottom: -5px;
        border-radius: 2px;
    }}
    QSlider::handle:horizontal:hover {{
        background: #FFFFFF;
        border-color: {COLOR_ACCENT};
    }}
    QSlider::handle:horizontal:focus {{
        border: 2px solid {COLOR_ACCENT};
    }}

    /* Progress Bar */
    QProgressBar {{
        background-color: {COLOR_BG_SURFACE};
        border: 1px solid {COLOR_BORDER_DISTINCT};
        border-radius: 2px;
        text-align: center;
        height: 14px;
        color: {COLOR_TEXT_PRIMARY};
        font-size: 11px;
    }}
    QProgressBar::chunk {{
        background-color: {COLOR_ACCENT};
    }}

    /* Group Box */
    QGroupBox {{
        border: 1px solid {COLOR_BORDER_SUBTLE};
        border-radius: 2px;
        margin-top: 18px;
        padding-top: 12px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 6px;
        color: {COLOR_TEXT_SECONDARY};
    }}
    """
