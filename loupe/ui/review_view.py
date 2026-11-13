"""Review screen culling workstation with full-resolution rendering, loupe zoom/pan, EXIF panel, and pause/resume."""

import os
from typing import Optional, List, Dict, Tuple
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QDialog, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsItem, QGraphicsRectItem, QProgressBar
)
from PySide6.QtCore import Qt, Signal, QRect, QRectF, QPointF, QPoint, QPropertyAnimation, QVariantAnimation, QEasingCurve, QTimer
from PySide6.QtGui import (
    QGuiApplication, QImage, QPixmap, QWheelEvent, QKeyEvent, QPainter, QBrush, QColor, QFont
)
from PySide6.QtWidgets import QGraphicsOpacityEffect

try:
    from PySide6.QtOpenGLWidgets import QOpenGLWidget
    from PySide6.QtOpenGL import QOpenGLTextureBlitter
    from PySide6.QtGui import QOpenGLContext
    _HAS_QT_OPENGL = True
except Exception:
    QOpenGLWidget = None  # type: ignore
    QOpenGLTextureBlitter = None  # type: ignore
    QOpenGLContext = None  # type: ignore
    _HAS_QT_OPENGL = False

from loupe.config import config
from loupe.models import Project, PhotoItem
from loupe.storage import storage
from loupe.core.preloader import PreloadManager
from loupe.core.vram_cache import VRAMTextureEntry
from loupe.core.metadata import MetadataExtractor
from loupe.ui.stats_panel import StatsPanel
from loupe.ui.not_accepted_dialog import NotAcceptedDialog
from loupe.ui.preload_overlay import PreloadOverlay
from loupe.ui.finish_session_dialog import FinishSessionDialog
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_SUBTLE,
    COLOR_BORDER_DISTINCT, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_STATUS_KEPT, COLOR_STATUS_REJECTED,
    COLOR_STATUS_MAYBE, get_display_font, get_body_font, get_mono_font, theme_manager
)
from loupe.ui.icons import render_icon

class QuotaToastBanner(QFrame):
    """Floating HUD toast banner notifying photographer when match photo quota is reached."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("quotaToastBanner")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("""
            QFrame#quotaToastBanner {
                background-color: rgba(6, 78, 59, 0.94);
                border: 1px solid #10B981;
                border-radius: 20px;
                padding: 6px 18px;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(10)

        self.icon_lbl = QLabel("🎯")
        self.icon_lbl.setFont(get_display_font(13))
        layout.addWidget(self.icon_lbl)

        self.text_lbl = QLabel("Target Quota Reached!")
        self.text_lbl.setFont(get_display_font(12, bold=True))
        self.text_lbl.setStyleSheet("color: #FFFFFF;")
        layout.addWidget(self.text_lbl)

        self.count_lbl = QLabel("15 / 15 Photos")
        self.count_lbl.setFont(get_mono_font(12, bold=True))
        self.count_lbl.setStyleSheet("color: #6EE7B7;")
        layout.addWidget(self.count_lbl)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)
        self.hide()

        self.slide_anim = None
        self.fade_anim = None
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._fade_out)

    def show_toast(self, selected: int, total: int):
        self.text_lbl.setText("Target Quota Reached!")
        self.count_lbl.setText(f"{selected} / {total} Photos")
        self.adjustSize()

        if self.parent():
            parent_w = self.parent().width()
            target_x = max(20, (parent_w - self.width()) // 2)
        else:
            target_x = 100

        start_y = -self.height()
        target_y = 54  # Float gracefully just beneath top navigation bar

        self.move(target_x, start_y)
        self.show()
        self.raise_()

        # Slide down animation
        self.slide_anim = QPropertyAnimation(self, b"pos")
        self.slide_anim.setDuration(350)
        self.slide_anim.setStartValue(QPoint(target_x, start_y))
        self.slide_anim.setEndValue(QPoint(target_x, target_y))
        self.slide_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.slide_anim.start()

        # Fade in animation
        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(250)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

        # Auto-dismiss after 2.5s
        self.hide_timer.stop()
        self.hide_timer.start(2500)

    def _fade_out(self):
        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(400)
        self.fade_anim.setStartValue(self.opacity_effect.opacity())
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.setEasingCurve(QEasingCurve.InQuad)
        self.fade_anim.finished.connect(self.hide)
        self.fade_anim.start()


def _is_gl_platform_supported() -> bool:
    """Return True when Qt OpenGL widget rendering is safe and supported on the active platform."""
    if not _HAS_QT_OPENGL or QOpenGLWidget is None or QOpenGLContext is None:
        return False
    env_plat = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    if env_plat in ("offscreen", "minimal", "vnc"):
        return False
    try:
        plat = QGuiApplication.platformName().strip().lower()
        if plat in ("offscreen", "minimal", "vnc"):
            return False
    except Exception:
        return False
    return True


class VRAMTextureGraphicsItem(QGraphicsItem):
    """QGraphicsItem rendering a GPU-resident VRAMTextureEntry via QOpenGLTextureBlitter with software fallback."""

    def __init__(self, entry: VRAMTextureEntry, blitter_getter=None, parent=None):
        super().__init__(parent)
        self._entry = entry
        self._blitter_getter = blitter_getter
        self._bounds = QRectF(0.0, 0.0, float(max(1, entry.width)), float(max(1, entry.height)))

    def boundingRect(self) -> QRectF:
        return self._bounds

    def paint(self, painter: QPainter, option, widget=None):
        entry = self._entry
        tex = entry.texture
        if (
            tex is not None
            and QOpenGLContext is not None
            and QOpenGLTextureBlitter is not None
            and QOpenGLContext.currentContext() is not None
        ):
            try:
                if tex.isCreated():
                    target_rect = painter.worldTransform().mapRect(self._bounds)
                    if widget is not None:
                        vp_rect = widget.rect()
                    else:
                        dev = painter.device()
                        dpr = max(1.0, float(dev.devicePixelRatioF())) if hasattr(dev, "devicePixelRatioF") else 1.0
                        vp_rect = QRect(0, 0, max(1, int(dev.width() / dpr)), max(1, int(dev.height() / dpr)))
                    target_xform = QOpenGLTextureBlitter.targetTransform(target_rect, vp_rect)
                    blitter = self._blitter_getter() if self._blitter_getter else None
                    if blitter is not None:
                        painter.beginNativePainting()
                        try:
                            if not blitter.isCreated():
                                blitter.create()
                            if blitter.isCreated():
                                target = tex.target()
                                target_gl = int(target.value) if hasattr(target, "value") else int(target)
                                blitter.bind(target_gl)
                                blitter.blit(
                                    tex.textureId(),
                                    target_xform,
                                    QOpenGLTextureBlitter.Origin.OriginTopLeft,
                                )
                                blitter.release()
                                return
                        finally:
                            painter.endNativePainting()
            except Exception:
                pass

        if entry.fallback_qimage is not None and not entry.fallback_qimage.isNull():
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawImage(self._bounds, entry.fallback_qimage)


if _HAS_QT_OPENGL and QOpenGLWidget is not None:
    class _PhotoGLViewport(QOpenGLWidget):
        """OpenGL viewport widget for PhotoCanvas with managed QOpenGLTextureBlitter lifecycle."""
        gl_initialized = Signal(object, object)  # QOpenGLContext, QSurface

        def __init__(self, parent=None):
            super().__init__(parent)
            self._blitter: Optional[QOpenGLTextureBlitter] = None

        def initializeGL(self):
            ctx = self.context()
            if ctx is None or not ctx.isValid():
                return
            if self._blitter is None and QOpenGLTextureBlitter is not None:
                self._blitter = QOpenGLTextureBlitter()
                self._blitter.create()
            try:
                ctx.aboutToBeDestroyed.connect(self._destroy_blitter)
            except Exception:
                pass
            self.gl_initialized.emit(ctx, ctx.surface())

        def get_blitter(self):
            if self._blitter is None and QOpenGLTextureBlitter is not None:
                self._blitter = QOpenGLTextureBlitter()
            return self._blitter

        def _destroy_blitter(self):
            if self._blitter is not None:
                try:
                    if self._blitter.isCreated():
                        self._blitter.destroy()
                except Exception:
                    pass
                self._blitter = None
else:
    _PhotoGLViewport = None  # type: ignore


class PhotoCanvas(QGraphicsView):
    """High-performance graphics view with OpenGL viewport (when available), smooth zoom/pan, and VRAM/RAM rendering."""
    gl_context_ready = Signal(object, object)  # QOpenGLContext, QSurface

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item: Optional[QGraphicsPixmapItem] = None
        self.vram_item: Optional[VRAMTextureGraphicsItem] = None
        self._gl_viewport = None

        if _is_gl_platform_supported() and _PhotoGLViewport is not None:
            try:
                gl_vp = _PhotoGLViewport(self)
                gl_vp.gl_initialized.connect(self.gl_context_ready.emit)
                self.setViewport(gl_vp)
                self._gl_viewport = gl_vp
            except Exception:
                self._gl_viewport = None

        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self._apply_canvas_background()
        theme_manager.theme_changed.connect(self._apply_canvas_background)

    def _apply_canvas_background(self, _theme_id=None):
        import loupe.ui.theme as _theme_mod
        bg = _theme_mod.COLOR_BG_BASE
        brush = QBrush(QColor(bg))
        self.setBackgroundBrush(brush)
        self.scene.setBackgroundBrush(brush)
        self.setStyleSheet(f"background-color: {bg}; border: none;")
        self.viewport().update()
    @property
    def is_gl_active(self) -> bool:
        if self._gl_viewport is None:
            return False
        try:
            ctx = self._gl_viewport.context()
            return bool(self._gl_viewport.isValid() and ctx is not None and ctx.isValid())
        except Exception:
            return False

    def get_gl_context_and_surface(self) -> Tuple[Optional[object], Optional[object]]:
        if self._gl_viewport is None:
            return None, None
        try:
            ctx = self._gl_viewport.context()
            if ctx is not None and ctx.isValid():
                return ctx, ctx.surface()
        except Exception:
            pass
        return None, None

    def _get_gl_blitter(self):
        if self._gl_viewport is not None:
            return self._gl_viewport.get_blitter()
        return None

    def _active_item(self) -> Optional[QGraphicsItem]:
        if self.pixmap_item is not None and not self.pixmap_item.pixmap().isNull():
            return self.pixmap_item
        if self.vram_item is not None:
            return self.vram_item
        return None

    def clear(self):
        """Purge any current pixmap/VRAM item and clear the scene completely."""
        self.scene.clear()
        self.pixmap_item = None
        self.vram_item = None
        self.resetTransform()
        self.viewport().update()
    def _apply_initial_view(self, width: int, height: int, start_zoomed_in: bool, zoom_level: float):
        if start_zoomed_in:
            self.resetTransform()
            self.scale(zoom_level, zoom_level)
            target_pt = QPointF(width * 0.2, height * 0.2)
            self.centerOn(target_pt)
        else:
            self.fit_to_window()

    def set_image(self, qimage: QImage, start_zoomed_in: bool = False, zoom_level: float = 2.0):
        self.scene.clear()
        self.pixmap_item = None
        self.vram_item = None
        if qimage is None or qimage.isNull():
            return

        pix = QPixmap.fromImage(qimage)
        self.pixmap_item = self.scene.addPixmap(pix)
        self.scene.setSceneRect(QRectF(pix.rect()))
        self._apply_initial_view(pix.width(), pix.height(), start_zoomed_in, zoom_level)
        self.viewport().update()
    def set_vram_entry(self, entry: Optional[VRAMTextureEntry], start_zoomed_in: bool = False, zoom_level: float = 2.0):
        """Display a GPU-resident VRAMTextureEntry (or fall back seamlessly to its QImage)."""
        self.scene.clear()
        self.pixmap_item = None
        self.vram_item = None
        if entry is None:
            return

        if entry.texture is not None and self.is_gl_active:
            self.vram_item = VRAMTextureGraphicsItem(entry, blitter_getter=self._get_gl_blitter)
            self.scene.addItem(self.vram_item)
            self.scene.setSceneRect(QRectF(0.0, 0.0, float(entry.width), float(entry.height)))
            self._apply_initial_view(entry.width, entry.height, start_zoomed_in, zoom_level)
            self.viewport().update()
            return

        if entry.fallback_qimage is not None and not entry.fallback_qimage.isNull():
            self.set_image(entry.fallback_qimage, start_zoomed_in=start_zoomed_in, zoom_level=zoom_level)

    def fit_to_window(self):
        item = self._active_item()
        if item is not None:
            self.resetTransform()
            self.fitInView(item, Qt.KeepAspectRatio)

    def actual_pixels(self):
        """100% 1:1 view."""
        item = self._active_item()
        if item is not None:
            self.resetTransform()
            self.centerOn(item)

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
        self.preload_manager.cache_stats_changed.connect(self._on_cache_stats_changed)

        self.preload_overlay = PreloadOverlay(self)
        self.preload_overlay.afk_requested.connect(self._on_afk_requested)
        self.preload_overlay.sort_now_requested.connect(self._on_sort_now_requested)
        self.is_afk_mode = False
        self.is_preloading_paused = False
        self._paused_for_jump = False
        self._pause_span_start = 0
        self._pause_span_end = 0
        self.target_nav_index: Optional[int] = None
        self.undo_stack: List[tuple] = []  # (index, old_status)
        self.is_inspecting_raw = False

        self._latest_speed_mb_s: float = 0.0
        self._last_ram_used_mb: int = 0
        self._last_vram_used_mb: int = 0
        self._last_total_cached: int = 0
        self._last_vram_count: int = 0
        self._last_ram_count: int = 0

        self._init_ui()
        self.canvas.gl_context_ready.connect(self._on_canvas_gl_ready)
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

        # Green Finish Session button (Top Left)
        self.finish_btn = QPushButton("Finish Session")
        self.finish_btn.setObjectName("finishButton")
        self.finish_btn.setIcon(render_icon("check", 14, "#FFFFFF"))
        self.finish_btn.clicked.connect(self._handle_finish_session)
        self.finish_btn.setVisible(False)
        top_layout.addWidget(self.finish_btn)

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

        # Non-blocking Background Buffer Status Pill
        self.buffer_status_lbl = QLabel("")
        self.buffer_status_lbl.setFont(get_mono_font(10, bold=True))
        self.buffer_status_lbl.setVisible(False)
        top_layout.addWidget(self.buffer_status_lbl)

        # Match Mode Quota Badge & Toast
        self.quota_toast = QuotaToastBanner(self)
        self._prev_quota_selected = None
        self._badge_anim = None
        self.quota_badge = QLabel("")
        self.quota_badge.setFont(get_mono_font(11, bold=True))
        self.quota_badge.setVisible(False)
        top_layout.addWidget(self.quota_badge)

        # Inspect RAW toggle button (for sessions using JPEG preview with linked RAW)
        self.inspect_raw_btn = QPushButton("Inspect RAW (R)")
        self.inspect_raw_btn.setFont(get_mono_font(11, bold=True))
        self.inspect_raw_btn.setIcon(render_icon("loupe", 14, COLOR_ACCENT))
        self.inspect_raw_btn.setVisible(False)
        self.inspect_raw_btn.clicked.connect(self._toggle_inspect_raw)
        top_layout.addWidget(self.inspect_raw_btn)

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
        self.stats_panel.start_zoomed_changed.connect(self._on_start_zoomed_changed)
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

        # MAYBE BUTTON
        self.maybe_btn = QPushButton("Maybe (E)")
        self.maybe_btn.setObjectName("maybeButton")
        self.maybe_btn.setIcon(render_icon("maybe", 14, "#FBBF24"))
        self.maybe_btn.setMinimumHeight(40)
        self.maybe_btn.clicked.connect(self.maybe_current)
        controls_row.addWidget(self.maybe_btn)

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
        self.refresh_key_bindings()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "preload_overlay") and self.preload_overlay:
            self.preload_overlay.setGeometry(self.rect())
        if hasattr(self, "quota_toast") and self.quota_toast and self.quota_toast.isVisible():
            target_x = max(20, (self.width() - self.quota_toast.width()) // 2)
            self.quota_toast.move(target_x, self.quota_toast.y())

    def refresh_key_bindings(self):
        keep_key = config.get_key_binding("keep").upper()
        reject_key = config.get_key_binding("reject").upper()
        maybe_key = config.get_key_binding("maybe", "E").upper()
        prev_key = config.get_key_binding("prev").upper()
        next_key = config.get_key_binding("next").upper()

        self.prev_btn.setText(f"Previous ({prev_key})")
        self.reject_btn.setText(f"Not Accepted ({reject_key})")
        self.maybe_btn.setText(f"Maybe ({maybe_key})")
        self.keep_btn.setText(f"Keep Photo ({keep_key})")
        self.next_btn.setText(f"Next ({next_key})")

    def _on_canvas_gl_ready(self, gl_ctx, gl_surf):
        self.preload_manager.set_gl_context(gl_ctx, gl_surf)

    @staticmethod
    def _format_mem_mb(val_mb: int) -> str:
        if val_mb >= 1024:
            return f"{val_mb / 1024.0:.1f} GB"
        return f"{max(0, int(val_mb))} MB"

    def _on_cache_stats_changed(
        self,
        ram_used_mb: int,
        vram_used_mb: int,
        total_cached: int,
        vram_count: int,
        ram_count: int,
    ):
        self._last_ram_used_mb = ram_used_mb
        self._last_vram_used_mb = vram_used_mb
        self._last_total_cached = total_cached
        self._last_vram_count = vram_count
        self._last_ram_count = ram_count
        self._update_buffer_status_pill()

    def _update_buffer_status_pill(self):
        if not self.project or not self.project.items:
            self.buffer_status_lbl.setVisible(False)
            self.buffer_status_lbl.setText("")
            return

        self.buffer_status_lbl.setVisible(True)
        total_items = len(self.project.items)
        cached_count = self.preload_manager.get_ready_count()
        mode = (getattr(self.project, "memory_mode", "ram") or "ram").lower()

        if mode == "vram":
            mem_str = f"VRAM {self._format_mem_mb(self._last_vram_used_mb)}"
        elif mode == "mixed":
            mem_str = f"VRAM {self._format_mem_mb(self._last_vram_used_mb)} + RAM {self._format_mem_mb(self._last_ram_used_mb)}"
        else:
            mem_str = f"RAM {self._format_mem_mb(self._last_ram_used_mb)}"

        is_streaming = bool(getattr(self.preload_manager, "is_streaming", False))
        if not is_streaming and cached_count >= min(total_items, self.project.batch_size):
            self.buffer_status_lbl.setText(f"✓ Buffered {cached_count}/{total_items} • {mem_str}")
            self.buffer_status_lbl.setStyleSheet(f"""
                background-color: #0D2B20;
                color: #34D399;
                border: 1px solid #059669;
                padding: 4px 10px;
                border-radius: 4px;
            """)
        else:
            speed_str = f" • {self._latest_speed_mb_s:.0f} MB/s" if self._latest_speed_mb_s > 0 else ""
            self.buffer_status_lbl.setText(f"Buffer: {cached_count}/{total_items} • {mem_str}{speed_str}")
            self.buffer_status_lbl.setStyleSheet(f"""
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                padding: 4px 10px;
                border-radius: 4px;
            """)

    def _on_start_zoomed_changed(self, enabled: bool, zoom_level: float):
        if self.project and self.project.items:
            idx = self.project.current_index
            vram_entry = self.preload_manager.get_vram_entry(idx)
            if vram_entry is not None:
                self.canvas.set_vram_entry(vram_entry, start_zoomed_in=enabled, zoom_level=zoom_level)
                return
            qimg = self.preload_manager.get_image(idx)
            if qimg and not qimg.isNull():
                self.canvas.set_image(qimg, start_zoomed_in=enabled, zoom_level=zoom_level)

    def unload_project(self):
        """Completely unload active session and purge all cached buffers and display items."""
        if self.project:
            storage.save_project(self.project)
        self.project = None
        self.preload_manager.cleanup()
        self.canvas.clear()
        self.target_nav_index = None
        self.is_preloading_paused = False
        self._paused_for_jump = False
        self._pause_span_start = 0
        self._pause_span_end = 0
        self._latest_speed_mb_s = 0.0
        self._last_ram_used_mb = 0
        self._last_vram_used_mb = 0
        self._last_total_cached = 0
        self._last_vram_count = 0
        self._last_ram_count = 0
        self.preload_overlay.hide()
        self.buffer_status_lbl.setVisible(False)
        self.buffer_status_lbl.setText("")
        self.undo_stack.clear()
        self.project_title_lbl.setText("")
        self.counter_lbl.setText("0 of 0")
        self.current_filename_lbl.setText("No photos in session")
        self.tally_lbl.setText("Kept: 0  |  Maybe: 0  |  Not Accepted: 0  |  Remaining: 0")
        self.badge_lbl.setText("UNREVIEWED")
        self.finish_btn.setVisible(False)
        if hasattr(self, "stats_panel"):
            self.stats_panel.reset_telemetry()

    def load_project(self, project: Project):
        # 1. Fully unload and purge previous session
        self.unload_project()

        self.project = project
        self._prev_quota_selected = project.selected_count if project else 0
        if hasattr(self, "quota_toast"):
            self.quota_toast.hide()
        self.project_title_lbl.setText(project.name)
        self.undo_stack.clear()
        self.refresh_key_bindings()

        # Sync stats panel zoom controls from config
        self.stats_panel.start_zoomed_cb.blockSignals(True)
        self.stats_panel.zoom_slider.blockSignals(True)
        self.stats_panel.start_zoomed_cb.setChecked(config.get("start_zoomed_in", False))
        curr_lvl = int(config.get("zoom_start_level", 2.0) * 100)
        self.stats_panel.zoom_slider.setValue(curr_lvl)
        self.stats_panel.zoom_lvl_lbl.setText(f"{curr_lvl}%")
        self.stats_panel.start_zoomed_cb.blockSignals(False)
        self.stats_panel.zoom_slider.blockSignals(False)

        # Initialize preloader with 3-tier RAM / VRAM / Mixed capacity math
        start_idx = max(0, min(project.current_index, len(project.items) - 1)) if project.items else 0
        memory_mode = (getattr(project, "memory_mode", "ram") or "ram").strip().lower()
        if memory_mode not in ("ram", "vram", "mixed"):
            memory_mode = "ram"
        ram_mb = getattr(project, "ram_allocation_mb", 2048) or 2048
        vram_mb = getattr(project, "vram_allocation_mb", 0) or 0
        avg_photo_mb = 18 if getattr(project, "preview_mode", "raw") == "jpeg" else 75

        if memory_mode == "vram":
            calc_capacity = max(4, int(vram_mb / avg_photo_mb)) if vram_mb > 0 else max(4, int(ram_mb / avg_photo_mb))
        elif memory_mode == "mixed":
            ram_cap = max(4, int(ram_mb / avg_photo_mb))
            vram_cap = max(0, int(vram_mb / avg_photo_mb))
            calc_capacity = max(4, ram_cap + vram_cap)
        else:
            calc_capacity = max(4, int(ram_mb / avg_photo_mb))

        effective_batch_size = max(getattr(project, "batch_size", 16), calc_capacity)
        project.batch_size = effective_batch_size

        gl_ctx, gl_surf = self.canvas.get_gl_context_and_surface()
        self.preload_manager.initialize_session(
            project.items,
            effective_batch_size,
            start_idx,
            ram_allocation_mb=ram_mb,
            memory_mode=memory_mode,
            vram_allocation_mb=vram_mb,
            avg_photo_mb=avg_photo_mb,
            gl_context=gl_ctx,
            gl_surface=gl_surf,
        )

        # Immediately update labels & metadata for the loaded session
        self._display_current_photo()
        self._update_buffer_status_pill()

        # Initial preload batch
        if project.items:
            batch_id = start_idx // project.batch_size
            b_start = batch_id * project.batch_size
            b_end = min(len(project.items) - 1, b_start + project.batch_size - 1)

            # Show pause overlay for initial load (unlocks Sort Now at min(10, batch_count))
            self.is_preloading_paused = True
            self._paused_for_jump = False
            self._pause_span_start = b_start
            self._pause_span_end = b_end
            self.target_nav_index = start_idx
            self.preload_overlay.set_batch_info(
                b_start,
                b_end,
                start_idx,
                total_items=len(project.items),
                memory_mode=memory_mode,
            )
            self.preload_overlay.show()
            self.preload_manager.request_batch(batch_id, list(range(b_start, b_end + 1)), priority_index=start_idx)

    def _on_preload_progress(self, completed: int, total: int, speed: float, eta: float, fname: str):
        self._latest_speed_mb_s = speed
        self._update_buffer_status_pill()
        if self.is_preloading_paused:
            if self._paused_for_jump and self.project:
                span_ready = self.preload_manager.get_ready_count(self._pause_span_start, self._pause_span_end)
                span_total = max(1, self._pause_span_end - self._pause_span_start + 1)
                self.preload_overlay.update_progress(span_ready, span_total, speed, eta, fname)
            else:
                self.preload_overlay.update_progress(completed, total, speed, eta, fname)

    def _on_sort_now_requested(self):
        """Dismiss loading overlay early and begin culling while PreloadWorker streams remaining photos."""
        self.is_preloading_paused = False
        self._paused_for_jump = False
        self.preload_overlay.hide()
        if self.target_nav_index is not None and self.project:
            self.project.current_index = self.target_nav_index
            self.target_nav_index = None
        self._display_current_photo()
        self._update_buffer_status_pill()

    def _on_afk_requested(self):
        self.is_afk_mode = True
        w = self.window()
        if w:
            w.showMinimized()

    def _on_preload_batch_completed(self, batch_id: int):
        self._update_buffer_status_pill()
        if self.is_preloading_paused:
            self.is_preloading_paused = False
            self._paused_for_jump = False
            self.preload_overlay.hide()
            if getattr(self, "is_afk_mode", False):
                self.is_afk_mode = False
                w = self.window()
                if w:
                    w.showNormal()
                    w.activateWindow()
                    w.raise_()
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass
            if self.target_nav_index is not None and self.project:
                self.project.current_index = self.target_nav_index
                self.target_nav_index = None
            self._display_current_photo()

    def _on_image_ready(self, index: int, qimg: QImage):
        if self.project and index == self.project.current_index:
            vram_entry = self.preload_manager.get_vram_entry(index)
            if vram_entry is not None:
                self._render_vram_entry(vram_entry)
            else:
                self._render_image(qimg)

    def _display_current_photo(self):
        if not self.project or not self.project.items:
            self.counter_lbl.setText("0 of 0")
            self.current_filename_lbl.setText("No photos in session")
            self.tally_lbl.setText("Kept: 0  |  Maybe: 0  |  Not Accepted: 0  |  Remaining: 0")
            self.finish_btn.setVisible(False)
            self.canvas.clear()
            return

        idx = self.project.current_index
        item = self.project.items[idx]

        self.counter_lbl.setText(f"Frame {idx + 1} of {len(self.project.items)}")
        
        is_jpeg_linked = bool(
            item.raw_path and item.jpeg_path and getattr(self.project, "preview_mode", "") == "jpeg" and getattr(self.project, "link_to_raw", False)
        )
        if is_jpeg_linked:
            fmt_str = "JPEG Preview (Linked to RAW)"
        elif item.has_both and self.project.sync_pairs:
            fmt_str = "RAW + JPEG (Synced)"
        else:
            fmt_str = "RAW" if item.raw_path else "JPEG"
        self.current_filename_lbl.setText(f"{item.base_name} • {fmt_str}")

        tally_msg = f"Kept: {self.project.kept_count}  |  Maybe: {self.project.maybe_count}  |  Not Accepted: {self.project.rejected_count}  |  Remaining: {self.project.pending_count}"
        if getattr(self.project, "is_match_mode", False) and getattr(self.project, "max_selected_count", 0) > 0:
            tally_msg += f"  |  Quota: {self.project.selected_count}/{self.project.max_selected_count}"
        self.tally_lbl.setText(tally_msg)

        self.stats_panel.update_rejected_count(self.project.rejected_count)
        if getattr(self.project, "is_match_mode", False) and getattr(self.project, "max_selected_count", 0) > 0:
            self.stats_panel.update_match_quota(self.project.selected_count, self.project.max_selected_count)
        else:
            self.stats_panel.update_match_quota(0, 0)

        # Update Match Mode Quota Badge
        if getattr(self.project, "is_match_mode", False) and getattr(self.project, "max_selected_count", 0) > 0:
            max_limit = self.project.max_selected_count
            current_sel = self.project.selected_count
            self.quota_badge.setVisible(True)

            if current_sel > max_limit:
                # 3. Over Quota State: Bright Red Warning Capsule
                over = current_sel - max_limit
                self.quota_badge.setText(f"OVER QUOTA: {current_sel} / {max_limit} (+{over})")
                self.quota_badge.setStyleSheet(f"""
                    background-color: #381212;
                    color: #F87171;
                    border: 1px solid {COLOR_STATUS_REJECTED};
                    padding: 4px 10px;
                    border-radius: 3px;
                """)
            elif current_sel == max_limit:
                # 2. Quota Reached State: Vivid Emerald Green + Animation & Floating HUD Toast
                self.quota_badge.setText(f"QUOTA REACHED: {current_sel} / {max_limit}")
                self.quota_badge.setStyleSheet(f"""
                    background-color: #064E3B;
                    color: #34D399;
                    border: 1px solid #059669;
                    padding: 4px 10px;
                    border-radius: 3px;
                """)
                # Trigger pulse animation & HUD toast if newly reached
                if self._prev_quota_selected is not None and self._prev_quota_selected < max_limit:
                    self._animate_quota_reached(current_sel, max_limit)
            else:
                # 1. Under Quota State (Still in progress): Warm Amber / Yellow
                self.quota_badge.setText(f"QUOTA: {current_sel} / {max_limit}")
                self.quota_badge.setStyleSheet(f"""
                    background-color: #2E2208;
                    color: #FBBF24;
                    border: 1px solid #D97706;
                    padding: 4px 10px;
                    border-radius: 3px;
                """)

            self._prev_quota_selected = current_sel
        else:
            self.quota_badge.setVisible(False)
            self._prev_quota_selected = None

        # Update Inspect RAW button visibility
        has_linked_raw = bool(item.raw_path and os.path.exists(item.raw_path) and item.primary_path != item.raw_path)
        self.inspect_raw_btn.setVisible(has_linked_raw)
        if not self.is_inspecting_raw:
            self.inspect_raw_btn.setText("Inspect RAW (R)")
            self.inspect_raw_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_BG_ELEVATED};
                    border: 1px solid {COLOR_BORDER_DISTINCT};
                    border-radius: 3px;
                    color: {COLOR_TEXT_PRIMARY};
                    padding: 0 12px;
                }}
                QPushButton:hover {{
                    border-color: {COLOR_ACCENT};
                    color: {COLOR_ACCENT};
                }}
            """)

        # Check if all pictures are done: show the green Finish Session button on top left!
        all_done = bool(self.project and len(self.project.items) > 0 and self.project.pending_count == 0)
        self.finish_btn.setVisible(all_done)

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
        elif item.status in ("maybe", "similar"):
            self.badge_lbl.setText("MAYBE")
            self.badge_lbl.setStyleSheet(f"""
                background-color: #2D2314;
                color: #FBBF24;
                border: 1px solid {COLOR_STATUS_MAYBE};
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

        # Render cached image or VRAM texture if available, else clear canvas
        self._render_cached_index(idx)

    def _render_cached_index(self, idx: int):
        vram_entry = self.preload_manager.get_vram_entry(idx)
        if vram_entry is not None:
            self._render_vram_entry(vram_entry)
            return
        qimg = self.preload_manager.get_image(idx)
        if qimg and not qimg.isNull():
            self._render_image(qimg)
        else:
            self.canvas.clear()

    def _render_vram_entry(self, entry: VRAMTextureEntry):
        start_zoom = config.get("start_zoomed_in", False)
        zoom_lvl = config.get("zoom_start_level", 2.0)
        self.canvas.set_vram_entry(entry, start_zoomed_in=start_zoom, zoom_level=zoom_lvl)

    def _render_image(self, qimg: QImage):
        start_zoom = config.get("start_zoomed_in", False)
        zoom_lvl = config.get("zoom_start_level", 2.0)
        self.canvas.set_image(qimg, start_zoomed_in=start_zoom, zoom_level=zoom_lvl)

    def navigate_to(self, target_idx: int, direction: int = 1):
        if not self.project or not self.project.items:
            return
        if not (0 <= target_idx < len(self.project.items)):
            return

        # Always update project current index to destination and persist
        self.project.current_index = target_idx
        storage.save_project(self.project)

        # Reset on-demand raw inspection on new frame navigation
        self.is_inspecting_raw = False

        total_items = len(self.project.items)
        memory_mode = (getattr(self.project, "memory_mode", "ram") or "ram").lower()

        if self.preload_manager.is_cached(target_idx):
            # Target frame is already ready: enter immediately without pausing
            self.is_preloading_paused = False
            self._paused_for_jump = False
            self.preload_overlay.hide()

            if self.preload_manager.is_streaming:
                step = 1 if direction >= 0 else -1
                lookahead = [
                    target_idx + offset * step
                    for offset in range(10)
                    if 0 <= target_idx + offset * step < total_items
                ]
                if any(not self.preload_manager.is_cached(i) for i in lookahead):
                    self.preload_manager.reprioritize_around(target_idx, direction)
            else:
                self.preload_manager.check_navigation(target_idx, direction)

            self._display_current_photo()
            return

        # Target frame is NOT cached yet: reprioritize [target_idx .. target_idx+9] and pause
        if self.preload_manager.is_streaming:
            self.preload_manager.reprioritize_around(target_idx, direction)
            batch_id = target_idx // self.project.batch_size
            b_start = batch_id * self.project.batch_size
            b_end = min(total_items - 1, b_start + self.project.batch_size - 1)
        else:
            _, b_start, b_end = self.preload_manager.check_navigation(target_idx, direction)

        if direction >= 0:
            span_start = target_idx
            span_end = min(total_items - 1, max(b_end, target_idx))
        else:
            span_start = max(0, b_start)
            span_end = target_idx

        self.is_preloading_paused = True
        self._paused_for_jump = True
        self._pause_span_start = span_start
        self._pause_span_end = span_end
        self.target_nav_index = target_idx
        self.preload_overlay.set_batch_info(
            span_start,
            span_end,
            target_idx,
            total_items=total_items,
            memory_mode=memory_mode,
        )
        self.preload_overlay.show()

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
        storage.save_project(self.project)
        self._display_current_photo()
        self.go_next()

    def maybe_current(self):
        if not self.project or not self.project.items:
            return
        idx = self.project.current_index
        item = self.project.items[idx]
        self.undo_stack.append((idx, item.status))
        item.status = "maybe"
        storage.save_project(self.project)
        self._display_current_photo()
        self.go_next()

    def reject_current(self):
        if not self.project or not self.project.items:
            return
        idx = self.project.current_index
        item = self.project.items[idx]
        self.undo_stack.append((idx, item.status))
        item.status = "rejected"
        storage.save_project(self.project)
        self._display_current_photo()
        self.go_next()

    def _handle_finish_session(self):
        if not self.project:
            return
        dlg = FinishSessionDialog(self.project, self)
        if dlg.exec() == QDialog.Accepted:
            pid = self.project.id
            if dlg.choice == FinishSessionDialog.FINISH_NOW:
                self.unload_project()
                self.back_to_dashboard.emit()
            elif dlg.choice == FinishSessionDialog.FINISH_AND_EXPORT:
                self.unload_project()
                self.export_requested.emit(pid)
                self.back_to_dashboard.emit()

    def undo_last_decision(self):
        if not self.undo_stack or not self.project:
            return
        idx, old_status = self.undo_stack.pop()
        if 0 <= idx < len(self.project.items):
            self.project.items[idx].status = old_status
            storage.save_project(self.project)
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
        storage.save_project(self.project)
        self._display_current_photo()

    def _on_export_clicked(self):
        if self.project:
            storage.save_project(self.project)
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
            self.unload_project()
            self.back_to_dashboard.emit()

    def _animate_quota_reached(self, current_sel: int, max_limit: int):
        """Play pulse/glow pop animation on quota badge and show floating HUD toast."""
        if hasattr(self, "quota_toast"):
            self.quota_toast.show_toast(current_sel, max_limit)

        import math
        self._badge_anim = QVariantAnimation(self)
        self._badge_anim.setDuration(500)
        self._badge_anim.setStartValue(0.0)
        self._badge_anim.setEndValue(1.0)

        def _on_anim_step(val):
            pulse = math.sin(val * math.pi)
            pad_v = int(4 + pulse * 3)
            pad_h = int(10 + pulse * 6)
            glow_col = "#6EE7B7" if pulse > 0.5 else "#059669"
            bg_col = "#065F46" if pulse > 0.3 else "#064E3B"
            self.quota_badge.setStyleSheet(f"""
                background-color: {bg_col};
                color: #FFFFFF;
                border: 2px solid {glow_col};
                padding: {pad_v}px {pad_h}px;
                border-radius: 4px;
            """)

        self._badge_anim.valueChanged.connect(_on_anim_step)
        self._badge_anim.finished.connect(lambda: self.quota_badge.setStyleSheet(f"""
            background-color: #064E3B;
            color: #34D399;
            border: 1px solid #059669;
            padding: 4px 10px;
            border-radius: 3px;
        """))
        self._badge_anim.start()

    def _toggle_inspect_raw(self):
        if not self.project or not self.project.items:
            return
        idx = self.project.current_index
        item = self.project.items[idx]
        if not item.raw_path or not os.path.exists(item.raw_path):
            return

        from loupe.core.decoder import ImageDecoder

        if self.is_inspecting_raw:
            # Revert to cached JPEG
            self.is_inspecting_raw = False
            self.inspect_raw_btn.setText("Inspect RAW (R)")
            self.inspect_raw_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_BG_ELEVATED};
                    border: 1px solid {COLOR_BORDER_DISTINCT};
                    border-radius: 3px;
                    color: {COLOR_TEXT_PRIMARY};
                    padding: 0 12px;
                }}
                QPushButton:hover {{
                    border-color: {COLOR_ACCENT};
                    color: {COLOR_ACCENT};
                }}
            """)
            self._render_cached_index(idx)
        else:
            # Decode RAW on demand
            qimg, _ = ImageDecoder.decode_to_qimage(item.raw_path)
            if qimg and not qimg.isNull():
                self.is_inspecting_raw = True
                self.inspect_raw_btn.setText("Viewing RAW (R)")
                self.inspect_raw_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: #382A10;
                        border: 1px solid {COLOR_ACCENT};
                        border-radius: 3px;
                        color: {COLOR_ACCENT};
                        font-weight: 700;
                        padding: 0 12px;
                    }}
                """)
                self._render_image(qimg)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        key_str = event.text().upper()

        # Remappable keys from config
        keep_key = config.get_key_binding("keep").upper()
        reject_key = config.get_key_binding("reject").upper()
        maybe_key = config.get_key_binding("maybe", "E").upper()
        prev_key = config.get_key_binding("prev").upper()
        next_key = config.get_key_binding("next").upper()

        if key == Qt.Key_Escape:
            self._handle_escape_request()
            event.accept()
        elif event.modifiers() & Qt.ControlModifier and key == Qt.Key_Z:
            self.undo_last_decision()
            event.accept()
        elif key_str and key_str == keep_key:
            self.keep_current()
            event.accept()
        elif key_str and key_str == reject_key:
            self.reject_current()
            event.accept()
        elif key_str and key_str == maybe_key:
            self.maybe_current()
            event.accept()
        elif (key_str and key_str == prev_key) or key == Qt.Key_Left:
            self.go_previous()
            event.accept()
        elif (key_str and key_str == next_key) or key == Qt.Key_Right:
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
        elif key == Qt.Key_R:
            self._toggle_inspect_raw()
            event.accept()
        elif key == Qt.Key_F11:
            win = self.window()
            if hasattr(win, "toggle_fullscreen"):
                win.toggle_fullscreen()
            event.accept()
        else:
            super().keyPressEvent(event)
