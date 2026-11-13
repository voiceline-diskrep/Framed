"""Preloading manager with parallel background decoding, 3-tier RAM/VRAM/Mixed caching, speed, and ETA."""

from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import os
import time
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, Signal
from PySide6.QtGui import QImage

from loupe.core.decoder import ImageDecoder
from loupe.core.vram_cache import VRAMTextureCache, VRAMTextureEntry
from loupe.models import PhotoItem


def _default_worker_count() -> int:
    return min(4, max(2, (os.cpu_count() or 4) // 2))


def prioritize_indices(indices: List[int], target_index: int, direction: int = 1, window: int = 10) -> List[int]:
    """Place up to `window` indices starting at `target_index` in `direction` at the front of `indices`."""
    if not indices:
        return []
    index_set = set(indices)
    step = 1 if direction >= 0 else -1
    front: List[int] = []
    front_set: Set[int] = set()
    for offset in range(window):
        candidate = target_index + offset * step
        if candidate in index_set and candidate not in front_set:
            front.append(candidate)
            front_set.add(candidate)
    rest = [i for i in indices if i not in front_set]
    return front + rest


class PreloadWorker(QThread):
    """Background worker using a thread pool to decode photos into QImage buffers without blocking the UI."""

    photo_loaded = Signal(int, int, QImage)  # generation, index, qimage
    progress_update = Signal(int, int, int, float, float, str)  # generation, loaded_in_batch, total_in_batch, speed_mb_s, eta_sec, filename
    batch_done = Signal(int, int)  # generation, batch_index

    def __init__(self, parent=None, max_workers: Optional[int] = None):
        super().__init__(parent)
        self.mutex = QMutex()
        self._is_running = True
        self._max_workers = max(1, int(max_workers or _default_worker_count()))
        self.current_generation: int = 0
        self._batch_seq: int = 0
        self.items: List[PhotoItem] = []
        self.queue: deque = deque()
        self._in_flight_indices: Set[int] = set()
        self.current_batch_id: int = 0
        self.batch_total: int = 0
        self.batch_completed: int = 0
        self.batch_bytes_total: int = 0
        self.batch_bytes_loaded: int = 0
        self.batch_start_time: float = 0.0

    def stop(self):
        with QMutexLocker(self.mutex):
            self._is_running = False
            self.current_generation += 1  # Invalidate in-flight tasks immediately
            self._batch_seq += 1
            self.queue.clear()
            self._in_flight_indices.clear()
        self.wait(1500)

    def ensure_running(self):
        with QMutexLocker(self.mutex):
            self._is_running = True
        if not self.isRunning():
            self.start()

    def has_pending_tasks(self, generation: int) -> bool:
        with QMutexLocker(self.mutex):
            if generation != self.current_generation:
                return False
            return bool(self.queue) or bool(self._in_flight_indices)

    def set_batch_tasks(
        self,
        generation: int,
        batch_id: int,
        indices: List[int],
        items: List[PhotoItem],
        priority_index: Optional[int] = None,
    ):
        self.ensure_running()
        ordered = (
            prioritize_indices(indices, priority_index)
            if priority_index is not None
            else list(indices)
        )
        with QMutexLocker(self.mutex):
            self.current_generation = generation
            self._batch_seq += 1
            self.items = items
            self.current_batch_id = batch_id
            self.queue.clear()
            self._in_flight_indices.clear()
            self.batch_total = len(ordered)
            self.batch_completed = 0
            self.batch_bytes_loaded = 0
            self.batch_start_time = time.perf_counter()

            total_b = 0
            for idx in ordered:
                if 0 <= idx < len(items):
                    p = items[idx].primary_path
                    if p and os.path.exists(p):
                        total_b += os.path.getsize(p)
                self.queue.append(idx)
            self.batch_bytes_total = max(1, total_b)

    def reprioritize(self, generation: int, priority_indices: List[int]) -> bool:
        """Move `priority_indices` to the front of the active queue for `generation`."""
        with QMutexLocker(self.mutex):
            if generation != self.current_generation or not self._is_running:
                return False
            if not self.queue and not self._in_flight_indices:
                return False

            current_q = list(self.queue)
            queued_set = set(current_q)
            prioritized_front: List[int] = []
            front_set: Set[int] = set()

            for idx in priority_indices:
                if idx in front_set:
                    continue
                if idx in queued_set:
                    prioritized_front.append(idx)
                    front_set.add(idx)
                elif idx not in self._in_flight_indices and 0 <= idx < len(self.items):
                    prioritized_front.append(idx)
                    front_set.add(idx)
                    self.batch_total += 1
                    p = self.items[idx].primary_path
                    if p and os.path.exists(p):
                        self.batch_bytes_total += os.path.getsize(p)

            remaining = [i for i in current_q if i not in front_set]
            self.queue = deque(prioritized_front + remaining)
            return True

    @staticmethod
    def _decode_task(filepath: str) -> Optional[QImage]:
        qimg, _ = ImageDecoder.decode_to_qimage(filepath)
        return qimg

    def run(self):
        in_flight: Dict[Future, Tuple[int, int, int, str, int]] = {}
        executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="LoupeDecode")
        try:
            while True:
                # Submit new tasks up to _max_workers
                with QMutexLocker(self.mutex):
                    if not self._is_running:
                        break
                    cur_gen = self.current_generation
                    cur_seq = self._batch_seq
                    items_ref = self.items

                    # Drop tracking for stale in-flight futures on generation/batch change
                    stale_keys = [
                        fut for fut, meta in in_flight.items()
                        if meta[0] != cur_gen or meta[1] != cur_seq
                    ]
                    for fut in stale_keys:
                        _, _, old_idx, _, _ = in_flight.pop(fut)
                        self._in_flight_indices.discard(old_idx)

                    while len(in_flight) < self._max_workers and self.queue:
                        target_idx = self.queue.popleft()
                        if not (0 <= target_idx < len(items_ref)):
                            self.batch_total = max(0, self.batch_total - 1)
                            continue
                        filepath = items_ref[target_idx].primary_path
                        file_size = (
                            os.path.getsize(filepath)
                            if filepath and os.path.exists(filepath)
                            else 1024 * 1024
                        )
                        self._in_flight_indices.add(target_idx)
                        fut = executor.submit(self._decode_task, filepath)
                        in_flight[fut] = (cur_gen, cur_seq, target_idx, filepath, file_size)

                if not in_flight:
                    self.msleep(20)
                    continue

                done, _ = wait(list(in_flight.keys()), timeout=0.03, return_when=FIRST_COMPLETED)
                if not done:
                    continue

                for fut in done:
                    meta = in_flight.pop(fut, None)
                    if meta is None:
                        continue
                    task_gen, task_seq, target_idx, filepath, file_size = meta
                    try:
                        qimg = fut.result()
                    except Exception:
                        qimg = None

                    emit_payload = None
                    with QMutexLocker(self.mutex):
                        self._in_flight_indices.discard(target_idx)
                        # Strict generation + batch sequence cancellation check
                        if (
                            task_gen != self.current_generation
                            or task_seq != self._batch_seq
                            or not self._is_running
                        ):
                            continue

                        self.batch_completed += 1
                        self.batch_bytes_loaded += file_size
                        elapsed = max(0.01, time.perf_counter() - self.batch_start_time)
                        speed_mb_s = (self.batch_bytes_loaded / (1024 * 1024)) / elapsed
                        remaining_bytes = max(0, self.batch_bytes_total - self.batch_bytes_loaded)
                        eta_sec = (
                            (remaining_bytes / (speed_mb_s * 1024 * 1024))
                            if speed_mb_s > 0.05
                            else 0.0
                        )
                        completed = self.batch_completed
                        total = self.batch_total
                        batch_id = self.current_batch_id
                        filename = os.path.basename(filepath) if filepath else ""
                        emit_payload = (completed, total, speed_mb_s, eta_sec, filename, batch_id)

                    if emit_payload is not None:
                        completed, total, speed_mb_s, eta_sec, filename, batch_id = emit_payload
                        if qimg is not None and not qimg.isNull():
                            self.photo_loaded.emit(task_gen, target_idx, qimg)
                        self.progress_update.emit(task_gen, completed, total, speed_mb_s, eta_sec, filename)
                        if completed >= total:
                            self.batch_done.emit(task_gen, batch_id)
        finally:
            for fut in list(in_flight.keys()):
                fut.cancel()
            executor.shutdown(wait=False, cancel_futures=True)


class PreloadManager(QObject):
    """Manages the 3-tier photo buffer (RAM / VRAM / Mixed), parallel prefetching, and eviction."""

    image_ready = Signal(int, QImage)
    pause_needed = Signal(int, int, int)  # target_idx, batch_start, batch_end
    batch_progress = Signal(int, int, float, float, str)
    batch_completed = Signal(int)
    cache_stats_changed = Signal(int, int, int, int, int)  # ram_used_mb, vram_used_mb, total_cached, vram_count, ram_count

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session_generation: int = 0
        self.items: List[PhotoItem] = []
        self.batch_size: int = 16
        self.ram_allocation_mb: Optional[int] = None
        self.vram_allocation_mb: int = 0
        self.memory_mode: str = "ram"
        self.avg_photo_mb: int = 75
        self.current_index: int = 0
        self.direction: int = 1  # +1 for forward, -1 for backward
        self.is_streaming: bool = False
        self._cache: Dict[int, QImage] = {}
        self.vram_cache: VRAMTextureCache = VRAMTextureCache()
        self.loaded_batches: Set[int] = set()
        self._worker = PreloadWorker(self)
        self._worker.photo_loaded.connect(self._on_photo_loaded)
        self._worker.progress_update.connect(self._on_progress_update)
        self._worker.batch_done.connect(self._on_batch_done)

    def set_gl_context(self, gl_context, gl_surface=None) -> None:
        """Attach or update the OpenGL context used for VRAM texture uploads."""
        self.vram_cache.set_gl_context(gl_context, gl_surface)

    def cleanup(self):
        self.session_generation += 1
        self.is_streaming = False
        if self._worker and self._worker.isRunning():
            self._worker.stop()
        self._cache.clear()
        self.vram_cache.clear()
        self.loaded_batches.clear()
        self._emit_cache_stats()

    def initialize_session(
        self,
        items: List[PhotoItem],
        batch_size: int = 16,
        start_index: int = 0,
        ram_allocation_mb: Optional[int] = None,
        memory_mode: str = "ram",
        vram_allocation_mb: int = 0,
        avg_photo_mb: int = 75,
        gl_context=None,
        gl_surface=None,
    ):
        self.session_generation += 1
        self.items = items
        self.batch_size = max(4, batch_size)
        self.ram_allocation_mb = ram_allocation_mb
        mode = (memory_mode or "ram").strip().lower()
        self.memory_mode = mode if mode in ("ram", "vram", "mixed") else "ram"
        self.vram_allocation_mb = max(0, int(vram_allocation_mb or 0))
        self.avg_photo_mb = max(1, int(avg_photo_mb or 75))
        self.current_index = start_index
        self.is_streaming = False
        self._cache.clear()
        self.vram_cache.clear()
        self.loaded_batches.clear()
        if gl_context is not None or gl_surface is not None:
            self.set_gl_context(gl_context, gl_surface)
        if self._worker:
            self._worker.ensure_running()
        self._emit_cache_stats()

    def preload_batch_sync(self, batch_id: int):
        """Synchronously load a batch of photos into cache (used for immediate tests and startup)."""
        b_start = batch_id * self.batch_size
        b_end = min(len(self.items) - 1, b_start + self.batch_size - 1)
        for i in range(b_start, b_end + 1):
            if not self.is_cached(i) and 0 <= i < len(self.items):
                p = self.items[i].primary_path
                qimg, _ = ImageDecoder.decode_to_qimage(p)
                if qimg and not qimg.isNull():
                    self._store_decoded_image(i, qimg)
        self.loaded_batches.add(batch_id)
        self._enforce_cache_limits()
        self._emit_cache_stats()

    def is_cached(self, index: int) -> bool:
        if self.vram_cache.has(index):
            return True
        return index in self._cache and not self._cache[index].isNull()

    def get_vram_entry(self, index: int) -> Optional[VRAMTextureEntry]:
        return self.vram_cache.get_entry(index)

    def get_image(self, index: int) -> Optional[QImage]:
        qimg = self._cache.get(index)
        if qimg is not None:
            return qimg
        entry = self.vram_cache.get_entry(index)
        if entry is not None and entry.fallback_qimage is not None:
            return entry.fallback_qimage
        return None

    def get_ready_count(self, start_idx: int = 0, end_idx: Optional[int] = None) -> int:
        """Count cached photos in [start_idx .. end_idx] (inclusive, or to end of items when end_idx is None)."""
        if not self.items:
            return 0
        s = max(0, start_idx)
        e = len(self.items) if end_idx is None else min(len(self.items), end_idx + 1)
        return sum(1 for i in range(s, e) if self.is_cached(i))

    def request_batch(self, batch_index: int, indices: List[int], priority_index: Optional[int] = None):
        needed = [i for i in indices if not self.is_cached(i)]
        if not needed:
            self.is_streaming = False
            self.batch_completed.emit(batch_index)
            return
        target = self.current_index if priority_index is None else priority_index
        ordered = prioritize_indices(needed, target, self.direction, window=10)
        self.is_streaming = True
        self._worker.ensure_running()
        self._worker.set_batch_tasks(self.session_generation, batch_index, ordered, self.items)

    def reprioritize_around(self, target_index: int, direction: Optional[int] = None) -> None:
        """Prioritize decoding the 10 frames around `target_index` immediately."""
        self.current_index = target_index
        if direction is not None:
            self.direction = direction

        if not (0 <= target_index < len(self.items)):
            return

        step = 1 if self.direction >= 0 else -1
        priority_window: List[int] = []
        for offset in range(10):
            idx = target_index + offset * step
            if 0 <= idx < len(self.items) and not self.is_cached(idx):
                priority_window.append(idx)

        if self._worker.reprioritize(self.session_generation, priority_window):
            self.is_streaming = True
            return

        if priority_window:
            batch_id = target_index // self.batch_size
            batch_start = batch_id * self.batch_size
            batch_end = min(len(self.items) - 1, batch_start + self.batch_size - 1)
            span_indices = priority_window + [
                i for i in range(batch_start, batch_end + 1)
                if i not in priority_window and not self.is_cached(i)
            ]
            self.request_batch(batch_id, span_indices, priority_index=target_index)

    def check_navigation(self, target_index: int, direction: int = 1) -> Tuple[bool, int, int]:
        """
        Check if navigating to target_index requires a batch pause.
        Returns: (needs_pause, batch_start, batch_end)
        """
        self.direction = direction
        self.current_index = target_index

        if not (0 <= target_index < len(self.items)):
            return False, 0, 0

        batch_id = target_index // self.batch_size
        batch_start = batch_id * self.batch_size
        batch_end = min(len(self.items) - 1, batch_start + self.batch_size - 1)

        if not self.is_cached(target_index):
            batch_indices = list(range(batch_start, batch_end + 1))
            self.request_batch(batch_id, batch_indices, priority_index=target_index)
            return True, batch_start, batch_end

        if not self.is_streaming:
            self._schedule_background_prefetch(target_index, direction)
        return False, batch_start, batch_end

    def _schedule_background_prefetch(self, current_idx: int, direction: int):
        """Prefetch subsequent photos in direction of navigation."""
        prefetch_indices = []
        if direction >= 0:
            for i in range(current_idx + 1, min(len(self.items), current_idx + self.batch_size + 1)):
                if not self.is_cached(i):
                    prefetch_indices.append(i)
        else:
            for i in range(current_idx - 1, max(-1, current_idx - self.batch_size - 1), -1):
                if not self.is_cached(i):
                    prefetch_indices.append(i)

        if prefetch_indices:
            batch_id = current_idx // self.batch_size
            ordered = prioritize_indices(prefetch_indices, prefetch_indices[0], direction, window=10)
            self.is_streaming = True
            self._worker.ensure_running()
            self._worker.set_batch_tasks(self.session_generation, batch_id + 1000, ordered, self.items)

    def _on_photo_loaded(self, *args):
        # Support both (generation, index, qimage) and legacy test direct calls (index, qimage)
        if len(args) == 3:
            gen, index, qimage = args
            if gen != self.session_generation:
                return
        elif len(args) == 2:
            index, qimage = args
        else:
            return

        self._store_decoded_image(index, qimage)
        self.image_ready.emit(index, qimage)
        self._enforce_cache_limits()
        self._emit_cache_stats()

    def _on_progress_update(self, *args):
        if len(args) == 6:
            gen, completed, total, speed, eta, fname = args
            if gen != self.session_generation:
                return
        elif len(args) == 5:
            completed, total, speed, eta, fname = args
        else:
            return

        self.batch_progress.emit(completed, total, speed, eta, fname)

    def _on_batch_done(self, *args):
        if len(args) == 2:
            gen, batch_id = args
            if gen != self.session_generation:
                return
        elif len(args) == 1:
            batch_id = args[0]
        else:
            return

        self.is_streaming = self._worker.has_pending_tasks(self.session_generation)
        self.loaded_batches.add(batch_id)
        self.batch_completed.emit(batch_id)

    def _ram_capacity_photos(self) -> int:
        if self.ram_allocation_mb and self.ram_allocation_mb > 0:
            ram_cap = max(1, int(self.ram_allocation_mb / self.avg_photo_mb))
            if self.memory_mode == "ram":
                return max(self.batch_size, ram_cap)
            return ram_cap
        return self.batch_size * 3

    def _vram_capacity_photos(self) -> int:
        if self.vram_allocation_mb > 0:
            return max(1, int(self.vram_allocation_mb / self.avg_photo_mb))
        return 0 if self.memory_mode == "mixed" else self.batch_size * 3

    def _store_decoded_image(self, index: int, qimage: QImage) -> None:
        if self.memory_mode == "vram":
            if self.vram_cache.upload(index, qimage):
                self._cache.pop(index, None)
            else:
                self._cache[index] = qimage
            return

        if self.memory_mode == "mixed":
            max_vram = self._vram_capacity_photos()
            vram_limit_bytes = self.vram_allocation_mb * 1024 * 1024 if self.vram_allocation_mb > 0 else 0
            est_bytes = qimage.width() * qimage.height() * 4

            if max_vram > 0:
                fits_vram_count = self.vram_cache.count < max_vram
                fits_vram_bytes = (
                    vram_limit_bytes == 0
                    or self.vram_cache.used_bytes + est_bytes <= vram_limit_bytes
                    or self.vram_cache.count == 0
                )
                if fits_vram_count and fits_vram_bytes:
                    self.vram_cache.upload(index, qimage)
                    self._cache.pop(index, None)
                    return

                vram_keys = self.vram_cache.keys()
                if vram_keys:
                    furthest_vram = max(vram_keys, key=lambda idx: abs(idx - self.current_index))
                    if abs(index - self.current_index) < abs(furthest_vram - self.current_index):
                        demoted = self.vram_cache.get_entry(furthest_vram)
                        if demoted is not None and demoted.fallback_qimage is not None:
                            self._cache[furthest_vram] = demoted.fallback_qimage
                        self.vram_cache.release(furthest_vram)
                        self.vram_cache.upload(index, qimage)
                        self._cache.pop(index, None)
                        return

            self._cache[index] = qimage
            return

        # Default "ram" mode
        self._cache[index] = qimage

    def _enforce_cache_limits(self):
        if self.memory_mode == "ram":
            if self.ram_allocation_mb and self.ram_allocation_mb > 0:
                ram_capacity = max(self.batch_size, int(self.ram_allocation_mb / self.avg_photo_mb))
                max_cached = max(self.batch_size * 3, ram_capacity)
            else:
                max_cached = self.batch_size * 3

            if len(self.items) <= max_cached:
                return

            if len(self._cache) > max_cached:
                sorted_keys = sorted(
                    self._cache.keys(),
                    key=lambda idx: abs(idx - self.current_index),
                    reverse=True,
                )
                for k in sorted_keys[: len(self._cache) - max_cached]:
                    del self._cache[k]
            return

        if self.memory_mode == "vram":
            max_vram = self._vram_capacity_photos()
            vram_limit_bytes = self.vram_allocation_mb * 1024 * 1024 if self.vram_allocation_mb > 0 else 0
            while self.vram_cache.count > max_vram or (
                vram_limit_bytes > 0 and self.vram_cache.used_bytes > vram_limit_bytes and self.vram_cache.count > 1
            ):
                furthest = max(self.vram_cache.keys(), key=lambda idx: abs(idx - self.current_index))
                self.vram_cache.release(furthest)
            return

        # "mixed" mode: enforce VRAM hot tier + RAM overflow tier
        max_vram = self._vram_capacity_photos()
        max_ram = self._ram_capacity_photos()
        vram_limit_bytes = self.vram_allocation_mb * 1024 * 1024 if self.vram_allocation_mb > 0 else 0

        for idx in self.vram_cache.keys():
            self._cache.pop(idx, None)

        while self.vram_cache.count > max_vram or (
            vram_limit_bytes > 0 and self.vram_cache.used_bytes > vram_limit_bytes and self.vram_cache.count > 1
        ):
            vram_keys = self.vram_cache.keys()
            if not vram_keys:
                break
            furthest = max(vram_keys, key=lambda idx: abs(idx - self.current_index))
            entry = self.vram_cache.get_entry(furthest)
            if entry is not None and entry.fallback_qimage is not None and len(self._cache) < max_ram:
                self._cache[furthest] = entry.fallback_qimage
            self.vram_cache.release(furthest)

        if len(self._cache) > max_ram:
            sorted_keys = sorted(
                self._cache.keys(),
                key=lambda idx: abs(idx - self.current_index),
                reverse=True,
            )
            for k in sorted_keys[: len(self._cache) - max_ram]:
                del self._cache[k]

    def _emit_cache_stats(self) -> None:
        ram_bytes = sum(q.sizeInBytes() for q in self._cache.values() if q is not None and not q.isNull())
        ram_used_mb = int(round(ram_bytes / (1024 * 1024)))
        vram_used_mb = int(round(self.vram_cache.used_mb))
        vram_count = self.vram_cache.count
        ram_count = len(self._cache)
        total_cached = len(set(self._cache.keys()) | set(self.vram_cache.keys()))
        self.cache_stats_changed.emit(ram_used_mb, vram_used_mb, total_cached, vram_count, ram_count)
