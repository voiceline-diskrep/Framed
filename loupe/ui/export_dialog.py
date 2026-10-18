"""Export dialog and progress monitor creating structured Selected/Unselected RAW/JPEG folders on Local Disk or Google Drive."""

import os
import subprocess
import webbrowser
from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QProgressBar, QFrame, QFileDialog, QMessageBox, QCheckBox,
    QRadioButton, QButtonGroup, QWidget, QScrollArea, QApplication
)
from PySide6.QtCore import Qt
from loupe.config import config
from loupe.models import Project
from loupe.core.exporter import ExportWorker, sanitize_folder_name
from loupe.core.gdrive import (
    GoogleDriveClient, GDriveUploadWorker, parse_gdrive_folder_id, format_eta
)
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_SUBTLE,
    COLOR_BORDER_DISTINCT, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_STATUS_KEPT, COLOR_STATUS_REJECTED,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon


class ExportDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Export Structured Photographic Session")
        self.setMinimumSize(540, 400)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")

        self.worker: Optional[ExportWorker] = None
        self.gdrive_worker: Optional[GDriveUploadWorker] = None
        self.exported_dir: Optional[str] = None
        self.exported_gdrive_url: Optional[str] = None
        self.gdrive_parent_id: str = config.get("gdrive_export_parent_id", "root") or "root"
        self.gdrive_parent_name: str = config.get("gdrive_export_parent_name", "My Drive") or "My Drive"

        self._init_ui()
        self._fit_to_available_screen()

    def _fit_to_available_screen(self):
        try:
            screen = self.screen() or QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                target_w = min(680, max(560, avail.width() - 40))
                target_h = min(700, max(500, avail.height() - 60))
                self.resize(target_w, target_h)
                x = avail.x() + (avail.width() - target_w) // 2
                y = avail.y() + max(10, (avail.height() - target_h) // 2)
                self.move(x, y)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_to_available_screen()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 16)
        main_layout.setSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(16)

        # Header
        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel(f"Export '{self.project.name}'")
        title.setFont(get_display_font(18, bold=True))
        sub = QLabel("Files are safely copied into structured Selected and Unselected folders.")
        sub.setFont(get_body_font(12))
        sub.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        header.addWidget(title)
        header.addWidget(sub)
        content_layout.addLayout(header)

        # Experimental Destination Mode Selector (Local Disk vs Google Drive)
        self.mode_frame = QFrame()
        self.mode_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
                padding: 10px 14px;
            }}
        """)
        mode_layout = QHBoxLayout(self.mode_frame)
        mode_layout.setContentsMargins(4, 4, 4, 4)
        mode_layout.setSpacing(16)

        lbl_target = QLabel("TARGET:")
        lbl_target.setFont(get_mono_font(10, bold=True))
        lbl_target.setStyleSheet(f"color: {COLOR_ACCENT};")
        mode_layout.addWidget(lbl_target)

        self.dest_mode_group = QButtonGroup(self)
        self.rb_dest_local = QRadioButton("Local Disk")
        self.rb_dest_local.setFont(get_body_font(12, bold=True))
        self.rb_dest_local.setChecked(True)
        self.rb_dest_gdrive = QRadioButton("Google Drive (Experimental)")
        self.rb_dest_gdrive.setFont(get_body_font(12, bold=True))

        self.dest_mode_group.addButton(self.rb_dest_local, 1)
        self.dest_mode_group.addButton(self.rb_dest_gdrive, 2)
        self.rb_dest_local.toggled.connect(self._on_dest_mode_changed)

        mode_layout.addWidget(self.rb_dest_local)
        mode_layout.addWidget(self.rb_dest_gdrive)
        mode_layout.addStretch()

        self.mode_frame.setVisible(bool(config.get("experimental_mode", False)))
        content_layout.addWidget(self.mode_frame)

        # Destination Folder Input
        dest_layout = QVBoxLayout()
        dest_layout.setSpacing(8)
        self.dest_lbl = QLabel("Export Destination:")
        self.dest_lbl.setFont(get_body_font(12, bold=True))
        dest_layout.addWidget(self.dest_lbl)

        row_dest = QHBoxLayout()
        self.dest_edit = QLineEdit()
        self.dest_edit.setMinimumHeight(38)
        self.dest_edit.setFont(get_body_font(12))
        self.dest_edit.setStyleSheet(f"""
            QLineEdit {{
                padding: 0 10px;
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        default_dir = config.get("default_export_dir", "") or os.path.join(os.path.expanduser("~"), "Pictures", "Framed Exports")
        self.dest_edit.setText(default_dir)
        row_dest.addWidget(self.dest_edit, stretch=1)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setFont(get_body_font(12, bold=True))
        self.browse_btn.setMinimumHeight(38)
        self.browse_btn.setStyleSheet(f"""
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
        self.browse_btn.clicked.connect(self._browse_dest)
        row_dest.addWidget(self.browse_btn)
        dest_layout.addLayout(row_dest)

        # Workspace Folder Separation Checkbox
        ws_name = self.project.get_workspace_name()
        self.cb_workspace = QCheckBox(f"Separate into Workspace Folder ('{ws_name}')")
        self.cb_workspace.setFont(get_body_font(12))
        self.cb_workspace.setChecked(config.get("export_separate_by_workspace", True))
        self.cb_workspace.toggled.connect(self._on_workspace_toggled)
        dest_layout.addWidget(self.cb_workspace)

        content_layout.addLayout(dest_layout)

        # Google Drive Category Selection Card (Visible when Google Drive mode is selected)
        self.gdrive_cat_card = QFrame()
        self.gdrive_cat_card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
                padding: 12px;
            }}
        """)
        gc_layout = QVBoxLayout(self.gdrive_cat_card)
        gc_layout.setSpacing(8)

        t_gc = QLabel("GOOGLE DRIVE UPLOAD CATEGORIES")
        t_gc.setFont(get_mono_font(10, bold=True))
        t_gc.setStyleSheet(f"color: {COLOR_ACCENT};")
        gc_layout.addWidget(t_gc)

        self.cb_up_selected = QCheckBox(f"Selected ({self.project.kept_count} photos)")
        self.cb_up_selected.setChecked(True)
        self.cb_up_selected.toggled.connect(self._update_hierarchy_preview)
        gc_layout.addWidget(self.cb_up_selected)

        self.cb_up_maybe = QCheckBox(f"Maybe ({self.project.maybe_count} photos)")
        self.cb_up_maybe.setChecked(True)
        self.cb_up_maybe.toggled.connect(self._update_hierarchy_preview)
        gc_layout.addWidget(self.cb_up_maybe)

        self.cb_up_edited = QCheckBox(f"Edited Result ({self.project.edited_count} photos)")
        self.cb_up_edited.setChecked(True)
        self.cb_up_edited.toggled.connect(self._update_hierarchy_preview)
        gc_layout.addWidget(self.cb_up_edited)

        unsel_total = self.project.rejected_count + self.project.pending_count
        self.cb_up_unselected = QCheckBox(f"Unselected / Rejected ({unsel_total} photos — unchecked by default to save cloud storage)")
        self.cb_up_unselected.setChecked(False)
        self.cb_up_unselected.toggled.connect(self._update_hierarchy_preview)
        gc_layout.addWidget(self.cb_up_unselected)

        self.gdrive_cat_card.setVisible(False)
        content_layout.addWidget(self.gdrive_cat_card)

        # Structure Preview Card
        struct_card = QFrame()
        struct_card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
                padding: 14px;
            }}
        """)
        struct_layout = QVBoxLayout(struct_card)
        struct_layout.setSpacing(6)

        t_struct = QLabel("EXPORT DIRECTORY HIERARCHY")
        t_struct.setFont(get_mono_font(10, bold=True))
        t_struct.setStyleSheet(f"color: {COLOR_ACCENT};")
        struct_layout.addWidget(t_struct)

        self.preview_lbl = QLabel("")
        self.preview_lbl.setFont(get_mono_font(11))
        self.preview_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; line-height: 1.4;")
        struct_layout.addWidget(self.preview_lbl)
        content_layout.addWidget(struct_card)

        self._update_hierarchy_preview()

        # Progress / Status Telemetry Frame
        self.status_frame = QFrame()
        self.status_frame.setStyleSheet(
            f"background-color: {COLOR_BG_ELEVATED}; border: 1px solid {COLOR_BORDER_SUBTLE}; border-radius: 4px; padding: 10px;"
        )
        status_l = QVBoxLayout(self.status_frame)
        status_l.setSpacing(6)

        top_stat = QHBoxLayout()
        self.speed_lbl = QLabel("Ready to export.")
        self.speed_lbl.setFont(get_mono_font(11))
        self.speed_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        top_stat.addWidget(self.speed_lbl, stretch=1)

        self.pct_lbl = QLabel("0%")
        self.pct_lbl.setFont(get_mono_font(11, bold=True))
        self.pct_lbl.setStyleSheet(f"color: {COLOR_ACCENT};")
        top_stat.addWidget(self.pct_lbl)
        status_l.addLayout(top_stat)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        status_l.addWidget(self.progress_bar)

        row_stat = QHBoxLayout()
        self.eta_lbl = QLabel("")
        self.eta_lbl.setFont(get_mono_font(10))
        self.eta_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        row_stat.addWidget(self.eta_lbl)

        row_stat.addStretch()

        self.count_lbl = QLabel("")
        self.count_lbl.setFont(get_mono_font(11))
        row_stat.addWidget(self.count_lbl)
        status_l.addLayout(row_stat)

        content_layout.addWidget(self.status_frame)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, stretch=1)

        # Pinned Action Buttons Footer
        footer = QHBoxLayout()
        footer.setSpacing(12)

        self.start_btn = QPushButton("Export Photos")
        self.start_btn.setObjectName("accentButton")
        self.start_btn.setIcon(render_icon("export", 14, "#FFFFFF"))
        self.start_btn.setFont(get_body_font(12, bold=True))
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #D97706;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 13px;
                border: 1px solid #F59E0B;
                border-radius: 4px;
                padding: 0 20px;
            }
            QPushButton:hover {
                background-color: #F59E0B;
                color: #FFFFFF;
            }
            QPushButton:disabled {
                background-color: #2D2214;
                color: #5E6672;
                border-color: #3B414B;
            }
        """)
        self.start_btn.clicked.connect(self._start_export)
        footer.addWidget(self.start_btn, stretch=1)

        self.open_folder_btn = QPushButton("Open in Explorer")
        self.open_folder_btn.setFont(get_body_font(12, bold=True))
        self.open_folder_btn.setMinimumHeight(40)
        self.open_folder_btn.setVisible(False)
        self.open_folder_btn.clicked.connect(self._open_in_explorer)
        footer.addWidget(self.open_folder_btn)

        self.open_gdrive_btn = QPushButton("Open in Google Drive")
        self.open_gdrive_btn.setIcon(render_icon("cloud", 14, COLOR_ACCENT))
        self.open_gdrive_btn.setFont(get_body_font(12, bold=True))
        self.open_gdrive_btn.setMinimumHeight(40)
        self.open_gdrive_btn.setVisible(False)
        self.open_gdrive_btn.clicked.connect(self._open_in_gdrive)
        footer.addWidget(self.open_gdrive_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFont(get_body_font(12))
        self.cancel_btn.setMinimumHeight(40)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 0 18px;
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
        self.cancel_btn.clicked.connect(self._cancel_or_close)
        footer.addWidget(self.cancel_btn)

        main_layout.addLayout(footer)

    def _on_dest_mode_changed(self):
        is_gdrive = self.rb_dest_gdrive.isChecked()
        self.gdrive_cat_card.setVisible(is_gdrive)
        if is_gdrive:
            self.dest_lbl.setText("Google Drive Destination Folder (or paste Folder Link / ID):")
            self.dest_edit.setText(self.gdrive_parent_name)
            self.browse_btn.setText("Choose Drive Folder...")
            self.start_btn.setText("Upload to Google Drive")
            self.start_btn.setIcon(render_icon("cloud", 14, "#FFFFFF"))
        else:
            self.dest_lbl.setText("Export Destination:")
            default_dir = config.get("default_export_dir", "") or os.path.join(os.path.expanduser("~"), "Pictures", "Framed Exports")
            self.dest_edit.setText(default_dir)
            self.browse_btn.setText("Browse...")
            self.start_btn.setText("Export Photos")
            self.start_btn.setIcon(render_icon("export", 14, "#FFFFFF"))
        self._update_hierarchy_preview()

    def _browse_dest(self):
        if self.rb_dest_gdrive.isChecked():
            from loupe.ui.gdrive_dialog import GDriveBrowserDialog
            from loupe.ui.settings_dialog import SettingsDialog

            if not GoogleDriveClient().is_authenticated():
                ans = QMessageBox.question(
                    self,
                    "Connect Google Drive",
                    "You need to sign in to Google Drive in Preferences first.\n\nOpen Preferences now?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if ans == QMessageBox.Yes:
                    SettingsDialog(self).exec()
                if not GoogleDriveClient().is_authenticated():
                    return

            dlg = GDriveBrowserDialog(mode="select_folder", media_mode="photo", parent=self)
            if dlg.exec() == QDialog.Accepted:
                self.gdrive_parent_id = dlg.selected_folder_id or "root"
                self.gdrive_parent_name = dlg.selected_folder_name or "My Drive"
                config.set("gdrive_export_parent_id", self.gdrive_parent_id)
                config.set("gdrive_export_parent_name", self.gdrive_parent_name)
                self.dest_edit.setText(self.gdrive_parent_name)
                self._update_hierarchy_preview()
        else:
            d = QFileDialog.getExistingDirectory(self, "Select Export Destination")
            if d:
                self.dest_edit.setText(d)

    def _on_workspace_toggled(self, checked: bool):
        config.set("export_separate_by_workspace", checked)
        self._update_hierarchy_preview()

    def _update_hierarchy_preview(self):
        p_name = sanitize_folder_name(self.project.name)
        use_ws = self.cb_workspace.isChecked()
        w_name = sanitize_folder_name(self.project.get_workspace_name())
        fmt_mode = getattr(self.project, "format_mode", "both")
        is_gdrive = self.rb_dest_gdrive.isChecked()

        lines = []
        if is_gdrive:
            lines.append(f"☁️ Google Drive ({self.gdrive_parent_name})/")
            base_indent = "   "
        else:
            base_indent = ""

        if use_ws:
            lines.append(f"{base_indent}📁 {w_name}/")
            lines.append(f"{base_indent}   └── 📁 {p_name}/")
            indent = base_indent + "        "
        else:
            lines.append(f"{base_indent}📁 {p_name}/")
            indent = base_indent + "   "

        def _fmt_subfolders(prefix: str):
            if fmt_mode == "raw_only":
                return [f"{prefix}└── 📁 RAW/"]
            elif fmt_mode == "jpeg_only":
                return [f"{prefix}└── 📁 JPEG/"]
            return [
                f"{prefix}├── 📁 RAW/",
                f"{prefix}└── 📁 JPEG/",
            ]

        inc_sel = not is_gdrive or self.cb_up_selected.isChecked()
        inc_maybe = (not is_gdrive and self.project.maybe_count > 0) or (is_gdrive and self.cb_up_maybe.isChecked() and self.project.maybe_count > 0)
        inc_unsel = not is_gdrive or self.cb_up_unselected.isChecked()
        inc_edit = (not is_gdrive and self.project.edited_count > 0) or (is_gdrive and self.cb_up_edited.isChecked() and self.project.edited_count > 0)

        if inc_sel:
            lines.append(f"{indent}├── 📁 Selected/     ({self.project.kept_count} photos)")
            lines.extend(_fmt_subfolders(f"{indent}│    "))
        if inc_maybe:
            lines.append(f"{indent}├── 📁 Maybe/        ({self.project.maybe_count} photos)")
            lines.extend(_fmt_subfolders(f"{indent}│    "))
        if inc_unsel:
            lines.append(f"{indent}└── 📁 Unselected/   ({self.project.rejected_count + self.project.pending_count} photos)")
            lines.extend(_fmt_subfolders(f"{indent}     "))
        if inc_edit:
            lines.append(f"{indent}└── 📁 edited result/ ({self.project.edited_count} photos)")
        self.preview_lbl.setText("\n".join(lines))

    def _start_export(self):
        use_ws = self.cb_workspace.isChecked()

        if self.rb_dest_gdrive.isChecked():
            from loupe.ui.settings_dialog import SettingsDialog
            if not GoogleDriveClient().is_authenticated():
                ans = QMessageBox.question(
                    self,
                    "Connect Google Drive",
                    "Please sign in to Google Drive in Preferences before uploading.\n\nOpen Preferences now?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if ans == QMessageBox.Yes:
                    SettingsDialog(self).exec()
                if not GoogleDriveClient().is_authenticated():
                    return

            # Check if user pasted a URL/ID into dest_edit
            typed_dest = self.dest_edit.text().strip()
            parent_id = self.gdrive_parent_id
            if typed_dest and typed_dest != self.gdrive_parent_name:
                try:
                    parent_id = parse_gdrive_folder_id(typed_dest)
                except Exception:
                    parent_id = self.gdrive_parent_id

            self.start_btn.setEnabled(False)
            self.dest_edit.setEnabled(False)
            self.cancel_btn.setText("Cancel Upload")

            self.gdrive_worker = GDriveUploadWorker(
                project=self.project,
                parent_folder_id=parent_id,
                separate_by_workspace=use_ws,
                include_selected=self.cb_up_selected.isChecked(),
                include_maybe=self.cb_up_maybe.isChecked(),
                include_unselected=self.cb_up_unselected.isChecked(),
                include_edited=self.cb_up_edited.isChecked(),
                parent=self
            )
            self.gdrive_worker.telemetry_update.connect(self._on_gdrive_telemetry)
            self.gdrive_worker.upload_finished.connect(self._on_gdrive_finished)
            self.gdrive_worker.upload_failed.connect(self._on_failed)
            self.gdrive_worker.start()
            return

        dest_root = self.dest_edit.text().strip()
        if not dest_root:
            QMessageBox.warning(self, "Invalid Destination", "Please choose a valid destination directory.")
            return

        self.start_btn.setEnabled(False)
        self.dest_edit.setEnabled(False)
        self.cancel_btn.setText("Cancel Copy")

        self.worker = ExportWorker(self.project, dest_root, separate_by_workspace=use_ws, parent=self)
        self.worker.progress_update.connect(self._on_progress)
        self.worker.export_finished.connect(self._on_finished)
        self.worker.export_failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, copied: int, total: int, speed: float, current_file: str):
        pct = int((copied / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.pct_lbl.setText(f"{pct}%")
        self.speed_lbl.setText(f"Speed: {speed:.1f} MB/s • Copying {current_file}...")
        self.count_lbl.setText(f"{copied} / {total} files")

    def _on_gdrive_telemetry(
        self, completed: int, total: int, pct: float, speed_mb_s: float, eta_sec: float, current_file: str
    ):
        self.progress_bar.setValue(int(round(pct)))
        self.pct_lbl.setText(f"{pct:.1f}%")
        self.speed_lbl.setText(f"Uploading: {current_file}")
        self.eta_lbl.setText(f"Speed: {speed_mb_s:.2f} MB/s  •  ETA: {format_eta(eta_sec)}")
        self.count_lbl.setText(f"{completed} / {total} files")

    def _on_finished(self, summary: dict):
        self.exported_dir = summary.get("base_dir")
        self.progress_bar.setValue(100)
        self.pct_lbl.setText("100%")
        self.speed_lbl.setText("Export completed successfully.")
        self.speed_lbl.setStyleSheet(f"color: {COLOR_STATUS_KEPT};")
        self.count_lbl.setText(f"{summary.get('total_copied', 0)} files copied")
        self.start_btn.setVisible(False)
        self.open_folder_btn.setVisible(True)
        self.cancel_btn.setText("Close")

    def _on_gdrive_finished(self, summary: dict):
        self.exported_gdrive_url = summary.get("web_url")
        self.progress_bar.setValue(100)
        self.pct_lbl.setText("100%")
        self.speed_lbl.setText("✓ Google Drive upload completed successfully!")
        self.speed_lbl.setStyleSheet(f"color: {COLOR_STATUS_KEPT};")
        self.eta_lbl.setText("Uploaded to Google Drive")
        self.count_lbl.setText(f"{summary.get('total_uploaded', 0)} files uploaded")
        self.start_btn.setVisible(False)
        self.open_gdrive_btn.setVisible(True)
        self.cancel_btn.setText("Close")

    def _on_failed(self, msg: str):
        self.speed_lbl.setText(f"Error: {msg}")
        self.speed_lbl.setStyleSheet(f"color: {COLOR_STATUS_REJECTED};")
        self.start_btn.setEnabled(True)
        self.dest_edit.setEnabled(True)
        self.cancel_btn.setText("Close")

    def _open_in_explorer(self):
        if self.exported_dir and os.path.exists(self.exported_dir):
            if os.name == "nt":
                subprocess.Popen(f'explorer "{self.exported_dir}"')
            else:
                subprocess.Popen(["xdg-open", self.exported_dir])
        self.accept()

    def _open_in_gdrive(self):
        if self.exported_gdrive_url:
            webbrowser.open(self.exported_gdrive_url)
        self.accept()

    def _cancel_or_close(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(1000)
        if self.gdrive_worker and self.gdrive_worker.isRunning():
            self.gdrive_worker.cancel()
            self.gdrive_worker.wait(1500)
        self.reject()
