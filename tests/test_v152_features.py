"""Unit tests for FRAMED v1.5.2 features:
- 5-second safe deletion countdown
- Multi-project selection & floating bulk actions
- Sequential in-order batch export
- Clean gallery folders (Personal, School, Work) & subfolder deletion
- Missing files synchronization & removal
"""

import os
import shutil
import tempfile
import unittest
from PySide6.QtWidgets import QApplication

from loupe.models import Project, PhotoItem, GalleryFolder, GalleryPhoto
from loupe.storage import StorageManager
from loupe.ui.dashboard_view import DashboardView, ProjectCard, DashboardModalOverlay
from loupe.ui.gallery_dialogs import DeleteGalleryFolderDialog
from loupe.ui.gallery_view import GalleryView
from loupe.ui.batch_export_dialog import BatchExportDialog, BatchExportWorker

_app = QApplication.instance() or QApplication([])


class TestV152Features(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="framed_v152_test_")
        self.db_path = os.path.join(self.test_dir, "database.json")
        self.storage = StorageManager(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_seed_clean_defaults(self):
        """Verify that default fresh seed contains ONLY Personal and Work workspace folders, and Personal, School, Work gallery folders."""
        ws_folders = list(self.storage.folders.values())
        self.assertEqual(len(ws_folders), 2)
        self.assertEqual({f.name for f in ws_folders}, {"Personal", "Work"})

        g_folders = list(self.storage.gallery_folders.values())
        self.assertEqual(len(g_folders), 3)
        self.assertEqual({f.name for f in g_folders}, {"Personal", "School", "Work"})

    def test_delete_gallery_folder_and_subfolder(self):
        """Verify creating and deleting a subfolder in gallery."""
        school = next(f for f in self.storage.gallery_folders.values() if f.name == "School")
        sub = self.storage.create_gallery_folder("Class of 2026", parent_id=school.id)
        self.assertIn(sub.id, self.storage.gallery_folders)
        self.assertEqual(sub.parent_id, school.id)

        # Delete subfolder
        deleted = self.storage.delete_gallery_folder(sub.id)
        self.assertTrue(deleted)
        self.assertNotIn(sub.id, self.storage.gallery_folders)

    def test_five_second_countdown_on_delete_gallery_folder_dialog(self):
        """Verify DeleteGalleryFolderDialog starts with disabled button and counts down."""
        work = next(f for f in self.storage.gallery_folders.values() if f.name == "Work")
        dlg = DeleteGalleryFolderDialog(work, 0)

        # Button should be disabled initially with (5s) countdown text
        self.assertFalse(dlg.b_del.isEnabled())
        self.assertIn("(5s)", dlg.b_del.text())

        # Simulate 5 ticks
        for i in range(5):
            dlg._on_del_tick()

        # Button should now be enabled and countdown removed
        self.assertTrue(dlg.b_del.isEnabled())
        self.assertEqual(dlg.b_del.text(), "Delete Folder Safely")
        dlg.close()

    def test_five_second_countdown_on_modal_overlay(self):
        """Verify DashboardModalOverlay.show_confirm_delete has 5s countdown when destructive."""
        overlay = DashboardModalOverlay()
        confirmed = False
        def _cb():
            nonlocal confirmed
            confirmed = True

        overlay.show_confirm_delete("Delete Session", "Are you sure?", _cb, confirm_text="Delete", is_destructive=True)
        self.assertTrue(hasattr(overlay, "btn_confirm"))
        self.assertFalse(overlay.btn_confirm.isEnabled())
        self.assertIn("(5s)", overlay.btn_confirm.text())
        self.assertTrue(hasattr(overlay, "_del_timer"))
        self.assertTrue(overlay._del_timer.isActive())
        overlay.hide()

    def test_multi_project_selection_and_bulk_actions(self):
        """Verify ProjectCard selection toggle and DashboardView bulk actions."""
        p1 = Project(name="Shoot 1", media_type="photo", shoot_date="2026-10-01")
        p2 = Project(name="Shoot 2", media_type="photo", shoot_date="2026-10-02")
        self.storage.save_project(p1)
        self.storage.save_project(p2)
        
        card1 = ProjectCard(p1, view_mode="list")
        card2 = ProjectCard(p2, view_mode="list")
        self.assertFalse(card1.is_selected)

        card1.set_selected(True)
        self.assertTrue(card1.is_selected)
        self.assertTrue(card1.select_cb.isChecked())

        dash = DashboardView()
        dash.selected_project_ids.add(p1.id)
        dash.selected_project_ids.add(p2.id)
        dash._update_bulk_bar()
        self.assertFalse(dash.bulk_bar.isHidden())
        self.assertIn("2 Selected", dash.bulk_count_lbl.text())

        dash.resize(1280, 840)
        dash.right_area.resize(1040, 800)
        dash._position_bulk_bar()
        self.assertGreaterEqual(dash.bulk_bar.width(), dash.bulk_bar.sizeHint().width())
        self.assertFalse(dash.btn_bulk_resume.icon().isNull())
        self.assertFalse(dash.btn_bulk_export.icon().isNull())

        dash._deselect_all()
        self.assertEqual(len(dash.selected_project_ids), 0)
        self.assertTrue(dash.bulk_bar.isHidden())

    def test_sequential_batch_export_worker(self):
        """Verify BatchExportWorker copies projects sequentially in order into structured folders."""
        # Create test source files
        src_dir = os.path.join(self.test_dir, "source")
        os.makedirs(src_dir, exist_ok=True)
        img1 = os.path.join(src_dir, "IMG_0001.JPG")
        img2 = os.path.join(src_dir, "IMG_0002.JPG")
        with open(img1, "wb") as f: f.write(b"PHOTO1" * 100)
        with open(img2, "wb") as f: f.write(b"PHOTO2" * 100)

        p1 = Project(name="Project A", items=[
            PhotoItem(base_name="IMG_0001", primary_path=img1, jpeg_path=img1, status="kept")
        ])
        p2 = Project(name="Project B", items=[
            PhotoItem(base_name="IMG_0002", primary_path=img2, jpeg_path=img2, status="kept")
        ])

        out_dir = os.path.join(self.test_dir, "exported_batch")
        worker = BatchExportWorker([p1, p2], out_dir, separate_by_workspace=False)
        worker.run()

        # Both should exist in destination
        p1_dst = os.path.join(out_dir, "Project A", "Selected", "JPEG", "IMG_0001.JPG")
        p2_dst = os.path.join(out_dir, "Project B", "Selected", "JPEG", "IMG_0002.JPG")
        self.assertTrue(os.path.exists(p1_dst))
        self.assertTrue(os.path.exists(p2_dst))


if __name__ == "__main__":
    unittest.main()
