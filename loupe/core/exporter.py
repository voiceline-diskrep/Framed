"""Non-destructive export engine creating the structured Selected/Unselected RAW/JPEG hierarchy."""

import os
import shutil
import time
import re
from typing import List, Dict, Any
from PySide6.QtCore import QThread, Signal
from loupe.models import Project, PhotoItem

def sanitize_folder_name(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "_", name).strip()
    return s if s else "Exported_Project"

class ExportWorker(QThread):
    """Background worker for copying photographic files to structured export folders."""
    progress_update = Signal(int, int, float, str)  # copied_files, total_files, speed_mb_s, current_file
    export_finished = Signal(dict)                  # summary_dict
    export_failed = Signal(str)                     # error_message

    def __init__(self, project: Project, destination_root: str, separate_by_workspace: bool = True, parent=None):
        super().__init__(parent)
        self.project = project
        self.destination_root = destination_root
        self.separate_by_workspace = separate_by_workspace
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            proj_folder_name = sanitize_folder_name(self.project.name)
            if self.separate_by_workspace:
                ws_name = sanitize_folder_name(self.project.get_workspace_name())
                base_dir = os.path.join(self.destination_root, ws_name, proj_folder_name)
            else:
                base_dir = os.path.join(self.destination_root, proj_folder_name)
            
            selected_raw = os.path.join(base_dir, "Selected", "RAW")
            selected_jpeg = os.path.join(base_dir, "Selected", "JPEG")
            maybe_raw = os.path.join(base_dir, "Maybe", "RAW")
            maybe_jpeg = os.path.join(base_dir, "Maybe", "JPEG")
            unselected_raw = os.path.join(base_dir, "Unselected", "RAW")
            unselected_jpeg = os.path.join(base_dir, "Unselected", "JPEG")

            # Collect all operations: list of (src_path, dst_dir)
            fmt_mode = getattr(self.project, "format_mode", "both")
            include_raw = fmt_mode in ("both", "raw_only")
            include_jpeg = fmt_mode in ("both", "jpeg_only")

            tasks = []
            for item in self.project.items:
                if item.status in ("kept", "selected"):
                    target_raw_dir = selected_raw
                    target_jpeg_dir = selected_jpeg
                elif item.status in ("maybe", "similar"):
                    target_raw_dir = maybe_raw
                    target_jpeg_dir = maybe_jpeg
                else:
                    target_raw_dir = unselected_raw
                    target_jpeg_dir = unselected_jpeg

                if include_raw and item.raw_path and os.path.exists(item.raw_path):
                    tasks.append((item.raw_path, target_raw_dir))
                if include_jpeg and item.jpeg_path and os.path.exists(item.jpeg_path):
                    tasks.append((item.jpeg_path, target_jpeg_dir))

            # Include any 'edited result' Lightroom photos if present
            edited_dest_dir = os.path.join(base_dir, "edited result")
            if self.project.edited_files:
                for ef in self.project.edited_files:
                    if ef and os.path.exists(ef):
                        tasks.append((ef, edited_dest_dir))
            elif self.project.edited_result_dir and os.path.exists(self.project.edited_result_dir):
                try:
                    for f in os.listdir(self.project.edited_result_dir):
                        fp = os.path.join(self.project.edited_result_dir, f)
                        if os.path.isfile(fp):
                            tasks.append((fp, edited_dest_dir))
                except Exception:
                    pass

            total_files = len(tasks)
            if total_files == 0:
                self.export_finished.emit({
                    "base_dir": base_dir,
                    "total_copied": 0,
                    "selected_count": 0,
                    "maybe_count": 0,
                    "unselected_count": 0,
                })
                return

            # Ensure all destination directories that have tasks exist
            dst_dirs = set(d for _, d in tasks)
            for d in dst_dirs:
                os.makedirs(d, exist_ok=True)

            copied_count = 0
            bytes_copied = 0
            start_time = time.perf_counter()

            for src, dst_folder in tasks:
                if self._is_cancelled:
                    self.export_failed.emit("Export cancelled by user.")
                    return

                fname = os.path.basename(src)
                dst_path = os.path.join(dst_folder, fname)

                # Copy file non-destructively preserving metadata
                shutil.copy2(src, dst_path)
                copied_count += 1
                try:
                    bytes_copied += os.path.getsize(src)
                except Exception:
                    pass

                elapsed = max(0.01, time.perf_counter() - start_time)
                speed_mb_s = (bytes_copied / (1024 * 1024)) / elapsed

                self.progress_update.emit(copied_count, total_files, speed_mb_s, fname)

            self.export_finished.emit({
                "base_dir": base_dir,
                "total_copied": copied_count,
                "selected_count": self.project.kept_count,
                "maybe_count": self.project.maybe_count,
                "unselected_count": self.project.rejected_count + self.project.pending_count,
            })

        except Exception as e:
            self.export_failed.emit(f"Export error: {str(e)}")
