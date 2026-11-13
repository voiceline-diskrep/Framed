from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame, QPushButton, QCheckBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_DISTINCT,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
    COLOR_ACCENT, COLOR_ACCENT_HOVER, COLOR_ACCENT_PRESSED, COLOR_STATUS_KEPT,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon

class PreloadOverlay(QWidget):
    """In-app pause overlay displayed when navigating beyond currently preloaded buffer."""
    afk_requested = Signal()
    sort_now_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self.setObjectName("PreloadOverlay")
        self._batch_count: int = 0
        self._completed_count: int = 0
        self._memory_mode: str = "ram"
        self._sort_now_triggered: bool = False
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
        self.card.setFixedWidth(540)
        self.card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 6px;
            }}
        """)
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Top Title, Icon & Memory Mode Pill
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

        top_row.addLayout(title_v, stretch=1)

        self.memory_mode_lbl = QLabel("RAM")
        self.memory_mode_lbl.setFont(get_mono_font(10, bold=True))
        self.memory_mode_lbl.setAlignment(Qt.AlignCenter)
        self.memory_mode_lbl.setStyleSheet(f"""
            background-color: {COLOR_BG_ELEVATED};
            color: {COLOR_ACCENT};
            border: 1px solid {COLOR_ACCENT};
            border-radius: 4px;
            padding: 3px 9px;
        """)
        top_row.addWidget(self.memory_mode_lbl, alignment=Qt.AlignTop)
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

        # Primary Early-Sort Action ("Sort Now")
        self.btn_sort_now = QPushButton("Sort Now (Waiting: 0/10 Ready)")
        self.btn_sort_now.setFont(get_body_font(12, bold=True))
        self.btn_sort_now.setMinimumHeight(40)
        self.btn_sort_now.setEnabled(False)
        self.btn_sort_now.clicked.connect(self._on_sort_now_clicked)
        self._apply_sort_now_style(enabled=False)
        layout.addWidget(self.btn_sort_now)

        # Auto-start checkbox
        self.auto_sort_cb = QCheckBox("Auto-start sorting once 10 photos are ready")
        self.auto_sort_cb.setFont(get_body_font(11))
        self.auto_sort_cb.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; border: none;")
        self.auto_sort_cb.toggled.connect(self._on_auto_sort_toggled)
        layout.addWidget(self.auto_sort_cb)

        # AFK Mode Action Row
        afk_row = QHBoxLayout()
        afk_row.setSpacing(10)
        self.btn_afk = QPushButton("  AFK Mode (Minimize & Notify When Done)")
        self.btn_afk.setIcon(render_icon("settings", 12, COLOR_ACCENT))
        self.btn_afk.setFont(get_body_font(11, bold=True))
        self.btn_afk.setMinimumHeight(32)
        self.btn_afk.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_ACCENT};
                border-radius: 6px;
                padding: 0 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {COLOR_ACCENT};
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                padding-top: 2px;
            }}
        """)
        self.btn_afk.clicked.connect(self._on_afk_clicked)
        afk_row.addWidget(self.btn_afk)
        layout.addLayout(afk_row)

        outer_layout.addWidget(self.card)

    def _apply_sort_now_style(self, enabled: bool):
        if enabled:
            self.btn_sort_now.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_ACCENT};
                    color: #FFFFFF;
                    border: 1px solid {COLOR_ACCENT_HOVER};
                    border-radius: 6px;
                    padding: 0 18px;
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    background-color: {COLOR_ACCENT_HOVER};
                    color: #FFFFFF;
                }}
                QPushButton:pressed {{
                    background-color: {COLOR_ACCENT_PRESSED};
                    padding-top: 2px;
                }}
            """)
        else:
            self.btn_sort_now.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_BG_ELEVATED};
                    color: {COLOR_TEXT_MUTED};
                    border: 1px solid {COLOR_BORDER_DISTINCT};
                    border-radius: 6px;
                    padding: 0 18px;
                    font-weight: 600;
                }}
            """)

    def set_memory_mode(self, memory_mode: str = "ram"):
        mode = (memory_mode or "ram").lower()
        self._memory_mode = mode
        if mode == "vram":
            label_txt = "GPU VRAM"
            pill_color = COLOR_STATUS_KEPT
        elif mode == "mixed":
            label_txt = "MIXED (VRAM + RAM)"
            pill_color = COLOR_ACCENT
        else:
            label_txt = "SYSTEM RAM"
            pill_color = COLOR_ACCENT
        self.memory_mode_lbl.setText(label_txt)
        self.memory_mode_lbl.setStyleSheet(f"""
            background-color: {COLOR_BG_ELEVATED};
            color: {pill_color};
            border: 1px solid {pill_color};
            border-radius: 4px;
            padding: 3px 9px;
        """)

    def set_batch_info(
        self,
        start_idx: int,
        end_idx: int,
        target_idx: int,
        total_items: Optional[int] = None,
        memory_mode: str = "ram",
    ):
        count = max(0, end_idx - start_idx + 1)
        self._batch_count = count
        self._completed_count = 0
        self._sort_now_triggered = False
        self.set_memory_mode(memory_mode)

        mode_desc = {
            "vram": "GPU VRAM",
            "mixed": "VRAM + RAM",
            "ram": "RAM",
        }.get(self._memory_mode, "RAM")

        if total_items and start_idx == 0 and end_idx >= total_items - 1:
            self.title_lbl.setText(f"Preloading Entire Session into {mode_desc}")
            self.subtitle_lbl.setText(
                f"Loading all {total_items} full-resolution photos into {mode_desc} for zero-lag culling..."
            )
        else:
            self.title_lbl.setText(f"Preloading Photo Buffer ({mode_desc})")
            self.subtitle_lbl.setText(
                f"Navigated to photo {target_idx + 1}. Loading {count} photos (photos {start_idx + 1} to {end_idx + 1}) into {mode_desc}..."
            )

        min_ready = min(10, count) if count > 0 else 0
        self.btn_sort_now.setEnabled(False)
        self.btn_sort_now.setText(f"Sort Now (Waiting: 0/{min_ready} Ready)")
        self._apply_sort_now_style(enabled=False)

        self.btn_afk.setEnabled(True)
        self.btn_afk.setText("  AFK Mode (Minimize & Notify When Done)")

        self.progress_bar.setValue(0)
        self.speed_lbl.setText("Speed: Initializing...")
        self.eta_lbl.setText("ETA: Calculating...")
        self.file_lbl.setText("Preparing cache buffer...")

    def update_progress(self, completed: int, total: int, speed_mb_s: float, eta_sec: float, filename: str):
        self._completed_count = completed
        effective_total = total if total > 0 else self._batch_count
        if total > 0:
            self._batch_count = total
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
            self.file_lbl.setText(f"Decoded: {filename} ({completed}/{effective_total})")

        # Update Sort Now gate: min(10, total_batch_count)
        min_ready = min(10, effective_total) if effective_total > 0 else 0
        if effective_total > 0 and completed >= min_ready:
            if not self.btn_sort_now.isEnabled():
                self.btn_sort_now.setEnabled(True)
                self._apply_sort_now_style(enabled=True)
            self.btn_sort_now.setText(f"⚡ Sort Now ({completed} Ready — Stream Rest in Background)")
            if self.auto_sort_cb.isChecked() and not self._sort_now_triggered:
                self._sort_now_triggered = True
                self.sort_now_requested.emit()
        else:
            if self.btn_sort_now.isEnabled():
                self.btn_sort_now.setEnabled(False)
                self._apply_sort_now_style(enabled=False)
            self.btn_sort_now.setText(f"Sort Now (Waiting: {completed}/{min_ready} Ready)")

    def _on_sort_now_clicked(self):
        if not self.btn_sort_now.isEnabled():
            return
        self._sort_now_triggered = True
        self.sort_now_requested.emit()

    def _on_auto_sort_toggled(self, checked: bool):
        if checked and self.btn_sort_now.isEnabled() and not self._sort_now_triggered:
            self._sort_now_triggered = True
            self.sort_now_requested.emit()

    def _on_afk_clicked(self):
        self.btn_afk.setText("✓ AFK Mode Active — You will be notified when ready")
        self.btn_afk.setEnabled(False)
        self.afk_requested.emit()
