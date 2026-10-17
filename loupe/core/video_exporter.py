"""Non-destructive video export pipeline: copies clips into Selected, Unselected, and Similar."""

import os
import time
import shutil
from typing import Dict, Any, List
from PySide6.QtCore import QThread, Signal
from loupe.models import Project, PhotoItem
from loupe.core.exporter import sanitize_folder_name

class VideoExportWorker(QThread):
    """Background worker copying videos non-destructively into Selected, Unselected, Similar."""
    progress_changed = Signal(int, int, str, float)  # (current, total, filename, mb_per_sec)
    export_finished = Signal(dict)                  # summary dictionary
    error_occurred = Signal(str)

    def __init__(self, project: Project, destination_root: str, separate_by_workspace: bool = True, parent=None):
        super().__init__(parent)
        self.project = project
        self.dest_root = destination_root
        self.separate_by_workspace = separate_by_workspace
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            folder_name = sanitize_folder_name(self.project.name)
            if self.separate_by_workspace:
                ws_name = sanitize_folder_name(self.project.get_workspace_name())
                base_dir = os.path.join(self.dest_root, ws_name, folder_name)
            else:
                base_dir = os.path.join(self.dest_root, folder_name)

            selected_dir = os.path.join(base_dir, "Selected")
            unselected_dir = os.path.join(base_dir, "Unselected")
            similar_dir = os.path.join(base_dir, "Similar")

            os.makedirs(selected_dir, exist_ok=True)
            os.makedirs(unselected_dir, exist_ok=True)
            os.makedirs(similar_dir, exist_ok=True)

            items_to_export: List[PhotoItem] = [
                i for i in self.project.items if i.primary_path and os.path.exists(i.primary_path)
            ]
            total = len(items_to_export)

            selected_count = 0
            unselected_count = 0
            similar_count = 0
            total_bytes_copied = 0
            start_time = time.time()

            for idx, item in enumerate(items_to_export):
                if self._is_cancelled:
                    break

                fname = os.path.basename(item.primary_path)
                fsize = os.path.getsize(item.primary_path) if os.path.exists(item.primary_path) else 0

                # Determine target folder
                if item.status in ("selected", "kept"):
                    target_dir = selected_dir
                    selected_count += 1
                elif item.status == "similar":
                    target_dir = similar_dir
                    similar_count += 1
                else:  # "unselected", "rejected", or "pending"
                    target_dir = unselected_dir
                    unselected_count += 1

                dest_file = os.path.join(target_dir, fname)

                # Copy file non-destructively
                t0 = time.time()
                shutil.copy2(item.primary_path, dest_file)
                total_bytes_copied += fsize

                dt = max(0.001, time.time() - start_time)
                mb_s = (total_bytes_copied / (1024 * 1024)) / dt

                self.progress_changed.emit(idx + 1, total, fname, mb_s)

            summary = {
                "base_dir": base_dir,
                "selected_dir": selected_dir,
                "unselected_dir": unselected_dir,
                "similar_dir": similar_dir,
                "selected_count": selected_count,
                "unselected_count": unselected_count,
                "similar_count": similar_count,
                "total_exported": selected_count + unselected_count + similar_count,
                "total_bytes": total_bytes_copied,
            }
            self.export_finished.emit(summary)

        except Exception as e:
            self.error_occurred.emit(str(e))
