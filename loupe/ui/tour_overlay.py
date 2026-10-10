"""Skippable guided onboarding tour explaining each area and walking through project creation."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget
)
from PySide6.QtCore import Qt, Signal
from loupe.config import config
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_SUBTLE,
    COLOR_BORDER_DISTINCT, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_STATUS_KEPT,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon

TOUR_STEPS = [
    {
        "title": "Welcome to Framed",
        "badge": "OPTICAL WORKSTATION OVERVIEW",
        "body": (
            "Framed is engineered for photographers who need to inspect and cull high-volume RAW shoots without fatigue.\n\n"
            "By directly decoding sensor data with LibRaw and caching full-resolution frames into memory, "
            "you get instant navigation with zero shutter lag."
        ),
        "highlight": "No compressed previews, no cloud uploads, and never touches your original files."
    },
    {
        "title": "Workspace Folders & Sessions",
        "badge": "ORGANIZATION",
        "body": (
            "Organize ongoing work into custom folders like 'School', 'Weddings', or 'Personal'.\n\n"
            "Each session tracks its shoot date, format modes (RAW, JPEG, or paired), "
            "and saves your exact culling state automatically when you exit."
        ),
        "highlight": "Click '+ New Culling Session' anytime to import a directory."
    },
    {
        "title": "Rapid Culling Ergonomics",
        "badge": "CORE WORKFLOW",
        "body": (
            "Review photos using high-speed keyboard shortcuts designed for muscle memory:\n\n"
            "•  W — Keep Photo (Forest Sage)\n"
            "•  S — Move to Not Accepted (Cinnabar Red)\n"
            "•  A / D — Previous / Next Frame\n"
            "•  Ctrl+Z — Reversible Undo"
        ),
        "highlight": "All keys can be customized anytime in Settings."
    },
    {
        "title": "Inspection Loupe & Telemetry",
        "badge": "PRECISION OPTICS",
        "body": (
            "Press 'I' to toggle the Optical Telemetry panel for camera, ISO, shutter, and aperture EXIF readouts.\n\n"
            "Enable 'Start zoomed in' to automatically inspect facial focus at 200% on the top-left quadrant "
            "the moment each photo opens, without repeated zooming."
        ),
        "highlight": "Accidental rejections can be restored anytime via the Not Accepted drawer."
    },
    {
        "title": "Two-Folder Structured Export",
        "badge": "NON-DESTRUCTIVE ARCHITECTURE",
        "body": (
            "When your culling session is complete, click Export.\n\n"
            "Framed generates a clean project folder with two subfolders:\n"
            "•  Selected/ (RAW and JPEG folders)\n"
            "•  Unselected/ (RAW and JPEG folders)"
        ),
        "highlight": "Original files are safely copied — never moved, overwritten, or deleted."
    }
]

class TourDialog(QDialog):
    tour_completed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Framed — Quick Guided Tour")
        self.setFixedSize(580, 420)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE}; border: 1px solid {COLOR_BORDER_DISTINCT};")
        self.current_step = 0

        self._init_ui()
        self._update_step()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 24, 28, 24)
        main_layout.setSpacing(16)

        # Header: Step Counter & Skip
        header = QHBoxLayout()
        self.step_counter_lbl = QLabel("Step 1 of 5")
        self.step_counter_lbl.setFont(get_mono_font(11, bold=True))
        self.step_counter_lbl.setStyleSheet(f"color: {COLOR_ACCENT};")
        header.addWidget(self.step_counter_lbl)

        header.addStretch()

        self.skip_btn = QPushButton("Skip Tour")
        self.skip_btn.setFont(get_body_font(12))
        self.skip_btn.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; border: none; padding: 4px 8px;")
        self.skip_btn.clicked.connect(self._skip_tour)
        header.addWidget(self.skip_btn)

        main_layout.addLayout(header)

        # Content Card
        self.card = QFrame()
        self.card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_SUBTLE};
                border-radius: 2px;
                padding: 16px;
            }}
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setSpacing(10)

        self.badge_lbl = QLabel("OVERVIEW")
        self.badge_lbl.setFont(get_mono_font(10, bold=True))
        self.badge_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; letter-spacing: 1px;")
        card_layout.addWidget(self.badge_lbl)

        self.title_lbl = QLabel("Welcome to Loupe")
        self.title_lbl.setFont(get_display_font(18, bold=True))
        card_layout.addWidget(self.title_lbl)

        self.body_lbl = QLabel("")
        self.body_lbl.setFont(get_body_font(13))
        self.body_lbl.setWordWrap(True)
        self.body_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; line-height: 1.5;")
        card_layout.addWidget(self.body_lbl, stretch=1)

        # Highlight callout box
        self.callout_frame = QFrame()
        self.callout_frame.setStyleSheet(f"background-color: {COLOR_BG_ELEVATED}; border-left: 3px solid {COLOR_ACCENT}; padding: 8px 12px;")
        callout_layout = QVBoxLayout(self.callout_frame)
        callout_layout.setContentsMargins(0, 0, 0, 0)
        self.callout_lbl = QLabel("")
        self.callout_lbl.setFont(get_mono_font(11))
        self.callout_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")
        callout_layout.addWidget(self.callout_lbl)
        card_layout.addWidget(self.callout_frame)

        main_layout.addWidget(self.card, stretch=1)

        # Footer Buttons
        footer = QHBoxLayout()
        footer.setSpacing(12)

        self.prev_btn = QPushButton("Back")
        self.prev_btn.setMinimumHeight(36)
        self.prev_btn.clicked.connect(self._prev_step)
        footer.addWidget(self.prev_btn)

        footer.addStretch()

        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("accentButton")
        self.next_btn.setMinimumHeight(36)
        self.next_btn.setMinimumWidth(120)
        self.next_btn.clicked.connect(self._next_step)
        footer.addWidget(self.next_btn)

        main_layout.addLayout(footer)

    def _update_step(self):
        step_data = TOUR_STEPS[self.current_step]
        self.step_counter_lbl.setText(f"Step {self.current_step + 1} of {len(TOUR_STEPS)}")
        self.badge_lbl.setText(step_data["badge"])
        self.title_lbl.setText(step_data["title"])
        self.body_lbl.setText(step_data["body"])
        self.callout_lbl.setText(step_data["highlight"])

        self.prev_btn.setEnabled(self.current_step > 0)
        if self.current_step == len(TOUR_STEPS) - 1:
            self.next_btn.setText("Get Started")
        else:
            self.next_btn.setText("Next")

    def _next_step(self):
        if self.current_step < len(TOUR_STEPS) - 1:
            self.current_step += 1
            self._update_step()
        else:
            self._finish_tour()

    def _prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            self._update_step()

    def _skip_tour(self):
        self._finish_tour()

    def _finish_tour(self):
        config.set("has_completed_tour", True)
        self.tour_completed.emit()
        self.accept()
