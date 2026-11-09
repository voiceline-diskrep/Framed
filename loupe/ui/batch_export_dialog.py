"""Sequential batch export dialog for exporting multiple projects in order."""

import os
import shutil
import time
import subprocess
import sys
from typing import List, Optional, Dict
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QScrollArea, QWidget, QFrame, QFileDialog,
    QCheckBox, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, Signal, QThread
from loupe.models import Project
from loupe.config import config
from loupe.core.exporter import sanitize_folder_name
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BG_HOVER,
    COLOR_BORDER_DISTINCT, COLOR_BORDER_SUBTLE, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_STATUS_KEPT,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon


class BatchExportWorker(QThread):
    """Executes non-destructive exports for multiple projects sequentially in order."""
    project_started = Signal(int, int, str)       # current_proj_idx, total_projs, proj_name
    file_progress = Signal(int, int, float, str)  # copied_files, total_files, speed_mb_s, filename
    batch_finished = Signal(dict)                 # summary dict
    batch_failed = Signal(str)                   # error message

    def __init__(self, projects: List[Project], destination_root: str, separate_by_workspace: bool = True, parent=None):
        super().__init__(parent)
        self.projects = projects
        self.destination_root = destination_root
        self.separate_by_workspace = separate_by_workspace
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            total_projects = len(self.projects)
            total_files_all = 0
            total_bytes_all = 0
            start_time = time.perf_counter()

            for p_idx, project in enumerate(self.projects, start=1):
                if self._is_cancelled:
                    break

                self.project_started.emit(p_idx, total_projects, project.name)

                proj_folder_name = sanitize_folder_name(project.name)
                if self.separate_by_workspace:
                    ws_parts = [sanitize_folder_name(p) for p in project.get_workspace_parts()]
                    base_dir = os.path.join(self.destination_root, *ws_parts, proj_folder_name)
                else:
                    base_dir = os.path.join(self.destination_root, proj_folder_name)

                is_vid = getattr(project, "media_type", "photo") == "video"

                if is_vid:
                    # Video export tasks
                    selected_dir = os.path.join(base_dir, "Selected")
                    similar_dir = os.path.join(base_dir, "Similar")
                    unselected_dir = os.path.join(base_dir, "Unselected")
                    tasks = []
                    for item in project.items:
                        if item.status in ("kept", "selected"):
                            target_dir = selected_dir
                        elif item.status in ("maybe", "similar"):
                            target_dir = similar_dir
                        elif item.status in ("rejected", "unselected"):
                            target_dir = unselected_dir
                        else:
                            continue
                        if item.primary_path and os.path.exists(item.primary_path):
                            tasks.append((item.primary_path, target_dir))
                else:
                    # Photo export tasks
                    match_raw = os.path.join(base_dir, "Match Selection", "RAW")
                    match_jpeg = os.path.join(base_dir, "Match Selection", "JPEG")
                    selected_raw = os.path.join(base_dir, "Selected", "RAW")
                    selected_jpeg = os.path.join(base_dir, "Selected", "JPEG")
                    maybe_raw = os.path.join(base_dir, "Maybe", "RAW")
                    maybe_jpeg = os.path.join(base_dir, "Maybe", "JPEG")
                    unselected_raw = os.path.join(base_dir, "Unselected", "RAW")
                    unselected_jpeg = os.path.join(base_dir, "Unselected", "JPEG")

                    fmt_mode = getattr(project, "format_mode", "both")
                    include_raw = fmt_mode in ("both", "raw_only")
                    include_jpeg = fmt_mode in ("both", "jpeg_only")

                    match_quota = getattr(project, "match_quota", 0)
                    match_count = 0
                    tasks = []

                    for item in project.items:
                        is_selected = item.status in ("kept", "selected")
                        is_match = False
                        if is_selected and match_quota > 0 and match_count < match_quota:
                            is_match = True
                            match_count += 1

                        if is_match:
                            raw_dst = match_raw
                            jpg_dst = match_jpeg
                        elif is_selected:
                            raw_dst = selected_raw
                            jpg_dst = selected_jpeg
                        elif item.status in ("maybe", "similar"):
                            raw_dst = maybe_raw
                            jpg_dst = maybe_jpeg
                        elif item.status in ("rejected", "unselected"):
                            raw_dst = unselected_raw
                            jpg_dst = unselected_jpeg
                        else:
                            continue

                        if include_raw and item.raw_path and os.path.exists(item.raw_path):
                            tasks.append((item.raw_path, raw_dst))
                        if include_jpeg:
                            jp = item.jpeg_path or item.primary_path
                            if jp and os.path.exists(jp):
                                tasks.append((jp, jpg_dst))

                proj_total = len(tasks)
                proj_copied = 0
                proj_bytes = 0
                proj_start = time.perf_counter()

                for src, dst_folder in tasks:
                    if self._is_cancelled:
                        break

                    os.makedirs(dst_folder, exist_ok=True)
                    fname = os.path.basename(src)
                    dst_file = os.path.join(dst_folder, fname)

                    if not os.path.exists(dst_file):
                        shutil.copy2(src, dst_file)

                    fsize = os.path.getsize(src) if os.path.exists(src) else 0
                    proj_copied += 1
                    proj_bytes += fsize
                    total_files_all += 1
                    total_bytes_all += fsize

                    elapsed = max(0.01, time.perf_counter() - proj_start)
                    speed_mb_s = (proj_bytes / (1024 * 1024)) / elapsed
                    self.file_progress.emit(proj_copied, proj_total, speed_mb_s, fname)

            total_elapsed = max(0.01, time.perf_counter() - start_time)
            summary = {
                "total_projects": len(self.projects),
                "total_files": total_files_all,
                "total_bytes": total_bytes_all,
                "total_time_sec": total_elapsed,
                "destination_root": self.destination_root,
                "cancelled": self._is_cancelled,
            }
            self.batch_finished.emit(summary)

        except Exception as e:
            self.batch_failed.emit(str(e))


class BatchExportDialog(QDialog):
    """Clean workstation dialog for exporting multiple projects in order."""

    def __init__(self, projects: List[Project], parent=None):
        super().__init__(parent)
        self.projects = list(projects)
        self.worker: Optional[BatchExportWorker] = None
        self.exported_root: Optional[str] = None

        self.setWindowTitle(f"Batch Export — {len(self.projects)} Sessions in Order")
        self.setMinimumSize(580, 460)
        self.resize(620, 520)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE}; color: {COLOR_TEXT_PRIMARY};")

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        # Header
        h_layout = QVBoxLayout()
        h_layout.setSpacing(2)
        title = QLabel(f"Export {len(self.projects)} Sessions in Order")
        title.setFont(get_display_font(17, bold=True))
        h_layout.addWidget(title)

        sub = QLabel("Files are safely copied in sequence into structured Selected and Unselected folders.")
        sub.setFont(get_body_font(12))
        sub.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        h_layout.addWidget(sub)
        main_layout.addLayout(h_layout)

        # Projects list preview (in order)
        list_frame = QFrame()
        list_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 8px;
            }}
        """)
        lf_layout = QVBoxLayout(list_frame)
        lf_layout.setContentsMargins(12, 10, 12, 10)
        lf_layout.setSpacing(6)

        hdr_lbl = QLabel("EXPORT ORDER:")
        hdr_lbl.setFont(get_mono_font(10, bold=True))
        hdr_lbl.setStyleSheet(f"color: {COLOR_ACCENT}; letter-spacing: 1px;")
        lf_layout.addWidget(hdr_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(140)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        s_content = QWidget()
        s_layout = QVBoxLayout(s_content)
        s_layout.setContentsMargins(0, 0, 0, 0)
        s_layout.setSpacing(4)

        for i, proj in enumerate(self.projects, start=1):
            row = QHBoxLayout()
            row.setSpacing(8)
            num_lbl = QLabel(f"{i}.")
            num_lbl.setFont(get_mono_font(11, bold=True))
            num_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
            num_lbl.setFixedWidth(24)
            row.addWidget(num_lbl)

            name_lbl = QLabel(proj.name)
            name_lbl.setFont(get_body_font(12, bold=True))
            row.addWidget(name_lbl)

            is_vid = getattr(proj, "media_type", "photo") == "video"
            type_lbl = QLabel("VIDEO" if is_vid else "PHOTO")
            type_lbl.setFont(get_mono_font(9, bold=True))
            t_col = "#F59E0B" if is_vid else "#22C55E"
            type_lbl.setStyleSheet(f"color: {t_col}; padding: 1px 4px;")
            row.addWidget(type_lbl)

            cnt_lbl = QLabel(f"{proj.total_count} files • 📁 {proj.get_workspace_name()}")
            cnt_lbl.setFont(get_mono_font(11))
            cnt_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
            row.addWidget(cnt_lbl)
            row.addStretch()
            s_layout.addLayout(row)

        scroll.setWidget(s_content)
        lf_layout.addWidget(scroll)
        main_layout.addWidget(list_frame)

        # Destination selector
        dest_frame = QFrame()
        dest_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 8px;
            }}
        """)
        df_layout = QVBoxLayout(dest_frame)
        df_layout.setContentsMargins(14, 12, 14, 12)
        df_layout.setSpacing(10)

        dest_title = QLabel("Destination Directory:")
        dest_title.setFont(get_body_font(12, bold=True))
        df_layout.addWidget(dest_title)

        d_row = QHBoxLayout()
        d_row.setSpacing(8)
        default_root = config.get("last_export_dir", os.path.join(os.path.expanduser("~"), "Desktop"))
        self.dest_lbl = QLabel(default_root)
        self.dest_lbl.setFont(get_mono_font(11))
        self.dest_lbl.setStyleSheet(f"background-color: {COLOR_BG_ELEVATED}; padding: 6px 10px; border-radius: 6px; border: 1px solid {COLOR_BORDER_SUBTLE};")
        d_row.addWidget(self.dest_lbl, 1)

        btn_browse = QPushButton("Browse...")
        btn_browse.setFont(get_body_font(11))
        btn_browse.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 6px;
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        btn_browse.clicked.connect(self._browse_dest)
        d_row.addWidget(btn_browse)
        df_layout.addLayout(d_row)

        self.cb_separate_ws = QCheckBox("Separate into workspace folder hierarchy (e.g., Destination / Work / Session)")
        self.cb_separate_ws.setChecked(True)
        self.cb_separate_ws.setFont(get_body_font(11))
        df_layout.addWidget(self.cb_separate_ws)

        main_layout.addWidget(dest_frame)

        # Progress Section (Initially hidden)
        self.progress_frame = QFrame()
        self.progress_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 8px;
            }}
        """)
        pf_layout = QVBoxLayout(self.progress_frame)
        pf_layout.setContentsMargins(14, 12, 14, 12)
        pf_layout.setSpacing(8)

        self.proj_progress_lbl = QLabel("Preparing export...")
        self.proj_progress_lbl.setFont(get_body_font(12, bold=True))
        pf_layout.addWidget(self.proj_progress_lbl)

        self.proj_bar = QProgressBar()
        self.proj_bar.setRange(0, len(self.projects))
        self.proj_bar.setValue(0)
        self.proj_bar.setFixedHeight(8)
        self.proj_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLOR_BG_ELEVATED};
                border-radius: 4px;
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_ACCENT};
                border-radius: 4px;
            }}
        """)
        pf_layout.addWidget(self.proj_bar)

        self.file_progress_lbl = QLabel("Copying files...")
        self.file_progress_lbl.setFont(get_mono_font(11))
        self.file_progress_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        pf_layout.addWidget(self.file_progress_lbl)

        self.file_bar = QProgressBar()
        self.file_bar.setRange(0, 100)
        self.file_bar.setValue(0)
        self.file_bar.setFixedHeight(6)
        self.file_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLOR_BG_ELEVATED};
                border-radius: 3px;
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: #22C55E;
                border-radius: 3px;
            }}
        """)
        pf_layout.addWidget(self.file_bar)

        self.progress_frame.setVisible(False)
        main_layout.addWidget(self.progress_frame)

        # Action Buttons
        main_layout.addStretch()
        b_row = QHBoxLayout()
        b_row.setSpacing(10)

        self.btn_open_folder = QPushButton("Open Destination")
        self.btn_open_folder.setIcon(render_icon("folder", 12, COLOR_TEXT_PRIMARY))
        self.btn_open_folder.setFont(get_body_font(11))
        self.btn_open_folder.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 7px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        self.btn_open_folder.clicked.connect(self._open_dest_folder)
        self.btn_open_folder.setVisible(False)
        b_row.addWidget(self.btn_open_folder)

        b_row.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFont(get_body_font(12))
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 7px;
                padding: 8px 18px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_HOVER};
            }}
        """)
        self.btn_cancel.clicked.connect(self._on_cancel)
        b_row.addWidget(self.btn_cancel)

        self.btn_start = QPushButton(f"Export {len(self.projects)} Sessions in Order")
        self.btn_start.setIcon(render_icon("export", 13, "#FFFFFF"))
        self.btn_start.setFont(get_body_font(12, bold=True))
        self.btn_start.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COLOR_ACCENT}, stop:1 #D97706);
                color: #FFFFFF;
                border: 1px solid #FBBF24;
                border-radius: 7px;
                padding: 8px 22px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: #FBBF24;
            }}
        """)
        self.btn_start.clicked.connect(self._start_export)
        b_row.addWidget(self.btn_start)

        main_layout.addLayout(b_row)

    def _browse_dest(self):
        curr = self.dest_lbl.text()
        chosen = QFileDialog.getExistingDirectory(self, "Select Destination Directory", curr)
        if chosen:
            self.dest_lbl.setText(chosen)
            config.set("last_export_dir", chosen)

    def _start_export(self):
        dest_dir = self.dest_lbl.text().strip()
        if not dest_dir or not os.path.exists(dest_dir):
            QMessageBox.warning(self, "Invalid Destination", "Please choose a valid destination directory.")
            return

        self.btn_start.setEnabled(False)
        self.btn_start.setVisible(False)
        self.btn_cancel.setText("Cancel Export")
        self.progress_frame.setVisible(True)

        sep_ws = self.cb_separate_ws.isChecked()
        self.worker = BatchExportWorker(self.projects, dest_dir, separate_by_workspace=sep_ws, parent=self)
        self.worker.project_started.connect(self._on_project_started)
        self.worker.file_progress.connect(self._on_file_progress)
        self.worker.batch_finished.connect(self._on_batch_finished)
        self.worker.batch_failed.connect(self._on_batch_failed)
        self.worker.start()

    def _on_project_started(self, curr_idx: int, total: int, name: str):
        self.proj_bar.setValue(curr_idx - 1)
        self.proj_progress_lbl.setText(f"Session {curr_idx} of {total}: '{name}'")
        self.file_bar.setValue(0)
        self.file_progress_lbl.setText("Starting file copy...")

    def _on_file_progress(self, copied: int, total: int, speed: float, filename: str):
        if total > 0:
            pct = int((copied / total) * 100)
            self.file_bar.setValue(pct)
        self.file_progress_lbl.setText(f"Copying {filename} ({copied} / {total}) • {speed:.1f} MB/s")

    def _on_batch_finished(self, summary: dict):
        self.proj_bar.setValue(len(self.projects))
        self.file_bar.setValue(100)
        self.exported_root = summary["destination_root"]

        t_mb = summary["total_bytes"] / (1024 * 1024)
        t_sec = summary["total_time_sec"]
        msg = f"✓ Finished! {summary['total_files']} files ({t_mb:.1f} MB) exported in {t_sec:.1f}s."
        self.proj_progress_lbl.setText(msg)
        self.proj_progress_lbl.setStyleSheet(f"color: {COLOR_STATUS_KEPT}; font-weight: bold;")
        self.file_progress_lbl.setText("All sessions successfully organized in order.")

        self.btn_cancel.setText("Close")
        self.btn_open_folder.setVisible(True)

    def _on_batch_failed(self, error_msg: str):
        QMessageBox.critical(self, "Export Error", f"Batch export failed:\n{error_msg}")
        self.btn_cancel.setText("Close")

    def _open_dest_folder(self):
        root = self.exported_root or self.dest_lbl.text()
        if root and os.path.exists(root):
            if sys.platform == "win32":
                os.startfile(root)
            elif sys.platform == "darwin":
                subprocess.run(["open", root])
            else:
                subprocess.run(["xdg-open", root])

    def _on_cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(1000)
        self.reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(1000)
        super().closeEvent(event)
