"""Preloading pause overlay showing batch progress, live transfer speed (MB/s), and ETA."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame, QPushButton
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_DISTINCT,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
    COLOR_ACCENT, COLOR_STATUS_KEPT, get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon

class PreloadOverlay(QWidget):
    """In-app pause overlay displayed when navigating beyond currently preloaded buffer."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self.setObjectName("PreloadOverlay")
        self._init_ui()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 12, 16, 215))

    def show(self):
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().show()
        self.raise_()

    def _init_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(24, 24, 24, 24)
        outer_layout.setAlignment(Qt.AlignCenter)

        self.card = QFrame(self)
        self.card.setFixedWidth(520)
        self.card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 6px;
            }}
        """)
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Top Title & Icon
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(render_icon("loupe", 24, COLOR_ACCENT).pixmap(24, 24))
        icon_lbl.setStyleSheet("border: none;")
        top_row.addWidget(icon_lbl)

        title_v = QVBoxLayout()
        title_v.setSpacing(2)
        self.title_lbl = QLabel("Preloading Next Photo Buffer")
        self.title_lbl.setFont(get_display_font(16, bold=True))
        self.title_lbl.setStyleSheet("border: none;")
        title_v.addWidget(self.title_lbl)

        self.subtitle_lbl = QLabel("Loading next batch of full-resolution photos into memory...")
        self.subtitle_lbl.setFont(get_body_font(12))
        self.subtitle_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; border: none;")
        self.subtitle_lbl.setWordWrap(True)
        title_v.addWidget(self.subtitle_lbl)

        top_row.addLayout(title_v)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(12)
        layout.addWidget(self.progress_bar)

        # Telemetry Row (Speed, ETA, Filename)
        telemetry_frame = QFrame()
        telemetry_frame.setStyleSheet(f"background-color: {COLOR_BG_ELEVATED}; border-radius: 3px; padding: 6px; border: 1px solid {COLOR_BORDER_DISTINCT};")
        t_layout = QVBoxLayout(telemetry_frame)
        t_layout.setContentsMargins(10, 8, 10, 8)
        t_layout.setSpacing(4)

        row_metrics = QHBoxLayout()
        self.speed_lbl = QLabel("Speed: — MB/s")
        self.speed_lbl.setFont(get_mono_font(12, bold=True))
        self.speed_lbl.setStyleSheet(f"color: {COLOR_ACCENT}; border: none;")
        row_metrics.addWidget(self.speed_lbl)

        row_metrics.addStretch()

        self.eta_lbl = QLabel("ETA: Calculating...")
        self.eta_lbl.setFont(get_mono_font(12, bold=True))
        self.eta_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; border: none;")
        row_metrics.addWidget(self.eta_lbl)
        t_layout.addLayout(row_metrics)

        self.file_lbl = QLabel("Preparing cache buffer...")
        self.file_lbl.setFont(get_body_font(11))
        self.file_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; border: none;")
        t_layout.addWidget(self.file_lbl)

        layout.addWidget(telemetry_frame)
        outer_layout.addWidget(self.card)

    def set_batch_info(self, start_idx: int, end_idx: int, target_idx: int):
        self.title_lbl.setText("Decoded Cache Limit Reached")
        self.subtitle_lbl.setText(
            f"Navigated to photo {target_idx + 1}. Loading photos {start_idx + 1} to {end_idx + 1} into memory..."
        )
        self.progress_bar.setValue(0)
        self.speed_lbl.setText("Speed: Initializing...")
        self.eta_lbl.setText("ETA: Calculating...")

    def update_progress(self, completed: int, total: int, speed_mb_s: float, eta_sec: float, filename: str):
        if total > 0:
            pct = int((completed / total) * 100)
            self.progress_bar.setValue(pct)

        speed_str = f"Speed: {speed_mb_s:.1f} MB/s" if speed_mb_s > 0 else "Speed: — MB/s"
        self.speed_lbl.setText(speed_str)

        if eta_sec > 0:
            eta_str = f"ETA: {eta_sec:.1f}s"
        else:
            eta_str = "ETA: Finishing..."
        self.eta_lbl.setText(eta_str)

        if filename:
            self.file_lbl.setText(f"Decoded: {filename} ({completed}/{total})")
