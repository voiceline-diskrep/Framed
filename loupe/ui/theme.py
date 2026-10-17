"""Theme, typography scale, palette, and multi-theme styling for Framed Workstation."""

import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional
from PySide6.QtGui import QFont, QFontDatabase, QPalette, QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal
from loupe.config import config

@dataclass
class ThemeDefinition:
    id: str
    name: str
    description: str
    is_light: bool
    colors: Dict[str, str]

THEMES: Dict[str, ThemeDefinition] = {
    "dark_amber": ThemeDefinition(
        id="dark_amber",
        name="Dark Amber",
        description="Dark gray background with warm amber accents.",
        is_light=False,
        colors={
            "COLOR_BG_BASE": "#101113",
            "COLOR_BG_SURFACE": "#17191C",
            "COLOR_BG_ELEVATED": "#202327",
            "COLOR_BG_HOVER": "#2A2E35",
            "COLOR_BG_ACTIVE": "#32373F",
            "COLOR_BORDER_SUBTLE": "#282C33",
            "COLOR_BORDER_DISTINCT": "#3B414B",
            "COLOR_BORDER_FOCUS": "#E59533",
            "COLOR_TEXT_PRIMARY": "#EDEFEA",
            "COLOR_TEXT_SECONDARY": "#9DA4AE",
            "COLOR_TEXT_MUTED": "#5E6672",
            "COLOR_ACCENT": "#E59533",
            "COLOR_ACCENT_HOVER": "#F0A342",
            "COLOR_ACCENT_PRESSED": "#CF8024",
            "COLOR_STATUS_KEPT": "#3EA66A",
            "COLOR_STATUS_REJECTED": "#D44747",
            "COLOR_STATUS_MAYBE": "#D97706",
            "COLOR_STATUS_PENDING": "#727B88",
        }
    ),
    "oled": ThemeDefinition(
        id="oled",
        name="OLED",
        description="Pure black background for OLED screens with cyan accents.",
        is_light=False,
        colors={
            "COLOR_BG_BASE": "#090C10",
            "COLOR_BG_SURFACE": "#0F141C",
            "COLOR_BG_ELEVATED": "#161E2A",
            "COLOR_BG_HOVER": "#1E293B",
            "COLOR_BG_ACTIVE": "#26354D",
            "COLOR_BORDER_SUBTLE": "#1B2330",
            "COLOR_BORDER_DISTINCT": "#2E3D52",
            "COLOR_BORDER_FOCUS": "#06B6D4",
            "COLOR_TEXT_PRIMARY": "#F1F5F9",
            "COLOR_TEXT_SECONDARY": "#94A3B8",
            "COLOR_TEXT_MUTED": "#64748B",
            "COLOR_ACCENT": "#06B6D4",
            "COLOR_ACCENT_HOVER": "#22D3EE",
            "COLOR_ACCENT_PRESSED": "#0891B2",
            "COLOR_STATUS_KEPT": "#10B981",
            "COLOR_STATUS_REJECTED": "#EF4444",
            "COLOR_STATUS_MAYBE": "#F59E0B",
            "COLOR_STATUS_PENDING": "#64748B",
        }
    ),
    "dark_blue": ThemeDefinition(
        id="dark_blue",
        name="Dark Blue",
        description="Dark navy background with blue accents.",
        is_light=False,
        colors={
            "COLOR_BG_BASE": "#0A0E17",
            "COLOR_BG_SURFACE": "#101624",
            "COLOR_BG_ELEVATED": "#182235",
            "COLOR_BG_HOVER": "#22304A",
            "COLOR_BG_ACTIVE": "#2C3E5F",
            "COLOR_BORDER_SUBTLE": "#1C273C",
            "COLOR_BORDER_DISTINCT": "#2E4062",
            "COLOR_BORDER_FOCUS": "#6366F1",
            "COLOR_TEXT_PRIMARY": "#F8FAFC",
            "COLOR_TEXT_SECONDARY": "#94A3B8",
            "COLOR_TEXT_MUTED": "#64748B",
            "COLOR_ACCENT": "#6366F1",
            "COLOR_ACCENT_HOVER": "#818CF8",
            "COLOR_ACCENT_PRESSED": "#4F46E5",
            "COLOR_STATUS_KEPT": "#22C55E",
            "COLOR_STATUS_REJECTED": "#F43F5E",
            "COLOR_STATUS_MAYBE": "#EAB308",
            "COLOR_STATUS_PENDING": "#64748B",
        }
    ),
    "dark_green": ThemeDefinition(
        id="dark_green",
        name="Dark Green",
        description="Dark green background with green accents.",
        is_light=False,
        colors={
            "COLOR_BG_BASE": "#09120E",
            "COLOR_BG_SURFACE": "#0F1A14",
            "COLOR_BG_ELEVATED": "#16271F",
            "COLOR_BG_HOVER": "#1F372C",
            "COLOR_BG_ACTIVE": "#294739",
            "COLOR_BORDER_SUBTLE": "#1B3127",
            "COLOR_BORDER_DISTINCT": "#2D4F3F",
            "COLOR_BORDER_FOCUS": "#10B981",
            "COLOR_TEXT_PRIMARY": "#ECFDF5",
            "COLOR_TEXT_SECONDARY": "#A7F3D0",
            "COLOR_TEXT_MUTED": "#4D7C66",
            "COLOR_ACCENT": "#10B981",
            "COLOR_ACCENT_HOVER": "#34D399",
            "COLOR_ACCENT_PRESSED": "#059669",
            "COLOR_STATUS_KEPT": "#10B981",
            "COLOR_STATUS_REJECTED": "#E11D48",
            "COLOR_STATUS_MAYBE": "#D97706",
            "COLOR_STATUS_PENDING": "#4D7C66",
        }
    ),
    "neutral_gray": ThemeDefinition(
        id="neutral_gray",
        name="Neutral Gray",
        description="Neutral gray background with orange accents.",
        is_light=False,
        colors={
            "COLOR_BG_BASE": "#181A1D",
            "COLOR_BG_SURFACE": "#202327",
            "COLOR_BG_ELEVATED": "#2A2D33",
            "COLOR_BG_HOVER": "#343840",
            "COLOR_BG_ACTIVE": "#3E434D",
            "COLOR_BORDER_SUBTLE": "#30343B",
            "COLOR_BORDER_DISTINCT": "#444953",
            "COLOR_BORDER_FOCUS": "#F97316",
            "COLOR_TEXT_PRIMARY": "#FFFFFF",
            "COLOR_TEXT_SECONDARY": "#B0B8C4",
            "COLOR_TEXT_MUTED": "#6B7685",
            "COLOR_ACCENT": "#F97316",
            "COLOR_ACCENT_HOVER": "#FB923C",
            "COLOR_ACCENT_PRESSED": "#EA580C",
            "COLOR_STATUS_KEPT": "#22C55E",
            "COLOR_STATUS_REJECTED": "#EF4444",
            "COLOR_STATUS_MAYBE": "#F59E0B",
            "COLOR_STATUS_PENDING": "#6B7685",
        }
    ),
    "light": ThemeDefinition(
        id="light",
        name="Light",
        description="Light white background with blue accents.",
        is_light=True,
        colors={
            "COLOR_BG_BASE": "#F3F4F6",
            "COLOR_BG_SURFACE": "#FFFFFF",
            "COLOR_BG_ELEVATED": "#E5E7EB",
            "COLOR_BG_HOVER": "#D1D5DB",
            "COLOR_BG_ACTIVE": "#9CA3AF",
            "COLOR_BORDER_SUBTLE": "#E5E7EB",
            "COLOR_BORDER_DISTINCT": "#D1D5DB",
            "COLOR_BORDER_FOCUS": "#2563EB",
            "COLOR_TEXT_PRIMARY": "#111827",
            "COLOR_TEXT_SECONDARY": "#4B5563",
            "COLOR_TEXT_MUTED": "#6B7280",
            "COLOR_ACCENT": "#2563EB",
            "COLOR_ACCENT_HOVER": "#3B82F6",
            "COLOR_ACCENT_PRESSED": "#1D4ED8",
            "COLOR_STATUS_KEPT": "#059669",
            "COLOR_STATUS_REJECTED": "#DC2626",
            "COLOR_STATUS_MAYBE": "#D97706",
            "COLOR_STATUS_PENDING": "#9CA3AF",
        }
    ),
}

# Backward compatibility aliases for previously saved theme names
THEME_ALIASES: Dict[str, str] = {
    "darkroom_amber": "dark_amber",
    "obsidian_cyan": "oled",
    "midnight_sapphire": "dark_blue",
    "forest_emerald": "dark_green",
    "slate_studio": "neutral_gray",
    "paper_light": "light",
    "oled_cyan": "oled",
    "oled_black": "oled",
    "light_mode": "light",
}

class ThemeManager(QObject):
    theme_changed = Signal(str)  # theme_id

theme_manager = ThemeManager()

# Initialize active theme from config or default
current_theme_id = config.get("theme", "dark_amber")
current_theme_id = THEME_ALIASES.get(current_theme_id, current_theme_id)
if current_theme_id not in THEMES:
    current_theme_id = "dark_amber"

_active_colors = THEMES[current_theme_id].colors

# Color Constants (exported for direct module-level import)
COLOR_BG_BASE = _active_colors["COLOR_BG_BASE"]
COLOR_BG_SURFACE = _active_colors["COLOR_BG_SURFACE"]
COLOR_BG_ELEVATED = _active_colors["COLOR_BG_ELEVATED"]
COLOR_BG_HOVER = _active_colors["COLOR_BG_HOVER"]
COLOR_BG_ACTIVE = _active_colors["COLOR_BG_ACTIVE"]

COLOR_BORDER_SUBTLE = _active_colors["COLOR_BORDER_SUBTLE"]
COLOR_BORDER_DISTINCT = _active_colors["COLOR_BORDER_DISTINCT"]
COLOR_BORDER_FOCUS = _active_colors["COLOR_BORDER_FOCUS"]

COLOR_TEXT_PRIMARY = _active_colors["COLOR_TEXT_PRIMARY"]
COLOR_TEXT_SECONDARY = _active_colors["COLOR_TEXT_SECONDARY"]
COLOR_TEXT_MUTED = _active_colors["COLOR_TEXT_MUTED"]

COLOR_ACCENT = _active_colors["COLOR_ACCENT"]
COLOR_ACCENT_HOVER = _active_colors["COLOR_ACCENT_HOVER"]
COLOR_ACCENT_PRESSED = _active_colors["COLOR_ACCENT_PRESSED"]

COLOR_STATUS_KEPT = _active_colors["COLOR_STATUS_KEPT"]
COLOR_STATUS_REJECTED = _active_colors["COLOR_STATUS_REJECTED"]
COLOR_STATUS_MAYBE = _active_colors["COLOR_STATUS_MAYBE"]
COLOR_STATUS_PENDING = _active_colors["COLOR_STATUS_PENDING"]

# Fonts loaded dynamically
_DISPLAY_FONT_FAMILY = "Space Grotesk"
_BODY_FONT_FAMILY = "Plus Jakarta Sans"
_MONO_FONT_FAMILY = "IBM Plex Mono"

def is_current_theme_light() -> bool:
    """Returns True if the current active theme is light/high-key."""
    return THEMES.get(current_theme_id, THEMES["dark_amber"]).is_light

def apply_theme(theme_id: str, app: Optional[QApplication] = None) -> bool:
    """
    Applies the specified theme live across the entire application:
    updates global variables, propagates to all loaded loupe modules,
    and updates the QApplication palette and stylesheet.
    """
    global current_theme_id, COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED
    global COLOR_BG_HOVER, COLOR_BG_ACTIVE, COLOR_BORDER_SUBTLE, COLOR_BORDER_DISTINCT
    global COLOR_BORDER_FOCUS, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED
    global COLOR_ACCENT, COLOR_ACCENT_HOVER, COLOR_ACCENT_PRESSED
    global COLOR_STATUS_KEPT, COLOR_STATUS_REJECTED, COLOR_STATUS_MAYBE, COLOR_STATUS_PENDING

    theme_id = THEME_ALIASES.get(theme_id, theme_id)
    if theme_id not in THEMES:
        theme_id = "dark_amber"

    current_theme_id = theme_id
    theme_def = THEMES[theme_id]
    config.set("theme", theme_id)

    # 1. Update theme module variables
    theme_mod = sys.modules[__name__]
    for k, v in theme_def.colors.items():
        setattr(theme_mod, k, v)
        globals()[k] = v

    # 2. Propagate to all loaded loupe modules that imported these variables
    for mod_name, mod in list(sys.modules.items()):
        if mod and (mod_name.startswith("loupe.") or mod_name == "loupe"):
            for k, v in theme_def.colors.items():
                if hasattr(mod, k):
                    setattr(mod, k, v)

    # 3. Apply Qt Palette and Stylesheet
    app = app or QApplication.instance()
    if app:
        setup_palette(app)
        app.setStyleSheet(get_application_stylesheet())

    theme_manager.theme_changed.emit(theme_id)
    return True

def setup_palette(app: QApplication):
    """Enforce correct light or dark palette on QApplication."""
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
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF") if not is_current_theme_light() else QColor("#000000"))
    palette.setColor(QPalette.ColorRole.Link, accent)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, text_mut)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_mut)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, text_mut)

    app.setPalette(palette)

# Backward compatibility alias
setup_dark_palette = setup_palette

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
    """Returns the comprehensive stylesheet dynamically tuned to the active theme."""
    is_light = is_current_theme_light()

    if is_light:
        keep_bg = "#DCFCE7"
        keep_color = "#15803D"
        keep_border = "#22C55E"
        keep_hover_bg = "#BBF7D0"

        reject_bg = "#FEE2E2"
        reject_color = "#B91C1C"
        reject_border = "#EF4444"
        reject_hover_bg = "#FECACA"

        maybe_bg = "#FEF3C7"
        maybe_color = "#B45309"
        maybe_border = "#F59E0B"
        maybe_hover_bg = "#FDE68A"

        resume_bg = "#EFF6FF"
        resume_color = COLOR_ACCENT
        resume_border = COLOR_ACCENT
    else:
        keep_bg = "#1A3323"
        keep_color = "#7BE4A2"
        keep_border = COLOR_STATUS_KEPT
        keep_hover_bg = "#244631"

        reject_bg = "#381B1B"
        reject_color = "#F87171"
        reject_border = COLOR_STATUS_REJECTED
        reject_hover_bg = "#4D2525"

        maybe_bg = "#2D2314"
        maybe_color = "#FBBF24"
        maybe_border = "#D97706"
        maybe_hover_bg = "#42321B"

        resume_bg = "#2D2214" if current_theme_id == "darkroom_amber" else COLOR_BG_ELEVATED
        resume_color = "#FFAE42" if current_theme_id == "darkroom_amber" else COLOR_ACCENT
        resume_border = COLOR_ACCENT

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
        background-color: {COLOR_ACCENT};
        color: #FFFFFF;
        font-weight: 700;
        font-size: 13px;
        border: 1px solid {COLOR_ACCENT_HOVER};
        border-radius: 3px;
        padding: 7px 16px;
    }}
    QPushButton#accentButton:hover {{
        background-color: {COLOR_ACCENT_HOVER};
        color: #FFFFFF;
        border-color: {COLOR_BORDER_FOCUS};
    }}
    QPushButton#accentButton:pressed {{
        background-color: {COLOR_ACCENT_PRESSED};
        color: #FFFFFF;
    }}
    QPushButton#accentButton:focus {{
        border: 2px solid #FFFFFF;
    }}

    /* Card Primary Action Button */
    QPushButton#resumeCullButton {{
        background-color: {resume_bg};
        color: {resume_color};
        border: 1px solid {resume_border};
        border-radius: 2px;
        padding: 7px 16px;
        font-weight: 600;
        font-size: 13px;
    }}
    QPushButton#resumeCullButton:hover {{
        background-color: {COLOR_ACCENT};
        color: #FFFFFF;
        border: 1px solid {COLOR_ACCENT_HOVER};
    }}
    QPushButton#resumeCullButton:pressed {{
        background-color: {COLOR_ACCENT_PRESSED};
        color: #FFFFFF;
    }}

    /* Keep (W) Button */
    QPushButton#keepButton {{
        background-color: {keep_bg};
        color: {keep_color};
        border: 1px solid {keep_border};
        font-weight: 600;
        padding: 9px 18px;
    }}
    QPushButton#keepButton:hover {{
        background-color: {keep_hover_bg};
    }}
    QPushButton#keepButton:pressed {{
        background-color: {keep_bg};
    }}
    QPushButton#keepButton:focus {{
        border: 2px solid {keep_border};
    }}

    /* Reject (S) Button */
    QPushButton#rejectButton {{
        background-color: {reject_bg};
        color: {reject_color};
        border: 1px solid {reject_border};
        font-weight: 600;
        padding: 9px 18px;
    }}
    QPushButton#rejectButton:hover {{
        background-color: {reject_hover_bg};
    }}
    QPushButton#rejectButton:pressed {{
        background-color: {reject_bg};
    }}
    QPushButton#rejectButton:focus {{
        border: 2px solid {reject_border};
    }}

    /* Maybe (E) Button */
    QPushButton#maybeButton {{
        background-color: {maybe_bg};
        color: {maybe_color};
        border: 1px solid {maybe_border};
        font-weight: 600;
        padding: 9px 18px;
    }}
    QPushButton#maybeButton:hover {{
        background-color: {maybe_hover_bg};
    }}
    QPushButton#maybeButton:pressed {{
        background-color: {maybe_bg};
    }}
    QPushButton#maybeButton:focus {{
        border: 2px solid {maybe_border};
    }}

    /* Finish Session Button */
    QPushButton#finishButton {{
        background-color: #065F46;
        color: #FFFFFF;
        border: 1px solid #10B981;
        font-weight: 700;
        font-size: 13px;
        padding: 6px 16px;
        border-radius: 3px;
    }}
    QPushButton#finishButton:hover {{
        background-color: #047857;
        color: #FFFFFF;
        border-color: #34D399;
    }}
    QPushButton#finishButton:pressed {{
        background-color: #064E3B;
    }}
    QPushButton#finishButton:focus {{
        border: 2px solid #34D399;
    }}

    /* Line Edits & Inputs */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
        background-color: {COLOR_BG_SURFACE};
        color: {COLOR_TEXT_PRIMARY};
        border: 1px solid {COLOR_BORDER_DISTINCT};
        border-radius: 2px;
        padding: 6px 10px;
        selection-background-color: {COLOR_ACCENT};
        selection-color: #FFFFFF;
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
