"""Comprehensive automated tests for Loupe: Models, Storage, EXIF, Decoder, Preloader, Exporter, and UI."""

import os
import sys
import shutil
import tempfile
import unittest

# Ensure headless offscreen platform for Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication
from loupe.config import config, ConfigManager
from loupe.models import Folder, Project, PhotoItem
from loupe.storage import StorageManager
from loupe.core.decoder import ImageDecoder
from loupe.core.metadata import MetadataExtractor
from loupe.core.preloader import PreloadManager
from loupe.core.exporter import ExportWorker, sanitize_folder_name
from loupe.ui.theme import load_application_fonts, get_application_stylesheet
from loupe.ui.dashboard_view import DashboardView
from loupe.ui.review_view import ReviewView
from loupe.ui.stats_panel import StatsPanel
from loupe.ui.not_accepted_dialog import NotAcceptedDialog
from loupe.ui.tour_overlay import TourDialog
from loupe.ui.settings_dialog import SettingsDialog

class TestLoupeWorkstation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication([])
        load_application_fonts()
        cls.app.setStyleSheet(get_application_stylesheet())
        cls.sample_shoot_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sample_shoot"))

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_config_manager(self):
        """Verify configuration load, save, and key binding management."""
        cfg = ConfigManager()
        cfg.set_key_binding("keep", "K")
        self.assertEqual(cfg.get_key_binding("keep"), "K")
        cfg.reset_to_defaults()
        self.assertEqual(cfg.get_key_binding("keep"), "W")
        self.assertGreaterEqual(cfg.get("ram_budget_gb"), 4)

    def test_storage_and_folders(self):
        """Verify working folder creation, renaming, deletion, and project date updates."""
        sm = StorageManager()
        # Test folder creation
        school_folder = sm.create_folder("School Shootings")
        self.assertIsNotNone(school_folder)
        self.assertEqual(school_folder.name, "School Shootings")

        # Test renaming
        sm.rename_folder(school_folder.id, "School")
        self.assertEqual(sm.get_folder_by_id(school_folder.id).name, "School")

        # Test project creation and association
        proj = Project(name="Graduation Ceremony", folder_id=school_folder.id, shoot_date="2026-05-15")
        sm.save_project(proj)
        self.assertEqual(len(sm.get_projects(school_folder.id)), 1)

        # Test editable project date
        sm.update_project_date(proj.id, "2026-05-20")
        updated_proj = sm.get_project_by_id(proj.id)
        self.assertEqual(updated_proj.shoot_date, "2026-05-20")

        # Clean up
        sm.delete_project(proj.id)
        sm.delete_folder(school_folder.id)

    def test_metadata_extraction(self):
        """Verify EXIF extraction of camera make, model, ISO, shutter, aperture, and focal length."""
        # Find a sample JPEG or ARW in sample_shoot
        test_file = os.path.join(self.sample_shoot_dir, "DSC08491.JPG")
        self.assertTrue(os.path.exists(test_file), f"Sample file not found: {test_file}")

        meta = MetadataExtractor.extract(test_file)
        self.assertNotEqual(meta["camera"], "Unknown Camera")
        self.assertIn("ISO", meta["iso"])
        self.assertTrue("s" in meta["shutter_speed"] or "/" in meta["shutter_speed"])
        self.assertTrue(meta["aperture"].startswith("f/"))
        self.assertTrue(meta["focal_length"].endswith("mm"))
        self.assertNotEqual(meta["date_taken"], "—")

    def test_image_decoder(self):
        """Verify full-resolution decoding into valid QImage."""
        test_file = os.path.join(self.sample_shoot_dir, "DSC08491.JPG")
        qimg, mem_cost = ImageDecoder.decode_to_qimage(test_file)
        self.assertIsNotNone(qimg)
        self.assertFalse(qimg.isNull())
        self.assertEqual(qimg.width(), 1920)
        self.assertEqual(qimg.height(), 1280)
        self.assertGreater(mem_cost, 1024 * 1024)

    def test_preloader_and_batching(self):
        """Verify preloader initialization, cache lookups, and batch boundary pause detection."""
        items = []
        for i in range(1, 19):
            stem = f"DSC{8490 + i:05d}"
            p = os.path.join(self.sample_shoot_dir, f"{stem}.JPG")
            items.append(PhotoItem(base_name=stem, primary_path=p))

        pm = PreloadManager()
        pm.initialize_session(items, batch_size=16, start_index=0)

        # Target index 16 is at the boundary of a 16-item batch and not cached yet
        needs_pause, b_start, b_end = pm.check_navigation(16, direction=1)
        self.assertTrue(needs_pause)
        self.assertEqual(b_start, 16)
        self.assertEqual(b_end, 17)
        pm.cleanup()

    def test_structured_export(self):
        """Verify non-destructive export creates Selected/Unselected RAW/JPEG hierarchy without altering originals."""
        # Create a mock project with 2 kept, 1 rejected
        items = []
        for i in range(1, 4):
            stem = f"DSC{8490 + i:05d}"
            j_path = os.path.join(self.sample_shoot_dir, f"{stem}.JPG")
            r_path = os.path.join(self.sample_shoot_dir, f"{stem}.ARW")
            status = "kept" if i <= 2 else "rejected"
            items.append(PhotoItem(base_name=stem, raw_path=r_path, jpeg_path=j_path, primary_path=j_path, status=status))

        proj = Project(name="Autumn Landscape Test", items=items)
        dest_root = os.path.join(self.temp_dir, "exports")

        worker = ExportWorker(proj, dest_root)
        finished_results = []
        worker.export_finished.connect(lambda res: finished_results.append(res))
        worker.run()

        self.assertEqual(len(finished_results), 1)
        summary = finished_results[0]
        base_dir = summary["base_dir"]

        # Check directories exist
        selected_raw = os.path.join(base_dir, "Selected", "RAW")
        selected_jpeg = os.path.join(base_dir, "Selected", "JPEG")
        unselected_raw = os.path.join(base_dir, "Unselected", "RAW")
        unselected_jpeg = os.path.join(base_dir, "Unselected", "JPEG")

        self.assertTrue(os.path.exists(selected_raw))
        self.assertTrue(os.path.exists(selected_jpeg))
        self.assertTrue(os.path.exists(unselected_raw))
        self.assertTrue(os.path.exists(unselected_jpeg))

        # Check file counts
        self.assertEqual(len(os.listdir(selected_raw)), 2)
        self.assertEqual(len(os.listdir(selected_jpeg)), 2)
        self.assertEqual(len(os.listdir(unselected_raw)), 1)
        self.assertEqual(len(os.listdir(unselected_jpeg)), 1)

        # Check that original source files were preserved
        for item in items:
            self.assertTrue(os.path.exists(item.raw_path))
            self.assertTrue(os.path.exists(item.jpeg_path))

    def test_culling_actions_and_reversibility(self):
        """Verify W (Keep), S (Reject), A (Previous), D (Next), and Ctrl+Z Undo in ReviewView."""
        items = []
        for i in range(1, 5):
            stem = f"DSC{8490 + i:05d}"
            p = os.path.join(self.sample_shoot_dir, f"{stem}.JPG")
            items.append(PhotoItem(base_name=stem, primary_path=p, status="pending"))

        proj = Project(name="Culling Test Session", items=items, current_index=0)
        review = ReviewView()
        review.load_project(proj)

        # Initial state: photo 0 is pending
        self.assertEqual(proj.items[0].status, "pending")
        self.assertEqual(proj.current_index, 0)

        # Keep current (W action) -> marks kept and advances to 1
        review.keep_current()
        self.assertEqual(proj.items[0].status, "kept")
        self.assertEqual(proj.current_index, 1)

        # Reject current (S action) -> marks rejected and advances to 2
        review.reject_current()
        self.assertEqual(proj.items[1].status, "rejected")
        self.assertEqual(proj.current_index, 2)

        # Maybe current (E action) -> marks maybe and advances to 3
        review.maybe_current()
        self.assertEqual(proj.items[2].status, "maybe")
        self.assertEqual(proj.current_index, 3)

        # Keep current on photo 3 -> all 4 photos reviewed!
        review.keep_current()
        self.assertEqual(proj.items[3].status, "kept")
        self.assertEqual(proj.pending_count, 0)
        self.assertEqual(proj.maybe_count, 1)
        self.assertFalse(review.finish_btn.isHidden())

        # Test FinishSessionDialog choices
        from loupe.ui.finish_session_dialog import FinishSessionDialog
        fs_dlg = FinishSessionDialog(proj)
        self.assertIsNotNone(fs_dlg)
        fs_dlg._choose_finish_now()
        self.assertEqual(fs_dlg.choice, FinishSessionDialog.FINISH_NOW)
        fs_dlg._choose_export()
        self.assertEqual(fs_dlg.choice, FinishSessionDialog.FINISH_AND_EXPORT)

        # Undo last action (Ctrl+Z) -> restores photo 3 status and navigates back
        review.undo_last_decision()
        self.assertEqual(proj.items[3].status, "pending")
        self.assertEqual(proj.current_index, 3)

        # Test recovery from Not Accepted tray
        proj.items[1].status = "rejected"
        dlg = NotAcceptedDialog([proj.items[1]])
        dlg.item_restored.connect(review._restore_rejected_item)
        dlg._on_restore(proj.items[1].id)
        self.assertEqual(proj.items[1].status, "kept")

        review.preload_manager.cleanup()

    def test_tour_dialog(self):
        """Verify guided tour navigation and skip functionality."""
        tour = TourDialog()
        self.assertEqual(tour.current_step, 0)
        tour._next_step()
        self.assertEqual(tour.current_step, 1)
        tour._skip_tour()
        self.assertTrue(config.get("has_completed_tour"))

    def test_session_setup_dialog(self):
        """Verify format options, pair sync toggle, and RAM budget calculations."""
        from loupe.ui.session_setup_dialog import SessionSetupDialog
        dlg = SessionSetupDialog()
        dlg.source_dir_edit.setText(self.sample_shoot_dir)
        dlg._rescan_items()

        self.assertGreater(len(dlg.scanned_items), 0)
        # Check that both formats are found and paired
        self.assertTrue(dlg.rb_both.isChecked())
        self.assertFalse(dlg.sec3.isHidden())

        # Test selecting RAW only hides pair sync
        dlg.rb_raw.setChecked(True)
        dlg._on_format_changed(2)
        self.assertTrue(dlg.sec3.isHidden())

        # Test RAM budget batch calculation
        dlg._update_batch_calc(2048)
        self.assertGreaterEqual(dlg.calculated_batch_size, 4)

    def test_dashboard_and_folder_filtering(self):
        """Verify dashboard folder filtering and project counts."""
        dash = DashboardView()
        dash.refresh()
        self.assertGreaterEqual(dash.folder_list.count(), 1)

    def test_edited_results_and_folder_editing(self):
        """Verify folder editing, session renaming, and 'edited result' folder file copying."""
        sm = StorageManager()
        f1 = sm.create_folder("Wedding Work")
        f2 = sm.create_folder("Portfolio Work")

        # Create dummy project
        proj_dir = os.path.join(self.temp_dir, "Shoot101")
        os.makedirs(proj_dir, exist_ok=True)
        proj = Project(name="Shoot 101", folder_id=f1.id, source_dir=proj_dir)
        sm.save_project(proj)

        # Test folder rename
        sm.rename_folder(f1.id, "Weddings 2026")
        self.assertEqual(sm.get_folder_by_id(f1.id).name, "Weddings 2026")

        # Test project folder reassign
        sm.update_project_folder(proj.id, f2.id)
        self.assertEqual(sm.get_project_by_id(proj.id).folder_id, f2.id)

        # Test project rename
        sm.update_project_name(proj.id, "Sarah & John Wedding")
        self.assertEqual(sm.get_project_by_id(proj.id).name, "Sarah & John Wedding")

        # Test creating 'edited result' folder and copying LRC files
        edited_dir = os.path.join(proj.source_dir, "edited result")
        os.makedirs(edited_dir, exist_ok=True)

        # Create 2 sample LRC export files
        sample_lrc1 = os.path.join(self.temp_dir, "LRC_001.JPG")
        sample_lrc2 = os.path.join(self.temp_dir, "LRC_002.JPG")
        with open(sample_lrc1, "wb") as f:
            f.write(b"SAMPLE_LRC_DATA_1")
        with open(sample_lrc2, "wb") as f:
            f.write(b"SAMPLE_LRC_DATA_2")

        shutil.copy2(sample_lrc1, os.path.join(edited_dir, "LRC_001.JPG"))
        shutil.copy2(sample_lrc2, os.path.join(edited_dir, "LRC_002.JPG"))

        proj.edited_result_dir = edited_dir
        proj.edited_files = [os.path.join(edited_dir, "LRC_001.JPG"), os.path.join(edited_dir, "LRC_002.JPG")]
        sm.save_project(proj)

        loaded_proj = sm.get_project_by_id(proj.id)
        self.assertEqual(loaded_proj.edited_count, 2)
        self.assertTrue(os.path.exists(os.path.join(edited_dir, "LRC_001.JPG")))
        self.assertTrue(os.path.exists(os.path.join(edited_dir, "LRC_002.JPG")))

        # Clean up
        sm.delete_project(proj.id)
        sm.delete_folder(f1.id)
        sm.delete_folder(f2.id)

    def test_auto_updater(self):
        """Verify version comparison, manifest parsing, and update detection."""
        import json
        from loupe.core.updater import parse_version_tuple, is_newer_version, fetch_update_info

        self.assertEqual(parse_version_tuple("v1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version_tuple("1.0.0"), (1, 0, 0))
        self.assertTrue(is_newer_version("1.1.0", "1.0.0"))
        self.assertTrue(is_newer_version("2.0.0", "1.9.9"))
        self.assertFalse(is_newer_version("1.0.0", "1.0.0"))
        self.assertFalse(is_newer_version("0.9.5", "1.0.0"))

        # Test local manifest JSON parsing
        manifest_file = os.path.join(self.temp_dir, "version.json")
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump({
                "version": "1.2.0",
                "download_url": "https://example.com/Framed-Setup-v1.2.0.exe",
                "release_notes": "Added auto updater support."
            }, f)

        info = fetch_update_info(manifest_file)
        self.assertEqual(info.version, "1.2.0")
        self.assertEqual(info.download_url, "https://example.com/Framed-Setup-v1.2.0.exe")
        self.assertIn("updater", info.release_notes)
        self.assertTrue(is_newer_version(info.version, "1.0.0"))

    def test_video_pipeline_and_export(self):
        """Verify video metadata, proxy compression, non-destructive Selected/Similar/Unselected export, and dual mode switching."""
        import cv2
        import numpy as np
        from loupe.core.video_engine import get_video_metadata, compress_video_to_proxy
        from loupe.core.video_exporter import VideoExportWorker

        # 1. Create a dummy 1920x1080 video clip
        test_video = os.path.join(self.temp_dir, "CLIP_001.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(test_video, fourcc, 24.0, (1920, 1080))
        for _ in range(24):
            frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
            cv2.putText(frame, "TEST CLIP", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
            writer.write(frame)
        writer.release()

        self.assertTrue(os.path.exists(test_video))

        # 2. Test metadata extraction
        meta = get_video_metadata(test_video)
        self.assertEqual(meta["width"], 1920)
        self.assertEqual(meta["height"], 1080)
        self.assertEqual(meta["fps"], 24.0)
        self.assertGreater(meta["duration_seconds"], 0.8)

        # 3. Test proxy compression
        proxy_path = os.path.join(self.temp_dir, "CLIP_001_proxy.mp4")
        compress_video_to_proxy(test_video, proxy_path, target_max_width=960)
        self.assertTrue(os.path.exists(proxy_path))
        p_meta = get_video_metadata(proxy_path)
        self.assertEqual(p_meta["width"], 960)
        self.assertEqual(p_meta["height"], 540)

        # 4. Test non-destructive VideoExportWorker with Selected, Similar, and Unselected
        clip2 = os.path.join(self.temp_dir, "CLIP_002.mp4")
        clip3 = os.path.join(self.temp_dir, "CLIP_003.mp4")
        shutil.copy2(test_video, clip2)
        shutil.copy2(test_video, clip3)

        items = [
            PhotoItem(base_name="CLIP_001", primary_path=test_video, is_video=True, status="selected"),
            PhotoItem(base_name="CLIP_002", primary_path=clip2, is_video=True, status="similar"),
            PhotoItem(base_name="CLIP_003", primary_path=clip3, is_video=True, status="unselected"),
        ]

        proj = Project(name="Commercial Shoot Reel", media_type="video", items=items)
        export_root = os.path.join(self.temp_dir, "video_exports")

        worker = VideoExportWorker(proj, export_root)
        results = []
        worker.export_finished.connect(lambda res: results.append(res))
        worker.run()

        self.assertEqual(len(results), 1)
        res = results[0]
        base_dir = res["base_dir"]

        sel_dir = os.path.join(base_dir, "Selected")
        sim_dir = os.path.join(base_dir, "Similar")
        unsel_dir = os.path.join(base_dir, "Unselected")

        self.assertTrue(os.path.exists(sel_dir))
        self.assertTrue(os.path.exists(sim_dir))
        self.assertTrue(os.path.exists(unsel_dir))

        self.assertEqual(len(os.listdir(sel_dir)), 1)
        self.assertEqual(len(os.listdir(sim_dir)), 1)
        self.assertEqual(len(os.listdir(unsel_dir)), 1)

        # Verify original source files were untouched
        self.assertTrue(os.path.exists(test_video))
        self.assertTrue(os.path.exists(clip2))
        self.assertTrue(os.path.exists(clip3))

        # 5. Test dashboard dual mode switching
        dash = DashboardView()
        dash._set_media_mode("video")
        self.assertEqual(dash.current_media_mode, "video")
        self.assertIn("Video", dash.new_session_btn.text())
        dash._set_media_mode("photo")
        self.assertEqual(dash.current_media_mode, "photo")
        self.assertIn("Photo", dash.new_session_btn.text())

if __name__ == "__main__":
    unittest.main()
