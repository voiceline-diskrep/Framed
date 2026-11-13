"""Comprehensive unit tests for VRAM/Mixed allocation, GPU detection, and 10-photo Sort Now."""

import copy
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

# Ensure headless offscreen platform for Qt before importing QtGui/QtWidgets
os.environ["QT_QPA_PLATFORM"] = "offscreen"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from loupe.config import config, ConfigManager
from loupe.core.gpu_info import GPUInfo, detect_gpu_vram, format_memory_mb, get_total_vram_gb
from loupe.core.preloader import PreloadManager, prioritize_indices
from loupe.core.vram_cache import VRAMTextureCache
from loupe.models import PhotoItem, Project
from loupe.ui.preload_overlay import PreloadOverlay
from loupe.ui.review_view import ReviewView
from loupe.ui.session_setup_dialog import SessionSetupView
from loupe.ui.settings_dialog import SettingsDialog
from loupe.ui.theme import get_application_stylesheet, load_application_fonts


class TestVramAndEarlySort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        load_application_fonts()
        cls.app.setStyleSheet(get_application_stylesheet())

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="loupe_vram_test_")
        self._saved_config_snapshot = copy.deepcopy(config._config)

    def tearDown(self):
        config._config = copy.deepcopy(self._saved_config_snapshot)
        config.save()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @staticmethod
    def _make_dummy_qimage(width: int = 100, height: int = 100) -> QImage:
        img = QImage(width, height, QImage.Format_RGB888)
        img.fill(0x336699)
        return img

    def _create_sample_jpegs(self, count: int, size=(160, 120)):
        items = []
        for i in range(count):
            path = os.path.join(self.temp_dir, f"DSC_{i:04d}.JPG")
            Image.new("RGB", size, color=((i * 29) % 255, (i * 53) % 255, (i * 89) % 255)).save(
                path, "JPEG", quality=85
            )
            items.append(PhotoItem(base_name=f"DSC_{i:04d}", jpeg_path=path, primary_path=path))
        return items

    # ------------------------------------------------------------------
    # 1. GPU Info Detection
    # ------------------------------------------------------------------
    def test_gpu_info_detection_and_graceful_fallback(self):
        """Verify detect_gpu_vram returns valid GPUInfo and degrades gracefully on failure."""
        info = detect_gpu_vram()
        self.assertIsInstance(info, GPUInfo)
        self.assertIsInstance(info.name, str)
        self.assertTrue(len(info.name) > 0)
        self.assertIsInstance(info.total_vram_mb, int)
        self.assertIsInstance(info.available_vram_mb, int)
        self.assertIsInstance(info.is_dedicated, bool)
        self.assertGreaterEqual(info.total_vram_mb, 0)
        self.assertGreaterEqual(info.available_vram_mb, 0)
        self.assertLessEqual(info.available_vram_mb, info.total_vram_mb)

        self.assertIsInstance(get_total_vram_gb(), int)
        self.assertEqual(format_memory_mb(8192), "8 GB (8,192 MB)")
        self.assertEqual(format_memory_mb(512), "512 MB")

        # Simulate all platform detectors failing -> safe non-crashing fallback
        with (
            patch("loupe.core.gpu_info._detect_via_windows_registry", side_effect=OSError("no reg")),
            patch("loupe.core.gpu_info._detect_via_dxgi", side_effect=RuntimeError("no dxgi")),
            patch("loupe.core.gpu_info._detect_via_cim", return_value=None),
        ):
            fallback = detect_gpu_vram()
            self.assertIsInstance(fallback, GPUInfo)
            self.assertEqual(fallback.total_vram_mb, 0)
            self.assertEqual(fallback.available_vram_mb, 0)
            self.assertFalse(fallback.is_dedicated)
            self.assertIn("Fallback", fallback.name)
            self.assertEqual(get_total_vram_gb(), 0)

    # ------------------------------------------------------------------
    # 2. SessionSetupView Memory Mode Toggling, VRAM Slider & RAM Scaling
    # ------------------------------------------------------------------
    def test_session_setup_memory_modes_and_ram_scaling(self):
        """Verify RAM/VRAM/Mixed toggling, VRAM slider range & math, and legacy RAM scaling."""
        fake_gpu = GPUInfo(
            name="AMD Radeon RX 6600",
            total_vram_mb=8192,
            available_vram_mb=7168,
            is_dedicated=True,
        )
        with patch("loupe.ui.session_setup_dialog.detect_gpu_vram", return_value=fake_gpu):
            view = SessionSetupView()

        # Verify detected GPU text appears
        self.assertIn("AMD Radeon RX 6600", view.hw_info_lbl.text())
        self.assertEqual(view.vram_slider.minimum(), 512)
        self.assertEqual(view.vram_slider.maximum(), 8192)

        # Preserve existing RAM scaling behavior
        view.set_memory_mode("ram")
        self.assertFalse(view.ram_row_widget.isHidden())
        self.assertTrue(view.vram_row_widget.isHidden())
        view._update_batch_calc(8192)
        self.assertEqual(view.calculated_batch_size, 109)
        view._update_batch_calc(16384)
        self.assertEqual(view.calculated_batch_size, 218)

        # Toggle to VRAM mode
        view.set_memory_mode("vram")
        self.assertTrue(view.ram_row_widget.isHidden())
        self.assertFalse(view.vram_row_widget.isHidden())
        view.vram_slider.setValue(4096)  # 4096 // 75 = 54 photos
        self.assertEqual(view.calculated_batch_size, 54)
        self.assertIn("VRAM buffer:", view.batch_calc_lbl.text())
        self.assertIn("54 photos", view.batch_calc_lbl.text())

        # Toggle to Mixed mode
        view.set_memory_mode("mixed")
        self.assertFalse(view.ram_row_widget.isHidden())
        self.assertFalse(view.vram_row_widget.isHidden())
        view.ram_slider.setValue(8192)   # 109 photos
        view.vram_slider.setValue(4096)  # 54 photos
        self.assertEqual(view.calculated_batch_size, 163)
        self.assertIn("Mixed buffer:", view.batch_calc_lbl.text())
        self.assertIn("163 photos total", view.batch_calc_lbl.text())

        # Verify _start_session creates Project with selected mode & allocations
        sample_dir = os.path.join(self.temp_dir, "shoot")
        os.makedirs(sample_dir, exist_ok=True)
        img_path = os.path.join(sample_dir, "IMG_0001.JPG")
        Image.new("RGB", (64, 64), color=(10, 20, 30)).save(img_path, "JPEG")
        view.source_dir_edit.setText(sample_dir)
        view.set_memory_mode("mixed")
        view.ram_slider.setValue(4096)
        view.vram_slider.setValue(2048)

        created_ids = []
        view.session_created.connect(lambda pid: created_ids.append(pid))
        view._start_session()
        self.assertIsNotNone(view.created_project)
        self.assertEqual(view.created_project.memory_mode, "mixed")
        self.assertEqual(view.created_project.ram_allocation_mb, 4096)
        self.assertEqual(view.created_project.vram_allocation_mb, 2048)
        self.assertEqual(len(created_ids), 1)
        view.close()

    # ------------------------------------------------------------------
    # 3. SettingsDialog Save/Load of default_memory_mode & vram_budget_gb
    # ------------------------------------------------------------------
    def test_settings_dialog_memory_mode_and_vram_budget(self):
        """Verify SettingsDialog loads and saves default_memory_mode and vram_budget_gb."""
        fake_gpu = GPUInfo(
            name="NVIDIA GeForce RTX 4070",
            total_vram_mb=12288,
            available_vram_mb=11264,
            is_dedicated=True,
        )
        config.set("default_memory_mode", "mixed")
        config.set("vram_budget_gb", 8)

        with (
            patch("loupe.ui.settings_dialog.detect_gpu_vram", return_value=fake_gpu),
            patch("loupe.ui.settings_dialog.get_total_vram_gb", return_value=12),
        ):
            dlg = SettingsDialog()
            self.assertEqual(dlg._get_memory_mode(), "mixed")
            self.assertEqual(dlg.vram_slider.value(), 8)
            self.assertEqual(dlg.vram_val_lbl.text(), "8 GB")

            # Change to VRAM and 6 GB, save, and verify config persistence
            dlg.set_memory_mode("vram")
            dlg.vram_slider.setValue(6)
            dlg._save_values()
            dlg.close()

        self.assertEqual(config.get("default_memory_mode"), "vram")
        self.assertEqual(config.get("vram_budget_gb"), 6)

        # Verify ConfigManager defaults include keys cleanly
        cm = ConfigManager()
        self.assertIn("default_memory_mode", cm._config)
        self.assertIn("vram_budget_gb", cm._config)

    # ------------------------------------------------------------------
    # 4. PreloadManager 3-Mode Caching, Priority Ordering, Eviction & Stats
    # ------------------------------------------------------------------
    def test_preloader_priority_and_3_mode_caching(self):
        """Verify first-10 priority ordering, 3-mode eviction, and cache_stats_changed telemetry."""
        # Priority ordering helper puts first 10 frames starting at target_index first
        ordered = prioritize_indices(list(range(25)), target_index=12, direction=1, window=10)
        self.assertEqual(ordered[:10], list(range(12, 22)))
        self.assertEqual(len(ordered), 25)

        items = [PhotoItem(base_name=f"P_{i:03d}", primary_path=f"p_{i}.jpg") for i in range(25)]
        qimg = self._make_dummy_qimage(256, 256)

        # A. RAM mode: eviction respects max_cached when total items > max_cached
        pm_ram = PreloadManager()
        stats_events = []
        pm_ram.cache_stats_changed.connect(lambda *args: stats_events.append(args))
        pm_ram.initialize_session(items, batch_size=4, start_index=10, ram_allocation_mb=150, memory_mode="ram")
        # batch_size=4 -> max_cached = max(4*3, 150//75) = 12
        for i in range(20):
            pm_ram._on_photo_loaded(i, qimg)
        self.assertEqual(len(pm_ram._cache), 12)
        self.assertTrue(pm_ram.is_cached(10))
        self.assertFalse(pm_ram.is_cached(0))  # Furthest from current_index=10 evicted
        self.assertGreater(len(stats_events), 0)
        last_stats = stats_events[-1]
        self.assertEqual(last_stats[2], 12)  # total_cached
        self.assertEqual(last_stats[3], 0)   # vram_count
        self.assertEqual(last_stats[4], 12)  # ram_count
        pm_ram.cleanup()

        # B. VRAM mode: stores in vram_cache (fallback in headless), keeps CPU _cache empty, evicts furthest
        pm_vram = PreloadManager()
        vram_stats = []
        pm_vram.cache_stats_changed.connect(lambda *args: vram_stats.append(args))
        # vram_allocation_mb=375 with avg_photo_mb=75 -> capacity = 5 photos
        pm_vram.initialize_session(
            items, batch_size=4, start_index=10, memory_mode="vram", vram_allocation_mb=375, avg_photo_mb=75
        )
        for i in range(15):
            pm_vram._on_photo_loaded(i, qimg)
        self.assertEqual(pm_vram.vram_cache.count, 5)
        self.assertEqual(len(pm_vram._cache), 0)
        self.assertTrue(pm_vram.is_cached(10))
        self.assertIsNotNone(pm_vram.get_vram_entry(10))
        self.assertFalse(pm_vram.is_cached(0))
        self.assertEqual(vram_stats[-1][3], 5)  # vram_count
        self.assertEqual(vram_stats[-1][4], 0)  # ram_count
        pm_vram.cleanup()

        # C. Mixed mode: closest frames stay in VRAM, overflow stays in CPU RAM, total bounded
        pm_mixed = PreloadManager()
        mixed_stats = []
        pm_mixed.cache_stats_changed.connect(lambda *args: mixed_stats.append(args))
        # vram=225 MB (3 photos), ram=300 MB (4 photos) -> 3 VRAM + 4 RAM = 7 cached
        pm_mixed.initialize_session(
            items,
            batch_size=4,
            start_index=10,
            ram_allocation_mb=300,
            memory_mode="mixed",
            vram_allocation_mb=225,
            avg_photo_mb=75,
        )
        for i in range(15):
            pm_mixed._on_photo_loaded(i, qimg)
        self.assertEqual(pm_mixed.vram_cache.count, 3)
        self.assertEqual(len(pm_mixed._cache), 4)
        self.assertTrue(pm_mixed.vram_cache.has(10))  # Hot frame around current_index in VRAM
        self.assertEqual(mixed_stats[-1][2], 7)
        self.assertEqual(mixed_stats[-1][3], 3)
        self.assertEqual(mixed_stats[-1][4], 4)
        pm_mixed.cleanup()

    def test_vram_texture_cache_headless_accounting(self):
        """Verify VRAMTextureCache accurate RGBA8 byte accounting and release/clear in offscreen mode."""
        cache = VRAMTextureCache()
        self.assertFalse(cache.is_gl_supported)
        qimg = self._make_dummy_qimage(100, 50)
        self.assertTrue(cache.upload(0, qimg))
        self.assertTrue(cache.has(0))
        self.assertEqual(cache.count, 1)
        self.assertEqual(cache.used_bytes, 100 * 50 * 4)
        freed = cache.release(0)
        self.assertEqual(freed, 100 * 50 * 4)
        self.assertEqual(cache.count, 0)
        self.assertEqual(cache.used_bytes, 0)

    # ------------------------------------------------------------------
    # 5. PreloadOverlay 10-Photo "Sort Now" Gate, Auto-Start & Filename Fix
    # ------------------------------------------------------------------
    def test_preload_overlay_sort_now_gate_and_filename_fix(self):
        """Verify 10-photo gate for >=10 and <10 sessions, auto-start checkbox, and filename label update."""
        overlay = PreloadOverlay()
        sort_clicks = []
        overlay.sort_now_requested.connect(lambda: sort_clicks.append(True))

        # A. Session >= 10 photos (25 photos): locked below 10, unlocked at 10
        overlay.set_batch_info(0, 24, 0, total_items=25, memory_mode="vram")
        self.assertEqual(overlay.memory_mode_lbl.text(), "GPU VRAM")
        self.assertFalse(overlay.btn_sort_now.isEnabled())
        self.assertIn("0/10", overlay.btn_sort_now.text())

        overlay.update_progress(9, 25, 120.0, 2.0, "DSC_0009.ARW")
        self.assertFalse(overlay.btn_sort_now.isEnabled())
        self.assertIn("9/10", overlay.btn_sort_now.text())
        self.assertIn("DSC_0009.ARW", overlay.file_lbl.text())

        overlay.update_progress(10, 25, 135.0, 1.5, "DSC_0010.ARW")
        self.assertTrue(overlay.btn_sort_now.isEnabled())
        self.assertIn("10 Ready", overlay.btn_sort_now.text())
        self.assertIn("DSC_0010.ARW", overlay.file_lbl.text())

        overlay.btn_sort_now.click()
        self.assertEqual(len(sort_clicks), 1)

        # B. Small session < 10 photos (6 photos): unlocks at 6
        overlay.set_batch_info(0, 5, 0, total_items=6, memory_mode="mixed")
        self.assertIn("MIXED", overlay.memory_mode_lbl.text())
        overlay.update_progress(5, 6, 90.0, 0.2, "DSC_0005.JPG")
        self.assertFalse(overlay.btn_sort_now.isEnabled())
        self.assertIn("5/6", overlay.btn_sort_now.text())

        overlay.update_progress(6, 6, 95.0, 0.0, "DSC_0006.JPG")
        self.assertTrue(overlay.btn_sort_now.isEnabled())

        # C. Auto-start checkbox emits sort_now_requested once per batch pause when threshold reached
        overlay.set_batch_info(0, 19, 0, total_items=20, memory_mode="ram")
        sort_clicks.clear()
        overlay.auto_sort_cb.setChecked(True)
        overlay.update_progress(9, 20, 100.0, 1.0, "A.JPG")
        self.assertEqual(len(sort_clicks), 0)
        overlay.update_progress(10, 20, 110.0, 0.9, "B.JPG")
        self.assertEqual(len(sort_clicks), 1)
        overlay.update_progress(11, 20, 112.0, 0.8, "C.JPG")
        self.assertEqual(len(sort_clicks), 1)  # Must not re-emit on subsequent ticks

        # Checking auto-start after threshold is already met triggers immediately once
        overlay.auto_sort_cb.setChecked(False)
        overlay.set_batch_info(0, 19, 0, total_items=20, memory_mode="ram")
        overlay.update_progress(10, 20, 110.0, 0.9, "D.JPG")
        sort_clicks.clear()
        overlay.auto_sort_cb.setChecked(True)
        self.assertEqual(len(sort_clicks), 1)
        overlay.close()

    # ------------------------------------------------------------------
    # 6. ReviewView Early Sort ("Sort Now") & Non-Blocking Background Streaming
    # ------------------------------------------------------------------
    def test_review_view_sort_now_keeps_background_streaming(self):
        """Verify clicking Sort Now at >=10 photos hides overlay while background streaming finishes and updates pill."""
        items = self._create_sample_jpegs(14, size=(120, 90))
        proj = Project(
            name="Early Sort Streaming Test",
            memory_mode="mixed",
            ram_allocation_mb=2048,
            vram_allocation_mb=1024,
            preview_mode="jpeg",
            items=items,
        )

        review = ReviewView()
        review.resize(1200, 800)
        review.load_project(proj)

        # Wait until at least 10 photos are ready (unlocking Sort Now)
        deadline = time.time() + 10.0
        while time.time() < deadline:
            QCoreApplication.processEvents()
            if review.preload_overlay.btn_sort_now.isEnabled():
                break
            time.sleep(0.02)

        self.assertTrue(
            review.preload_overlay.btn_sort_now.isEnabled(),
            "Expected Sort Now button to unlock once >=10 photos decoded.",
        )

        # Click Sort Now immediately
        review.preload_overlay.btn_sort_now.click()
        QCoreApplication.processEvents()

        self.assertFalse(review.is_preloading_paused)
        self.assertTrue(review.preload_overlay.isHidden())
        self.assertFalse(review.buffer_status_lbl.isHidden())

        # Background worker must finish streaming all 14 items cleanly
        deadline = time.time() + 10.0
        while time.time() < deadline:
            QCoreApplication.processEvents()
            if review.preload_manager.get_ready_count() == 14 and not review.preload_manager.is_streaming:
                break
            time.sleep(0.02)

        self.assertEqual(review.preload_manager.get_ready_count(), 14)
        self.assertFalse(review.preload_manager.is_streaming)
        self.assertIn("Buffered 14/14", review.buffer_status_lbl.text())

        review.unload_project()
        review.close()

    def test_canvas_full_viewport_update_and_theme_background(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QGraphicsView
        from loupe.ui.theme import apply_theme, THEMES
        import loupe.ui.theme as theme_mod

        review = ReviewView()
        canvas = review.canvas
        self.assertEqual(canvas.viewportUpdateMode(), QGraphicsView.FullViewportUpdate)
        self.assertNotEqual(canvas.backgroundBrush().style(), Qt.NoBrush)
        self.assertNotEqual(canvas.scene.backgroundBrush().style(), Qt.NoBrush)

        original = theme_mod.current_theme_id
        try:
            apply_theme("light")
            expected = THEMES["light"].colors["COLOR_BG_BASE"].lower()
            self.assertEqual(canvas.backgroundBrush().color().name().lower(), expected)
            self.assertEqual(canvas.scene.backgroundBrush().color().name().lower(), expected)
        finally:
            apply_theme(original)
        review.close()

    def test_vram_item_binds_int_gl_target(self):
        from unittest.mock import MagicMock
        from PySide6.QtGui import QPainter
        from loupe.core.vram_cache import VRAMTextureEntry
        import loupe.ui.review_view as rv

        class _Target:
            value = 3553

        tex = MagicMock()
        tex.isCreated.return_value = True
        tex.target.return_value = _Target()
        tex.textureId.return_value = 7
        blitter = MagicMock()
        blitter.isCreated.return_value = True
        entry = VRAMTextureEntry(index=0, texture=tex, width=10, height=10, bytes_used=400)
        item = rv.VRAMTextureGraphicsItem(entry, blitter_getter=lambda: blitter)

        img = QImage(20, 20, QImage.Format_ARGB32)
        painter = QPainter(img)
        widget = MagicMock()
        from PySide6.QtCore import QRect
        widget.rect.return_value = QRect(0, 0, 20, 20)
        with patch.object(rv.QOpenGLContext, "currentContext", return_value=object()):
            item.paint(painter, None, widget)
        painter.end()

        blitter.bind.assert_called_once_with(3553)
        self.assertIsInstance(blitter.bind.call_args[0][0], int)

if __name__ == "__main__":
    unittest.main()
