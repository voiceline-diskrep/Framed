"""Video session setup dialog for scanning video directories and initializing video sorting sessions."""

import os
from typing import Optional, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QComboBox, QFrame, QMessageBox
)
from PySide6.QtCore import Qt
from loupe.models import Project, PhotoItem
from loupe.storage import storage
from loupe.core.video_engine import VIDEO_EXTENSIONS
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_DISTINCT,
    COLOR_BORDER_SUBTLE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_ACCENT,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon

class VideoSessionDialog(QDialog):
    """Setup dialog specifically for video sorting sessions."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Video Sort Session — Framed")
        self.setFixedSize(540, 460)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")
        self.scanned_items: List[PhotoItem] = []
        self.created_project: Optional[Project] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        h_layout = QVBoxLayout()
        tag = QLabel("VIDEO SORT WORKSTATION")
        tag.setFont(get_mono_font(10, bold=True))
        tag.setStyleSheet(f"color: {COLOR_ACCENT}; letter-spacing: 1px;")
        h_layout.addWidget(tag)

        title = QLabel("Create Video Sorting Session")
        title.setFont(get_display_font(18, bold=True))
        h_layout.addWidget(title)
        layout.addLayout(h_layout)

        # 1. Source Folder
        card_dir = QFrame()
        card_dir.setStyleSheet(f"background-color: {COLOR_BG_SURFACE}; border: 1px solid {COLOR_BORDER_DISTINCT}; border-radius: 2px; padding: 12px;")
        cd_layout = QVBoxLayout(card_dir)
        cd_layout.setSpacing(8)

        lbl_dir = QLabel("SOURCE FOOTAGE DIRECTORY:")
        lbl_dir.setFont(get_mono_font(10, bold=True))
        lbl_dir.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        cd_layout.addWidget(lbl_dir)

        r_dir = QHBoxLayout()
        self.edit_dir = QLineEdit()
        self.edit_dir.setFont(get_body_font(12))
        self.edit_dir.setPlaceholderText("Select folder containing video clips (MP4, MOV, MKV, etc.)...")
        self.edit_dir.setStyleSheet(f"padding: 6px 10px; background-color: {COLOR_BG_ELEVATED}; border: 1px solid {COLOR_BORDER_SUBTLE};")
        r_dir.addWidget(self.edit_dir)

        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse)
        r_dir.addWidget(btn_browse)
        cd_layout.addLayout(r_dir)

        self.lbl_scan_status = QLabel("No directory selected.")
        self.lbl_scan_status.setFont(get_mono_font(11))
        self.lbl_scan_status.setStyleSheet(f"color: {COLOR_ACCENT};")
        cd_layout.addWidget(self.lbl_scan_status)
        layout.addWidget(card_dir)

        # 2. Session Name & Workspace Folder
        card_meta = QFrame()
        card_meta.setStyleSheet(f"background-color: {COLOR_BG_SURFACE}; border: 1px solid {COLOR_BORDER_DISTINCT}; border-radius: 2px; padding: 12px;")
        cm_layout = QVBoxLayout(card_meta)
        cm_layout.setSpacing(10)

        lbl_name = QLabel("Session Name:")
        lbl_name.setFont(get_body_font(12, bold=True))
        cm_layout.addWidget(lbl_name)

        self.edit_name = QLineEdit("Untitled Video Session")
        self.edit_name.setFont(get_body_font(12))
        self.edit_name.setStyleSheet(f"padding: 6px 10px; background-color: {COLOR_BG_ELEVATED}; border: 1px solid {COLOR_BORDER_SUBTLE};")
        cm_layout.addWidget(self.edit_name)

        lbl_folder = QLabel("Workspace Folder:")
        lbl_folder.setFont(get_body_font(12, bold=True))
        cm_layout.addWidget(lbl_folder)

        self.combo_folder = QComboBox()
        self.combo_folder.setFont(get_body_font(12))
        for f in storage.get_folders():
            self.combo_folder.addItem(f.name, f.id)
        cm_layout.addWidget(self.combo_folder)

        layout.addWidget(card_meta)

        # Telemetry notice
        notice = QLabel("• Videos stream directly from disk (0 RAM consumption).\n• Fast ~250MB proxies generate in the background with uncompressed toggle.")
        notice.setFont(get_body_font(11))
        notice.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        layout.addWidget(notice)

        layout.addStretch()

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_row.addStretch()

        self.btn_create = QPushButton("Start Video Session")
        self.btn_create.setObjectName("accentButton")
        self.btn_create.setIcon(render_icon("arrow_right", 13, "#0E1013"))
        self.btn_create.setMinimumHeight(36)
        self.btn_create.clicked.connect(self._create_session)
        btn_row.addWidget(self.btn_create)

        layout.addLayout(btn_row)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select Video Directory", self.edit_dir.text())
        if d:
            self.edit_dir.setText(d)
            self._scan_directory(d)

    def _scan_directory(self, folder_path: str):
        self.scanned_items.clear()
        if not os.path.exists(folder_path):
            self.lbl_scan_status.setText("Directory does not exist.")
            return

        total_bytes = 0
        try:
            for entry in os.scandir(folder_path):
                if entry.is_file():
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext in VIDEO_EXTENSIONS:
                        sz = entry.stat().st_size
                        total_bytes += sz
                        item = PhotoItem(
                            base_name=os.path.splitext(entry.name)[0],
                            primary_path=entry.path,
                            raw_size=sz,
                            is_video=True,
                            status="pending"
                        )
                        self.scanned_items.append(item)
        except Exception as e:
            self.lbl_scan_status.setText(f"Scan error: {e}")
            return

        count = len(self.scanned_items)
        mb = total_bytes / (1024 * 1024)
        gb = mb / 1024.0

        if count > 0:
            sz_str = f"{gb:.2f} GB" if gb >= 1.0 else f"{mb:.1f} MB"
            self.lbl_scan_status.setText(f"✓ Found {count} video clip(s) ({sz_str})")
            # Suggest name from folder
            folder_base = os.path.basename(os.path.normpath(folder_path))
            if folder_base:
                self.edit_name.setText(folder_base)
        else:
            self.lbl_scan_status.setText("No supported video clips found in directory.")

    def _create_session(self):
        if not self.scanned_items:
            # Try scanning current edit_dir text if user typed it
            p = self.edit_dir.text().strip()
            if p and os.path.exists(p):
                self._scan_directory(p)

        if not self.scanned_items:
            QMessageBox.warning(self, "No Videos Found", "Please choose a directory with video files (MP4, MOV, MKV, etc.).")
            return

        name = self.edit_name.text().strip() or "Untitled Video Session"
        folder_id = self.combo_folder.currentData() or "default"
        src_dir = self.edit_dir.text().strip()

        proj = Project(
            name=name,
            folder_id=folder_id,
            source_dir=src_dir,
            media_type="video",
            items=self.scanned_items
        )
        storage.save_project(proj)
        self.created_project = proj
        self.accept()
