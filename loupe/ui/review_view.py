"""Review screen culling workstation with full-resolution rendering, loupe zoom/pan, EXIF panel, and pause/resume."""

import os
from typing import Optional, List, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsRectItem, QProgressBar
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QImage, QPixmap, QWheelEvent, QKeyEvent, QPainter, QBrush, QColor, QFont
)
from loupe.config import config
from loupe.models import Project, PhotoItem
from loupe.storage import storage
from loupe.core.preloader import PreloadManager
from loupe.core.metadata import MetadataExtractor
from loupe.ui.stats_panel import StatsPanel
from loupe.ui.not_accepted_dialog import NotAcceptedDialog
from loupe.ui.preload_overlay import PreloadOverlay
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_SUBTLE,
    COLOR_BORDER_DISTINCT, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_STATUS_KEPT, COLOR_STATUS_REJECTED,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon

class PhotoCanvas(QGraphicsView):
    """High-performance graphics view with smooth wheel zoom, panning, fit-to-window, and 100% actual pixels."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item: Optional[QGraphicsPixmapItem] = None

        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("background-color: #0E0F11; border: none;")

        self._zoom_factor = 1.0

    def set_image(self, qimage: QImage, start_zoomed_in: bool = False, zoom_level: float = 2.0):
        self.scene.clear()
        if qimage.isNull():
            return

        pix = QPixmap.fromImage(qimage)
        self.pixmap_item = self.scene.addPixmap(pix)
        self.scene.setSceneRect(QRectF(pix.rect()))

        if start_zoomed_in:
            # Open at set zoom level focused on top-left
            self.resetTransform()
            self.scale(zoom_level, zoom_level)
            # Center near top-left quadrant
            target_pt = QPointF(pix.width() * 0.2, pix.height() * 0.2)
            self.centerOn(target_pt)
        else:
            self.fit_to_window()

    def fit_to_window(self):
        if self.pixmap_item and not self.pixmap_item.pixmap().isNull():
            self.resetTransform()
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def actual_pixels(self):
        """100% 1:1 view."""
        if self.pixmap_item and not self.pixmap_item.pixmap().isNull():
            self.resetTransform()
            self.centerOn(self.pixmap_item)

    def wheelEvent(self, event: QWheelEvent):
        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor
        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)


class ReviewView(QWidget):
    """Main culling and photo inspection workstation."""
    back_to_dashboard = Signal()
    export_requested = Signal(str)  # project_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Optional[Project] = None
        self.preload_manager = PreloadManager(self)
        self.preload_manager.image_ready.connect(self._on_image_ready)
        self.preload_manager.batch_progress.connect(self._on_preload_progress)
        self.preload_manager.batch_completed.connect(self._on_preload_batch_completed)

        self.preload_overlay = PreloadOverlay(self)
        self.is_preloading_paused = False
        self.target_nav_index: Optional[int] = None
        self.undo_stack: List[tuple] = []  # (index, old_status)

        self._init_ui()
        self.setFocusPolicy(Qt.StrongFocus)

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Top Workstation Navigation Bar
        top_bar = QFrame()
        top_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border-bottom: 1px solid {COLOR_BORDER_DISTINCT};
            }}
        """)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 10, 16, 10)
        top_layout.setSpacing(14)

        # Back to Dashboard button
        self.back_btn = QPushButton("Dashboard")
        self.back_btn.setIcon(render_icon("arrow_left", 14, COLOR_TEXT_PRIMARY))
        self.back_btn.clicked.connect(self._handle_escape_request)
        top_layout.addWidget(self.back_btn)

        # Project Info
        proj_info_layout = QVBoxLayout()
        proj_info_layout.setSpacing(2)
        self.project_title_lbl = QLabel("Session Name")
        self.project_title_lbl.setFont(get_display_font(15, bold=True))
        self.current_filename_lbl = QLabel("DSC08492.ARW")
        self.current_filename_lbl.setFont(get_mono_font(11))
        self.current_filename_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        proj_info_layout.addWidget(self.project_title_lbl)
        proj_info_layout.addWidget(self.current_filename_lbl)
        top_layout.addLayout(proj_info_layout)

        top_layout.addStretch()

        # Canvas Zoom Tools
        self.fit_btn = QPushButton("Fit (F)")
        self.fit_btn.setIcon(render_icon("fit", 14, COLOR_TEXT_PRIMARY))
        self.fit_btn.clicked.connect(self._fit_current_image)
        top_layout.addWidget(self.fit_btn)

        self.actual_btn = QPushButton("100% (Z)")
        self.actual_btn.setIcon(render_icon("actual_size", 14, COLOR_TEXT_PRIMARY))
        self.actual_btn.clicked.connect(self._actual_pixels_current_image)
        top_layout.addWidget(self.actual_btn)

        # Stats toggle
        self.stats_toggle_btn = QPushButton("Stats (I)")
        self.stats_toggle_btn.setIcon(render_icon("info", 14, COLOR_ACCENT))
        self.stats_toggle_btn.clicked.connect(self._toggle_stats_panel)
        top_layout.addWidget(self.stats_toggle_btn)

        # Export button
        self.export_btn = QPushButton("Export")
        self.export_btn.setIcon(render_icon("export", 14, COLOR_TEXT_PRIMARY))
        self.export_btn.clicked.connect(self._on_export_clicked)
        top_layout.addWidget(self.export_btn)

        root_layout.addWidget(top_bar)

        # Central Area: Canvas + Stats Side Panel
        center_area = QHBoxLayout()
        center_area.setContentsMargins(0, 0, 0, 0)
        center_area.setSpacing(0)

        # Left Canvas Container with floating decision badge
        canvas_container = QWidget()
        canvas_layout = QVBoxLayout(canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)

        self.canvas = PhotoCanvas(self)
        canvas_layout.addWidget(self.canvas)

        # Floating Decision Badge overlay
        self.badge_lbl = QLabel(canvas_container)
        self.badge_lbl.setFont(get_mono_font(12, bold=True))
        self.badge_lbl.setStyleSheet(f"""
            background-color: {COLOR_BG_SURFACE};
            color: {COLOR_TEXT_MUTED};
            border: 1px solid {COLOR_BORDER_DISTINCT};
            padding: 5px 12px;
            border-radius: 2px;
        """)
        self.badge_lbl.move(24, 20)
        self.badge_lbl.setText("UNREVIEWED")

        center_area.addWidget(canvas_container, stretch=1)

        # Right Side Panel (Stats & EXIF)
        self.stats_panel = StatsPanel(self)
        self.stats_panel.open_not_accepted_requested.connect(self._open_not_accepted_tray)
        center_area.addWidget(self.stats_panel)

        root_layout.addLayout(center_area, stretch=1)

        # Bottom Culling Deck & Filmstrip
        bottom_bar = QFrame()
        bottom_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border-top: 1px solid {COLOR_BORDER_DISTINCT};
            }}
        """)
        bottom_layout = QVBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(20, 10, 20, 10)
        bottom_layout.setSpacing(8)

        # Main Culling Action Buttons
        controls_row = QHBoxLayout()
        controls_row.setSpacing(14)

        self.prev_btn = QPushButton("Previous (A)")
        self.prev_btn.setIcon(render_icon("arrow_left", 14, COLOR_TEXT_PRIMARY))
        self.prev_btn.setMinimumHeight(40)
        self.prev_btn.clicked.connect(self.go_previous)
        controls_row.addWidget(self.prev_btn)

        # REJECT BUTTON
        self.reject_btn = QPushButton("Not Accepted (S)")
        self.reject_btn.setObjectName("rejectButton")
        self.reject_btn.setIcon(render_icon("cross", 14, "#F87171"))
        self.reject_btn.setMinimumHeight(40)
        self.reject_btn.clicked.connect(self.reject_current)
        controls_row.addWidget(self.reject_btn)

        # KEEP BUTTON
        self.keep_btn = QPushButton("Keep Photo (W)")
        self.keep_btn.setObjectName("keepButton")
        self.keep_btn.setIcon(render_icon("check", 14, "#7BE4A2"))
        self.keep_btn.setMinimumHeight(40)
        self.keep_btn.clicked.connect(self.keep_current)
        controls_row.addWidget(self.keep_btn)

        self.next_btn = QPushButton("Next (D)")
        self.next_btn.setIcon(render_icon("arrow_right", 14, COLOR_TEXT_PRIMARY))
        self.next_btn.setMinimumHeight(40)
        self.next_btn.clicked.connect(self.go_next)
        controls_row.addWidget(self.next_btn)

        self.undo_btn = QPushButton("Undo (Ctrl+Z)")
        self.undo_btn.setIcon(render_icon("restore", 12, COLOR_TEXT_SECONDARY))
        self.undo_btn.setMinimumHeight(40)
        self.undo_btn.clicked.connect(self.undo_last_decision)
        controls_row.addWidget(self.undo_btn)

        bottom_layout.addLayout(controls_row)

        # Status & Tally Row
        status_row = QHBoxLayout()
        self.counter_lbl = QLabel("Frame 1 of 1")
        self.counter_lbl.setFont(get_mono_font(12, bold=True))
        status_row.addWidget(self.counter_lbl)

        status_row.addStretch()

        self.tally_lbl = QLabel("Kept: 0  |  Not Accepted: 0  |  Remaining: 0")
        self.tally_lbl.setFont(get_mono_font(11))
        self.tally_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        status_row.addWidget(self.tally_lbl)

        bottom_layout.addLayout(status_row)
        root_layout.addWidget(bottom_bar)

    def load_project(self, project: Project):
        self.project = project
        self.project_title_lbl.setText(project.name)
        self.undo_stack.clear()

        # Initialize preloader
        start_idx = max(0, min(project.current_index, len(project.items) - 1)) if project.items else 0
        self.preload_manager.initialize_session(project.items, project.batch_size, start_idx)

        # Initial preload batch (e.g. first 16 photos)
        if project.items:
            batch_id = start_idx // project.batch_size
            b_start = batch_id * project.batch_size
            b_end = min(len(project.items) - 1, b_start + project.batch_size - 1)
            
            # Show pause overlay for initial load
            self.is_preloading_paused = True
            self.target_nav_index = start_idx
            self.preload_overlay.set_batch_info(b_start, b_end, start_idx)
            self.preload_overlay.show()
            self.preload_manager.request_batch(batch_id, list(range(b_start, b_end + 1)))
        else:
            self._display_current_photo()

    def _on_preload_progress(self, completed: int, total: int, speed: float, eta: float, fname: str):
        if self.is_preloading_paused:
            self.preload_overlay.update_progress(completed, total, speed, eta, fname)

    def _on_preload_batch_completed(self, batch_id: int):
        if self.is_preloading_paused:
            self.is_preloading_paused = False
            self.preload_overlay.hide()
            if self.target_nav_index is not None:
                self.project.current_index = self.target_nav_index
                self.target_nav_index = None
                self._display_current_photo()

    def _on_image_ready(self, index: int, qimg: QImage):
        if self.project and index == self.project.current_index and not self.is_preloading_paused:
            self._render_image(qimg)

    def _display_current_photo(self):
        if not self.project or not self.project.items:
            self.counter_lbl.setText("0 of 0")
            self.current_filename_lbl.setText("No photos in session")
            self.tally_lbl.setText("Kept: 0  |  Not Accepted: 0  |  Remaining: 0")
            return

        idx = self.project.current_index
        item = self.project.items[idx]

        self.counter_lbl.setText(f"Frame {idx + 1} of {len(self.project.items)}")
        
        fmt_str = "RAW + JPEG (Synced)" if item.has_both and self.project.sync_pairs else ("RAW" if item.raw_path else "JPEG")
        self.current_filename_lbl.setText(f"{item.base_name} • {fmt_str}")

        self.tally_lbl.setText(
            f"Kept: {self.project.kept_count}  |  Not Accepted: {self.project.rejected_count}  |  Remaining: {self.project.pending_count}"
        )
        self.stats_panel.update_rejected_count(self.project.rejected_count)

        # Update Badge
        if item.status == "kept":
            self.badge_lbl.setText("KEPT")
            self.badge_lbl.setStyleSheet(f"""
                background-color: #172D20;
                color: #7BE4A2;
                border: 1px solid {COLOR_STATUS_KEPT};
                padding: 5px 12px;
                border-radius: 2px;
                font-weight: 600;
            """)
        elif item.status == "rejected":
            self.badge_lbl.setText("NOT ACCEPTED")
            self.badge_lbl.setStyleSheet(f"""
                background-color: #2F1717;
                color: #F87171;
                border: 1px solid {COLOR_STATUS_REJECTED};
                padding: 5px 12px;
                border-radius: 2px;
                font-weight: 600;
            """)
        else:
            self.badge_lbl.setText("UNREVIEWED")
            self.badge_lbl.setStyleSheet(f"""
                background-color: {COLOR_BG_SURFACE};
                color: {COLOR_TEXT_MUTED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                padding: 5px 12px;
                border-radius: 2px;
            """)

        # Extract and update EXIF telemetry
        if not item.metadata:
            item.metadata = MetadataExtractor.extract(item.primary_path)
        self.stats_panel.update_metadata(item.metadata)

        # Render cached image if available
        qimg = self.preload_manager.get_image(idx)
        if qimg:
            self._render_image(qimg)

    def _render_image(self, qimg: QImage):
        start_zoom = config.get("start_zoomed_in", False)
        zoom_lvl = config.get("zoom_start_level", 2.0)
        self.canvas.set_image(qimg, start_zoomed_in=start_zoom, zoom_level=zoom_lvl)

    def navigate_to(self, target_idx: int, direction: int = 1):
        if not self.project or not self.project.items:
            return
        if not (0 <= target_idx < len(self.project.items)):
            return

        # Always update project current index to destination
        self.project.current_index = target_idx

        # Check if navigating requires a batch pause
        needs_pause, b_start, b_end = self.preload_manager.check_navigation(target_idx, direction)
        if needs_pause:
            self.is_preloading_paused = True
            self.target_nav_index = target_idx
            self.preload_overlay.set_batch_info(b_start, b_end, target_idx)
            self.preload_overlay.show()
        else:
            self._display_current_photo()

    def go_next(self):
        if self.project and self.project.current_index < len(self.project.items) - 1:
            self.navigate_to(self.project.current_index + 1, direction=1)

    def go_previous(self):
        if self.project and self.project.current_index > 0:
            self.navigate_to(self.project.current_index - 1, direction=-1)

    def keep_current(self):
        if not self.project or not self.project.items:
            return
        idx = self.project.current_index
        item = self.project.items[idx]
        self.undo_stack.append((idx, item.status))
        item.status = "kept"
        self._display_current_photo()
        self.go_next()

    def reject_current(self):
        if not self.project or not self.project.items:
            return
        idx = self.project.current_index
        item = self.project.items[idx]
        self.undo_stack.append((idx, item.status))
        item.status = "rejected"
        self._display_current_photo()
        self.go_next()

    def undo_last_decision(self):
        if not self.undo_stack or not self.project:
            return
        idx, old_status = self.undo_stack.pop()
        if 0 <= idx < len(self.project.items):
            self.project.items[idx].status = old_status
            self.navigate_to(idx, direction=-1)

    def _fit_current_image(self):
        self.canvas.fit_to_window()

    def _actual_pixels_current_image(self):
        self.canvas.actual_pixels()

    def _toggle_stats_panel(self):
        self.stats_panel.setVisible(not self.stats_panel.isVisible())

    def _open_not_accepted_tray(self):
        if not self.project:
            return
        rejected = [it for it in self.project.items if it.status == "rejected"]
        dlg = NotAcceptedDialog(rejected, self)
        dlg.item_restored.connect(self._restore_rejected_item)
        dlg.exec()
        self._display_current_photo()

    def _restore_rejected_item(self, item_id: str):
        if not self.project:
            return
        for it in self.project.items:
            if it.id == item_id:
                it.status = "kept"
                break
        self._display_current_photo()

    def _on_export_clicked(self):
        if self.project:
            self.export_requested.emit(self.project.id)

    def _handle_escape_request(self):
        if not self.project:
            self.back_to_dashboard.emit()
            return

        confirm = QMessageBox.question(
            self,
            "Pause Culling Session",
            f"Pause session '{self.project.name}'?\n\n"
            f"Your current frame ({self.project.current_index + 1} of {len(self.project.items)}), "
            f"decisions, and settings will be saved so you can resume exactly where you stopped.",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            # Save session state
            storage.save_project(self.project)
            self.preload_manager.cleanup()
            self.back_to_dashboard.emit()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        key_str = event.text().upper()

        # Remappable keys from config
        keep_key = config.get_key_binding("keep").upper()
        reject_key = config.get_key_binding("reject").upper()
        prev_key = config.get_key_binding("prev").upper()
        next_key = config.get_key_binding("next").upper()

        if key == Qt.Key_Escape:
            self._handle_escape_request()
            event.accept()
        elif event.modifiers() & Qt.ControlModifier and key == Qt.Key_Z:
            self.undo_last_decision()
            event.accept()
        elif key_str == keep_key:
            self.keep_current()
            event.accept()
        elif key_str == reject_key:
            self.reject_current()
            event.accept()
        elif key_str == prev_key or key == Qt.Key_Left:
            self.go_previous()
            event.accept()
        elif key_str == next_key or key == Qt.Key_Right:
            self.go_next()
            event.accept()
        elif key == Qt.Key_F:
            self._fit_current_image()
            event.accept()
        elif key == Qt.Key_Z:
            self._actual_pixels_current_image()
            event.accept()
        elif key == Qt.Key_I:
            self._toggle_stats_panel()
            event.accept()
        else:
            super().keyPressEvent(event)
