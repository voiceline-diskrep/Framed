"""Video export modal dialog with progress telemetry and open folder action."""

import os
import subprocess
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QProgressBar, QMessageBox, QFrame,
    QCheckBox, QWidget, QScrollArea, QApplication
)
from PySide6.QtCore import Qt
from loupe.models import Project
from loupe.config import config
from loupe.core.exporter import sanitize_folder_name
from loupe.core.video_exporter import VideoExportWorker
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_DISTINCT,
    COLOR_BORDER_SUBTLE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
    COLOR_ACCENT, COLOR_STATUS_KEPT, COLOR_STATUS_REJECTED, get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon

class VideoExportDialog(QDialog):
    """Dialog to initiate non-destructive video export into Selected, Unselected, and Similar."""
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.worker: VideoExportWorker = None
        self.exported_base_dir = ""

        self.setWindowTitle("Export Video Session — Framed")
        self.setMinimumSize(540, 420)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")
        self._init_ui()
        self._fit_to_available_screen()

    def _fit_to_available_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            target_w = min(680, max(560, avail.width() - 40))
            target_h = min(680, max(500, avail.height() - 60))
            self.resize(target_w, target_h)
            x = avail.x() + (avail.width() - target_w) // 2
            y = avail.y() + max(10, (avail.height() - target_h) // 2)
            self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_to_available_screen()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 16)
        main_layout.setSpacing(14)

        # Scrollable content area so it never squishes on any display scaling
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(16)

        # Header
        h_layout = QVBoxLayout()
        h_layout.setSpacing(4)
        tag = QLabel("EXPORT DESTINATION")
        tag.setFont(get_mono_font(10, bold=True))
        tag.setStyleSheet(f"color: {COLOR_ACCENT}; letter-spacing: 1px;")
        h_layout.addWidget(tag)

        title = QLabel(f"Export '{self.project.name}'")
        title.setFont(get_display_font(18, bold=True))
        h_layout.addWidget(title)
        layout.addLayout(h_layout)

        # Summary of decisions card
        card_summary = QFrame()
        card_summary.setObjectName("cardSummary")
        card_summary.setStyleSheet(f"""
            QFrame#cardSummary {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
            }}
        """)
        cs_layout = QVBoxLayout(card_summary)
        cs_layout.setContentsMargins(18, 16, 18, 16)
        cs_layout.setSpacing(10)

        lbl_head = QLabel("CLIPS TO COPY (ORIGINAL HIGH QUALITY):")
        lbl_head.setFont(get_mono_font(10, bold=True))
        lbl_head.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        cs_layout.addWidget(lbl_head)

        r_layout = QHBoxLayout()
        lbl_sel = QLabel(f"Selected: {self.project.selected_count}")
        lbl_sel.setFont(get_mono_font(12, bold=True))
        lbl_sel.setStyleSheet("color: #7BE4A2;")
        r_layout.addWidget(lbl_sel)

        lbl_sim = QLabel(f"Similar: {self.project.similar_count}")
        lbl_sim.setFont(get_mono_font(12, bold=True))
        lbl_sim.setStyleSheet("color: #5BC0DE;")
        r_layout.addWidget(lbl_sim)

        lbl_unsel = QLabel(f"Unselected: {self.project.unselected_count}")
        lbl_unsel.setFont(get_mono_font(12, bold=True))
        lbl_unsel.setStyleSheet("color: #F87171;")
        r_layout.addWidget(lbl_unsel)
        cs_layout.addLayout(r_layout)

        dest_note = QLabel("Files will be cleanly organized into Selected, Unselected, and Similar subfolders.")
        dest_note.setFont(get_body_font(11))
        dest_note.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        cs_layout.addWidget(dest_note)
        layout.addWidget(card_summary)

        # Destination input
        dir_layout = QVBoxLayout()
        dir_layout.setSpacing(8)
        lbl_dest = QLabel("Export Directory:")
        lbl_dest.setFont(get_body_font(12, bold=True))
        dir_layout.addWidget(lbl_dest)

        row_dest = QHBoxLayout()
        row_dest.setSpacing(10)
        self.edit_dir = QLineEdit()
        self.edit_dir.setFont(get_body_font(12))
        default_dir = config.get("default_export_dir") or os.path.join(os.path.expanduser("~"), "Videos")
        self.edit_dir.setText(default_dir)
        self.edit_dir.setMinimumHeight(40)
        self.edit_dir.setStyleSheet(f"""
            QLineEdit {{
                padding: 0 12px;
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        row_dest.addWidget(self.edit_dir, stretch=1)

        btn_browse = QPushButton("Browse...")
        btn_browse.setFont(get_body_font(12))
        btn_browse.setMinimumHeight(40)
        btn_browse.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_PRIMARY};
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {COLOR_TEXT_SECONDARY};
                background-color: #2A2E35;
            }}
        """)
        btn_browse.clicked.connect(self._browse)
        row_dest.addWidget(btn_browse)
        dir_layout.addLayout(row_dest)

        # Workspace Folder Separation Checkbox
        ws_name = self.project.get_workspace_name()
        self.cb_workspace = QCheckBox(f"Separate into Workspace Folder ('{ws_name}')")
        self.cb_workspace.setFont(get_body_font(12))
        self.cb_workspace.setChecked(config.get("export_separate_by_workspace", True))
        self.cb_workspace.toggled.connect(self._on_workspace_toggled)
        dir_layout.addWidget(self.cb_workspace)

        layout.addLayout(dir_layout)

        # Structure Preview Card
        struct_card = QFrame()
        struct_card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
                padding: 12px;
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
        layout.addWidget(struct_card)

        self._update_hierarchy_preview()

        # Progress bar
        self.progress_frame = QFrame()
        self.progress_frame.setVisible(False)
        p_layout = QVBoxLayout(self.progress_frame)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(6)

        self.lbl_status = QLabel("Copying video files...")
        self.lbl_status.setFont(get_mono_font(11))
        self.lbl_status.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        p_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_ACCENT};
            }}
        """)
        p_layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_frame)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, stretch=1)

        # Pinned Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFont(get_body_font(12))
        self.btn_cancel.setMinimumHeight(40)
        self.btn_cancel.setStyleSheet(f"""
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
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        btn_row.addStretch()

        self.btn_open_folder = QPushButton("Open Folder")
        self.btn_open_folder.setFont(get_body_font(12, bold=True))
        self.btn_open_folder.setIcon(render_icon("folder", 13, COLOR_ACCENT))
        self.btn_open_folder.setMinimumHeight(40)
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self._open_output_folder)
        btn_row.addWidget(self.btn_open_folder)

        self.btn_start = QPushButton("Start Export")
        self.btn_start.setObjectName("accentButton")
        self.btn_start.setIcon(render_icon("export", 13, "#FFFFFF"))
        self.btn_start.setFont(get_body_font(12, bold=True))
        self.btn_start.setMinimumHeight(40)
        self.btn_start.setStyleSheet("""
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
        self.btn_start.clicked.connect(self._start_export)
        btn_row.addWidget(self.btn_start)

        main_layout.addLayout(btn_row)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select Export Destination", self.edit_dir.text())
        if d:
            self.edit_dir.setText(d)
            self._update_hierarchy_preview()

    def _on_workspace_toggled(self, checked: bool):
        config.set("export_separate_by_workspace", checked)
        self._update_hierarchy_preview()

    def _update_hierarchy_preview(self):
        p_name = sanitize_folder_name(self.project.name)
        use_ws = self.cb_workspace.isChecked()
        w_name = sanitize_folder_name(self.project.get_workspace_name())

        lines = []
        if use_ws:
            lines.append(f"📁 {w_name}/")
            lines.append(f"   └── 📁 {p_name}/")
            indent = "        "
        else:
            lines.append(f"📁 {p_name}/")
            indent = "   "

        lines.extend([
            f"{indent}├── 📁 Selected/     ({self.project.selected_count} clips)",
            f"{indent}├── 📁 Similar/      ({self.project.similar_count} clips)",
            f"{indent}└── 📁 Unselected/   ({self.project.unselected_count} clips)",
        ])
        self.preview_lbl.setText("\n".join(lines))

    def _start_export(self):
        root = self.edit_dir.text().strip()
        if not root or not os.path.exists(root):
            QMessageBox.warning(self, "Invalid Directory", "Please select a valid destination directory.")
            return

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.progress_frame.setVisible(True)

        use_ws = self.cb_workspace.isChecked()
        self.worker = VideoExportWorker(self.project, root, separate_by_workspace=use_ws, parent=self)
        self.worker.progress_changed.connect(self._on_progress)
        self.worker.export_finished.connect(self._on_finished)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, current: int, total: int, fname: str, mb_s: float):
        pct = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(f"Copying [{current}/{total}] {fname} ({mb_s:.1f} MB/s)")

    def _on_finished(self, summary: dict):
        self.exported_base_dir = summary["base_dir"]
        self.lbl_status.setText("Export completed successfully!")
        self.btn_cancel.setText("Close")
        self.btn_cancel.setEnabled(True)
        self.btn_start.setVisible(False)
        self.btn_open_folder.setVisible(True)

        QMessageBox.information(
            self, "Video Export Complete",
            f"Successfully exported {summary['total_exported']} videos into:\n\n{self.exported_base_dir}\n\n"
            f"• Selected: {summary['selected_count']}\n"
            f"• Similar: {summary['similar_count']}\n"
            f"• Unselected: {summary['unselected_count']}"
        )

    def _on_error(self, err_msg: str):
        QMessageBox.critical(self, "Export Error", f"An error occurred during video export:\n{err_msg}")
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.progress_frame.setVisible(False)

    def _open_output_folder(self):
        if self.exported_base_dir and os.path.exists(self.exported_base_dir):
            if os.name == "nt":
                os.startfile(self.exported_base_dir)
            else:
                subprocess.Popen(["xdg-open", self.exported_base_dir])
        self.accept()
