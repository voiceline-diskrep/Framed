"""Finish Session confirmation dialog allowing user to choose between 'Finish Now' and 'Finish and Export'."""

from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QApplication
)
from PySide6.QtCore import Qt
from loupe.models import Project
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BG_HOVER,
    COLOR_BORDER_SUBTLE, COLOR_BORDER_DISTINCT, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_ACCENT,
    COLOR_STATUS_KEPT, COLOR_STATUS_REJECTED, COLOR_STATUS_MAYBE,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon

class FinishSessionDialog(QDialog):
    FINISH_NOW = "finish_now"
    FINISH_AND_EXPORT = "finish_and_export"

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.choice: Optional[str] = None
        self.setWindowTitle("Session Complete — Finish Session")
        self.setMinimumSize(480, 360)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")

        self._init_ui()
        self._fit_to_available_screen()

    def _fit_to_available_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            target_w = min(540, max(460, avail.width() - 40))
            target_h = min(460, max(360, avail.height() - 60))
            self.resize(target_w, target_h)
            x = avail.x() + (avail.width() - target_w) // 2
            y = avail.y() + max(10, (avail.height() - target_h) // 2)
            self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_to_available_screen()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Header with green checkmark
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(16)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(render_icon("check", 28, "#10B981").pixmap(32, 32))
        icon_lbl.setStyleSheet("background-color: #064E3B; padding: 6px; border: 1px solid #059669; border-radius: 6px;")
        hdr_row.addWidget(icon_lbl)

        hdr_text = QVBoxLayout()
        hdr_text.setSpacing(4)
        title = QLabel("All Items Culled!")
        title.setFont(get_display_font(18, bold=True))
        title.setStyleSheet("color: #FFFFFF;")

        term = "clips" if self.project.media_type == "video" else "pictures"
        sub = QLabel(f"You have finished sorting all {self.project.total_count} {term} in '{self.project.name}'.")
        sub.setFont(get_body_font(12))
        sub.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        sub.setWordWrap(True)

        hdr_text.addWidget(title)
        hdr_text.addWidget(sub)
        hdr_row.addLayout(hdr_text)
        hdr_row.addStretch()
        layout.addLayout(hdr_row)

        # Summary Tally Card
        summary_card = QFrame()
        summary_card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
                padding: 12px;
            }}
        """)
        s_layout = QHBoxLayout(summary_card)
        s_layout.setContentsMargins(16, 10, 16, 10)
        s_layout.setSpacing(20)

        # Kept / Selected
        lbl_kept = QLabel(f"✓ {self.project.kept_count} Kept")
        lbl_kept.setFont(get_mono_font(12, bold=True))
        lbl_kept.setStyleSheet("color: #7BE4A2;")
        s_layout.addWidget(lbl_kept)

        # Maybe / Similar
        lbl_maybe = QLabel(f"? {self.project.maybe_count} Maybe")
        lbl_maybe.setFont(get_mono_font(12, bold=True))
        lbl_maybe.setStyleSheet("color: #FBBF24;")
        s_layout.addWidget(lbl_maybe)

        # Rejected / Unselected
        lbl_rej = QLabel(f"✕ {self.project.rejected_count} Not Accepted")
        lbl_rej.setFont(get_mono_font(12, bold=True))
        lbl_rej.setStyleSheet("color: #F87171;")
        s_layout.addWidget(lbl_rej)

        s_layout.addStretch()
        layout.addWidget(summary_card)

        # Prompt question
        question_lbl = QLabel("How would you like to proceed?")
        question_lbl.setFont(get_body_font(13, bold=True))
        question_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")
        layout.addWidget(question_lbl)

        # Action Choices Container
        actions_layout = QVBoxLayout()
        actions_layout.setSpacing(12)

        # Option 1: Finish and Export
        btn_export = QPushButton("  Finish and Export")
        btn_export.setIcon(render_icon("export", 16, "#FFFFFF"))
        btn_export.setMinimumHeight(48)
        btn_export.setStyleSheet(f"""
            QPushButton {{
                background-color: #D97706;
                color: #FFFFFF;
                border: 1px solid #F59E0B;
                border-radius: 4px;
                font-weight: 700;
                font-size: 14px;
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: #F59E0B;
            }}
            QPushButton:pressed {{
                background-color: #B45309;
            }}
        """)
        btn_export.clicked.connect(self._choose_export)
        actions_layout.addWidget(btn_export)

        # Option 2: Finish Now
        btn_finish = QPushButton("  Finish Now (Return to Dashboard)")
        btn_finish.setIcon(render_icon("check", 16, "#FFFFFF"))
        btn_finish.setMinimumHeight(46)
        btn_finish.setStyleSheet(f"""
            QPushButton {{
                background-color: #065F46;
                color: #FFFFFF;
                border: 1px solid #10B981;
                border-radius: 4px;
                font-weight: 700;
                font-size: 13px;
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: #047857;
            }}
            QPushButton:pressed {{
                background-color: #064E3B;
            }}
        """)
        btn_finish.clicked.connect(self._choose_finish_now)
        actions_layout.addWidget(btn_finish)

        layout.addLayout(actions_layout)

        # Footer Cancel / Review More
        footer = QHBoxLayout()
        footer.addStretch()
        cancel_btn = QPushButton("Continue Reviewing")
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLOR_TEXT_MUTED};
                border: none;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                text-decoration: underline;
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)
        footer.addStretch()
        layout.addLayout(footer)

    def _choose_finish_now(self):
        self.choice = self.FINISH_NOW
        self.accept()

    def _choose_export(self):
        self.choice = self.FINISH_AND_EXPORT
        self.accept()
