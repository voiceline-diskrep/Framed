"""In-app video session setup view and dialog for scanning video directories and initializing sorting sessions."""

import os
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QComboBox, QFrame, QMessageBox,
    QDateEdit, QRadioButton, QButtonGroup, QScrollArea, QApplication
)
from PySide6.QtCore import Qt, QDate, Signal
from loupe.models import Project, PhotoItem
from loupe.storage import storage
from loupe.core.video_engine import VIDEO_EXTENSIONS
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_DISTINCT,
    COLOR_BORDER_SUBTLE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
    COLOR_ACCENT, COLOR_STATUS_KEPT, COLOR_STATUS_REJECTED,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon


class VideoSessionView(QWidget):
    """Full in-app view for setting up and ingesting new video sorting sessions."""

    session_created = Signal(str)  # Emits project_id when project is created
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")

        self.scanned_items: List[PhotoItem] = []
        self.created_project: Optional[Project] = None

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Top Navigation Bar (Always visible)
        top_bar = QFrame()
        top_bar.setObjectName("videoSetupTopBar")
        top_bar.setStyleSheet(f"""
            QFrame#videoSetupTopBar {{
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

        title_lbl = QLabel("NEW VIDEO SORTING SESSION")
        title_lbl.setFont(get_mono_font(11, bold=True))
        title_lbl.setStyleSheet(f"color: {COLOR_ACCENT}; letter-spacing: 1px;")
        top_layout.addWidget(title_lbl)

        top_layout.addStretch()

        badge = QLabel("VIDEO SORT WORKSTATION")
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

        center_container = QWidget()
        center_container.setMaximumWidth(880)
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(18)

        # Header intro
        head_v = QVBoxLayout()
        head_v.setSpacing(4)
        h_title = QLabel("Create Video Sorting Session")
        h_title.setFont(get_display_font(20, bold=True))
        h_sub = QLabel("Select your video clips directory, configure streaming, and set up non-destructive sorting.")
        h_sub.setFont(get_body_font(13))
        h_sub.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        head_v.addWidget(h_title)
        head_v.addWidget(h_sub)
        center_layout.addLayout(head_v)

        # 1. Source Folder Card
        card_dir = self._create_card()
        cd_layout = QVBoxLayout(card_dir)
        cd_layout.setSpacing(12)

        lbl_dir = QLabel("1. SOURCE FOOTAGE DIRECTORY")
        lbl_dir.setFont(get_mono_font(11, bold=True))
        lbl_dir.setStyleSheet(f"color: {COLOR_ACCENT};")
        cd_layout.addWidget(lbl_dir)

        r_dir = QHBoxLayout()
        r_dir.setSpacing(10)
        self.edit_dir = QLineEdit()
        self.edit_dir.setFont(get_body_font(12))
        self.edit_dir.setPlaceholderText("Select folder containing video clips (MP4, MOV, MKV, etc.)...")
        self.edit_dir.setMinimumHeight(40)
        self.edit_dir.setStyleSheet(f"""
            QLineEdit {{
                padding: 0 12px;
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        r_dir.addWidget(self.edit_dir, stretch=1)

        btn_browse = QPushButton("Browse Folder...")
        btn_browse.setFont(get_body_font(12, bold=True))
        btn_browse.setIcon(render_icon("folder", 14, COLOR_TEXT_PRIMARY))
        btn_browse.setMinimumHeight(40)
        btn_browse.setStyleSheet(f"""
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
        btn_browse.clicked.connect(self._browse)
        r_dir.addWidget(btn_browse)
        cd_layout.addLayout(r_dir)

        self.lbl_scan_status = QLabel("No directory selected.")
        self.lbl_scan_status.setFont(get_mono_font(11))
        self.lbl_scan_status.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        cd_layout.addWidget(self.lbl_scan_status)
        center_layout.addWidget(card_dir)

        # 2. Session Name & Workspace Folder Card
        card_meta = self._create_card()
        cm_layout = QVBoxLayout(card_meta)
        cm_layout.setSpacing(14)

        lbl_meta = QLabel("2. SESSION IDENTITY & WORKSPACE")
        lbl_meta.setFont(get_mono_font(11, bold=True))
        lbl_meta.setStyleSheet(f"color: {COLOR_ACCENT};")
        cm_layout.addWidget(lbl_meta)

        row_meta = QHBoxLayout()
        row_meta.setSpacing(12)

        # Name
        v_name = QVBoxLayout()
        v_name.addWidget(QLabel("Session Name:"))
        self.edit_name = QLineEdit("Untitled Video Session")
        self.edit_name.setFont(get_body_font(12))
        self.edit_name.setMinimumHeight(40)
        self.edit_name.setStyleSheet(f"""
            QLineEdit {{
                padding: 0 12px;
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        v_name.addWidget(self.edit_name)
        row_meta.addLayout(v_name, stretch=2)

        # Workspace Folder
        v_folder = QVBoxLayout()
        v_folder.addWidget(QLabel("Workspace Folder:"))
        self.combo_folder = QComboBox()
        self.combo_folder.setFont(get_body_font(12))
        self.combo_folder.setMinimumHeight(40)
        self.combo_folder.setStyleSheet(f"""
            QComboBox {{
                padding: 0 12px;
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
        v_folder.addWidget(self.combo_folder)
        row_meta.addLayout(v_folder, stretch=1)

        # Shoot Date
        v_date = QVBoxLayout()
        v_date.addWidget(QLabel("Shoot Date:"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setFont(get_body_font(12))
        self.date_edit.setMinimumHeight(40)
        self.date_edit.setStyleSheet(f"""
            QDateEdit {{
                padding: 0 12px;
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QDateEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        v_date.addWidget(self.date_edit)
        row_meta.addLayout(v_date, stretch=1)

        cm_layout.addLayout(row_meta)
        center_layout.addWidget(card_meta)

        # 3. Playback & Scrubbing Options
        card_opt = self._create_card()
        co_layout = QVBoxLayout(card_opt)
        co_layout.setSpacing(12)

        lbl_opt = QLabel("3. PLAYBACK ENGINE & PROXY CONFIGURATION")
        lbl_opt.setFont(get_mono_font(11, bold=True))
        lbl_opt.setStyleSheet(f"color: {COLOR_ACCENT};")
        co_layout.addWidget(lbl_opt)

        self.group_mode = QButtonGroup(self)
        self.rb_compressed = QRadioButton("Fast Compressed Previews (reduces 1GB+ files to ~250MB for zero-stutter scrubbing)")
        self.rb_compressed.setChecked(True)
        self.rb_uncompressed = QRadioButton("View with no compression (Direct original playback from disk)")

        self.group_mode.addButton(self.rb_compressed, 1)
        self.group_mode.addButton(self.rb_uncompressed, 2)

        co_layout.addWidget(self.rb_compressed)
        co_layout.addWidget(self.rb_uncompressed)

        notice = QLabel("• 0 RAM consumption: videos stream directly from disk to keep your system ultra responsive.\n• Keyboard shortcuts: W = Selected, S = Similar, X = Unselected, A / D = Previous / Next clip.")
        notice.setFont(get_body_font(11))
        notice.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; line-height: 1.4;")
        co_layout.addWidget(notice)

        center_layout.addWidget(card_opt)

        content_outer_layout.addStretch(1)
        content_outer_layout.addWidget(center_container, stretch=6)
        content_outer_layout.addStretch(1)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, stretch=1)

        # 3. Fixed Bottom Action Bar
        bottom_bar = QFrame()
        bottom_bar.setObjectName("videoSetupBottomBar")
        bottom_bar.setStyleSheet(f"""
            QFrame#videoSetupBottomBar {{
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

        self.btn_create = QPushButton("Start Video Session")
        self.btn_create.setObjectName("accentButton")
        self.btn_create.setIcon(render_icon("arrow_right", 13, "#FFFFFF"))
        self.btn_create.setMinimumHeight(40)
        self.btn_create.setStyleSheet("""
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
        self.btn_create.setEnabled(False)
        self.btn_create.clicked.connect(self._create_session)
        bottom_layout.addWidget(self.btn_create)

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
        self.combo_folder.clear()
        for f in storage.get_folders():
            self.combo_folder.addItem(f.name, f.id)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select Video Directory", self.edit_dir.text())
        if d:
            self.edit_dir.setText(d)
            self._scan_directory(d)

    def _scan_directory(self, folder_path: str):
        self.scanned_items.clear()
        if not os.path.exists(folder_path):
            self.lbl_scan_status.setText("Directory does not exist.")
            self.lbl_scan_status.setStyleSheet(f"color: {COLOR_STATUS_REJECTED};")
            self.btn_create.setEnabled(False)
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
            self.lbl_scan_status.setStyleSheet(f"color: {COLOR_STATUS_REJECTED};")
            self.btn_create.setEnabled(False)
            return

        count = len(self.scanned_items)
        mb = total_bytes / (1024 * 1024)
        gb = mb / 1024.0

        if count > 0:
            sz_str = f"{gb:.2f} GB" if gb >= 1.0 else f"{mb:.1f} MB"
            self.lbl_scan_status.setText(f"✓ Found {count} video clip(s) ({sz_str})")
            self.lbl_scan_status.setStyleSheet(f"color: {COLOR_STATUS_KEPT};")
            self.btn_create.setEnabled(True)
            folder_base = os.path.basename(os.path.normpath(folder_path))
            if folder_base and self.edit_name.text() in ("Untitled Video Session", ""):
                self.edit_name.setText(folder_base)
        else:
            self.lbl_scan_status.setText("No supported video clips found in directory.")
            self.lbl_scan_status.setStyleSheet(f"color: {COLOR_STATUS_REJECTED};")
            self.btn_create.setEnabled(False)

    def reset_form(self):
        """Reset form fields when starting fresh."""
        self._populate_folders()
        self.edit_dir.setText("")
        self.lbl_scan_status.setText("No directory selected.")
        self.lbl_scan_status.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        self.btn_create.setEnabled(False)
        self.scanned_items = []
        self.created_project = None
        self.edit_name.setText("New Video Session")
        self.date_edit.setDate(QDate.currentDate())
        self.rb_compressed.setChecked(True)

    def _create_session(self):
        if not self.scanned_items:
            p = self.edit_dir.text().strip()
            if p and os.path.exists(p):
                self._scan_directory(p)

        if not self.scanned_items:
            QMessageBox.warning(self, "No Videos Found", "Please choose a directory with video files (MP4, MOV, MKV, etc.).")
            return

        name = self.edit_name.text().strip() or "Untitled Video Session"
        folder_id = self.combo_folder.currentData() or "folder_personal"
        src_dir = self.edit_dir.text().strip()

        proj = Project(
            name=name,
            folder_id=folder_id,
            source_dir=src_dir,
            media_type="video",
            shoot_date=self.date_edit.date().toString("yyyy-MM-dd"),
            items=self.scanned_items
        )
        storage.save_project(proj)
        self.created_project = proj
        self.session_created.emit(proj.id)


class VideoSessionDialog(QDialog):
    """Dialog wrapper around VideoSessionView for standalone test compatibility."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Video Sort Session — Framed")
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")
        self.setMinimumSize(600, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.view = VideoSessionView(self)
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

    def __getattr__(self, name):
        return getattr(self.view, name)
