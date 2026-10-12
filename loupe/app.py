"""Main application coordinator integrating Dashboard, Photo Review, Video Review, Tour, and Settings."""

import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QWidget, QMessageBox, QDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from loupe.config import config
from loupe.storage import storage
from loupe.ui.theme import load_application_fonts, get_application_stylesheet, setup_dark_palette
from loupe.ui.icons import render_icon
from loupe.ui.dashboard_view import DashboardView
from loupe.ui.review_view import ReviewView
from loupe.ui.video_review_view import VideoReviewView
from loupe.ui.session_setup_dialog import SessionSetupDialog
from loupe.ui.video_session_dialog import VideoSessionDialog
from loupe.ui.settings_dialog import SettingsDialog
from loupe.ui.export_dialog import ExportDialog
from loupe.ui.video_export_dialog import VideoExportDialog
from loupe.ui.tour_overlay import TourDialog

class FramedMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Framed — Photographer & Videographer Workstation")
        self.resize(1280, 840)
        self.setMinimumSize(960, 640)

        # Set application window icon
        app_icon = render_icon("loupe", 32, "#E59533")
        self.setWindowIcon(app_icon)

        # Stacked central container
        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)

        # Views
        self.dashboard_view = DashboardView(self)
        self.review_view = ReviewView(self)
        self.video_review_view = VideoReviewView(self)

        self.stack.addWidget(self.dashboard_view)        # Index 0: Dashboard
        self.stack.addWidget(self.review_view)           # Index 1: Photo Culling View
        self.stack.addWidget(self.video_review_view)     # Index 2: Video Sorting View

        self._connect_signals()

        # Check first launch tour
        if not config.get("has_completed_tour", False):
            self.dashboard_view.layout().activate()
            tour = TourDialog(self)
            tour.show()

        # Check for software updates in background if enabled
        if config.get("auto_check_updates", True) and config.get("update_manifest_url", ""):
            self._check_for_updates_background()

    def _check_for_updates_background(self):
        url = config.get("update_manifest_url", "").strip()
        if url:
            from loupe.core.updater import UpdateCheckWorker
            self.bg_update_worker = UpdateCheckWorker(url, self)
            self.bg_update_worker.check_finished.connect(self._on_background_update_check_result)
            self.bg_update_worker.start()

    def _on_background_update_check_result(self, has_update: bool, info, error_msg: str):
        if has_update and info:
            from loupe.ui.update_dialog import UpdateDialog
            dlg = UpdateDialog(info, self)
            dlg.exec()

    def _connect_signals(self):
        # Dashboard signals
        self.dashboard_view.new_session_requested.connect(self._open_new_session_dialog)
        self.dashboard_view.open_project_requested.connect(self._open_project)
        self.dashboard_view.export_project_requested.connect(self._export_project)
        self.dashboard_view.open_settings_requested.connect(self._open_settings)

        # Photo Review screen signals
        self.review_view.back_to_dashboard.connect(self._show_dashboard)
        self.review_view.export_requested.connect(self._export_project)

        # Video Review screen signals
        self.video_review_view.back_to_dashboard.connect(self._show_dashboard)
        self.video_review_view.export_requested.connect(self._export_project)

    def _open_new_session_dialog(self):
        # Determine mode from dashboard
        if self.dashboard_view.current_media_mode == "video":
            dlg = VideoSessionDialog(self)
        else:
            dlg = SessionSetupDialog(self)

        if dlg.exec() == QDialog.Accepted and dlg.created_project:
            self._open_project(dlg.created_project.id)

    def _open_project(self, project_id: str):
        proj = storage.get_project_by_id(project_id)
        if not proj:
            QMessageBox.warning(self, "Session Not Found", "The requested session could not be found.")
            return

        if getattr(proj, "media_type", "photo") == "video":
            self.video_review_view.load_project(proj)
            self.stack.setCurrentIndex(2)
            self.video_review_view.setFocus()
        else:
            self.review_view.load_project(proj)
            self.stack.setCurrentIndex(1)
            self.review_view.setFocus()

    def _show_dashboard(self):
        self.dashboard_view.refresh()
        self.stack.setCurrentIndex(0)

    def _export_project(self, project_id: str):
        proj = storage.get_project_by_id(project_id)
        if not proj:
            return

        if getattr(proj, "media_type", "photo") == "video":
            dlg = VideoExportDialog(proj, self)
            dlg.exec()
        else:
            dlg = ExportDialog(proj, self)
            dlg.exec()

    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.restart_tour_requested.connect(self._restart_tour)
        dlg.exec()

    def _restart_tour(self):
        tour = TourDialog(self)
        tour.exec()


# Alias for backward compatibility
LoupeMainWindow = FramedMainWindow
