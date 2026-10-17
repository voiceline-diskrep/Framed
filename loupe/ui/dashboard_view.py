"""Dashboard (main menu) view displaying working folders, projects, dates, and dual-mode Photo/Video switching."""

import os
import shutil
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QScrollArea, QFrame, QInputDialog,
    QMessageBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
    QLineEdit, QComboBox
)
from PySide6.QtCore import Qt, Signal, QDate, QSize
from PySide6.QtGui import QPainter, QColor
from loupe.models import Folder, Project
from loupe.storage import storage
from loupe.config import config
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BG_HOVER,
    COLOR_BORDER_SUBTLE, COLOR_BORDER_DISTINCT, COLOR_BORDER_FOCUS,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
    COLOR_ACCENT, COLOR_STATUS_KEPT, COLOR_STATUS_REJECTED,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon


class DashboardModalOverlay(QWidget):
    """Semi-transparent in-app modal overlay to host cards natively inside DashboardView."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self.setObjectName("DashboardModalOverlay")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(20, 20, 20, 20)
        outer_layout.setAlignment(Qt.AlignCenter)

        self.card = QFrame(self)
        self.card.setObjectName("inAppModalCard")
        self.card.setFixedWidth(460)
        self.card.setStyleSheet(f"""
            QFrame#inAppModalCard {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 6px;
            }}
            QLineEdit, QComboBox, QDateEdit {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(24, 22, 24, 22)
        self.card_layout.setSpacing(14)

        outer_layout.addWidget(self.card)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 12, 16, 215))

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.pos()):
            self.hide()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def _clear_card(self):
        while self.card_layout.count():
            item = self.card_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            l = item.layout()
            if l:
                while l.count():
                    sub = l.takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

    def show_create_folder(self, on_created):
        self._clear_card()

        # Header
        h_row = QHBoxLayout()
        title = QLabel("Create Workspace Folder")
        title.setFont(get_display_font(15, bold=True))
        h_row.addWidget(title)
        h_row.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(24, 24)
        btn_x.setStyleSheet(f"border: none; color: {COLOR_TEXT_MUTED}; font-size: 14px; font-weight: bold;")
        btn_x.clicked.connect(self.hide)
        h_row.addWidget(btn_x)
        self.card_layout.addLayout(h_row)

        desc = QLabel("Enter a name for your new workspace category (e.g. Commercial, Weddings, Portraits):")
        desc.setFont(get_body_font(12))
        desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; line-height: 1.4;")
        desc.setWordWrap(True)
        self.card_layout.addWidget(desc)

        edit = QLineEdit()
        edit.setPlaceholderText("Folder Name...")
        edit.setMinimumHeight(38)
        self.card_layout.addWidget(edit)

        # Buttons
        b_row = QHBoxLayout()
        b_row.setSpacing(10)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(get_body_font(12))
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        btn_cancel.clicked.connect(self.hide)
        b_row.addWidget(btn_cancel)

        b_row.addStretch()

        btn_confirm = QPushButton("Create Folder")
        btn_confirm.setObjectName("accentButton")
        btn_confirm.setFont(get_body_font(12, bold=True))
        btn_confirm.setMinimumHeight(36)
        btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #D97706;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 12px;
                border: 1px solid #F59E0B;
                border-radius: 3px;
                padding: 0 18px;
            }
            QPushButton:hover {
                background-color: #F59E0B;
            }
        """)

        def _submit():
            val = edit.text().strip()
            if val:
                self.hide()
                on_created(val)

        btn_confirm.clicked.connect(_submit)
        edit.returnPressed.connect(_submit)
        b_row.addWidget(btn_confirm)

        self.card_layout.addLayout(b_row)

        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        edit.setFocus()

    def show_rename_folder(self, current_name, on_renamed):
        self._clear_card()

        h_row = QHBoxLayout()
        title = QLabel("Rename Workspace Folder")
        title.setFont(get_display_font(15, bold=True))
        h_row.addWidget(title)
        h_row.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(24, 24)
        btn_x.setStyleSheet(f"border: none; color: {COLOR_TEXT_MUTED}; font-size: 14px; font-weight: bold;")
        btn_x.clicked.connect(self.hide)
        h_row.addWidget(btn_x)
        self.card_layout.addLayout(h_row)

        desc = QLabel("Enter a new name for this workspace folder:")
        desc.setFont(get_body_font(12))
        desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        self.card_layout.addWidget(desc)

        edit = QLineEdit(current_name)
        edit.setMinimumHeight(38)
        self.card_layout.addWidget(edit)

        b_row = QHBoxLayout()
        b_row.setSpacing(10)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(get_body_font(12))
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        btn_cancel.clicked.connect(self.hide)
        b_row.addWidget(btn_cancel)

        b_row.addStretch()

        btn_confirm = QPushButton("Save Name")
        btn_confirm.setObjectName("accentButton")
        btn_confirm.setFont(get_body_font(12, bold=True))
        btn_confirm.setMinimumHeight(36)
        btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #D97706;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 12px;
                border: 1px solid #F59E0B;
                border-radius: 3px;
                padding: 0 18px;
            }
            QPushButton:hover {
                background-color: #F59E0B;
            }
        """)

        def _submit():
            val = edit.text().strip()
            if val:
                self.hide()
                on_renamed(val)

        btn_confirm.clicked.connect(_submit)
        edit.returnPressed.connect(_submit)
        b_row.addWidget(btn_confirm)

        self.card_layout.addLayout(b_row)

        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        edit.setFocus()
        edit.selectAll()

    def show_edit_project(self, project, on_saved):
        self._clear_card()

        h_row = QHBoxLayout()
        title = QLabel(f"Edit Session Details")
        title.setFont(get_display_font(15, bold=True))
        h_row.addWidget(title)
        h_row.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(24, 24)
        btn_x.setStyleSheet(f"border: none; color: {COLOR_TEXT_MUTED}; font-size: 14px; font-weight: bold;")
        btn_x.clicked.connect(self.hide)
        h_row.addWidget(btn_x)
        self.card_layout.addLayout(h_row)

        self.card_layout.addWidget(QLabel("Session Name:"))
        name_edit = QLineEdit(project.name)
        name_edit.setMinimumHeight(38)
        self.card_layout.addWidget(name_edit)

        self.card_layout.addWidget(QLabel("Assigned Workspace Folder:"))
        combo = QComboBox()
        combo.setMinimumHeight(38)
        folders = storage.get_folders()
        sel_idx = 0
        for i, f in enumerate(folders):
            combo.addItem(f.name, f.id)
            if f.id == project.folder_id:
                sel_idx = i
        combo.setCurrentIndex(sel_idx)
        self.card_layout.addWidget(combo)

        self.card_layout.addWidget(QLabel("Shoot Date:"))
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("yyyy-MM-dd")
        date_edit.setMinimumHeight(38)
        qd = QDate.fromString(project.shoot_date, "yyyy-MM-dd")
        if not qd.isValid():
            qd = QDate.currentDate()
        date_edit.setDate(qd)
        self.card_layout.addWidget(date_edit)

        b_row = QHBoxLayout()
        b_row.setSpacing(10)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(get_body_font(12))
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        btn_cancel.clicked.connect(self.hide)
        b_row.addWidget(btn_cancel)

        b_row.addStretch()

        btn_confirm = QPushButton("Save Changes")
        btn_confirm.setObjectName("accentButton")
        btn_confirm.setFont(get_body_font(12, bold=True))
        btn_confirm.setMinimumHeight(36)
        btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #D97706;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 12px;
                border: 1px solid #F59E0B;
                border-radius: 3px;
                padding: 0 18px;
            }
            QPushButton:hover {
                background-color: #F59E0B;
            }
        """)

        def _submit():
            n = name_edit.text().strip()
            fid = combo.currentData()
            d = date_edit.date().toString("yyyy-MM-dd")
            self.hide()
            on_saved(n, fid, d)

        btn_confirm.clicked.connect(_submit)
        name_edit.returnPressed.connect(_submit)
        b_row.addWidget(btn_confirm)

        self.card_layout.addLayout(b_row)

        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        name_edit.setFocus()
        name_edit.selectAll()

    def show_edit_folder_project(self, current_folder_id, on_saved):
        self._clear_card()

        h_row = QHBoxLayout()
        title = QLabel("Edit Folder / Move Session")
        title.setFont(get_display_font(15, bold=True))
        h_row.addWidget(title)
        h_row.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(24, 24)
        btn_x.setStyleSheet(f"border: none; color: {COLOR_TEXT_MUTED}; font-size: 14px; font-weight: bold;")
        btn_x.clicked.connect(self.hide)
        h_row.addWidget(btn_x)
        self.card_layout.addLayout(h_row)

        folder = storage.get_folder_by_id(current_folder_id)
        current_name = folder.name if folder else "Personal"

        self.card_layout.addWidget(QLabel("Folder Name:"))
        name_edit = QLineEdit(current_name)
        name_edit.setMinimumHeight(38)
        self.card_layout.addWidget(name_edit)

        self.card_layout.addWidget(QLabel("Move this session to another folder:"))
        combo = QComboBox()
        combo.setMinimumHeight(38)
        folders = storage.get_folders()
        sel_idx = 0
        for i, f in enumerate(folders):
            combo.addItem(f.name, f.id)
            if f.id == current_folder_id:
                sel_idx = i
        combo.setCurrentIndex(sel_idx)
        self.card_layout.addWidget(combo)

        b_row = QHBoxLayout()
        b_row.setSpacing(10)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(get_body_font(12))
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        btn_cancel.clicked.connect(self.hide)
        b_row.addWidget(btn_cancel)

        b_row.addStretch()

        btn_confirm = QPushButton("Save Changes")
        btn_confirm.setObjectName("accentButton")
        btn_confirm.setFont(get_body_font(12, bold=True))
        btn_confirm.setMinimumHeight(36)
        btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #D97706;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 12px;
                border: 1px solid #F59E0B;
                border-radius: 3px;
                padding: 0 18px;
            }
            QPushButton:hover {
                background-color: #F59E0B;
            }
        """)

        def _submit():
            n = name_edit.text().strip()
            fid = combo.currentData()
            self.hide()
            on_saved(n, fid)

        btn_confirm.clicked.connect(_submit)
        name_edit.returnPressed.connect(_submit)
        b_row.addWidget(btn_confirm)

        self.card_layout.addLayout(b_row)

        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        name_edit.setFocus()

    def show_edit_date(self, current_date_str, on_saved):
        self._clear_card()

        h_row = QHBoxLayout()
        title = QLabel("Edit Shoot Date")
        title.setFont(get_display_font(15, bold=True))
        h_row.addWidget(title)
        h_row.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(24, 24)
        btn_x.setStyleSheet(f"border: none; color: {COLOR_TEXT_MUTED}; font-size: 14px; font-weight: bold;")
        btn_x.clicked.connect(self.hide)
        h_row.addWidget(btn_x)
        self.card_layout.addLayout(h_row)

        self.card_layout.addWidget(QLabel("Select Date:"))
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("yyyy-MM-dd")
        date_edit.setMinimumHeight(38)
        qd = QDate.fromString(current_date_str, "yyyy-MM-dd")
        if not qd.isValid():
            qd = QDate.currentDate()
        date_edit.setDate(qd)
        self.card_layout.addWidget(date_edit)

        b_row = QHBoxLayout()
        b_row.setSpacing(10)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(get_body_font(12))
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        btn_cancel.clicked.connect(self.hide)
        b_row.addWidget(btn_cancel)

        b_row.addStretch()

        btn_confirm = QPushButton("Save Date")
        btn_confirm.setObjectName("accentButton")
        btn_confirm.setFont(get_body_font(12, bold=True))
        btn_confirm.setMinimumHeight(36)
        btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #D97706;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 12px;
                border: 1px solid #F59E0B;
                border-radius: 3px;
                padding: 0 18px;
            }
            QPushButton:hover {
                background-color: #F59E0B;
            }
        """)

        def _submit():
            d = date_edit.date().toString("yyyy-MM-dd")
            self.hide()
            on_saved(d)

        btn_confirm.clicked.connect(_submit)
        b_row.addWidget(btn_confirm)

        self.card_layout.addLayout(b_row)

        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()

    def show_confirm_delete(self, title, message, on_confirmed, confirm_text="Delete", is_destructive=True):
        self._clear_card()

        h_row = QHBoxLayout()
        t_lbl = QLabel(title)
        t_lbl.setFont(get_display_font(15, bold=True))
        h_row.addWidget(t_lbl)
        h_row.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(24, 24)
        btn_x.setStyleSheet(f"border: none; color: {COLOR_TEXT_MUTED}; font-size: 14px; font-weight: bold;")
        btn_x.clicked.connect(self.hide)
        h_row.addWidget(btn_x)
        self.card_layout.addLayout(h_row)

        desc = QLabel(message)
        desc.setFont(get_body_font(12))
        desc.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; line-height: 1.4;")
        desc.setWordWrap(True)
        self.card_layout.addWidget(desc)

        b_row = QHBoxLayout()
        b_row.setSpacing(10)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(get_body_font(12))
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        btn_cancel.clicked.connect(self.hide)
        b_row.addWidget(btn_cancel)

        b_row.addStretch()

        btn_confirm = QPushButton(confirm_text)
        btn_confirm.setFont(get_body_font(12, bold=True))
        btn_confirm.setMinimumHeight(36)
        if is_destructive:
            btn_confirm.setStyleSheet("""
                QPushButton {
                    background-color: #EF4444;
                    color: #FFFFFF;
                    font-weight: 700;
                    border: 1px solid #DC2626;
                    border-radius: 3px;
                    padding: 0 18px;
                }
                QPushButton:hover {
                    background-color: #DC2626;
                }
            """)
        else:
            btn_confirm.setStyleSheet("""
                QPushButton {
                    background-color: #D97706;
                    color: #FFFFFF;
                    font-weight: 700;
                    border: 1px solid #F59E0B;
                    border-radius: 3px;
                    padding: 0 18px;
                }
            """)

        def _submit():
            self.hide()
            on_confirmed()

        btn_confirm.clicked.connect(_submit)
        b_row.addWidget(btn_confirm)

        self.card_layout.addLayout(b_row)

        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()


class ProjectCard(QFrame):
    """Utilitarian project card with date, status, LRC edited result, and direct actions."""
    resume_clicked = Signal(str)  # project_id
    export_clicked = Signal(str)  # project_id
    delete_clicked = Signal(str)  # project_id
    date_changed = Signal(str, str) # project_id, new_date
    refresh_requested = Signal()
    edit_requested = Signal(object) # Project
    edit_folder_requested = Signal(object) # Project
    edit_date_requested = Signal(object) # Project

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setObjectName("projectCardFrame")
        self.setStyleSheet(f"""
            QFrame#projectCardFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                padding: 4px;
            }}
            QFrame#projectCardFrame:hover {{
                border-color: {COLOR_TEXT_SECONDARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(20)

        # Left: Details
        details_layout = QVBoxLayout()
        details_layout.setSpacing(8)

        # Title Row: Project Name + Mode Badge + Edit Session
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_lbl = QLabel(project.name)
        title_lbl.setFont(get_display_font(16, bold=True))
        title_row.addWidget(title_lbl)

        # Media Type Badge
        is_vid = getattr(project, "media_type", "photo") == "video"
        type_badge = QLabel("VIDEO" if is_vid else "PHOTO")
        type_badge.setFont(get_mono_font(10, bold=True))
        if is_vid:
            type_badge.setStyleSheet("color: #FFAE42; background-color: #2D2214; padding: 2px 6px; border: 1px solid #754B1A; border-radius: 2px;")
        else:
            type_badge.setStyleSheet("color: #7BE4A2; background-color: #1A3323; padding: 2px 6px; border: 1px solid #2E7D32; border-radius: 2px;")
        title_row.addWidget(type_badge)

        edit_session_btn = QPushButton("Edit")
        edit_session_btn.setIcon(render_icon("edit", 11, COLOR_TEXT_SECONDARY))
        edit_session_btn.setFont(get_body_font(11))
        edit_session_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 2px 8px;
                color: {COLOR_TEXT_SECONDARY};
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_SUBTLE};
                border-radius: 2px;
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                border-color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_HOVER};
            }}
        """)
        edit_session_btn.setToolTip("Edit session name, folder, and date")
        edit_session_btn.clicked.connect(self._on_edit_session)
        title_row.addWidget(edit_session_btn)

        title_row.addStretch()
        details_layout.addLayout(title_row)

        # Meta Row: Folder Info + Edit Folder + Shoot Date + Change Date
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(14)

        folder = storage.get_folder_by_id(project.folder_id)
        folder_name = folder.name if folder else "Default"

        folder_lbl = QLabel(f"Folder: {folder_name}")
        folder_lbl.setFont(get_mono_font(12))
        folder_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        meta_layout.addWidget(folder_lbl)

        edit_folder_btn = QPushButton("Edit Folder")
        edit_folder_btn.setIcon(render_icon("edit", 11, COLOR_ACCENT))
        edit_folder_btn.setFont(get_body_font(11))
        edit_folder_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 2px 8px;
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_BORDER_SUBTLE};
                background-color: transparent;
                border-radius: 2px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
                background-color: {COLOR_BG_HOVER};
            }}
        """)
        edit_folder_btn.setToolTip("Rename folder or move session")
        edit_folder_btn.clicked.connect(self._on_edit_folder)
        meta_layout.addWidget(edit_folder_btn)

        # Date with change button
        date_lbl = QLabel(f"Date: {project.shoot_date}")
        date_lbl.setFont(get_mono_font(12))
        date_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        meta_layout.addWidget(date_lbl)

        edit_date_btn = QPushButton("Change Date")
        edit_date_btn.setFont(get_body_font(11))
        edit_date_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 2px 8px;
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_BORDER_SUBTLE};
                background-color: transparent;
                border-radius: 2px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
                background-color: {COLOR_BG_HOVER};
            }}
        """)
        edit_date_btn.clicked.connect(self._on_edit_date)
        meta_layout.addWidget(edit_date_btn)

        meta_layout.addStretch()
        details_layout.addLayout(meta_layout)

        # Status & Counts row
        status_layout = QHBoxLayout()
        status_layout.setSpacing(12)

        status_text = project.status_label
        status_color = COLOR_STATUS_KEPT if "Completed" in status_text else (COLOR_ACCENT if "Progress" in status_text else COLOR_TEXT_MUTED)
        status_badge = QLabel(status_text)
        status_badge.setFont(get_mono_font(11, bold=True))
        status_badge.setStyleSheet(f"color: {status_color}; background-color: {COLOR_BG_BASE}; padding: 3px 8px; border: 1px solid {COLOR_BORDER_SUBTLE}; border-radius: 2px;")
        status_layout.addWidget(status_badge)

        if is_vid:
            format_info = f"Selected: {project.selected_count} • Similar: {project.similar_count} • Unselected: {project.unselected_count} • {project.total_count} Clips"
        else:
            format_info = f"{project.format_mode.replace('_', ' ').upper()}"
            if project.sync_pairs and project.format_mode == "both":
                format_info += " • Synced Pairs"
            format_info += f" • {project.total_count} Frames"

        info_lbl = QLabel(format_info)
        info_lbl.setFont(get_body_font(12))
        info_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        status_layout.addWidget(info_lbl)

        status_layout.addStretch()
        details_layout.addLayout(status_layout)

        # Photo-specific: LRC Edited Result row
        if not is_vid:
            edited_layout = QHBoxLayout()
            edited_layout.setSpacing(10)

            edited_count = project.edited_count
            if edited_count > 0:
                edited_badge = QLabel(f"✓ {edited_count} photo(s) in 'edited result'")
                edited_badge.setFont(get_mono_font(11, bold=True))
                edited_badge.setStyleSheet(f"color: {COLOR_ACCENT}; background-color: #261E14; padding: 3px 8px; border: 1px solid #754B1A; border-radius: 2px;")
                edited_layout.addWidget(edited_badge)

                add_more_btn = QPushButton("+ Add Files")
                add_more_btn.setIcon(render_icon("plus", 12, COLOR_TEXT_PRIMARY))
                add_more_btn.setFont(get_body_font(11))
                add_more_btn.setStyleSheet(f"""
                    QPushButton {{
                        padding: 3px 10px;
                        color: {COLOR_TEXT_PRIMARY};
                        border: 1px solid {COLOR_BORDER_DISTINCT};
                        background-color: {COLOR_BG_ELEVATED};
                        border-radius: 2px;
                    }}
                    QPushButton:hover {{
                        border-color: {COLOR_ACCENT};
                        color: {COLOR_ACCENT};
                    }}
                """)
                add_more_btn.setToolTip("Add more Lightroom edited photos into 'edited result'")
                add_more_btn.clicked.connect(self._on_add_edited_files)
                edited_layout.addWidget(add_more_btn)

                open_folder_btn = QPushButton("Open Folder")
                open_folder_btn.setIcon(render_icon("folder", 12, COLOR_ACCENT))
                open_folder_btn.setFont(get_body_font(11))
                open_folder_btn.setStyleSheet(f"""
                    QPushButton {{
                        padding: 3px 10px;
                        color: {COLOR_ACCENT};
                        border: 1px solid {COLOR_ACCENT};
                        background-color: #221A12;
                        font-weight: 600;
                        border-radius: 2px;
                    }}
                    QPushButton:hover {{
                        background-color: {COLOR_ACCENT};
                        color: #FFFFFF;
                    }}
                """)
                open_folder_btn.setToolTip("Open 'edited result' folder in Windows Explorer")
                open_folder_btn.clicked.connect(self._on_open_edited_folder)
                edited_layout.addWidget(open_folder_btn)
            else:
                edited_hint = QLabel("Edited Result:")
                edited_hint.setFont(get_mono_font(11))
                edited_hint.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
                edited_layout.addWidget(edited_hint)

                add_btn = QPushButton("+ Add Files (LRC)")
                add_btn.setIcon(render_icon("plus", 12, COLOR_ACCENT))
                add_btn.setFont(get_body_font(11))
                add_btn.setStyleSheet(f"""
                    QPushButton {{
                        padding: 3px 10px;
                        color: {COLOR_ACCENT};
                        border: 1px solid {COLOR_BORDER_DISTINCT};
                        background-color: {COLOR_BG_ELEVATED};
                        border-radius: 2px;
                    }}
                    QPushButton:hover {{
                        border-color: {COLOR_ACCENT};
                        background-color: #2A2216;
                    }}
                """)
                add_btn.setToolTip("Add photos already edited in Lightroom Classic. Framed will store them in 'edited result' folder.")
                add_btn.clicked.connect(self._on_add_edited_files)
                edited_layout.addWidget(add_btn)

            edited_layout.addStretch()
            details_layout.addLayout(edited_layout)

        main_layout.addLayout(details_layout, stretch=1)

        # Right: Actions
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        actions_layout.setAlignment(Qt.AlignVCenter)

        # Resume button (Video vs Photo)
        btn_text = "Resume Video Sort" if is_vid else "Resume Culling"
        icon_name = "arrow_right" if is_vid else "loupe"

        self.resume_btn = QPushButton(btn_text)
        self.resume_btn.setIcon(render_icon(icon_name, 14, "#FFAE42"))
        self.resume_btn.setMinimumHeight(36)
        self.resume_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2D2214;
                color: #FFAE42;
                border: 1px solid #E59533;
                border-radius: 2px;
                padding: 7px 16px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: #E59533;
                color: #FFFFFF;
                border: 1px solid #FFAE42;
            }}
            QPushButton:pressed {{
                background-color: #C87D20;
                color: #FFFFFF;
            }}
        """)
        self.resume_btn.clicked.connect(lambda checked=False, pid=project.id: self.resume_clicked.emit(pid))
        actions_layout.addWidget(self.resume_btn)

        self.export_btn = QPushButton("Export")
        self.export_btn.setIcon(render_icon("export", 14, COLOR_TEXT_PRIMARY))
        self.export_btn.setMinimumHeight(36)
        self.export_btn.setStyleSheet(f"""
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
        """)
        self.export_btn.clicked.connect(lambda checked=False, pid=project.id: self.export_clicked.emit(pid))
        actions_layout.addWidget(self.export_btn)

        self.del_btn = QPushButton()
        self.del_btn.setIcon(render_icon("trash", 14, COLOR_STATUS_REJECTED))
        self.del_btn.setToolTip("Delete Session")
        self.del_btn.setMinimumHeight(36)
        self.del_btn.setFixedWidth(36)
        self.del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 2px;
            }}
            QPushButton:hover {{
                background-color: #2E1517;
                border-color: {COLOR_STATUS_REJECTED};
            }}
        """)
        self.del_btn.clicked.connect(lambda checked=False, pid=project.id: self.delete_clicked.emit(pid))
        actions_layout.addWidget(self.del_btn)

        main_layout.addLayout(actions_layout)

    def _on_edit_session(self):
        self.edit_requested.emit(self.project)

    def _on_edit_folder(self):
        self.edit_folder_requested.emit(self.project)

    def _on_edit_date(self):
        self.edit_date_requested.emit(self.project)

    def _on_add_edited_files(self):
        initial_dir = ""
        if self.project.source_dir and os.path.exists(self.project.source_dir):
            initial_dir = self.project.source_dir
        else:
            initial_dir = os.path.expanduser("~/Pictures")

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Lightroom Edited Photos",
            initial_dir,
            "Images (*.jpg *.jpeg *.png *.tif *.tiff *.dng *.psd);;All Files (*.*)"
        )
        if not file_paths:
            return

        # Determine target folder 'edited result'
        if self.project.source_dir and os.path.isdir(self.project.source_dir):
            dest_dir = os.path.join(self.project.source_dir, "edited result")
        else:
            export_root = config.get("default_export_dir") or os.path.join(os.path.expanduser("~"), "Pictures", "Framed_Sessions")
            dest_dir = os.path.join(export_root, self.project.name, "edited result")

        try:
            os.makedirs(dest_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Error Creating Folder", f"Failed to create 'edited result' folder:\n{dest_dir}\n\nError: {e}")
            return

        copied_count = 0
        for src in file_paths:
            try:
                dest_file = os.path.join(dest_dir, os.path.basename(src))
                shutil.copy2(src, dest_file)
                copied_count += 1
            except Exception as e:
                print(f"Error copying {src}: {e}")

        # Scan all files inside dest_dir
        all_edited = []
        if os.path.exists(dest_dir):
            all_edited = [os.path.join(dest_dir, f) for f in os.listdir(dest_dir) if os.path.isfile(os.path.join(dest_dir, f))]

        self.project.edited_result_dir = dest_dir
        self.project.edited_files = all_edited
        storage.save_project(self.project)

        QMessageBox.information(
            self,
            "Edited Photos Added",
            f"Successfully added {copied_count} photo(s) to folder:\n\n{dest_dir}\n\nYou can click 'Open Folder' anytime to view them in Windows Explorer."
        )
        self.refresh_requested.emit()

    def _on_open_edited_folder(self):
        target_dir = self.project.edited_result_dir
        if not target_dir or not os.path.exists(target_dir):
            if self.project.source_dir:
                cand = os.path.join(self.project.source_dir, "edited result")
                if os.path.exists(cand):
                    target_dir = cand

        if target_dir and os.path.exists(target_dir):
            try:
                if os.name == "nt":
                    os.startfile(target_dir)
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", target_dir])
            except Exception as e:
                QMessageBox.warning(self, "Open Folder Error", f"Could not open folder:\n{e}")
        else:
            QMessageBox.warning(self, "Folder Not Found", "The 'edited result' folder does not exist yet. Click 'Add Files' first.")


class DashboardView(QWidget):
    """Main Dashboard with dual Photo/Video mode switching and real folder management."""
    new_session_requested = Signal()
    open_project_requested = Signal(str)  # project_id
    export_project_requested = Signal(str) # project_id
    open_settings_requested = Signal()
    fullscreen_requested = Signal()
    media_mode_changed = Signal(str)      # "photo" or "video"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_folder_id: Optional[str] = None
        self.current_media_mode: str = "photo"  # "photo" or "video"
        self._init_ui()
        self.modal_overlay = DashboardModalOverlay(self)
        self.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "modal_overlay") and self.modal_overlay:
            self.modal_overlay.setGeometry(self.rect())

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Top Header Bar
        header_bar = QFrame()
        header_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border-bottom: 1px solid {COLOR_BORDER_DISTINCT};
            }}
        """)
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(24, 12, 24, 12)
        header_layout.setSpacing(18)

        # App Brand
        brand_layout = QVBoxLayout()
        brand_layout.setSpacing(2)
        brand_title = QLabel("FRAMED")
        brand_title.setFont(get_display_font(20, bold=True))
        brand_title.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; letter-spacing: 2px;")
        brand_sub = QLabel("PHOTOGRAPHER & VIDEOGRAPHER WORKSTATION")
        brand_sub.setFont(get_mono_font(10, bold=True))
        brand_sub.setStyleSheet(f"color: {COLOR_ACCENT}; letter-spacing: 1px;")
        brand_layout.addWidget(brand_title)
        brand_layout.addWidget(brand_sub)
        header_layout.addLayout(brand_layout)

        # Mode Switcher (Photo Sort | Video Sort)
        mode_switcher_frame = QFrame()
        mode_switcher_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_BASE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
            }}
        """)
        ms_layout = QHBoxLayout(mode_switcher_frame)
        ms_layout.setContentsMargins(3, 3, 3, 3)
        ms_layout.setSpacing(4)

        self.btn_mode_photo = QPushButton("PHOTO SORT")
        self.btn_mode_photo.setFont(get_mono_font(11, bold=True))
        self.btn_mode_photo.clicked.connect(lambda: self._set_media_mode("photo"))
        ms_layout.addWidget(self.btn_mode_photo)

        self.btn_mode_video = QPushButton("VIDEO SORT")
        self.btn_mode_video.setFont(get_mono_font(11, bold=True))
        self.btn_mode_video.clicked.connect(lambda: self._set_media_mode("video"))
        ms_layout.addWidget(self.btn_mode_video)

        header_layout.addWidget(mode_switcher_frame)
        self._update_mode_switcher_styles()

        header_layout.addStretch()

        # Action Buttons
        self.new_session_btn = QPushButton("New Photo Session")
        self.new_session_btn.setObjectName("accentButton")
        self.new_session_btn.setIcon(render_icon("plus", 14, "#FFFFFF"))
        self.new_session_btn.setMinimumHeight(36)
        self.new_session_btn.setStyleSheet("""
            QPushButton {
                background-color: #D97706;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 13px;
                border: 1px solid #F59E0B;
                border-radius: 3px;
                padding: 6px 16px;
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
        """)
        self.new_session_btn.clicked.connect(self.new_session_requested.emit)
        header_layout.addWidget(self.new_session_btn)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setIcon(render_icon("settings", 14, COLOR_TEXT_PRIMARY))
        self.settings_btn.setMinimumHeight(36)
        self.settings_btn.clicked.connect(self.open_settings_requested.emit)
        header_layout.addWidget(self.settings_btn)

        self.fullscreen_btn = QPushButton("Full Screen (F11)")
        self.fullscreen_btn.setIcon(render_icon("fit", 14, COLOR_TEXT_PRIMARY))
        self.fullscreen_btn.setMinimumHeight(36)
        self.fullscreen_btn.setToolTip("Toggle Full Screen Mode (or press F11)")
        self.fullscreen_btn.clicked.connect(self.fullscreen_requested.emit)
        header_layout.addWidget(self.fullscreen_btn)

        root_layout.addWidget(header_bar)

        # Content: Left Folders Sidebar + Right Projects Area
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Left Sidebar (Folders)
        sidebar = QFrame()
        sidebar.setFixedWidth(260)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border-right: 1px solid {COLOR_BORDER_DISTINCT};
            }}
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 20, 16, 16)
        sidebar_layout.setSpacing(14)

        sidebar_title_layout = QHBoxLayout()
        sidebar_title = QLabel("WORKSPACE FOLDERS")
        sidebar_title.setFont(get_mono_font(11, bold=True))
        sidebar_title.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; letter-spacing: 1px;")
        sidebar_title_layout.addWidget(sidebar_title)
        sidebar_title_layout.addStretch()

        add_folder_btn = QPushButton()
        add_folder_btn.setIcon(render_icon("plus", 12, COLOR_TEXT_PRIMARY))
        add_folder_btn.setToolTip("Create New Folder (e.g. School, Weddings, Personal)")
        add_folder_btn.setFixedSize(24, 24)
        add_folder_btn.clicked.connect(self._create_new_folder)
        sidebar_title_layout.addWidget(add_folder_btn)
        sidebar_layout.addLayout(sidebar_title_layout)

        # Folder List Widget
        self.folder_list = QListWidget()
        self.folder_list.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-radius: 2px;
                color: {COLOR_TEXT_PRIMARY};
                margin-bottom: 2px;
            }}
            QListWidget::item:hover {{
                background-color: {COLOR_BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {COLOR_BG_ELEVATED};
                border-left: 3px solid {COLOR_ACCENT};
                font-weight: 600;
            }}
        """)
        self.folder_list.itemClicked.connect(self._on_folder_selected)
        sidebar_layout.addWidget(self.folder_list, stretch=1)

        # Folder management actions (Edit Folder / Delete)
        folder_actions_layout = QHBoxLayout()
        folder_actions_layout.setSpacing(8)

        self.rename_folder_btn = QPushButton("Edit Folder")
        self.rename_folder_btn.setIcon(render_icon("edit", 12, COLOR_TEXT_PRIMARY))
        self.rename_folder_btn.setFont(get_body_font(11))
        self.rename_folder_btn.clicked.connect(self._rename_selected_folder)
        folder_actions_layout.addWidget(self.rename_folder_btn)

        self.delete_folder_btn = QPushButton("Delete")
        self.delete_folder_btn.setFont(get_body_font(11))
        self.delete_folder_btn.setStyleSheet(f"color: {COLOR_STATUS_REJECTED};")
        self.delete_folder_btn.clicked.connect(self._delete_selected_folder)
        folder_actions_layout.addWidget(self.delete_folder_btn)

        sidebar_layout.addLayout(folder_actions_layout)
        content_layout.addWidget(sidebar)

        # Right Area: Projects
        right_area = QWidget()
        right_area.setStyleSheet(f"background-color: {COLOR_BG_BASE};")
        right_layout = QVBoxLayout(right_area)
        right_layout.setContentsMargins(32, 24, 32, 24)
        right_layout.setSpacing(20)

        # Right Header (Folder Title, Edit button, count)
        right_header = QHBoxLayout()
        right_header.setSpacing(12)

        self.folder_title_lbl = QLabel("Projects")
        self.folder_title_lbl.setFont(get_display_font(20, bold=True))
        right_header.addWidget(self.folder_title_lbl)

        self.header_edit_folder_btn = QPushButton("Edit Folder")
        self.header_edit_folder_btn.setIcon(render_icon("edit", 12, COLOR_ACCENT))
        self.header_edit_folder_btn.setFont(get_body_font(11))
        self.header_edit_folder_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 3px 10px;
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_BORDER_SUBTLE};
                background-color: transparent;
                border-radius: 2px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
                background-color: {COLOR_BG_HOVER};
            }}
        """)
        self.header_edit_folder_btn.clicked.connect(self._rename_selected_folder)
        self.header_edit_folder_btn.setVisible(False)
        right_header.addWidget(self.header_edit_folder_btn)

        self.project_count_lbl = QLabel("0 ongoing sessions")
        self.project_count_lbl.setFont(get_mono_font(12))
        self.project_count_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        right_header.addWidget(self.project_count_lbl)
        right_header.addStretch()

        right_layout.addLayout(right_header)

        # Scrollable projects container
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.projects_container = QWidget()
        self.projects_layout = QVBoxLayout(self.projects_container)
        self.projects_layout.setContentsMargins(0, 0, 0, 0)
        self.projects_layout.setSpacing(12)
        self.projects_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.projects_container)
        right_layout.addWidget(self.scroll_area, stretch=1)

        content_layout.addWidget(right_area, stretch=1)
        root_layout.addLayout(content_layout, stretch=1)

    def _set_media_mode(self, mode: str):
        if self.current_media_mode != mode:
            self.current_media_mode = mode
            self._update_mode_switcher_styles()
            self.new_session_btn.setText("New Photo Session" if mode == "photo" else "New Video Session")
            self.media_mode_changed.emit(mode)
            self._load_projects_for_selection()

    def _update_mode_switcher_styles(self):
        active_style = f"""
            QPushButton {{
                background-color: #2D2214;
                color: #FFAE42;
                border: 1px solid #E59533;
                border-radius: 3px;
                padding: 6px 14px;
                font-weight: 700;
            }}
        """
        inactive_style = f"""
            QPushButton {{
                background-color: transparent;
                color: {COLOR_TEXT_MUTED};
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """
        if self.current_media_mode == "photo":
            self.btn_mode_photo.setStyleSheet(active_style)
            self.btn_mode_video.setStyleSheet(inactive_style)
        else:
            self.btn_mode_photo.setStyleSheet(inactive_style)
            self.btn_mode_video.setStyleSheet(active_style)

    def refresh(self):
        """Reload folders and projects from storage."""
        self.folder_list.clear()
        
        all_item = QListWidgetItem("All Projects")
        all_item.setData(Qt.UserRole, "__ALL__")
        all_item.setIcon(render_icon("folder", 14, COLOR_ACCENT))
        self.folder_list.addItem(all_item)

        folders = storage.get_folders()
        selected_row = 0
        for i, f in enumerate(folders):
            item = QListWidgetItem(f.name)
            item.setData(Qt.UserRole, f.id)
            item.setIcon(render_icon("folder", 14, COLOR_TEXT_SECONDARY))
            self.folder_list.addItem(item)
            if self.selected_folder_id == f.id:
                selected_row = i + 1

        self.folder_list.setCurrentRow(selected_row)
        self._load_projects_for_selection()

    def _on_folder_selected(self, item: QListWidgetItem):
        fid = item.data(Qt.UserRole)
        self.selected_folder_id = None if fid == "__ALL__" else fid
        self._load_projects_for_selection()

    def _load_projects_for_selection(self):
        # Clear existing cards
        while self.projects_layout.count():
            child = self.projects_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        mode = self.current_media_mode
        if self.selected_folder_id:
            folder = storage.get_folder_by_id(self.selected_folder_id)
            f_name = folder.name if folder else "Folder"
            self.folder_title_lbl.setText(f_name)
            self.header_edit_folder_btn.setVisible(True)
            self.rename_folder_btn.setEnabled(True)
            self.delete_folder_btn.setEnabled(True)
            projects = storage.get_projects(self.selected_folder_id, media_type=mode)
        else:
            self.folder_title_lbl.setText("All Projects")
            self.header_edit_folder_btn.setVisible(False)
            self.rename_folder_btn.setEnabled(False)
            self.delete_folder_btn.setEnabled(False)
            projects = storage.get_projects(media_type=mode)

        count = len(projects)
        term = "video session" if mode == "video" else "photo session"
        self.project_count_lbl.setText(f"{count} {term}{'' if count == 1 else 's'}")

        if count == 0:
            # Empty state
            empty_box = QFrame()
            empty_box.setObjectName("emptyBoxFrame")
            empty_box.setStyleSheet(f"""
                QFrame#emptyBoxFrame {{
                    background-color: {COLOR_BG_SURFACE};
                    border: 1px dashed {COLOR_BORDER_DISTINCT};
                    border-radius: 4px;
                    padding: 40px;
                }}
            """)
            empty_layout = QVBoxLayout(empty_box)
            empty_layout.setAlignment(Qt.AlignCenter)
            empty_layout.setSpacing(14)

            msg_text = f"No {mode} sorting sessions in this folder yet."
            msg = QLabel(msg_text)
            msg.setFont(get_body_font(14))
            msg.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
            empty_layout.addWidget(msg, alignment=Qt.AlignCenter)

            btn_label = f"Create First {mode.capitalize()} Session"
            create_btn = QPushButton(btn_label)
            create_btn.setObjectName("accentButton")
            create_btn.setIcon(render_icon("plus", 14, "#FFFFFF"))
            create_btn.setMinimumHeight(38)
            create_btn.setStyleSheet("""
                QPushButton {
                    background-color: #D97706;
                    color: #FFFFFF;
                    font-weight: 700;
                    font-size: 13px;
                    border: 1px solid #F59E0B;
                    border-radius: 4px;
                    padding: 8px 22px;
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
            """)
            create_btn.clicked.connect(self.new_session_requested.emit)
            empty_layout.addWidget(create_btn, alignment=Qt.AlignCenter)

            self.projects_layout.addWidget(empty_box)
        else:
            for proj in projects:
                card = ProjectCard(proj)
                card.resume_clicked.connect(self.open_project_requested.emit)
                card.export_clicked.connect(self.export_project_requested.emit)
                card.delete_clicked.connect(self._on_delete_project)
                card.date_changed.connect(self._on_project_date_changed)
                card.refresh_requested.connect(self.refresh)
                card.edit_requested.connect(self._on_edit_project_modal)
                card.edit_folder_requested.connect(self._on_edit_folder_modal)
                card.edit_date_requested.connect(self._on_edit_date_modal)
                self.projects_layout.addWidget(card)

    def _on_edit_project_modal(self, proj: Project):
        def _saved(name, folder_id, shoot_date):
            if name:
                storage.update_project_name(proj.id, name)
            if folder_id:
                storage.update_project_folder(proj.id, folder_id)
            if shoot_date:
                storage.update_project_date(proj.id, shoot_date)
            self.refresh()
        self.modal_overlay.show_edit_project(proj, _saved)

    def _on_edit_folder_modal(self, proj: Project):
        def _saved(new_name, target_folder_id):
            if new_name:
                storage.rename_folder(proj.folder_id, new_name)
            if target_folder_id and target_folder_id != proj.folder_id:
                storage.update_project_folder(proj.id, target_folder_id)
            self.refresh()
        self.modal_overlay.show_edit_folder_project(proj.folder_id, _saved)

    def _on_edit_date_modal(self, proj: Project):
        def _saved(new_date):
            storage.update_project_date(proj.id, new_date)
            self.refresh()
        self.modal_overlay.show_edit_date(proj.shoot_date, _saved)

    def _create_new_folder(self):
        def _created(name):
            new_f = storage.create_folder(name)
            self.selected_folder_id = new_f.id
            self.refresh()
        self.modal_overlay.show_create_folder(_created)

    def _rename_selected_folder(self):
        if not self.selected_folder_id:
            return
        folder = storage.get_folder_by_id(self.selected_folder_id)
        if not folder:
            return
        def _renamed(new_name):
            storage.rename_folder(folder.id, new_name)
            self.refresh()
        self.modal_overlay.show_rename_folder(folder.name, _renamed)

    def _delete_selected_folder(self):
        if not self.selected_folder_id:
            return
        folder = storage.get_folder_by_id(self.selected_folder_id)
        if not folder:
            return
        def _confirmed():
            storage.delete_folder(folder.id)
            self.selected_folder_id = None
            self.refresh()
        self.modal_overlay.show_confirm_delete(
            "Delete Workspace Folder",
            f"Are you sure you want to delete folder '{folder.name}'?\nProjects will be preserved in other folders.",
            _confirmed,
            confirm_text="Delete Folder",
            is_destructive=True
        )

    def _on_delete_project(self, project_id: str):
        proj = storage.get_project_by_id(project_id)
        if not proj:
            return
        def _confirmed():
            storage.delete_project(project_id)
            self._load_projects_for_selection()
        self.modal_overlay.show_confirm_delete(
            "Delete Session",
            f"Delete session '{proj.name}'?\nOriginal media on disk will never be touched.",
            _confirmed,
            confirm_text="Delete Session",
            is_destructive=True
        )

    def _on_project_date_changed(self, project_id: str, new_date: str):
        storage.update_project_date(project_id, new_date)
        self._load_projects_for_selection()
