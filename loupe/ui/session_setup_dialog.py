"""Session setup dialog asking format choice, pair synchronization, and plain-language RAM budget allocation."""

import os
from typing import Optional, List, Dict
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QRadioButton, QButtonGroup, QCheckBox, QSlider, QSpinBox,
    QFileDialog, QFrame, QMessageBox, QDateEdit, QWidget, QScrollArea
)
from PySide6.QtCore import Qt, QDate
from loupe.config import config, get_total_system_ram_gb
from loupe.storage import storage
from loupe.models import Project, PhotoItem, Folder
from loupe.core.decoder import RAW_EXTENSIONS, JPEG_EXTENSIONS
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_SUBTLE,
    COLOR_BORDER_DISTINCT, COLOR_BORDER_FOCUS, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_STATUS_KEPT,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon

class SessionSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Culling Session — Configuration")
        self.setMinimumSize(560, 360)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")

        self.scanned_items: List[PhotoItem] = []
        self.total_bytes_scanned: int = 0
        self.created_project: Optional[Project] = None

        self._init_ui()
        self._fit_to_available_screen()
        self._update_format_visibility()

    def _fit_to_available_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            target_w = min(700, max(560, avail.width() - 40))
            target_h = min(620, max(360, avail.height() - 60))
            self.resize(target_w, target_h)
            x = avail.x() + (avail.width() - target_w) // 2
            y = avail.y() + max(10, (avail.height() - target_h) // 2)
            self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_to_available_screen()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        title = QLabel("Setup New Culling Session")
        title.setFont(get_display_font(18, bold=True))
        sub = QLabel("Select photo source, choose format handling, and configure memory preloading.")
        sub.setFont(get_body_font(13))
        sub.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        header_layout.addWidget(title)
        header_layout.addWidget(sub)
        main_layout.addLayout(header_layout)

        # Scrollable form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        form_layout = QVBoxLayout(container)
        form_layout.setContentsMargins(0, 8, 0, 8)
        form_layout.setSpacing(18)

        # Section 1: Session Details
        sec1 = self._create_card()
        sec1_layout = QVBoxLayout(sec1)
        sec1_layout.setSpacing(12)

        sec1_title = QLabel("1. SESSION DETAILS & SOURCE")
        sec1_title.setFont(get_mono_font(11, bold=True))
        sec1_title.setStyleSheet(f"color: {COLOR_ACCENT};")
        sec1_layout.addWidget(sec1_title)

        row1 = QHBoxLayout()
        row1.setSpacing(12)

        # Session Name
        v1 = QVBoxLayout()
        v1.addWidget(QLabel("Session Name:"))
        self.name_edit = QLineEdit("Nordic Coastal Shoot")
        v1.addWidget(self.name_edit)
        row1.addLayout(v1, stretch=2)

        # Folder
        v2 = QVBoxLayout()
        v2.addWidget(QLabel("Folder:"))
        self.folder_combo = QComboBox()
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
        v3.addWidget(self.date_edit)
        row1.addLayout(v3, stretch=1)

        sec1_layout.addLayout(row1)

        # Source Directory Picker
        dir_layout = QVBoxLayout()
        dir_layout.setSpacing(6)
        dir_layout.addWidget(QLabel("Source Photo Directory:"))
        
        dir_row = QHBoxLayout()
        self.source_dir_edit = QLineEdit()
        self.source_dir_edit.setPlaceholderText("Select directory containing camera RAW or JPEG files...")
        dir_row.addWidget(self.source_dir_edit, stretch=1)

        browse_btn = QPushButton("Browse Folder")
        browse_btn.setIcon(render_icon("folder", 14, COLOR_TEXT_PRIMARY))
        browse_btn.clicked.connect(self._browse_directory)
        dir_row.addWidget(browse_btn)
        dir_layout.addLayout(dir_row)

        self.scan_status_lbl = QLabel("No directory selected yet.")
        self.scan_status_lbl.setFont(get_mono_font(11))
        self.scan_status_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        dir_layout.addWidget(self.scan_status_lbl)

        sec1_layout.addLayout(dir_layout)
        form_layout.addWidget(sec1)

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

        form_layout.addWidget(sec2)

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

        form_layout.addWidget(self.sec3)

        # Section 4: RAM Budget & Preloading
        sec4 = self._create_card()
        sec4_layout = QVBoxLayout(sec4)
        sec4_layout.setSpacing(12)

        sec4_title = QLabel("4. MEMORY BUFFER & PRELOADING BUDGET")
        sec4_title.setFont(get_mono_font(11, bold=True))
        sec4_title.setStyleSheet(f"color: {COLOR_ACCENT};")
        sec4_layout.addWidget(sec4_title)

        ram_expl = QLabel(
            "Preloading decodes full-resolution photos into RAM in advance so moving between photos has zero lag. "
            "Default allocation is 50% of this session's total photo size, capped by your global budget."
        )
        ram_expl.setFont(get_body_font(12))
        ram_expl.setWordWrap(True)
        ram_expl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        sec4_layout.addWidget(ram_expl)

        # Ram slider row
        slider_row = QHBoxLayout()
        slider_row.setSpacing(16)

        self.ram_slider = QSlider(Qt.Horizontal)
        self.ram_slider.setRange(512, 16384)  # 512 MB to 16 GB
        self.ram_slider.setValue(2048)
        self.ram_slider.valueChanged.connect(self._on_ram_slider_changed)
        slider_row.addWidget(self.ram_slider, stretch=1)

        self.ram_val_lbl = QLabel("2,048 MB")
        self.ram_val_lbl.setFont(get_mono_font(13, bold=True))
        self.ram_val_lbl.setFixedWidth(90)
        self.ram_val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider_row.addWidget(self.ram_val_lbl)

        sec4_layout.addLayout(slider_row)

        self.batch_calc_lbl = QLabel(
            "Buffer holding: 16 full-resolution photos.\n"
            "Preloads the first 16 photos before starting. When you reach photo 16, "
            "Framed will pause to load the next batch with live speed and ETA."
        )
        self.batch_calc_lbl.setFont(get_mono_font(11))
        self.batch_calc_lbl.setStyleSheet(f"color: {COLOR_STATUS_KEPT};")
        sec4_layout.addWidget(self.batch_calc_lbl)

        form_layout.addWidget(sec4)

        scroll.setWidget(container)
        main_layout.addWidget(scroll, stretch=1)

        # Footer Buttons
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(12)

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
                border-radius: 3px;
                padding: 0 20px;
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
        footer_layout.addWidget(self.start_btn, stretch=1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFont(get_body_font(12))
        cancel_btn.setMinimumHeight(40)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 0 18px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                border-color: {COLOR_TEXT_SECONDARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        footer_layout.addWidget(cancel_btn)

        main_layout.addLayout(footer_layout)

    def _create_card(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 2px;
                padding: 12px;
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

    def _browse_directory(self):
        d = QFileDialog.getExistingDirectory(self, "Select Photo Directory")
        if d:
            self.source_dir_edit.setText(d)
            # Default session name from directory name if untitled
            if self.name_edit.text() in ("Nordic Coastal Shoot", ""):
                self.name_edit.setText(os.path.basename(d))
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

            r_path = raw_files.get(stem)
            j_path = jpeg_files.get(stem)
            r_sz = os.path.getsize(r_path) if r_path else 0
            j_sz = os.path.getsize(j_path) if j_path else 0

            # Determine primary display path
            if fmt_mode == "raw_only":
                primary = r_path
            elif fmt_mode == "jpeg_only":
                primary = j_path
            else:  # both: prefer RAW for full raw inspection, or JPEG if raw missing
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

        # Calibrate default RAM preload: 50% of total session size, capped by global budget
        global_budget_mb = config.get("ram_budget_gb", 16) * 1024
        rec_ram_mb = max(512, min(int(total_mb * 0.5), global_budget_mb))
        self.ram_slider.setValue(rec_ram_mb)
        self._update_batch_calc(rec_ram_mb)

    def _on_ram_slider_changed(self, val_mb: int):
        self.ram_val_lbl.setText(f"{val_mb:,} MB")
        self._update_batch_calc(val_mb)

    def _update_batch_calc(self, ram_mb: int):
        # Average full-resolution uncompressed photo in RAM is ~60-80 MB
        avg_photo_mb = 75
        batch_size = max(4, min(32, int(ram_mb / avg_photo_mb)))
        self.calculated_batch_size = batch_size
        self.batch_calc_lbl.setText(
            f"Buffer holds: {batch_size} full-resolution photos in memory.\n"
            f"Loads the first {batch_size} photos before starting. When you reach photo {batch_size}, "
            f"Framed will pause to load the next {batch_size} photos with live speed and ETA."
        )

    def _start_session(self):
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
        self.accept()
