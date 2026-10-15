"""Export dialog and progress monitor creating the structured Selected/Unselected RAW/JPEG folders."""

import os
import subprocess
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QProgressBar, QFrame, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt
from loupe.config import config
from loupe.models import Project
from loupe.core.exporter import ExportWorker, sanitize_folder_name
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_SUBTLE,
    COLOR_BORDER_DISTINCT, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_STATUS_KEPT,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon

class ExportDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Export Structured Photographic Session")
        self.setMinimumSize(520, 360)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")

        self.worker: Optional[ExportWorker] = None
        self.exported_dir: Optional[str] = None

        self._init_ui()
        self._fit_to_available_screen()

    def _fit_to_available_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            target_w = min(580, max(520, avail.width() - 40))
            target_h = min(460, max(360, avail.height() - 60))
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
        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel(f"Export '{self.project.name}'")
        title.setFont(get_display_font(18, bold=True))
        sub = QLabel("Files are safely copied into structured Selected and Unselected folders.")
        sub.setFont(get_body_font(12))
        sub.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        header.addWidget(title)
        header.addWidget(sub)
        main_layout.addLayout(header)

        # Structure Preview Card
        struct_card = QFrame()
        struct_card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 2px;
                padding: 12px;
            }}
        """)
        struct_layout = QVBoxLayout(struct_card)
        struct_layout.setSpacing(6)

        t_struct = QLabel("EXPORT DIRECTORY HIERARCHY")
        t_struct.setFont(get_mono_font(10, bold=True))
        t_struct.setStyleSheet(f"color: {COLOR_ACCENT};")
        struct_layout.addWidget(t_struct)

        p_name = sanitize_folder_name(self.project.name)
        preview_text = (
            f"📁 {p_name}/\n"
            f"   ├── 📁 Selected/     ({self.project.kept_count} photos)\n"
            f"   │    ├── 📁 RAW/\n"
            f"   │    └── 📁 JPEG/\n"
            f"   └── 📁 Unselected/   ({self.project.rejected_count + self.project.pending_count} photos)\n"
            f"        ├── 📁 RAW/\n"
            f"        └── 📁 JPEG/"
        )
        preview_lbl = QLabel(preview_text)
        preview_lbl.setFont(get_mono_font(11))
        preview_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; line-height: 1.4;")
        struct_layout.addWidget(preview_lbl)
        main_layout.addWidget(struct_card)

        # Destination Folder Input
        dest_layout = QVBoxLayout()
        dest_layout.setSpacing(6)
        dest_lbl = QLabel("Export Destination:")
        dest_lbl.setFont(get_body_font(12, bold=True))
        dest_layout.addWidget(dest_lbl)

        row_dest = QHBoxLayout()
        self.dest_edit = QLineEdit()
        default_dir = config.get("default_export_dir", "") or os.path.join(os.path.expanduser("~"), "Pictures", "Loupe Exports")
        self.dest_edit.setText(default_dir)
        row_dest.addWidget(self.dest_edit, stretch=1)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_dest)
        row_dest.addWidget(browse_btn)
        dest_layout.addLayout(row_dest)
        main_layout.addLayout(dest_layout)

        # Progress / Status Frame
        self.status_frame = QFrame()
        self.status_frame.setStyleSheet(f"background-color: {COLOR_BG_ELEVATED}; border: 1px solid {COLOR_BORDER_SUBTLE}; border-radius: 2px; padding: 10px;")
        status_l = QVBoxLayout(self.status_frame)
        status_l.setSpacing(6)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        status_l.addWidget(self.progress_bar)

        row_stat = QHBoxLayout()
        self.speed_lbl = QLabel("Ready to export.")
        self.speed_lbl.setFont(get_mono_font(11))
        self.speed_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        row_stat.addWidget(self.speed_lbl)

        row_stat.addStretch()

        self.count_lbl = QLabel("")
        self.count_lbl.setFont(get_mono_font(11))
        row_stat.addWidget(self.count_lbl)
        status_l.addLayout(row_stat)

        main_layout.addWidget(self.status_frame)

        # Action Buttons
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.start_btn = QPushButton("Export Photos")
        self.start_btn.setObjectName("accentButton")
        self.start_btn.setIcon(render_icon("export", 14, "#000000"))
        self.start_btn.setMinimumHeight(38)
        self.start_btn.clicked.connect(self._start_export)
        footer.addWidget(self.start_btn, stretch=1)

        self.open_folder_btn = QPushButton("Open in Explorer")
        self.open_folder_btn.setMinimumHeight(38)
        self.open_folder_btn.setVisible(False)
        self.open_folder_btn.clicked.connect(self._open_in_explorer)
        footer.addWidget(self.open_folder_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(38)
        self.cancel_btn.clicked.connect(self._cancel_or_close)
        footer.addWidget(self.cancel_btn)

        main_layout.addLayout(footer)

    def _browse_dest(self):
        d = QFileDialog.getExistingDirectory(self, "Select Export Destination")
        if d:
            self.dest_edit.setText(d)

    def _start_export(self):
        dest_root = self.dest_edit.text().strip()
        if not dest_root:
            QMessageBox.warning(self, "Invalid Destination", "Please choose a valid destination directory.")
            return

        self.start_btn.setEnabled(False)
        self.dest_edit.setEnabled(False)
        self.cancel_btn.setText("Cancel Copy")

        self.worker = ExportWorker(self.project, dest_root, self)
        self.worker.progress_update.connect(self._on_progress)
        self.worker.export_finished.connect(self._on_finished)
        self.worker.export_failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, copied: int, total: int, speed: float, current_file: str):
        pct = int((copied / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.speed_lbl.setText(f"Speed: {speed:.1f} MB/s • Copying {current_file}...")
        self.count_lbl.setText(f"{copied} / {total} files")

    def _on_finished(self, summary: dict):
        self.exported_dir = summary.get("base_dir")
        self.progress_bar.setValue(100)
        self.speed_lbl.setText("Export completed successfully.")
        self.speed_lbl.setStyleSheet(f"color: {COLOR_STATUS_KEPT};")
        self.count_lbl.setText(f"{summary.get('total_copied', 0)} files copied")
        self.start_btn.setVisible(False)
        self.open_folder_btn.setVisible(True)
        self.cancel_btn.setText("Close")

    def _on_failed(self, msg: str):
        self.speed_lbl.setText(f"Error: {msg}")
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

    def _cancel_or_close(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(1000)
        self.reject()
