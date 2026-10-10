"""Update notification and in-app downloader dialog for Framed."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QFrame, QMessageBox
)
from PySide6.QtCore import Qt
from loupe.core.updater import UpdateInfo, UpdateDownloadWorker, apply_update_and_restart, CURRENT_VERSION
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_DISTINCT,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_ACCENT,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon

class UpdateDialog(QDialog):
    """Clean, purposeful dialog to display release notes, download updates, and restart."""
    def __init__(self, update_info: UpdateInfo, parent=None):
        super().__init__(parent)
        self.update_info = update_info
        self.download_worker = None
        self.setWindowTitle("Software Update Available — Framed")
        self.setFixedSize(520, 420)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLOR_BG_BASE};
            }}
        """)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header badge & title
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)

        tag = QLabel("SOFTWARE UPDATE")
        tag.setFont(get_mono_font(10, bold=True))
        tag.setStyleSheet(f"color: {COLOR_ACCENT}; letter-spacing: 1.5px;")
        header_layout.addWidget(tag)

        title = QLabel(f"Framed v{self.update_info.version} is available")
        title.setFont(get_display_font(18, bold=True))
        title.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")
        header_layout.addWidget(title)

        sub = QLabel(f"You are currently running v{CURRENT_VERSION}.")
        sub.setFont(get_body_font(12))
        sub.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        header_layout.addWidget(sub)
        layout.addLayout(header_layout)

        # Release notes box
        notes_frame = QFrame()
        notes_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 2px;
                padding: 4px;
            }}
        """)
        notes_layout = QVBoxLayout(notes_frame)
        notes_layout.setContentsMargins(12, 12, 12, 12)
        notes_layout.setSpacing(6)

        notes_title = QLabel("WHAT'S NEW")
        notes_title.setFont(get_mono_font(10, bold=True))
        notes_title.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        notes_layout.addWidget(notes_title)

        self.notes_text = QTextEdit()
        self.notes_text.setReadOnly(True)
        self.notes_text.setFont(get_body_font(12))
        self.notes_text.setStyleSheet("border: none; background: transparent; color: #EDEFEA;")
        self.notes_text.setPlainText(self.update_info.release_notes or "Bug fixes and performance improvements.")
        notes_layout.addWidget(self.notes_text)

        layout.addWidget(notes_frame, stretch=1)

        # Progress bar area (hidden until download starts)
        self.progress_container = QFrame()
        self.progress_container.setVisible(False)
        prog_layout = QVBoxLayout(self.progress_container)
        prog_layout.setContentsMargins(0, 0, 0, 0)
        prog_layout.setSpacing(6)

        self.progress_lbl = QLabel("Downloading update...")
        self.progress_lbl.setFont(get_mono_font(11))
        self.progress_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        prog_layout.addWidget(self.progress_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 2px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_ACCENT};
            }}
        """)
        prog_layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_container)

        # Action Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.btn_later = QPushButton("Remind Me Later")
        self.btn_later.setFont(get_body_font(12))
        self.btn_later.setMinimumHeight(36)
        self.btn_later.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                padding: 6px 14px;
            }}
        """)
        self.btn_later.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_later)

        button_layout.addStretch()

        self.btn_update = QPushButton("Update & Restart")
        self.btn_update.setIcon(render_icon("export", 13, "#0E1013"))
        self.btn_update.setFont(get_body_font(12, bold=True))
        self.btn_update.setMinimumHeight(36)
        self.btn_update.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_ACCENT};
                color: #0E1013;
                border: 1px solid {COLOR_ACCENT};
                padding: 6px 18px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: #FFAE42;
            }}
            QPushButton:disabled {{
                background-color: #332B20;
                color: #777;
                border-color: #443725;
            }}
        """)
        self.btn_update.clicked.connect(self._start_download)
        button_layout.addWidget(self.btn_update)

        layout.addLayout(button_layout)

    def _start_download(self):
        self.btn_update.setEnabled(False)
        self.btn_later.setEnabled(False)
        self.progress_container.setVisible(True)
        self.progress_lbl.setText("Connecting to download server...")

        self.download_worker = UpdateDownloadWorker(self.update_info.download_url, self)
        self.download_worker.progress_changed.connect(self._on_progress)
        self.download_worker.download_finished.connect(self._on_download_finished)
        self.download_worker.start()

    def _on_progress(self, downloaded: int, total: int, pct: float):
        self.progress_bar.setValue(int(pct))
        dl_mb = downloaded / (1024 * 1024)
        tot_mb = total / (1024 * 1024) if total > 0 else 0
        self.progress_lbl.setText(f"Downloading update: {dl_mb:.1f} MB / {tot_mb:.1f} MB ({pct:.0f}%)")

    def _on_download_finished(self, success: bool, installer_path: str, error_msg: str):
        if success and installer_path:
            self.progress_lbl.setText("Download complete! Launching silent update...")
            try:
                apply_update_and_restart(installer_path)
            except Exception as e:
                QMessageBox.critical(self, "Update Error", f"Failed to start installer:\n{e}")
                self.btn_update.setEnabled(True)
                self.btn_later.setEnabled(True)
        else:
            QMessageBox.warning(self, "Download Failed", f"Could not download update:\n{error_msg}")
            self.btn_update.setEnabled(True)
            self.btn_later.setEnabled(True)
            self.progress_container.setVisible(False)
