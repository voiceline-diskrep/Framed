"""In-app photo session setup view and dialog for configuring shoot ingestion, pair sync, and RAM preloading."""

import os
from typing import Optional, List, Dict
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QRadioButton, QButtonGroup, QCheckBox, QSlider, QSpinBox,
    QFileDialog, QFrame, QMessageBox, QDateEdit, QScrollArea, QApplication
)
from PySide6.QtCore import Qt, QDate, Signal
from loupe.config import config, get_total_system_ram_gb
from loupe.storage import storage
from loupe.models import Project, PhotoItem, Folder
from loupe.core.decoder import RAW_EXTENSIONS, JPEG_EXTENSIONS
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_SUBTLE,
    COLOR_BORDER_DISTINCT, COLOR_BORDER_FOCUS, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_STATUS_KEPT,
    COLOR_STATUS_REJECTED, get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon


class SessionSetupView(QWidget):
    """Full in-app view for setting up and ingesting new photographic culling sessions."""

    session_created = Signal(str)  # Emits project_id when project is created
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")

        self.scanned_items: List[PhotoItem] = []
        self.total_bytes_scanned: int = 0
        self.created_project: Optional[Project] = None
        self.calculated_batch_size: int = 16

        self._init_ui()
        self._update_format_visibility()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Top Navigation Bar (Always visible)
        top_bar = QFrame()
        top_bar.setObjectName("setupTopBar")
        top_bar.setStyleSheet(f"""
            QFrame#setupTopBar {{
                background-color: {COLOR_BG_SURFACE};
                border-bottom: 1px solid {COLOR_BORDER_SUBTLE};
            }}
        """)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(24, 12, 24, 12)
        top_layout.setSpacing(16)

        self.btn_back = QPushButton("  Back to Dashboard")
        self.btn_back.setIcon(render_icon("arrow_left", 14, COLOR_TEXT_PRIMARY))
        self.btn_back.setFont(get_body_font(12, bold=True))
        self.btn_back.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
                color: {COLOR_TEXT_PRIMARY};
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_BG_ELEVATED};
                border-color: {COLOR_TEXT_SECONDARY};
            }}
        """)
        self.btn_back.clicked.connect(self.cancelled.emit)
        top_layout.addWidget(self.btn_back)

        title_lbl = QLabel("NEW PHOTO CULLING SESSION")
        title_lbl.setFont(get_mono_font(11, bold=True))
        title_lbl.setStyleSheet(f"color: {COLOR_ACCENT}; letter-spacing: 1px;")
        top_layout.addWidget(title_lbl)

        top_layout.addStretch()

        badge = QLabel("PHOTO INGEST ENGINE")
        badge.setFont(get_mono_font(10, bold=True))
        badge.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; background: {COLOR_BG_ELEVATED}; padding: 4px 8px; border-radius: 3px;")
        top_layout.addWidget(badge)

        main_layout.addWidget(top_bar)

        # 2. Scrollable Form Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        content_outer_layout = QHBoxLayout(scroll_content)
        content_outer_layout.setContentsMargins(24, 20, 24, 20)

        # Centered container with responsive max-width for comfortable layout
        center_container = QWidget()
        center_container.setMaximumWidth(880)
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(18)

        # Header intro
        head_v = QVBoxLayout()
        head_v.setSpacing(4)
        h_title = QLabel("Setup New Culling Session")
        h_title.setFont(get_display_font(20, bold=True))
        h_sub = QLabel("Select your photo directory, configure RAW & JPEG handling, and calibrate RAM preloading.")
        h_sub.setFont(get_body_font(13))
        h_sub.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        head_v.addWidget(h_title)
        head_v.addWidget(h_sub)
        center_layout.addLayout(head_v)

        # Section 1: Session Details & Source
        sec1 = self._create_card()
        sec1_layout = QVBoxLayout(sec1)
        sec1_layout.setSpacing(14)

        sec1_title = QLabel("1. SESSION DETAILS & WORKSPACE")
        sec1_title.setFont(get_mono_font(11, bold=True))
        sec1_title.setStyleSheet(f"color: {COLOR_ACCENT};")
        sec1_layout.addWidget(sec1_title)

        row1 = QHBoxLayout()
        row1.setSpacing(12)

        # Session Name
        v1 = QVBoxLayout()
        v1.addWidget(QLabel("Session Name:"))
        self.name_edit = QLineEdit("Nordic Coastal Shoot")
        self.name_edit.setFont(get_body_font(12))
        self.name_edit.setMinimumHeight(38)
        self.name_edit.setStyleSheet(f"""
            QLineEdit {{
                padding: 0 10px;
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        v1.addWidget(self.name_edit)
        row1.addLayout(v1, stretch=2)

        # Workspace Folder
        v2 = QVBoxLayout()
        v2.addWidget(QLabel("Workspace Folder:"))
        self.folder_combo = QComboBox()
        self.folder_combo.setFont(get_body_font(12))
        self.folder_combo.setMinimumHeight(38)
        self.folder_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 0 10px;
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QComboBox:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        self._populate_folders()
        v2.addWidget(self.folder_combo)
        row1.addLayout(v2, stretch=1)

        # Shoot Date
        v3 = QVBoxLayout()
        v3.addWidget(QLabel("Shoot Date:"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setFont(get_body_font(12))
        self.date_edit.setMinimumHeight(38)
        self.date_edit.setStyleSheet(f"""
            QDateEdit {{
                padding: 0 10px;
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QDateEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        v3.addWidget(self.date_edit)
        row1.addLayout(v3, stretch=1)

        sec1_layout.addLayout(row1)

        # Source Directory Picker
        dir_layout = QVBoxLayout()
        dir_layout.setSpacing(6)
        dir_layout.addWidget(QLabel("Source Photo Directory:"))

        dir_row = QHBoxLayout()
        dir_row.setSpacing(10)
        self.source_dir_edit = QLineEdit()
        self.source_dir_edit.setFont(get_body_font(12))
        self.source_dir_edit.setPlaceholderText("Select folder containing camera RAW or JPEG files...")
        self.source_dir_edit.setMinimumHeight(38)
        self.source_dir_edit.setStyleSheet(f"""
            QLineEdit {{
                padding: 0 10px;
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        self.source_dir_edit.textChanged.connect(self._on_source_dir_text_changed)
        dir_row.addWidget(self.source_dir_edit, stretch=1)

        browse_btn = QPushButton("Browse Folder...")
        browse_btn.setFont(get_body_font(12, bold=True))
        browse_btn.setIcon(render_icon("folder", 14, COLOR_TEXT_PRIMARY))
        browse_btn.setMinimumHeight(38)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QPushButton:hover {{
                border-color: {COLOR_TEXT_SECONDARY};
                background-color: #2A2E35;
            }}
        """)
        browse_btn.clicked.connect(self._browse_directory)
        dir_row.addWidget(browse_btn)
        dir_layout.addLayout(dir_row)

        self.scan_status_lbl = QLabel("No directory selected yet.")
        self.scan_status_lbl.setFont(get_mono_font(11))
        self.scan_status_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        dir_layout.addWidget(self.scan_status_lbl)

        sec1_layout.addLayout(dir_layout)
        center_layout.addWidget(sec1)

        # Section 2: Format Selection
        sec2 = self._create_card()
        sec2_layout = QVBoxLayout(sec2)
        sec2_layout.setSpacing(12)

        sec2_title = QLabel("2. FORMAT SELECTION")
        sec2_title.setFont(get_mono_font(11, bold=True))
        sec2_title.setStyleSheet(f"color: {COLOR_ACCENT};")
        sec2_layout.addWidget(sec2_title)

        sec2_desc = QLabel("Which formats are you sorting in this session?")
        sec2_desc.setFont(get_body_font(12))
        sec2_desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        sec2_layout.addWidget(sec2_desc)

        self.format_group = QButtonGroup(self)
        self.rb_both = QRadioButton("Both RAW and JPEG (Recommended for paired shoots)")
        self.rb_raw = QRadioButton("RAW only (CR2/CR3, NEF, ARW, RAF, ORF, DNG, etc.)")
        self.rb_jpeg = QRadioButton("JPEG only (.JPG, .JPEG)")
        self.rb_both.setChecked(True)

        self.format_group.addButton(self.rb_both, 1)
        self.format_group.addButton(self.rb_raw, 2)
        self.format_group.addButton(self.rb_jpeg, 3)
        self.format_group.idClicked.connect(self._on_format_changed)

        sec2_layout.addWidget(self.rb_both)
        sec2_layout.addWidget(self.rb_raw)
        sec2_layout.addWidget(self.rb_jpeg)

        center_layout.addWidget(sec2)

        # Section 3: Pair Synchronization
        self.sec3 = self._create_card()
        sec3_layout = QVBoxLayout(self.sec3)
        sec3_layout.setSpacing(10)

        sec3_title = QLabel("3. RAW & JPEG PAIR SYNCHRONIZATION")
        sec3_title.setFont(get_mono_font(11, bold=True))
        sec3_title.setStyleSheet(f"color: {COLOR_ACCENT};")
        sec3_layout.addWidget(sec3_title)

        self.sync_checkbox = QCheckBox("Synchronize matching RAW and JPEG pairs")
        self.sync_checkbox.setChecked(config.get("default_sync_pairs", True))
        sec3_layout.addWidget(self.sync_checkbox)

        sync_desc = QLabel(
            "Matching files usually share a filename and differ only by extension "
            "(e.g., DSC0102.ARW and DSC0102.JPG). With sync on, deleting or rejecting a RAW "
            "also rejects its matching JPEG, and the reverse. Sync never permanently deletes any original files."
        )
        sync_desc.setFont(get_body_font(12))
        sync_desc.setWordWrap(True)
        sync_desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; line-height: 1.4;")
        sec3_layout.addWidget(sync_desc)

        center_layout.addWidget(self.sec3)

        # Section 4: RAM Budget & Preloading
        sec4 = self._create_card()
        sec4_layout = QVBoxLayout(sec4)
        sec4_layout.setSpacing(12)

        sec4_title = QLabel("4. MEMORY BUFFER & PRELOADING BUDGET")
        sec4_title.setFont(get_mono_font(11, bold=True))
        sec4_title.setStyleSheet(f"color: {COLOR_ACCENT};")
        sec4_layout.addWidget(sec4_title)

        total_sys_gb = get_total_system_ram_gb()
        ram_expl = QLabel(
            "Preloading decodes full-resolution photos into RAM in advance so moving between photos has zero lag. "
            f"The more RAM you allocate, the more photos Framed keeps in memory without needing to reload (System RAM: {total_sys_gb} GB)."
        )
        ram_expl.setFont(get_body_font(12))
        ram_expl.setWordWrap(True)
        ram_expl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        sec4_layout.addWidget(ram_expl)

        # RAM slider row
        slider_row = QHBoxLayout()
        slider_row.setSpacing(16)

        max_slider_mb = max(16384, total_sys_gb * 1024)
        default_ram_mb = min(config.get("ram_budget_gb", 16) * 1024, max_slider_mb)

        self.ram_slider = QSlider(Qt.Horizontal)
        self.ram_slider.setRange(512, max_slider_mb)
        self.ram_slider.setSingleStep(512)
        self.ram_slider.setPageStep(2048)
        self.ram_slider.setValue(default_ram_mb)
        self.ram_slider.valueChanged.connect(self._on_ram_slider_changed)
        slider_row.addWidget(self.ram_slider, stretch=1)

        self.ram_val_lbl = QLabel(self._format_ram_mb(default_ram_mb))
        self.ram_val_lbl.setFont(get_mono_font(12, bold=True))
        self.ram_val_lbl.setFixedWidth(160)
        self.ram_val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider_row.addWidget(self.ram_val_lbl)

        sec4_layout.addLayout(slider_row)

        self.batch_calc_lbl = QLabel("")
        self.batch_calc_lbl.setFont(get_mono_font(11))
        self.batch_calc_lbl.setStyleSheet(f"color: {COLOR_STATUS_KEPT};")
        self._update_batch_calc(default_ram_mb)
        sec4_layout.addWidget(self.batch_calc_lbl)

        center_layout.addWidget(sec4)

        content_outer_layout.addStretch(1)
        content_outer_layout.addWidget(center_container, stretch=6)
        content_outer_layout.addStretch(1)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, stretch=1)

        # 3. Fixed Bottom Action Bar
        bottom_bar = QFrame()
        bottom_bar.setObjectName("setupBottomBar")
        bottom_bar.setStyleSheet(f"""
            QFrame#setupBottomBar {{
                background-color: {COLOR_BG_SURFACE};
                border-top: 1px solid {COLOR_BORDER_DISTINCT};
            }}
        """)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(24, 14, 24, 14)
        bottom_layout.setSpacing(16)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFont(get_body_font(12))
        self.btn_cancel.setMinimumHeight(40)
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 0 20px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                border-color: {COLOR_TEXT_SECONDARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        self.btn_cancel.clicked.connect(self.cancelled.emit)
        bottom_layout.addWidget(self.btn_cancel)

        bottom_layout.addStretch()

        self.start_btn = QPushButton("Start Culling Session")
        self.start_btn.setObjectName("accentButton")
        self.start_btn.setIcon(render_icon("loupe", 14, "#FFFFFF"))
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #D97706;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 13px;
                border: 1px solid #F59E0B;
                border-radius: 4px;
                padding: 0 24px;
            }
            QPushButton:hover {
                background-color: #F59E0B;
                color: #FFFFFF;
                border: 1px solid #FBBF24;
            }
            QPushButton:pressed {
                background-color: #B45309;
                color: #FFFFFF;
            }
            QPushButton:disabled {
                background-color: #2D2214;
                color: #5E6672;
                border-color: #3B414B;
            }
        """)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start_session)
        bottom_layout.addWidget(self.start_btn)

        main_layout.addWidget(bottom_bar)

    def _create_card(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
                padding: 16px;
            }}
        """)
        return frame

    def _populate_folders(self):
        self.folder_combo.clear()
        folders = storage.get_folders()
        for f in folders:
            self.folder_combo.addItem(f.name, f.id)

    def _on_format_changed(self, button_id: int):
        self._update_format_visibility()
        self._rescan_items()

    def _update_format_visibility(self):
        is_both = self.rb_both.isChecked()
        self.sec3.setVisible(is_both)

    def _on_source_dir_text_changed(self, text: str):
        d = text.strip()
        if not d:
            self.scan_status_lbl.setText("No directory selected yet.")
            self.scan_status_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
            self.start_btn.setEnabled(False)
            self.scanned_items = []
            return
        if os.path.isdir(d):
            if self.name_edit.text() in ("Nordic Coastal Shoot", "New Photo Shoot", ""):
                self.name_edit.setText(os.path.basename(os.path.normpath(d)))
            self._rescan_items()
        else:
            self.scan_status_lbl.setText("Selected directory does not exist.")
            self.scan_status_lbl.setStyleSheet(f"color: {COLOR_STATUS_REJECTED};")
            self.start_btn.setEnabled(False)
            self.scanned_items = []

    def _browse_directory(self):
        d = QFileDialog.getExistingDirectory(self, "Select Photo Directory")
        if d:
            self.source_dir_edit.setText(d)
            if self.name_edit.text() in ("Nordic Coastal Shoot", "New Photo Shoot", ""):
                self.name_edit.setText(os.path.basename(os.path.normpath(d)))
            self._rescan_items()

    def _rescan_items(self):
        directory = self.source_dir_edit.text().strip()
        if not directory or not os.path.exists(directory):
            self.scan_status_lbl.setText("Selected directory does not exist.")
            self.start_btn.setEnabled(False)
            return

        fmt_mode = "both" if self.rb_both.isChecked() else ("raw_only" if self.rb_raw.isChecked() else "jpeg_only")
        raw_files: Dict[str, str] = {}
        jpeg_files: Dict[str, str] = {}

        try:
            for fname in os.listdir(directory):
                full = os.path.join(directory, fname)
                if not os.path.isfile(full):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                stem = os.path.splitext(fname)[0]
                if ext in RAW_EXTENSIONS:
                    raw_files[stem] = full
                elif ext in JPEG_EXTENSIONS:
                    jpeg_files[stem] = full
        except Exception as e:
            self.scan_status_lbl.setText(f"Error scanning directory: {e}")
            self.start_btn.setEnabled(False)
            return

        all_stems = sorted(list(set(raw_files.keys()) | set(jpeg_files.keys())))
        self.scanned_items = []
        total_bytes = 0

        for stem in all_stems:
            has_raw = stem in raw_files
            has_jpeg = stem in jpeg_files

            if fmt_mode == "raw_only" and not has_raw:
                continue
            if fmt_mode == "jpeg_only" and not has_jpeg:
                continue

            r_path = raw_files.get(stem) if fmt_mode in ("both", "raw_only") else None
            j_path = jpeg_files.get(stem) if fmt_mode in ("both", "jpeg_only") else None
            r_sz = os.path.getsize(r_path) if r_path else 0
            j_sz = os.path.getsize(j_path) if j_path else 0

            if fmt_mode == "raw_only":
                primary = r_path
            elif fmt_mode == "jpeg_only":
                primary = j_path
            else:
                primary = r_path if r_path else j_path

            item = PhotoItem(
                base_name=stem,
                raw_path=r_path,
                jpeg_path=j_path,
                primary_path=primary or "",
                raw_size=r_sz,
                jpeg_size=j_sz,
                status="pending"
            )
            self.scanned_items.append(item)
            total_bytes += (r_sz + j_sz)

        self.total_bytes_scanned = total_bytes
        total_mb = int(total_bytes / (1024 * 1024))
        count = len(self.scanned_items)

        self.scan_status_lbl.setText(
            f"Found {count} sorting items ({len(raw_files)} RAW, {len(jpeg_files)} JPEG) • Total Disk Size: {total_mb} MB"
        )
        self.scan_status_lbl.setStyleSheet(f"color: {COLOR_STATUS_KEPT if count > 0 else COLOR_STATUS_REJECTED};")
        self.start_btn.setEnabled(count > 0)

        global_budget_mb = config.get("ram_budget_gb", 16) * 1024
        total_sys_gb = get_total_system_ram_gb()
        max_slider_mb = max(16384, total_sys_gb * 1024)

        # Allocate enough RAM to hold scanned photos uncompressed without reload pauses
        needed_ram_mb = max(1024, count * 75)
        rec_ram_mb = min(needed_ram_mb, max(2048, global_budget_mb))
        rec_ram_mb = max(512, min(rec_ram_mb, max_slider_mb))

        self.ram_slider.blockSignals(True)
        self.ram_slider.setRange(512, max_slider_mb)
        self.ram_slider.setValue(rec_ram_mb)
        self.ram_val_lbl.setText(self._format_ram_mb(rec_ram_mb))
        self.ram_slider.blockSignals(False)
        self._update_batch_calc(rec_ram_mb)

    @staticmethod
    def _format_ram_mb(val_mb: int) -> str:
        if val_mb >= 1024:
            gb = val_mb / 1024.0
            if gb.is_integer():
                return f"{int(gb)} GB ({val_mb:,} MB)"
            return f"{gb:.1f} GB ({val_mb:,} MB)"
        return f"{val_mb:,} MB"

    def _on_ram_slider_changed(self, val_mb: int):
        self.ram_val_lbl.setText(self._format_ram_mb(val_mb))
        self._update_batch_calc(val_mb)

    def _update_batch_calc(self, ram_mb: int):
        avg_photo_mb = 75
        ram_capacity = max(4, int(ram_mb / avg_photo_mb))
        self.calculated_batch_size = ram_capacity

        count = len(self.scanned_items) if hasattr(self, "scanned_items") and self.scanned_items else 0
        if count > 0 and ram_capacity >= count:
            self.batch_calc_lbl.setText(
                f"Memory buffer: {ram_capacity} photos capacity.\n"
                f"✓ Entire session ({count} photos) will fit in RAM — instant browsing with zero reload pauses!"
            )
            self.batch_calc_lbl.setStyleSheet(f"color: {COLOR_STATUS_KEPT};")
        elif count > 0:
            self.batch_calc_lbl.setText(
                f"Memory buffer: {ram_capacity} photos capacity.\n"
                f"Preloads the first {ram_capacity} photos before starting. When you reach photo {ram_capacity}, "
                f"Framed will pause to load the next batch with live speed and ETA."
            )
            self.batch_calc_lbl.setStyleSheet(f"color: {COLOR_STATUS_KEPT};")
        else:
            self.batch_calc_lbl.setText(
                f"Memory buffer: {ram_capacity} photos capacity.\n"
                f"Holds up to {ram_capacity} full-resolution photos simultaneously in memory."
            )
            self.batch_calc_lbl.setStyleSheet(f"color: {COLOR_STATUS_KEPT};")

    def reset_form(self):
        """Reset form fields when opening a new session."""
        self._populate_folders()
        self.source_dir_edit.blockSignals(True)
        self.source_dir_edit.setText("")
        self.source_dir_edit.blockSignals(False)
        self.scan_status_lbl.setText("No directory selected yet.")
        self.scan_status_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        self.start_btn.setEnabled(False)
        self.scanned_items = []
        self.created_project = None
        self.name_edit.setText("New Photo Shoot")
        self.date_edit.setDate(QDate.currentDate())
        self.rb_both.setChecked(True)
        self._update_format_visibility()

        total_sys_gb = get_total_system_ram_gb()
        max_slider_mb = max(16384, total_sys_gb * 1024)
        default_ram_mb = min(config.get("ram_budget_gb", 16) * 1024, max_slider_mb)
        self.ram_slider.blockSignals(True)
        self.ram_slider.setRange(512, max_slider_mb)
        self.ram_slider.setValue(default_ram_mb)
        self.ram_val_lbl.setText(self._format_ram_mb(default_ram_mb))
        self.ram_slider.blockSignals(False)
        self._update_batch_calc(default_ram_mb)

    def _start_session(self):
        if not self.scanned_items and self.source_dir_edit.text().strip():
            self._rescan_items()

        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a valid session name.")
            return

        fid = self.folder_combo.currentData() or "folder_personal"
        fmt_mode = "both" if self.rb_both.isChecked() else ("raw_only" if self.rb_raw.isChecked() else "jpeg_only")
        sync_pairs = self.sync_checkbox.isChecked() if fmt_mode == "both" else False
        ram_alloc = self.ram_slider.value()

        project = Project(
            name=name,
            folder_id=fid,
            source_dir=self.source_dir_edit.text().strip(),
            format_mode=fmt_mode,
            sync_pairs=sync_pairs,
            ram_allocation_mb=ram_alloc,
            batch_size=getattr(self, "calculated_batch_size", 16),
            shoot_date=self.date_edit.date().toString("yyyy-MM-dd"),
            items=self.scanned_items
        )
        storage.save_project(project)
        self.created_project = project
        self.session_created.emit(project.id)


class SessionSetupDialog(QDialog):
    """Dialog wrapper around SessionSetupView for standalone test compatibility."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Culling Session — Configuration")
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")
        self.setMinimumSize(600, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.view = SessionSetupView(self)
        # In dialog mode, hide top back button since dialog has window titlebar/cancel
        self.view.btn_back.setVisible(False)
        layout.addWidget(self.view)

        self.view.session_created.connect(self._on_session_created)
        self.view.cancelled.connect(self.reject)

        self._fit_to_available_screen()

    def _fit_to_available_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            target_w = min(840, max(600, avail.width() - 40))
            target_h = min(740, max(480, avail.height() - 60))
            self.resize(target_w, target_h)
            x = avail.x() + (avail.width() - target_w) // 2
            y = avail.y() + max(10, (avail.height() - target_h) // 2)
            self.move(x, y)

    def _on_session_created(self, project_id: str):
        self.accept()

    @property
    def created_project(self):
        return self.view.created_project

    @property
    def scanned_items(self):
        return self.view.scanned_items

    @property
    def total_bytes_scanned(self):
        return self.view.total_bytes_scanned

    def __getattr__(self, name):
        return getattr(self.view, name)
