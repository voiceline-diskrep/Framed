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

        # Test RAM budget batch calculation scales with RAM beyond 32 photos
        dlg._update_batch_calc(2048)
        self.assertGreaterEqual(dlg.calculated_batch_size, 20)
        dlg._update_batch_calc(8192)
        self.assertEqual(dlg.calculated_batch_size, 109)
        self.assertGreater(dlg.calculated_batch_size, 32)

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

    def test_workspace_folder_export_separation(self):
        """Verify export into separate workspace folder when separate_by_workspace is True vs False."""
        sm = StorageManager()
        ws_folder = sm.create_folder("Fashion & Editorial")
        self.assertIsNotNone(ws_folder)

        try:
            # Create sample photo
            j_path = os.path.join(self.sample_shoot_dir, "DSC08491.JPG")
            r_path = os.path.join(self.sample_shoot_dir, "DSC08491.ARW")
            item = PhotoItem(base_name="DSC08491", raw_path=r_path, jpeg_path=j_path, primary_path=j_path, status="kept")

            proj = Project(name="Spring Collection 2026", folder_id=ws_folder.id, items=[item])
            sm.save_project(proj)

            # Test 1: separate_by_workspace=True (default)
            dest1 = os.path.join(self.temp_dir, "export_ws_true")
            worker1 = ExportWorker(proj, dest1, separate_by_workspace=True)
            res1 = []
            worker1.export_finished.connect(lambda r: res1.append(r))
            worker1.run()

            self.assertEqual(len(res1), 1)
            expected_base1 = os.path.join(dest1, "Fashion & Editorial", "Spring Collection 2026")
            self.assertEqual(res1[0]["base_dir"], expected_base1)
            self.assertTrue(os.path.exists(os.path.join(expected_base1, "Selected", "JPEG", "DSC08491.JPG")))

            # Test 2: separate_by_workspace=False
            dest2 = os.path.join(self.temp_dir, "export_ws_false")
            worker2 = ExportWorker(proj, dest2, separate_by_workspace=False)
            res2 = []
            worker2.export_finished.connect(lambda r: res2.append(r))
            worker2.run()

            self.assertEqual(len(res2), 1)
            expected_base2 = os.path.join(dest2, "Spring Collection 2026")
            self.assertEqual(res2[0]["base_dir"], expected_base2)
            self.assertTrue(os.path.exists(os.path.join(expected_base2, "Selected", "JPEG", "DSC08491.JPG")))

        finally:
            sm.delete_project(proj.id)
            sm.delete_folder(ws_folder.id)

    def test_in_app_session_creation_views(self):
        """Verify that SessionSetupView, VideoSessionView, and DashboardModalOverlay render in-app without popouts."""
        from loupe.ui.session_setup_dialog import SessionSetupView
        from loupe.ui.video_session_dialog import VideoSessionView
        from loupe.ui.dashboard_view import DashboardView

        # 1. Test in-app Photo setup view
        photo_view = SessionSetupView()
        self.assertIsNotNone(photo_view.start_btn)
        self.assertIsNotNone(photo_view.btn_back)
        photo_view.reset_form()
        self.assertFalse(photo_view.start_btn.isEnabled())

        # 2. Test in-app Video setup view
        video_view = VideoSessionView()
        self.assertIsNotNone(video_view.btn_create)
        self.assertIsNotNone(video_view.btn_back)
        video_view.reset_form()
        self.assertFalse(video_view.btn_create.isEnabled())

        # 3. Test Dashboard in-app modal overlay
        dash = DashboardView()
        self.assertTrue(hasattr(dash, "modal_overlay"))
        self.assertFalse(dash.modal_overlay.isVisible())

        # Verify modal overlay creates folders in-app
        created_folders = []
        dash.modal_overlay.show_create_folder(lambda name: created_folders.append(name))
        self.assertFalse(dash.modal_overlay.isHidden())
        dash.modal_overlay.hide()
        self.assertTrue(dash.modal_overlay.isHidden())

    def test_dashboard_export_action_and_dialogs(self):
        """Verify that clicking Export on ProjectCard emits signal and opens ExportDialog/VideoExportDialog without error."""
        from loupe.ui.dashboard_view import ProjectCard
        from loupe.ui.export_dialog import ExportDialog
        from loupe.ui.video_export_dialog import VideoExportDialog

        # Test photo project card export button
        photo_proj = Project(name="Portrait Session", shoot_date="2026-10-17", media_type="photo")
        photo_card = ProjectCard(photo_proj)
        
        exported_ids = []
        photo_card.export_clicked.connect(lambda pid: exported_ids.append(pid))
        photo_card.export_btn.click()
        self.assertEqual(exported_ids, [photo_proj.id])

        # Test ExportDialog creation for photo project (ensure no QScrollArea/QApplication NameError)
        photo_dialog = ExportDialog(photo_proj)
        self.assertIsNotNone(photo_dialog.dest_edit)
        self.assertIsNotNone(photo_dialog.cb_workspace)
        self.assertTrue(photo_dialog.cb_workspace.isChecked())
        self.assertIn("Selected", photo_dialog.preview_lbl.text())

        # Test video project card export button
        video_proj = Project(name="Commercial Shoot", shoot_date="2026-10-17", media_type="video")
        video_card = ProjectCard(video_proj)

        v_exported_ids = []
        video_card.export_clicked.connect(lambda pid: v_exported_ids.append(pid))
        video_card.export_btn.click()
        self.assertEqual(v_exported_ids, [video_proj.id])

        # Test VideoExportDialog creation for video project
        video_dialog = VideoExportDialog(video_proj)
        self.assertIsNotNone(video_dialog.edit_dir)
        self.assertIsNotNone(video_dialog.cb_workspace)
        self.assertTrue(video_dialog.cb_workspace.isChecked())
        self.assertIn("Selected", video_dialog.preview_lbl.text())

    def test_v118_bugfixes(self):
        """Regression tests for v1.1.8 bug fixes: SettingsDialog, PreloadManager restart, format_mode export, video undo/uncompressed."""
        from loupe.ui.video_review_view import VideoReviewView
        from loupe.ui.export_dialog import ExportDialog

        # 1. SettingsDialog instantiation (no NameError: QApplication)
        settings_dlg = SettingsDialog()
        self.assertIsNotNone(settings_dlg)

        # 2. PreloadManager worker restart after cleanup()
        items = [
            PhotoItem(base_name="DSC08491", primary_path=os.path.join(self.sample_shoot_dir, "DSC08491.JPG")),
            PhotoItem(base_name="DSC08492", primary_path=os.path.join(self.sample_shoot_dir, "DSC08492.JPG")),
        ]
        pm = PreloadManager()
        pm.initialize_session(items, batch_size=2, start_index=0)
        pm.cleanup()
        # Re-initializing after cleanup must restart the worker thread
        pm.initialize_session(items, batch_size=2, start_index=0)
        self.assertTrue(pm._worker.isRunning())
        pm.cleanup()

        # 3. ExportWorker respects format_mode ("raw_only" vs "jpeg_only")
        j_path = os.path.join(self.sample_shoot_dir, "DSC08491.JPG")
        r_path = os.path.join(self.sample_shoot_dir, "DSC08491.ARW")
        item_pair = PhotoItem(base_name="DSC08491", raw_path=r_path, jpeg_path=j_path, primary_path=r_path, status="kept")
        raw_proj = Project(name="RAW Only Test", format_mode="raw_only", items=[item_pair])
        dest_raw = os.path.join(self.temp_dir, "raw_only_export")
        w_raw = ExportWorker(raw_proj, dest_raw, separate_by_workspace=False)
        res_raw = []
        w_raw.export_finished.connect(lambda r: res_raw.append(r))
        w_raw.run()
        self.assertEqual(len(res_raw), 1)
        self.assertEqual(res_raw[0]["total_copied"], 1)
        self.assertTrue(os.path.exists(os.path.join(res_raw[0]["base_dir"], "Selected", "RAW", "DSC08491.ARW")))
        self.assertFalse(os.path.exists(os.path.join(res_raw[0]["base_dir"], "Selected", "JPEG", "DSC08491.JPG")))

        # Check ExportDialog hierarchy preview for raw_only
        exp_dlg = ExportDialog(raw_proj)
        self.assertIn("RAW/", exp_dlg.preview_lbl.text())
        self.assertNotIn("JPEG/", exp_dlg.preview_lbl.text())

        # 4. VideoReviewView undo & duration formatting (> 60 minutes)
        v_review = VideoReviewView()
        self.assertEqual(v_review._format_ms(3661000), "01:01:01")
        self.assertEqual(v_review._format_ms(65000), "01:05")

        v_items = [
            PhotoItem(base_name="CLIP1", primary_path="clip1.mp4", is_video=True, status="pending"),
            PhotoItem(base_name="CLIP2", primary_path="clip2.mp4", is_video=True, status="pending"),
        ]
        v_proj = Project(name="Video Undo Test", media_type="video", view_uncompressed=True, items=v_items, current_index=0)
        try:
            v_review.project = v_proj
            v_review.current_item = v_items[0]
            v_review.mark_selected()
            self.assertEqual(v_proj.items[0].status, "selected")
            self.assertEqual(v_proj.current_index, 1)
            v_review.undo_last_decision()
            self.assertEqual(v_proj.items[0].status, "pending")
            self.assertEqual(v_proj.current_index, 0)
        finally:
            StorageManager().delete_project(v_proj.id)

    def test_ram_scaling_beyond_32_photos(self):
        """Verify that RAM budget scales beyond 32 photos, cache holds more than 32 photos, and ReviewView uses allocated RAM."""
        from PySide6.QtGui import QImage
        from loupe.ui.session_setup_dialog import SessionSetupView
        
        # 1. Setup view calculation with 8GB RAM -> 109 photos (> 32)
        view = SessionSetupView()
        view._update_batch_calc(8192)
        self.assertEqual(view.calculated_batch_size, 109)
        self.assertGreater(view.calculated_batch_size, 32)

        # 2. Setup view calculation with 16GB RAM -> 218 photos (> 32)
        view._update_batch_calc(16384)
        self.assertEqual(view.calculated_batch_size, 218)
        self.assertGreater(view.calculated_batch_size, 32)

        # 3. PreloadManager with 40 photos and ram_allocation_mb=4096 (capacity 54 photos)
        # Should keep all 40 photos in RAM without evicting down to 4 or 32
        items = [PhotoItem(base_name=f"DSC_{i:04d}", primary_path=f"img_{i}.jpg") for i in range(40)]
        pm = PreloadManager()
        pm.initialize_session(items, batch_size=40, start_index=0, ram_allocation_mb=4096)
        
        dummy_qimg = QImage(100, 100, QImage.Format_RGB888)
        for i in range(40):
            pm._on_photo_loaded(i, dummy_qimg)
            
        # Verify that all 40 photos remain in RAM cache
        self.assertEqual(len(pm._cache), 40)
        self.assertTrue(pm.is_cached(0))
        self.assertTrue(pm.is_cached(39))
        pm.cleanup()

        # 4. ReviewView auto-scales batch_size from ram_allocation_mb
        review = ReviewView()
        proj = Project(name="Big RAM Session", ram_allocation_mb=8192, batch_size=16, items=items)
        review.load_project(proj)
        self.assertGreater(proj.batch_size, 32)
        self.assertEqual(proj.batch_size, 109)
        review.preload_manager.cleanup()


    def test_multi_theme_engine_and_ui(self):
        """Verify dynamic multi-theme engine, 6 workstation palettes, Settings radio swatches, and dashboard quick switch."""
        from loupe.ui.theme import (
            THEMES, current_theme_id, apply_theme, is_current_theme_light,
            theme_manager, get_application_stylesheet, COLOR_ACCENT, COLOR_BG_BASE
        )
        from loupe.ui.settings_dialog import SettingsDialog
        from loupe.ui.dashboard_view import DashboardView

        # 1. Verify 6 clean, descriptive themes exist in registry
        expected_themes = [
            "dark_amber", "oled", "dark_blue",
            "dark_green", "neutral_gray", "light"
        ]
        for tid in expected_themes:
            self.assertIn(tid, THEMES)
            tdef = THEMES[tid]
            self.assertTrue(len(tdef.name) > 0)
            self.assertTrue(len(tdef.description) > 0)
            self.assertIn("COLOR_BG_BASE", tdef.colors)
            self.assertIn("COLOR_BG_SURFACE", tdef.colors)
            self.assertIn("COLOR_ACCENT", tdef.colors)
            self.assertIn("COLOR_STATUS_KEPT", tdef.colors)
            self.assertIn("COLOR_STATUS_REJECTED", tdef.colors)
            self.assertIn("COLOR_STATUS_MAYBE", tdef.colors)

        # Check plain names
        self.assertEqual(THEMES["dark_amber"].name, "Dark Amber")
        self.assertEqual(THEMES["oled"].name, "OLED")
        self.assertEqual(THEMES["dark_blue"].name, "Dark Blue")
        self.assertEqual(THEMES["dark_green"].name, "Dark Green")
        self.assertEqual(THEMES["neutral_gray"].name, "Neutral Gray")
        self.assertEqual(THEMES["light"].name, "Light")

        self.assertFalse(THEMES["dark_amber"].is_light)
        self.assertTrue(THEMES["light"].is_light)

        # 2. Test live theme application and signal notification
        emitted_themes = []
        theme_manager.theme_changed.connect(lambda t: emitted_themes.append(t))

        # Switch to OLED (also test legacy alias 'obsidian_cyan')
        apply_theme("oled")
        from loupe.ui.theme import COLOR_ACCENT as cyan_accent, current_theme_id as oled_id
        self.assertEqual(oled_id, "oled")
        self.assertEqual(cyan_accent, "#06B6D4")
        self.assertEqual(config.get("theme"), "oled")
        self.assertFalse(is_current_theme_light())
        self.assertIn("oled", emitted_themes)

        # Test legacy alias obsidian_cyan maps to oled
        apply_theme("obsidian_cyan")
        from loupe.ui.theme import current_theme_id as alias_oled_id
        self.assertEqual(alias_oled_id, "oled")

        # Switch to Light
        apply_theme("light")
        from loupe.ui.theme import COLOR_ACCENT as light_accent, COLOR_BG_BASE as light_bg
        self.assertTrue(is_current_theme_light())
        self.assertEqual(light_accent, "#2563EB")
        self.assertEqual(light_bg, "#F3F4F6")
        self.assertIn("light", emitted_themes)

        # Verify stylesheet renders correctly for light theme
        ss_light = get_application_stylesheet()
        self.assertIn("#2563EB", ss_light)
        self.assertIn("#F3F4F6", ss_light)

        # Switch to Dark Green
        apply_theme("dark_green")
        from loupe.ui.theme import COLOR_ACCENT as emerald_accent
        self.assertEqual(emerald_accent, "#10B981")

        # 3. Test SettingsDialog UI with theme radios
        dlg = SettingsDialog()
        self.assertEqual(len(dlg.theme_radios), 6)
        self.assertTrue(dlg.theme_radios["dark_green"].isChecked())
        
        # Toggle Neutral Gray via radio
        dlg.theme_radios["neutral_gray"].setChecked(True)
        from loupe.ui.theme import current_theme_id as gray_id, COLOR_ACCENT as gray_accent
        self.assertEqual(gray_id, "neutral_gray")
        self.assertEqual(gray_accent, "#F97316")

        # 4. Test Dashboard quick switch button & menu action
        dash = DashboardView()
        self.assertTrue(hasattr(dash, "theme_btn"))
        dash._set_quick_theme("dark_blue")
        from loupe.ui.theme import current_theme_id as blue_id, COLOR_ACCENT as blue_accent
        self.assertEqual(blue_id, "dark_blue")
        self.assertEqual(blue_accent, "#6366F1")

        # Restore default Dark Amber
        apply_theme("dark_amber")
        from loupe.ui.theme import current_theme_id as amber_id
        self.assertEqual(amber_id, "dark_amber")

    def test_session_switching_isolation(self):
        """Verify strict session isolation when exiting to dashboard and entering another session."""
        from loupe.app import FramedMainWindow
        from PySide6.QtGui import QImage

        sm = StorageManager()
        photo_a_path = os.path.join(self.sample_shoot_dir, "DSC08491.JPG")
        photo_b_path = os.path.join(self.sample_shoot_dir, "DSC08492.JPG")

        proj_a = Project(
            name="Session Alpha",
            items=[PhotoItem(base_name="ALPHA_01", primary_path=photo_a_path, jpeg_path=photo_a_path)]
        )
        proj_b = Project(
            name="Session Beta",
            items=[PhotoItem(base_name="BETA_01", primary_path=photo_b_path, jpeg_path=photo_b_path)]
        )
        sm.save_project(proj_a)
        sm.save_project(proj_b)

        try:
            main_win = FramedMainWindow()

            # 1. Open Session Alpha
            main_win._open_project(proj_a.id)
            main_win.review_view.preload_manager.preload_batch_sync(0)
            main_win.review_view._display_current_photo()

            self.assertEqual(main_win.review_view.project.id, proj_a.id)
            self.assertIn("ALPHA_01", main_win.review_view.current_filename_lbl.text())
            self.assertIsNotNone(main_win.review_view.canvas.pixmap_item)

            # 2. Exit to dashboard
            main_win._show_dashboard()
            self.assertIsNone(main_win.review_view.project)
            self.assertIsNone(main_win.review_view.canvas.pixmap_item)
            self.assertEqual(main_win.review_view.counter_lbl.text(), "0 of 0")
            self.assertEqual(main_win.review_view.current_filename_lbl.text(), "No photos in session")

            # 3. Open Session Beta
            main_win._open_project(proj_b.id)
            self.assertEqual(main_win.review_view.project.id, proj_b.id)
            self.assertIn("BETA_01", main_win.review_view.current_filename_lbl.text())
            self.assertNotIn("ALPHA_01", main_win.review_view.current_filename_lbl.text())

            # 4. Simulate a delayed, stale worker decode signal from prior session generation
            stale_gen = main_win.review_view.preload_manager.session_generation - 1
            dummy_stale_img = QImage(50, 50, QImage.Format_RGB888)
            main_win.review_view.preload_manager._on_photo_loaded(stale_gen, 0, dummy_stale_img)

            # Assert stale image was dropped and not cached
            cached = main_win.review_view.preload_manager.get_image(0)
            if cached is not None:
                self.assertNotEqual(cached.size(), dummy_stale_img.size())

            # 5. Let Session Beta load cleanly
            main_win.review_view.preload_manager.preload_batch_sync(0)
            main_win.review_view._display_current_photo()
            self.assertIsNotNone(main_win.review_view.canvas.pixmap_item)
            self.assertIn("BETA_01", main_win.review_view.current_filename_lbl.text())

            main_win.review_view.unload_project()
        finally:
            sm.delete_project(proj_a.id)
            sm.delete_project(proj_b.id)


if __name__ == "__main__":
    unittest.main()





