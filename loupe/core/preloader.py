"""Preloading manager with background thread, batch boundary detection, speed (MB/s), and ETA calculation."""

import os
import time
from typing import Dict, List, Optional, Set, Tuple
from collections import deque
from PySide6.QtCore import QObject, Signal, QThread, QMutex, QMutexLocker
from PySide6.QtGui import QImage
from loupe.models import PhotoItem
from loupe.core.decoder import ImageDecoder

class PreloadWorker(QThread):
    """Background worker for decoding photos into QImage buffers without blocking the UI."""
    photo_loaded = Signal(int, QImage)  # index, qimage
    progress_update = Signal(int, int, float, float, str)  # loaded_in_batch, total_in_batch, speed_mb_s, eta_sec, filename
    batch_done = Signal(int)  # batch_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mutex = QMutex()
        self._is_running = True
        self.items: List[PhotoItem] = []
        self.queue: deque = deque()
        self.current_batch_id: int = 0
        self.batch_total: int = 0
        self.batch_completed: int = 0
        self.batch_bytes_total: int = 0
        self.batch_bytes_loaded: int = 0
        self.batch_start_time: float = 0.0

    def stop(self):
        with QMutexLocker(self.mutex):
            self._is_running = False
            self.queue.clear()
        self.wait(1500)

    def ensure_running(self):
        with QMutexLocker(self.mutex):
            self._is_running = True
        if not self.isRunning():
            self.start()

    def set_batch_tasks(self, batch_id: int, indices: List[int], items: List[PhotoItem]):
        self.ensure_running()
        with QMutexLocker(self.mutex):
            self.items = items
            self.current_batch_id = batch_id
            self.queue.clear()
            self.batch_total = len(indices)
            self.batch_completed = 0
            self.batch_bytes_loaded = 0
            self.batch_start_time = time.perf_counter()

            # Calculate total bytes in this batch
            total_b = 0
            for idx in indices:
                if 0 <= idx < len(items):
                    p = items[idx].primary_path
                    if p and os.path.exists(p):
                        total_b += os.path.getsize(p)
                self.queue.append(idx)
            self.batch_bytes_total = max(1, total_b)

    def run(self):
        while True:
            with QMutexLocker(self.mutex):
                if not self._is_running:
                    break
                if not self.queue:
                    target_idx = None
                else:
                    target_idx = self.queue.popleft()

            if target_idx is None:
                self.msleep(30)
                continue

            if 0 <= target_idx < len(self.items):
                item = self.items[target_idx]
                filepath = item.primary_path
                file_size = os.path.getsize(filepath) if filepath and os.path.exists(filepath) else 1024 * 1024
                
                # Decode image at full resolution
                qimg, _ = ImageDecoder.decode_to_qimage(filepath)
                if qimg and not qimg.isNull():
                    self.photo_loaded.emit(target_idx, qimg)

                with QMutexLocker(self.mutex):
                    self.batch_completed += 1
                    self.batch_bytes_loaded += file_size
                    elapsed = max(0.01, time.perf_counter() - self.batch_start_time)
                    speed_mb_s = (self.batch_bytes_loaded / (1024 * 1024)) / elapsed
                    remaining_bytes = max(0, self.batch_bytes_total - self.batch_bytes_loaded)
                    eta_sec = (remaining_bytes / (speed_mb_s * 1024 * 1024)) if speed_mb_s > 0.05 else 0.0
                    
                    completed = self.batch_completed
                    total = self.batch_total
                    batch_id = self.current_batch_id
                    filename = os.path.basename(filepath) if filepath else ""

                self.progress_update.emit(completed, total, speed_mb_s, eta_sec, filename)

                if completed >= total:
                    self.batch_done.emit(batch_id)


class PreloadManager(QObject):
    """Manages the photo buffer, prefetching, and batch pausing."""
    image_ready = Signal(int, QImage)
    pause_needed = Signal(int, int, int)  # target_idx, batch_start, batch_end
    batch_progress = Signal(int, int, float, float, str)
    batch_completed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: List[PhotoItem] = []
        self.batch_size: int = 16
        self.current_index: int = 0
        self.direction: int = 1  # +1 for forward, -1 for backward
        self._cache: Dict[int, QImage] = {}
        self.loaded_batches: Set[int] = set()
        self._worker = PreloadWorker(self)
        self._worker.photo_loaded.connect(self._on_photo_loaded)
        self._worker.progress_update.connect(self._on_progress_update)
        self._worker.batch_done.connect(self._on_batch_done)
        self._worker.start()

    def cleanup(self):
        if self._worker:
            self._worker.stop()
        self._cache.clear()
        self.loaded_batches.clear()

    def initialize_session(self, items: List[PhotoItem], batch_size: int = 16, start_index: int = 0):
        self.items = items
        self.batch_size = max(4, batch_size)
        self.current_index = start_index
        self._cache.clear()
        self.loaded_batches.clear()
        if self._worker:
            self._worker.ensure_running()

    def preload_batch_sync(self, batch_id: int):
        """Synchronously load a batch of photos into cache (used for immediate tests and startup)."""
        b_start = batch_id * self.batch_size
        b_end = min(len(self.items) - 1, b_start + self.batch_size - 1)
        for i in range(b_start, b_end + 1):
            if i not in self._cache and 0 <= i < len(self.items):
                p = self.items[i].primary_path
                qimg, _ = ImageDecoder.decode_to_qimage(p)
                if qimg and not qimg.isNull():
                    self._cache[i] = qimg
        self.loaded_batches.add(batch_id)

    def is_cached(self, index: int) -> bool:
        return index in self._cache and not self._cache[index].isNull()

    def get_image(self, index: int) -> Optional[QImage]:
        return self._cache.get(index)

    def request_batch(self, batch_index: int, indices: List[int]):
        # Filter out already cached indices
        needed = [i for i in indices if i not in self._cache]
        if not needed:
            self.batch_completed.emit(batch_index)
            return
        self._worker.ensure_running()
        self._worker.set_batch_tasks(batch_index, needed, self.items)

    def check_navigation(self, target_index: int, direction: int = 1) -> Tuple[bool, int, int]:
        """
        Check if navigating to target_index requires a batch pause.
        Returns: (needs_pause, batch_start, batch_end)
        """
        self.direction = direction
        self.current_index = target_index

        if not (0 <= target_index < len(self.items)):
            return False, 0, 0

        # Determine which batch block target_index belongs to
        batch_id = target_index // self.batch_size
        batch_start = batch_id * self.batch_size
        batch_end = min(len(self.items) - 1, batch_start + self.batch_size - 1)

        # If target image is not cached, we MUST pause to load this batch
        if not self.is_cached(target_index):
            batch_indices = list(range(batch_start, batch_end + 1))
            self.request_batch(batch_id, batch_indices)
            return True, batch_start, batch_end

        # If it is cached, preload next batch in the moving direction in background!
        self._schedule_background_prefetch(target_index, direction)
        return False, batch_start, batch_end

    def _schedule_background_prefetch(self, current_idx: int, direction: int):
        """Prefetch subsequent photos in direction of navigation."""
        prefetch_indices = []
        if direction >= 0:
            for i in range(current_idx + 1, min(len(self.items), current_idx + self.batch_size + 1)):
                if i not in self._cache:
                    prefetch_indices.append(i)
        else:
            for i in range(current_idx - 1, max(-1, current_idx - self.batch_size - 1), -1):
                if i not in self._cache:
                    prefetch_indices.append(i)

        if prefetch_indices:
            batch_id = current_idx // self.batch_size
            self._worker.set_batch_tasks(batch_id + 1000, prefetch_indices, self.items)

    def _on_photo_loaded(self, index: int, qimage: QImage):
        self._cache[index] = qimage
        self.image_ready.emit(index, qimage)
        # Evict photos further than 3 batches away to respect memory limits
        self._enforce_cache_limits()

    def _on_progress_update(self, completed: int, total: int, speed: float, eta: float, fname: str):
        self.batch_progress.emit(completed, total, speed, eta, fname)

    def _on_batch_done(self, batch_id: int):
        self.loaded_batches.add(batch_id)
        self.batch_completed.emit(batch_id)

    def _enforce_cache_limits(self):
        max_cached = self.batch_size * 3
        if len(self._cache) > max_cached:
            # Sort keys by distance from current_index
            sorted_keys = sorted(self._cache.keys(), key=lambda idx: abs(idx - self.current_index), reverse=True)
            to_remove = sorted_keys[: len(self._cache) - max_cached]
            for k in to_remove:
                del self._cache[k]
