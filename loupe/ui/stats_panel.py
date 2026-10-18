"""Stats and EXIF inspection side panel with 'Start zoomed in' preference and 'Not Accepted' recovery tray."""

from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QCheckBox, QSlider, QScrollArea
)
from PySide6.QtCore import Qt, Signal
from loupe.config import config
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_SUBTLE,
    COLOR_BORDER_DISTINCT, COLOR_BORDER_FOCUS, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_STATUS_REJECTED,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon

class StatsPanel(QFrame):
    start_zoomed_changed = Signal(bool, float)  # enabled, zoom_level
    open_not_accepted_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(310)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border-left: 1px solid {COLOR_BORDER_DISTINCT};
            }}
        """)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("OPTICAL TELEMETRY")
        title.setFont(get_mono_font(11, bold=True))
        title.setStyleSheet(f"color: {COLOR_ACCENT}; letter-spacing: 1px;")
        header.addWidget(title)
        header.addStretch()
        main_layout.addLayout(header)

        # Scrollable telemetry body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # Camera & Lens Card
        cam_card = self._create_card()
        cam_layout = QVBoxLayout(cam_card)
        cam_layout.setSpacing(6)

        self.camera_lbl = QLabel("—")
        self.camera_lbl.setFont(get_display_font(14, bold=True))
        self.camera_lbl.setWordWrap(True)
        cam_layout.addWidget(self.camera_lbl)

        self.lens_lbl = QLabel("—")
        self.lens_lbl.setFont(get_body_font(12))
        self.lens_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        self.lens_lbl.setWordWrap(True)
        cam_layout.addWidget(self.lens_lbl)
        layout.addWidget(cam_card)

        # Exposure Telemetry Grid Card
        exp_card = self._create_card()
        exp_layout = QVBoxLayout(exp_card)
        exp_layout.setSpacing(10)

        exp_title = QLabel("EXPOSURE METRICS")
        exp_title.setFont(get_mono_font(10, bold=True))
        exp_title.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        exp_layout.addWidget(exp_title)

        # 2x2 grid for Shutter, Aperture, ISO, Focal Length
        grid_row1 = QHBoxLayout()
        self.shutter_box = self._create_telemetry_box("SHUTTER", "—")
        self.aperture_box = self._create_telemetry_box("APERTURE", "—")
        grid_row1.addWidget(self.shutter_box)
        grid_row1.addWidget(self.aperture_box)
        exp_layout.addLayout(grid_row1)

        grid_row2 = QHBoxLayout()
        self.iso_box = self._create_telemetry_box("ISO", "—")
        self.focal_box = self._create_telemetry_box("FOCAL LENGTH", "—")
        grid_row2.addWidget(self.iso_box)
        grid_row2.addWidget(self.focal_box)
        exp_layout.addLayout(grid_row2)
        layout.addWidget(exp_card)

        # File Details Card
        file_card = self._create_card()
        file_layout = QVBoxLayout(file_card)
        file_layout.setSpacing(6)

        file_title = QLabel("FILE DETAILS")
        file_title.setFont(get_mono_font(10, bold=True))
        file_title.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        file_layout.addWidget(file_title)

        self.date_taken_lbl = self._create_detail_row("Timestamp:", "—", file_layout)
        self.dim_lbl = self._create_detail_row("Resolution:", "—", file_layout)
        self.size_lbl = self._create_detail_row("File Size:", "—", file_layout)
        self.filename_lbl = self._create_detail_row("Filename:", "—", file_layout)
        layout.addWidget(file_card)

        # Inspection Preference Card ("Start zoomed in")
        zoom_card = self._create_card()
        zoom_layout = QVBoxLayout(zoom_card)
        zoom_layout.setSpacing(10)

        zoom_title = QLabel("INSPECTION LOUPE")
        zoom_title.setFont(get_mono_font(10, bold=True))
        zoom_title.setStyleSheet(f"color: {COLOR_ACCENT};")
        zoom_layout.addWidget(zoom_title)

        self.start_zoomed_cb = QCheckBox("Start zoomed in")
        self.start_zoomed_cb.setChecked(config.get("start_zoomed_in", False))
        self.start_zoomed_cb.stateChanged.connect(self._on_zoom_setting_changed)
        zoom_layout.addWidget(self.start_zoomed_cb)

        zoom_desc = QLabel("Opens each photo at set zoom focused on top-left for rapid focus checking.")
        zoom_desc.setFont(get_body_font(11))
        zoom_desc.setWordWrap(True)
        zoom_desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        zoom_layout.addWidget(zoom_desc)

        # Zoom level slider
        slider_row = QHBoxLayout()
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(100, 400)
        curr_lvl = int(config.get("zoom_start_level", 2.0) * 100)
        self.zoom_slider.setValue(curr_lvl)
        self.zoom_slider.valueChanged.connect(self._on_zoom_setting_changed)
        slider_row.addWidget(self.zoom_slider, stretch=1)

        self.zoom_lvl_lbl = QLabel(f"{curr_lvl}%")
        self.zoom_lvl_lbl.setFont(get_mono_font(12, bold=True))
        self.zoom_lvl_lbl.setFixedWidth(45)
        slider_row.addWidget(self.zoom_lvl_lbl)
        zoom_layout.addLayout(slider_row)

        layout.addWidget(zoom_card)

        scroll.setWidget(container)
        main_layout.addWidget(scroll, stretch=1)

        # Bottom Button: Open "Not Accepted" Folder / Tray
        self.not_accepted_btn = QPushButton("Not Accepted Photos (0)")
        self.not_accepted_btn.setIcon(render_icon("cross", 14, COLOR_STATUS_REJECTED))
        self.not_accepted_btn.setMinimumHeight(38)
        self.not_accepted_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                color: {COLOR_TEXT_PRIMARY};
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {COLOR_STATUS_REJECTED};
            }}
        """)
        self.not_accepted_btn.clicked.connect(self.open_not_accepted_requested.emit)
        main_layout.addWidget(self.not_accepted_btn)

    def _create_card(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_SUBTLE};
                border-radius: 2px;
                padding: 10px;
            }}
        """)
        return frame

    def _create_telemetry_box(self, label: str, val: str) -> QFrame:
        box = QFrame()
        box.setStyleSheet(f"background-color: {COLOR_BG_SURFACE}; border: 1px solid {COLOR_BORDER_SUBTLE}; border-radius: 2px; padding: 6px;")
        l = QVBoxLayout(box)
        l.setContentsMargins(6, 6, 6, 6)
        l.setSpacing(2)

        lbl = QLabel(label)
        lbl.setFont(get_mono_font(9))
        lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        l.addWidget(lbl)

        val_lbl = QLabel(val)
        val_lbl.setFont(get_mono_font(13, bold=True))
        val_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")
        val_lbl.setObjectName("val")
        l.addWidget(val_lbl)
        return box

    def _create_detail_row(self, label: str, val: str, parent_layout: QVBoxLayout) -> QLabel:
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFont(get_body_font(11))
        lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        row.addWidget(lbl)

        val_lbl = QLabel(val)
        val_lbl.setFont(get_mono_font(11))
        val_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")
        val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(val_lbl, stretch=1)
        parent_layout.addLayout(row)
        return val_lbl

    def update_metadata(self, meta: Dict[str, Any]):
        self.camera_lbl.setText(meta.get("camera", "—"))
        self.lens_lbl.setText(meta.get("lens", "—"))

        # Update telemetry values
        self.shutter_box.findChild(QLabel, "val").setText(meta.get("shutter_speed", "—"))
        self.aperture_box.findChild(QLabel, "val").setText(meta.get("aperture", "—"))
        self.iso_box.findChild(QLabel, "val").setText(meta.get("iso", "—"))
        self.focal_box.findChild(QLabel, "val").setText(meta.get("focal_length", "—"))

        self.date_taken_lbl.setText(meta.get("date_taken", "—"))
        self.dim_lbl.setText(meta.get("dimensions", "—"))
        self.size_lbl.setText(meta.get("file_size", "—"))
        self.filename_lbl.setText(meta.get("file_name", "—"))

    def update_rejected_count(self, count: int):
        self.not_accepted_btn.setText(f"Not Accepted Photos ({count})")

    def reset_telemetry(self):
        """Reset all optical telemetry readouts to clean blank state."""
        self.camera_lbl.setText("—")
        self.lens_lbl.setText("—")
        shutter_val = self.shutter_box.findChild(QLabel, "val")
        if shutter_val:
            shutter_val.setText("—")
        aperture_val = self.aperture_box.findChild(QLabel, "val")
        if aperture_val:
            aperture_val.setText("—")
        iso_val = self.iso_box.findChild(QLabel, "val")
        if iso_val:
            iso_val.setText("—")
        focal_val = self.focal_box.findChild(QLabel, "val")
        if focal_val:
            focal_val.setText("—")
        self.date_taken_lbl.setText("—")
        self.dim_lbl.setText("—")
        self.size_lbl.setText("—")
        self.filename_lbl.setText("—")
        self.update_rejected_count(0)

    def _on_zoom_setting_changed(self):
        enabled = self.start_zoomed_cb.isChecked()
        level = self.zoom_slider.value() / 100.0
        self.zoom_lvl_lbl.setText(f"{self.zoom_slider.value()}%")
        config.set("start_zoomed_in", enabled)
        config.set("zoom_start_level", level)
        self.start_zoomed_changed.emit(enabled, level)
