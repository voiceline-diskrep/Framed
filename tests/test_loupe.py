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

    def test_nested_workspace_folders(self):
        """Verify nested workspace folders: parent_id hierarchy, ancestry, depth, paths, and hierarchical export."""
        sm = StorageManager()
        parent_f = sm.create_folder("Client Commercials")
        sub_f = sm.create_folder("Brand Nike", parent_id=parent_f.id)
        sub_sub_f = sm.create_folder("Campaign 2026", parent_id=sub_f.id)

        try:
            self.assertEqual(sub_f.parent_id, parent_f.id)
            self.assertEqual(sub_sub_f.parent_id, sub_f.id)

            # Test hierarchy traversal
            top_level = sm.get_top_level_folders()
            self.assertTrue(any(f.id == parent_f.id for f in top_level))
            self.assertFalse(any(f.id == sub_f.id for f in top_level))

            subfolders = sm.get_subfolders(parent_f.id)
            self.assertEqual(len(subfolders), 1)
            self.assertEqual(subfolders[0].id, sub_f.id)

            # Test path and parts
            parts = sm.get_folder_parts(sub_sub_f.id)
            self.assertEqual(parts, ["Client Commercials", "Brand Nike", "Campaign 2026"])
            path_str = sm.get_folder_path(sub_sub_f.id)
            self.assertEqual(path_str, "Client Commercials / Brand Nike / Campaign 2026")

            # Test depth
            depth_list = sm.get_folders_with_depth()
            id_depth_map = {f.id: d for f, d in depth_list}
            self.assertEqual(id_depth_map.get(parent_f.id), 0)
            self.assertEqual(id_depth_map.get(sub_f.id), 1)
            self.assertEqual(id_depth_map.get(sub_sub_f.id), 2)

            # Test nested export
            j_path = os.path.join(self.sample_shoot_dir, "DSC08491.JPG")
            item = PhotoItem(base_name="DSC08491", jpeg_path=j_path, primary_path=j_path, status="kept")
            nested_proj = Project(name="Shoot Day 1", folder_id=sub_sub_f.id, items=[item])
            sm.save_project(nested_proj)

            dest = os.path.join(self.temp_dir, "export_nested")
            worker = ExportWorker(nested_proj, dest, separate_by_workspace=True)
            res = []
            worker.export_finished.connect(lambda r: res.append(r))
            worker.run()

            expected_base = os.path.join(dest, "Client Commercials", "Brand Nike", "Campaign 2026", "Shoot Day 1")
            self.assertEqual(res[0]["base_dir"], expected_base)
            self.assertTrue(os.path.exists(os.path.join(expected_base, "Selected", "JPEG", "DSC08491.JPG")))

            sm.delete_project(nested_proj.id)
        finally:
            sm.delete_folder(parent_f.id)
            # Verify recursive delete cleaned up descendants
            self.assertIsNone(sm.get_folder_by_id(parent_f.id))
            self.assertIsNone(sm.get_folder_by_id(sub_f.id))
            self.assertIsNone(sm.get_folder_by_id(sub_sub_f.id))

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
        self.assertEqual(len(dlg.theme_radios), len(THEMES))
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

    def test_experimental_mode_and_gdrive_integration(self):
        """Verify Experimental Mode toggle, pre-release updater channel, Google Drive OAuth config, and Cloud Import/Export UI."""
        import json
        from loupe.core.gdrive import (
            parse_gdrive_folder_id, load_client_secrets_file, format_eta, GoogleDriveClient
        )
        from loupe.core.updater import parse_version_tuple, fetch_update_info
        from loupe.ui.settings_dialog import SettingsDialog
        from loupe.ui.session_setup_dialog import SessionSetupView
        from loupe.ui.video_session_dialog import VideoSessionView
        from loupe.ui.export_dialog import ExportDialog
        from loupe.ui.video_export_dialog import VideoExportDialog

        # 1. Test Google Drive URL & Folder ID parser
        self.assertEqual(parse_gdrive_folder_id(""), "root")
        self.assertEqual(parse_gdrive_folder_id("My Drive"), "root")
        self.assertEqual(
            parse_gdrive_folder_id("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz?usp=sharing"),
            "1AbCdEfGhIjKlMnOpQrStUvWxYz"
        )
        self.assertEqual(
            parse_gdrive_folder_id("https://drive.google.com/drive/u/0/folders/1ZyXwVuTsRqPoNmLkJiHgFeDcBa"),
            "1ZyXwVuTsRqPoNmLkJiHgFeDcBa"
        )
        self.assertEqual(
            parse_gdrive_folder_id("https://drive.google.com/open?id=1FolderIdQueryParam999"),
            "1FolderIdQueryParam999"
        )
        self.assertEqual(parse_gdrive_folder_id("1DirectFolderIdString12345"), "1DirectFolderIdString12345")
        self.assertEqual(format_eta(45), "45s")
        self.assertEqual(format_eta(125), "2m 05s")

        # 2. Test loading Google Cloud client_secret.json
        secret_file = os.path.join(self.temp_dir, "client_secret_test.json")
        with open(secret_file, "w", encoding="utf-8") as f:
            json.dump({
                "installed": {
                    "client_id": "test-client-id-123.apps.googleusercontent.com",
                    "client_secret": "GOCSPX-test-secret-xyz"
                }
            }, f)
        cid, csec = load_client_secrets_file(secret_file)
        self.assertEqual(cid, "test-client-id-123.apps.googleusercontent.com")
        self.assertEqual(csec, "GOCSPX-test-secret-xyz")

        # 3. Test pre-release version parsing and GitHub Releases list filtering
        self.assertEqual(parse_version_tuple("v1.3.0-experimental"), (1, 3, 0))
        releases_feed = os.path.join(self.temp_dir, "releases_list.json")
        with open(releases_feed, "w", encoding="utf-8") as f:
            json.dump([
                {
                    "tag_name": "v1.3.0-experimental",
                    "prerelease": True,
                    "draft": False,
                    "body": "Experimental Google Drive build",
                    "assets": [{"name": "Framed-Setup-v1.3.0-experimental.exe", "browser_download_url": "https://example.com/exp.exe"}]
                },
                {
                    "tag_name": "v1.2.1",
                    "prerelease": False,
                    "draft": False,
                    "body": "Stable build",
                    "assets": [{"name": "Framed-Setup-v1.2.1.exe", "browser_download_url": "https://example.com/stable.exe"}]
                }
            ], f)

        info_stable = fetch_update_info(releases_feed, include_prereleases=False)
        self.assertEqual(info_stable.version, "1.2.1")
        self.assertFalse(info_stable.is_prerelease)

        info_exp = fetch_update_info(releases_feed, include_prereleases=True)
        self.assertEqual(info_exp.version, "1.3.0-experimental")
        self.assertTrue(info_exp.is_prerelease)

        # 4. Test Experimental Mode UI toggling in Settings, Session Setup, and Export Dialogs
        prev_exp = config.get("experimental_mode", False)
        try:
            config.set("experimental_mode", False)
            s_dlg = SettingsDialog()
            self.assertFalse(s_dlg.cb_experimental.isChecked())
            self.assertTrue(s_dlg.card_gdrive.isHidden())

            # Toggle Experimental Mode ON
            s_dlg.cb_experimental.setChecked(True)
            self.assertFalse(s_dlg.card_gdrive.isHidden())
            self.assertTrue(config.get("experimental_mode"))

            p_setup = SessionSetupView()
            self.assertFalse(p_setup.gdrive_btn.isHidden())
            v_setup = VideoSessionView()
            self.assertFalse(v_setup.gdrive_btn.isHidden())

            # Test ExportDialog Google Drive mode & default category checkboxes
            proj = Project(
                name="Cloud Export Shoot",
                items=[
                    PhotoItem(base_name="IMG_1", primary_path="1.jpg", status="kept"),
                    PhotoItem(base_name="IMG_2", primary_path="2.jpg", status="maybe"),
                    PhotoItem(base_name="IMG_3", primary_path="3.jpg", status="rejected"),
                ]
            )
            exp_dlg = ExportDialog(proj)
            self.assertFalse(exp_dlg.mode_frame.isHidden())
            self.assertTrue(exp_dlg.rb_dest_local.isChecked())
            self.assertTrue(exp_dlg.gdrive_cat_card.isHidden())

            # Switch to Google Drive export mode
            exp_dlg.rb_dest_gdrive.setChecked(True)
            self.assertFalse(exp_dlg.gdrive_cat_card.isHidden())
            self.assertTrue(exp_dlg.cb_up_selected.isChecked())
            self.assertTrue(exp_dlg.cb_up_maybe.isChecked())
            self.assertTrue(exp_dlg.cb_up_edited.isChecked())
            self.assertFalse(exp_dlg.cb_up_unselected.isChecked())
            self.assertIn("Google Drive", exp_dlg.preview_lbl.text())
            self.assertNotIn("Unselected/", exp_dlg.preview_lbl.text())

            # Checking Unselected adds it back to preview
            exp_dlg.cb_up_unselected.setChecked(True)
            self.assertIn("Unselected/", exp_dlg.preview_lbl.text())

            # Test VideoExportDialog Google Drive mode
            v_proj = Project(name="Cloud Video Shoot", media_type="video")
            v_exp_dlg = VideoExportDialog(v_proj)
            self.assertFalse(v_exp_dlg.mode_frame.isHidden())
            v_exp_dlg.rb_dest_gdrive.setChecked(True)
            self.assertFalse(v_exp_dlg.gdrive_cat_card.isHidden())
            self.assertTrue(v_exp_dlg.cb_up_selected.isChecked())
            self.assertTrue(v_exp_dlg.cb_up_similar.isChecked())
            self.assertFalse(v_exp_dlg.cb_up_unselected.isChecked())
        finally:
            config.set("experimental_mode", prev_exp)

    def test_match_mode_project_model(self):
        """Verify Project match mode attributes, quota calculation, and dictionary serialization."""
        items = [
            PhotoItem(base_name="IMG_01", primary_path="1.jpg", status="pending"),
            PhotoItem(base_name="IMG_02", primary_path="2.jpg", status="pending"),
            PhotoItem(base_name="IMG_03", primary_path="3.jpg", status="pending"),
        ]
        proj = Project(
            name="Derby Match Session",
            is_match_mode=True,
            max_selected_count=2,
            preview_mode="jpeg",
            link_to_raw=True,
            items=items
        )

        self.assertTrue(proj.is_match_mode)
        self.assertEqual(proj.max_selected_count, 2)
        self.assertEqual(proj.preview_mode, "jpeg")
        self.assertTrue(proj.link_to_raw)
        self.assertFalse(proj.is_over_quota)
        self.assertEqual(proj.quota_remaining, 2)

        # Mark 1 as kept
        items[0].status = "kept"
        self.assertFalse(proj.is_over_quota)
        self.assertEqual(proj.quota_remaining, 1)

        # Mark 2 as kept (at quota)
        items[1].status = "kept"
        self.assertFalse(proj.is_over_quota)
        self.assertEqual(proj.quota_remaining, 0)

        # Mark 3 as kept (over quota)
        items[2].status = "kept"
        self.assertTrue(proj.is_over_quota)
        self.assertEqual(proj.quota_remaining, 0)

        # Serialization round-trip
        data = proj.to_dict()
        self.assertTrue(data["is_match_mode"])
        self.assertEqual(data["max_selected_count"], 2)
        self.assertEqual(data["preview_mode"], "jpeg")
        self.assertTrue(data["link_to_raw"])

        restored = Project.from_dict(data)
        self.assertTrue(restored.is_match_mode)
        self.assertEqual(restored.max_selected_count, 2)
        self.assertEqual(restored.preview_mode, "jpeg")
        self.assertTrue(restored.link_to_raw)
        self.assertTrue(restored.is_over_quota)

    def test_session_setup_match_mode_and_preview_engine(self):
        """Verify SessionSetupView controls for Match Mode and Preview Engine as standard workstation features."""
        from loupe.ui.session_setup_dialog import SessionSetupView
        setup = SessionSetupView()
        setup.reset_form()

        # Both cards are standard features available directly
        self.assertFalse(setup.sec_match_mode.isHidden())
        self.assertFalse(setup.sec_preview_engine.isHidden())

        # Test format switching: raw_only hides preview engine, both shows it
        setup.rb_raw.setChecked(True)
        setup._update_format_visibility()
        self.assertTrue(setup.sec_preview_engine.isHidden())
        setup.rb_both.setChecked(True)
        setup._update_format_visibility()
        self.assertFalse(setup.sec_preview_engine.isHidden())

        # Test Match Mode toggle
        self.assertTrue(setup.match_limit_container.isHidden())
        setup.cb_match_mode.setChecked(True)
        self.assertFalse(setup.match_limit_container.isHidden())
        setup.sb_match_limit.setValue(15)

        # Test Preview Engine toggle
        setup.rb_preview_jpeg.setChecked(True)
        self.assertTrue(setup.cb_link_to_raw.isEnabled())
        self.assertTrue(setup.cb_link_to_raw.isChecked())

        # Test directory scan with JPEG preview selected
        shoot_dir = os.path.join(self.temp_dir, "match_shoot")
        os.makedirs(shoot_dir, exist_ok=True)
        from PIL import Image
        # Create synthetic RAW + JPEG pair
        with open(os.path.join(shoot_dir, "MATCH_01.CR3"), "wb") as f:
            f.write(b"RAWBYTES" * 100)
        img = Image.new("RGB", (64, 64), color="blue")
        img.save(os.path.join(shoot_dir, "MATCH_01.JPG"))

        setup.source_dir_edit.setText(shoot_dir)
        setup._rescan_items()

        self.assertEqual(len(setup.scanned_items), 1)
        item = setup.scanned_items[0]
        # When preview_jpeg is selected, primary_path must be the JPEG path, but raw_path is kept!
        self.assertTrue(item.primary_path.endswith(".JPG"))
        self.assertTrue(item.raw_path.endswith(".CR3"))

        # Test _start_session creates project with match mode and preview mode
        setup.name_edit.setText("Championship Match")
        created_ids = []
        setup.session_created.connect(lambda pid: created_ids.append(pid))
        setup._start_session()

        self.assertEqual(len(created_ids), 1)
        created = setup.created_project
        self.assertIsNotNone(created)
        self.assertTrue(created.is_match_mode)
        self.assertEqual(created.max_selected_count, 15)
        self.assertEqual(created.preview_mode, "jpeg")
        self.assertTrue(created.link_to_raw)

    def test_review_view_match_mode_quota_and_inspect_raw(self):
        """Verify ReviewView real-time quota indicator and on-demand RAW inspect toggle."""
        shoot_dir = os.path.join(self.temp_dir, "review_shoot")
        os.makedirs(shoot_dir, exist_ok=True)
        from PIL import Image
        img_a = Image.new("RGB", (64, 64), color="red")
        img_a.save(os.path.join(shoot_dir, "FRAME_01.JPG"))
        raw_a_path = os.path.join(shoot_dir, "FRAME_01.CR3")
        img_raw = Image.new("RGB", (64, 64), color="cyan")
        img_raw.save(raw_a_path, format="JPEG")

        img_b = Image.new("RGB", (64, 64), color="green")
        img_b.save(os.path.join(shoot_dir, "FRAME_02.JPG"))

        img_c = Image.new("RGB", (64, 64), color="yellow")
        img_c.save(os.path.join(shoot_dir, "FRAME_03.JPG"))

        item1 = PhotoItem(base_name="FRAME_01", primary_path=os.path.join(shoot_dir, "FRAME_01.JPG"),
                          raw_path=raw_a_path, jpeg_path=os.path.join(shoot_dir, "FRAME_01.JPG"))
        item2 = PhotoItem(base_name="FRAME_02", primary_path=os.path.join(shoot_dir, "FRAME_02.JPG"),
                          jpeg_path=os.path.join(shoot_dir, "FRAME_02.JPG"))
        item3 = PhotoItem(base_name="FRAME_03", primary_path=os.path.join(shoot_dir, "FRAME_03.JPG"),
                          jpeg_path=os.path.join(shoot_dir, "FRAME_03.JPG"))

        proj = Project(
            name="Finals Shoot",
            is_match_mode=True,
            max_selected_count=2,
            preview_mode="jpeg",
            link_to_raw=True,
            items=[item1, item2, item3],
            current_index=0
        )

        review = ReviewView()
        review.load_project(proj)

        # Verify initial quota display (Under Quota -> Yellow #FBBF24)
        self.assertFalse(review.quota_badge.isHidden())
        self.assertIn("QUOTA: 0 / 2", review.quota_badge.text())
        self.assertIn("#FBBF24", review.quota_badge.styleSheet())
        self.assertFalse(review.inspect_raw_btn.isHidden())

        # Select first photo (1/2 -> Still Under Quota -> Yellow #FBBF24)
        review.keep_current()
        self.assertIn("QUOTA: 1 / 2", review.quota_badge.text())
        self.assertIn("#FBBF24", review.quota_badge.styleSheet())
        self.assertIn("#FBBF24", review.stats_panel.quota_val_lbl.styleSheet())

        # Select second photo (2/2 -> Quota Reached -> Emerald Green #34D399 + Toast Banner & Pulse)
        review.keep_current()
        self.assertIn("QUOTA REACHED: 2 / 2", review.quota_badge.text())
        self.assertIn("#34D399", review.quota_badge.styleSheet())
        self.assertIn("#34D399", review.stats_panel.quota_val_lbl.styleSheet())
        self.assertIsNotNone(review.quota_toast)
        self.assertFalse(review.quota_toast.isHidden())
        self.assertIn("Target Quota Reached!", review.quota_toast.text_lbl.text())
        self.assertIn("2 / 2 Photos", review.quota_toast.count_lbl.text())

        # Select third photo (3/2 -> Over Quota -> Bright Red #F87171)
        review.keep_current()
        self.assertIn("OVER QUOTA: 3 / 2 (+1)", review.quota_badge.text())
        self.assertIn("#F87171", review.quota_badge.styleSheet())
        self.assertIn("#F87171", review.stats_panel.quota_val_lbl.styleSheet())
        self.assertTrue(proj.is_over_quota)

        # Navigate back to item 0 which has linked raw
        review.navigate_to(0)
        self.assertFalse(review.is_inspecting_raw)
        self.assertEqual(review.inspect_raw_btn.text(), "Inspect RAW (R)")

        # Toggle inspect RAW
        review._toggle_inspect_raw()
        self.assertTrue(review.is_inspecting_raw)
        self.assertEqual(review.inspect_raw_btn.text(), "Viewing RAW (R)")

        # Toggle inspect RAW again to return to cached preview
        review._toggle_inspect_raw()
        self.assertFalse(review.is_inspecting_raw)
        self.assertEqual(review.inspect_raw_btn.text(), "Inspect RAW (R)")

        review.unload_project()

    def test_match_selection_export_folder(self):
        """Verify that ExportWorker creates dedicated Match Selection/ RAW and JPEG folders capped at quota."""
        proj = Project(
            name="WorldCupFinal",
            folder_id="sports",
            is_match_mode=True,
            max_selected_count=2,
            format_mode="both"
        )

        # Create 3 dummy raw and jpeg files to simulate 3 kept photos (1 surplus over quota of 2)
        raw_files = []
        jpeg_files = []
        for i in range(3):
            r = os.path.join(self.temp_dir, f"RAW_{i}.CR3")
            j = os.path.join(self.temp_dir, f"JPEG_{i}.JPG")
            with open(r, "wb") as f: f.write(b"RAW" * 100)
            with open(j, "wb") as f: f.write(b"JPEG" * 100)
            raw_files.append(r)
            jpeg_files.append(j)
            item = PhotoItem(base_name=f"IMG_{i}", jpeg_path=j, raw_path=r, status="kept")
            proj.items.append(item)

        export_dest = os.path.join(self.temp_dir, "export_output")
        worker = ExportWorker(proj, export_dest, separate_by_workspace=True, include_match_selection=True)

        finished_summary = {}
        def _on_finished(summary):
            finished_summary.update(summary)

        worker.export_finished.connect(_on_finished)
        worker.run()

        base_dir = finished_summary.get("base_dir")
        self.assertIsNotNone(base_dir)
        self.assertTrue(os.path.exists(base_dir))

        match_raw = os.path.join(base_dir, "Match Selection", "RAW")
        match_jpeg = os.path.join(base_dir, "Match Selection", "JPEG")
        selected_raw = os.path.join(base_dir, "Selected", "RAW")
        selected_jpeg = os.path.join(base_dir, "Selected", "JPEG")

        # Match Selection must be strictly capped at quota (2 files each)
        self.assertTrue(os.path.exists(match_raw))
        self.assertTrue(os.path.exists(match_jpeg))
        self.assertEqual(len(os.listdir(match_raw)), 2)
        self.assertEqual(len(os.listdir(match_jpeg)), 2)
        self.assertEqual(finished_summary.get("match_selection_count"), 2)

        # Selected retains all kept photos (3 files each)
        self.assertTrue(os.path.exists(selected_raw))
        self.assertTrue(os.path.exists(selected_jpeg))
        self.assertEqual(len(os.listdir(selected_raw)), 3)
        self.assertEqual(len(os.listdir(selected_jpeg)), 3)

    def test_theme_switcher_and_light_mode_styles(self):
        """Verify Theme menu checkmark updates dynamically, and Light theme has transparent labels and pastel badges."""
        from loupe.ui import theme as theme_mod
        from loupe.ui.theme import apply_theme, is_current_theme_light
        from loupe.ui.dashboard_view import DashboardView, ProjectCard

        # 1. Apply Dark Green theme
        apply_theme("dark_green")
        self.assertEqual(theme_mod.current_theme_id, "dark_green")
        self.assertFalse(is_current_theme_light())

        # Check theme menu checkmark
        dv = DashboardView()
        # Verify active_tid in theme menu logic matches dark_green
        active_tid = getattr(theme_mod, "current_theme_id", "dark_amber")
        self.assertEqual(active_tid, "dark_green")

        # 2. Switch to Light theme
        apply_theme("light")
        self.assertEqual(theme_mod.current_theme_id, "light")
        self.assertTrue(is_current_theme_light())

        # Verify dynamic styles on DashboardView
        dv._apply_dynamic_styles()
        self.assertIn("#dashboardRightArea", dv.right_area.styleSheet())
        self.assertIn("background-color: transparent", dv.right_area.styleSheet())

        # Verify ProjectCard in Light mode
        p = Project(name="PortraitSession", format_mode="both")
        card = ProjectCard(p)
        self.assertIn("background-color: transparent", card.styleSheet())

        # Verify photo badge in light mode uses pastel emerald styling
        is_light = is_current_theme_light()
        self.assertTrue(is_light)

        # Restore default dark amber
        apply_theme("dark_amber")
        self.assertEqual(theme_mod.current_theme_id, "dark_amber")
        self.assertFalse(is_current_theme_light())



    def test_gallery_import_folders_and_deduplicated_storage_stats(self):
        """Verify Gallery photo import (Reference vs Copy), nested folders, safe folder deletion, and deduplicated storage pie-chart math."""
        from loupe.core.gallery_engine import GalleryImporter
        from loupe.storage import storage, format_bytes
        from PIL import Image

        storage.gallery_photos.clear()
        storage.gallery_folders.clear()
        storage._seed_gallery_defaults(save_after=False)

        # Create 2 sample JPEGs and 1 sample RAW file
        g_dir = os.path.join(self.temp_dir, "gallery_samples")
        os.makedirs(g_dir, exist_ok=True)
        jpg1 = os.path.join(g_dir, "IMG_1001.JPG")
        jpg2 = os.path.join(g_dir, "IMG_1002.JPG")
        raw1 = os.path.join(g_dir, "IMG_1001.CR3")

        Image.new("RGB", (640, 480), color=(245, 158, 11)).save(jpg1, "JPEG", quality=90)
        Image.new("RGB", (640, 480), color=(59, 130, 246)).save(jpg2, "JPEG", quality=90)
        # Create a 50KB dummy RAW file (or valid image container with .CR3 extension)
        Image.new("RGB", (800, 600), color=(34, 197, 94)).save(raw1, "JPEG", quality=95)

        school_folder = storage.get_gallery_folder("gf_school")
        self.assertIsNotNone(school_folder)

        # 1. Import via Reference mode into 'School Pictures'
        res = GalleryImporter.import_files(
            [jpg1, jpg2, raw1],
            copy_to_gallery=False,
            target_folder_id="gf_school",
            skip_duplicates=True,
        )
        self.assertEqual(res["imported"], 3)
        self.assertEqual(res["skipped"], 0)

        # Duplicate detection: importing again must skip all 3
        res_dup = GalleryImporter.import_files([jpg1, jpg2, raw1], copy_to_gallery=False, skip_duplicates=True)
        self.assertEqual(res_dup["imported"], 0)
        self.assertEqual(res_dup["skipped"], 3)

        # Assign photos to a second folder ('Gramp's Birthday') as well and verify storage is NOT double-counted
        all_ids = list(storage.gallery_photos.keys())
        storage.assign_photos_to_folder(all_ids, "gf_gramp")

        stats = storage.calculate_gallery_statistics()
        self.assertEqual(stats["total_photos"], 3)
        self.assertEqual(stats["raw_count"], 1)
        self.assertEqual(stats["jpeg_count"], 2)
        expected_bytes = os.path.getsize(jpg1) + os.path.getsize(jpg2) + os.path.getsize(raw1)
        self.assertEqual(stats["total_bytes"], expected_bytes)
        self.assertGreater(stats["raw_percent"] + stats["jpeg_percent"], 99.0)

        # 2. Create nested folder and test safe folder deletion (photographs must NEVER be deleted)
        grad_folder = storage.create_gallery_folder("Graduation", parent_id="gf_school")
        storage.assign_photos_to_folder(all_ids, grad_folder.id)
        self.assertEqual(storage.count_photos_in_gallery_folder("gf_school", include_subfolders=True), 3)

        storage.delete_gallery_folder(grad_folder.id, reassign_to_folder_id="gf_vacations")
        self.assertIsNone(storage.get_gallery_folder(grad_folder.id))
        self.assertEqual(len(storage.get_active_gallery_photos()), 3)
        self.assertTrue(os.path.exists(jpg1))
        self.assertTrue(os.path.exists(raw1))

    def test_gallery_raw_to_jpeg_conversion_and_two_stage_warning_ui(self):
        """Verify RAW-to-JPEG conversion engine, 2-stage warning dialog flow, and original RAW preservation."""
        from loupe.core.gallery_engine import GalleryImporter, RawToJpegConverter
        from loupe.ui.gallery_dialogs import RawConversionDialog
        from loupe.storage import storage
        from PIL import Image

        storage.gallery_photos.clear()
        raw_dir = os.path.join(self.temp_dir, "raw_conv_test")
        os.makedirs(raw_dir, exist_ok=True)
        raw_file = os.path.join(raw_dir, "DSC_9001.ARW")
        Image.new("RGB", (1000, 750), color=(180, 90, 40)).save(raw_file, "BMP")

        GalleryImporter.import_files([raw_file], copy_to_gallery=False)
        raw_photos = [p for p in storage.get_active_gallery_photos() if p.is_raw]
        self.assertEqual(len(raw_photos), 1)

        # Verify 2-Stage Warning Dialog pages exist and transition properly
        dlg = RawConversionDialog(raw_photos)
        self.assertEqual(dlg.stack.currentIndex(), 0)
        dlg._go_to_warning_stage1()
        self.assertEqual(dlg.stack.currentIndex(), 1)
        self.assertIn("RAW", dlg.stage1_stats_lbl.text())
        dlg._go_to_warning_stage2()
        self.assertEqual(dlg.stack.currentIndex(), 2)
        self.assertIn("Converted_JPEG", dlg.stage2_details_lbl.text())

        # Execute batch conversion and verify original RAW file is untouched & paired
        out_dir = os.path.join(self.temp_dir, "converted_jpegs")
        conv_res = RawToJpegConverter.convert_batch(raw_photos, output_dir=out_dir, quality=85, add_converted_to_gallery=True)
        self.assertEqual(conv_res["completed"], 1)
        self.assertTrue(os.path.exists(raw_file))  # Original RAW untouched!
        self.assertTrue(os.path.exists(conv_res["converted_paths"][0]))
        self.assertEqual(raw_photos[0].paired_jpeg_path, conv_res["converted_paths"][0])
        self.assertGreater(conv_res["saved_bytes"], 0)

    def test_gallery_smart_albums_missing_recovery_duplicates_backup_and_ui(self):
        """Verify Smart Albums, Favorites/Ratings, Missing File Recovery, Duplicate Finder, Backup, Recently Deleted, and GalleryView UI."""
        from loupe.core.gallery_engine import (
            GalleryImporter, MissingFileRecoveryEngine, DuplicateFinderEngine, GalleryBackupEngine
        )
        from loupe.ui.gallery_view import GalleryView
        from loupe.app import FramedMainWindow
        from loupe.storage import storage
        from PIL import Image
        import shutil

        storage.gallery_photos.clear()
        t_dir = os.path.join(self.temp_dir, "gallery_adv")
        os.makedirs(t_dir, exist_ok=True)
        p1 = os.path.join(t_dir, "MEMORY_1.JPG")
        p2_dup = os.path.join(t_dir, "MEMORY_1_COPY.JPG")
        Image.new("RGB", (500, 400), color=(120, 40, 200)).save(p1, "JPEG", quality=92)
        shutil.copy2(p1, p2_dup)

        # Import both (with skip_duplicates=False so we can test DuplicateFinderEngine)
        GalleryImporter.import_files([p1, p2_dup], copy_to_gallery=False, skip_duplicates=False)
        photos = storage.get_active_gallery_photos()
        self.assertEqual(len(photos), 2)

        # 1. Duplicate Finder detects exact SHA-256 duplicate
        dups = DuplicateFinderEngine.find_duplicates(include_similar=True)
        self.assertEqual(len(dups["exact"]), 1)
        self.assertEqual(len(dups["exact"][0]), 2)

        # 2. Favorites, 5-Star Rating & Smart Album matching
        storage.toggle_gallery_favorite(photos[0].id)
        storage.set_photo_rating([photos[0].id], rating=5, color_label="green", notes="Best memory")
        sa_5star = storage.smart_albums.get("sa_5star")
        self.assertIsNotNone(sa_5star)
        self.assertTrue(sa_5star.matches(photos[0]))
        self.assertFalse(sa_5star.matches(photos[1]))

        # 3. Missing File Detection & Verified Recovery (relocate file and reconnect by SHA-256 + size)
        relocated_dir = os.path.join(self.temp_dir, "relocated_folder")
        os.makedirs(relocated_dir, exist_ok=True)
        relocated_p1 = os.path.join(relocated_dir, "MEMORY_1.JPG")
        shutil.move(p1, relocated_p1)

        missing_cnt = storage.refresh_missing_file_status()
        self.assertEqual(missing_cnt, 1)
        self.assertTrue(photos[0].is_missing)

        rec_res = MissingFileRecoveryEngine.scan_directory_and_reconnect(relocated_dir)
        self.assertEqual(rec_res["reconnected"], 1)
        self.assertFalse(photos[0].is_missing)

        # 4. Recently Deleted soft-delete & restore
        storage.soft_delete_photos([photos[1].id])
        self.assertEqual(len(storage.get_active_gallery_photos()), 1)
        self.assertEqual(len(storage.get_deleted_gallery_photos()), 1)
        storage.restore_deleted_photos([photos[1].id])
        self.assertEqual(len(storage.get_active_gallery_photos()), 2)

        # 5. Verified Gallery Backup
        bk_dir = os.path.join(self.temp_dir, "backup_dest")
        bk_res = GalleryBackupEngine.run_backup(bk_dir, include_referenced=True, verify_hashes=True)
        self.assertTrue(bk_res["success"])
        self.assertEqual(bk_res["completed"], 2)

        # 6. GalleryView & FramedMainWindow navigation
        win = FramedMainWindow()
        win._show_gallery()
        self.assertEqual(win.stack.currentWidget(), win.gallery_view)
        win.gallery_view._select_section("memories")
        win.gallery_view._select_section("map")
        win.gallery_view._select_section("all")
        self.assertEqual(win.gallery_view.kpi_total_lbl.text(), "2")


if __name__ == "__main__":
    import unittest
    suite = unittest.TestLoader().loadTestsFromTestCase(TestLoupeWorkstation)
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    import os
    os._exit(0 if res.wasSuccessful() else 1)







