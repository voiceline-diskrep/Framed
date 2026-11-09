"""Complete Gallery System workspace view for FRAMED."""

import os
import math
from datetime import datetime
from typing import List, Optional, Dict, Set

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QComboBox, QScrollArea, QStackedWidget,
    QGridLayout, QMenu, QInputDialog, QMessageBox, QFileDialog,
    QSizePolicy, QToolButton
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QSize
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QPixmap,
    QFont, QLinearGradient, QCursor, QAction
)

from ..models import GalleryPhoto, GalleryFolder, SmartAlbum
from ..storage import storage, format_bytes
from ..core.gallery_engine import (
    thumbnail_cache, ThumbnailBatchWorker, MissingFileRecoveryEngine, RawToJpegConverter
)
from .icons import render_icon
from .gallery_dialogs import (
    GalleryImportDialog, RawConversionDialog, DeleteGalleryFolderDialog,
    GalleryPhotoViewerModal, BeforeAfterComparisonDialog,
    GallerySlideshowModal, DuplicateFinderDialog, GalleryBackupDialog,
    SmartAlbumDialog
)


# ==============================================================================
# CUSTOM PAINTED WIDGETS: STORAGE DONUT RING & INTERACTIVE WORLD MAP
# ==============================================================================

class StorageDonutWidget(QWidget):
    """Custom painted donut pie chart showing JPEG (Orange), RAW (Blue), and Other (Gray) storage."""

    def __init__(self, size_px: int = 110, stroke_w: float = 13.0, parent=None):
        super().__init__(parent)
        self.setFixedSize(size_px, size_px)
        self.stroke_w = stroke_w
        self.jpeg_pct = 0.0
        self.raw_pct = 0.0
        self.other_pct = 0.0

    def set_percentages(self, jpeg_pct: float, raw_pct: float, other_pct: float):
        self.jpeg_pct = max(0.0, jpeg_pct)
        self.raw_pct = max(0.0, raw_pct)
        self.other_pct = max(0.0, other_pct)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        pad = self.stroke_w / 2.0 + 4.0
        rect = QRectF(pad, pad, self.width() - pad * 2, self.height() - pad * 2)

        # Base track
        track_pen = QPen(QColor("#262A34"), self.stroke_w, Qt.SolidLine, Qt.FlatCap)
        p.setPen(track_pen)
        p.drawEllipse(rect)

        total = self.jpeg_pct + self.raw_pct + self.other_pct
        if total <= 0.01:
            # Subtle empty state ring
            empty_pen = QPen(QColor("#363B47"), self.stroke_w, Qt.SolidLine, Qt.RoundCap)
            p.setPen(empty_pen)
            p.drawArc(rect, 90 * 16, -60 * 16)
            p.end()
            return

        start_angle = 90.0 * 16.0  # Top 12 o'clock
        segments = [
            (self.jpeg_pct / total, QColor("#F59E0B")),  # Orange for JPEG
            (self.raw_pct / total, QColor("#60A5FA")),   # Blue for RAW
            (self.other_pct / total, QColor("#9CA3AF")), # Gray for Other
        ]

        for frac, col in segments:
            if frac <= 0.001:
                continue
            span = -frac * 360.0 * 16.0
            pen = QPen(col, self.stroke_w, Qt.SolidLine, Qt.FlatCap)
            p.setPen(pen)
            p.drawArc(rect, int(start_angle), int(span))
            start_angle += span

        p.end()


class QuickFeatureBannerCard(QFrame):
    """5 Quick-Access Feature Cards shown across the top of the Gallery content area."""

    clicked = Signal()

    def __init__(self, card_type: str, title: str, subtitle: str, icon_name: str, accent_hex: str = "#F59E0B", parent=None):
        super().__init__(parent)
        self.card_type = card_type
        self.title_str = title
        self.subtitle_str = subtitle
        self.icon_name = icon_name
        self.accent_hex = accent_hex
        self.hovered = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(108)
        self.setMinimumWidth(148)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def apply_ready_thumbnail(self):
        pix, is_final = thumbnail_cache.get_cached_or_placeholder_pixmap(self.photo, 220, 152, radius=0)
        if is_final:
            self.thumb_pix = pix
            self.needs_async_thumb = False
            self.update()

    def enterEvent(self, event):
        self.hovered = True
        self.update()

    def leaveEvent(self, event):
        self.hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        rect = QRectF(1, 1, w - 2, h - 2)

        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        p.setClipPath(path)

        # Card base
        p.fillRect(rect, QColor("#181B21" if not self.hovered else "#1E222A"))

        if self.card_type == "new_album":
            # Centered circular + button style matching mockup
            cx, cy = w / 2.0, h * 0.36
            p.setPen(QPen(QColor("#F59E0B"), 1.4))
            p.setBrush(QColor(245, 158, 11, 28))
            p.drawEllipse(QPointF(cx, cy), 17, 17)
            p.drawLine(QPointF(cx - 6, cy), QPointF(cx + 6, cy))
            p.drawLine(QPointF(cx, cy - 6), QPointF(cx, cy + 6))

            p.setPen(QColor("#F4F4F5"))
            f1 = QFont("Inter", 10, QFont.Bold)
            p.setFont(f1)
            p.drawText(QRectF(0, h * 0.60, w, 18), Qt.AlignCenter, self.title_str)

            p.setPen(QColor("#969BA5"))
            f2 = QFont("Inter", 8)
            p.setFont(f2)
            p.drawText(QRectF(0, h * 0.76, w, 16), Qt.AlignCenter, self.subtitle_str)
        else:
            # Artwork banner in top 58% of card
            banner_h = h * 0.56
            banner_rect = QRectF(4, 4, w - 8, banner_h)
            b_path = QPainterPath()
            b_path.addRoundedRect(banner_rect, 7, 7)
            p.save()
            p.setClipPath(b_path)

            grad = QLinearGradient(0, 4, w, banner_h)
            if self.card_type == "memories":
                grad.setColorAt(0.0, QColor("#3B1D1E"))
                grad.setColorAt(0.5, QColor("#9A4B1A"))
                grad.setColorAt(1.0, QColor("#F59E0B"))
                p.fillRect(banner_rect, grad)
                # Horizon & sun silhouette
                p.setBrush(QColor(255, 230, 150, 180))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(w * 0.52, banner_h * 0.58), 10, 10)
                mtn = QPainterPath()
                mtn.moveTo(0, banner_h + 4)
                mtn.lineTo(w * 0.3, banner_h * 0.65)
                mtn.lineTo(w * 0.55, banner_h * 0.80)
                mtn.lineTo(w * 0.8, banner_h * 0.58)
                mtn.lineTo(w, banner_h + 4)
                p.fillPath(mtn, QColor("#14161B"))
            elif self.card_type == "favorites":
                grad.setColorAt(0.0, QColor("#17253B"))
                grad.setColorAt(0.6, QColor("#29486B"))
                grad.setColorAt(1.0, QColor("#64748B"))
                p.fillRect(banner_rect, grad)
                mtn = QPainterPath()
                mtn.moveTo(0, banner_h + 4)
                mtn.lineTo(w * 0.38, banner_h * 0.30)
                mtn.lineTo(w * 0.62, banner_h * 0.62)
                mtn.lineTo(w * 0.78, banner_h * 0.40)
                mtn.lineTo(w, banner_h + 4)
                p.fillPath(mtn, QColor("#1E293B"))
            elif self.card_type == "map":
                grad.setColorAt(0.0, QColor("#0F2942"))
                grad.setColorAt(1.0, QColor("#164E63"))
                p.fillRect(banner_rect, grad)
                # Stylized continents
                p.setBrush(QColor("#A3E635"))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(w * 0.14, banner_h * 0.25, w * 0.22, banner_h * 0.45), 6, 6)
                p.drawRoundedRect(QRectF(w * 0.46, banner_h * 0.22, w * 0.36, banner_h * 0.50), 6, 6)
            else:  # missing files
                grad.setColorAt(0.0, QColor("#1F232B"))
                grad.setColorAt(1.0, QColor("#111318"))
                p.fillRect(banner_rect, grad)
                p.setPen(QPen(QColor("#4B5563"), 1.5))
                p.setBrush(QColor("#272B35"))
                p.drawRoundedRect(QRectF(w * 0.35, banner_h * 0.22, w * 0.30, banner_h * 0.58), 4, 4)

            p.restore()

            # Icon + Title + Subtitle in bottom 42%
            icon_pix = render_icon(self.icon_name, 16, self.accent_hex).pixmap(16, 16)
            p.drawPixmap(12, int(banner_h + 13), icon_pix)

            p.setPen(QColor("#F4F4F5"))
            p.setFont(QFont("Inter", 9, QFont.Bold))
            p.drawText(QRectF(34, banner_h + 7, w - 40, 16), Qt.AlignLeft | Qt.AlignVCenter, self.title_str)

            p.setPen(QColor("#969BA5"))
            p.setFont(QFont("Inter", 8))
            p.drawText(QRectF(34, banner_h + 23, w - 40, 15), Qt.AlignLeft | Qt.AlignVCenter, self.subtitle_str)

        # Border
        p.setClipping(False)
        border_col = QColor("#F59E0B") if self.hovered else QColor("#2B303B")
        p.setPen(QPen(border_col, 1.1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, 10, 10)
        p.end()


class InteractiveWorldMapWidget(QWidget):
    """100% Offline Interactive Vector World Map with glowing GPS photo cluster pins and manual tagging."""

    photo_selected = Signal(object)  # GalleryPhoto
    location_tagged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(420)
        self.photos: List[GalleryPhoto] = []
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self._pin_rects: List[tuple] = []  # (QRectF, List[GalleryPhoto], label)

    def set_photos(self, photos: List[GalleryPhoto]):
        self.photos = photos
        self.update()

    def _latlon_to_xy(self, lat: float, lon: float, map_rect: QRectF) -> QPointF:
        x = map_rect.left() + ((lon + 180.0) / 360.0) * map_rect.width()
        y = map_rect.top() + ((90.0 - lat) / 180.0) * map_rect.height()
        return QPointF(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position()
            for r, grp, lbl in self._pin_rects:
                if r.contains(pos):
                    self.photo_selected.emit(grp[0])
                    return

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        rect = QRectF(0, 0, w, h)

        # Deep ocean background
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor("#0B1522"))
        grad.setColorAt(1.0, QColor("#0E1D2F"))
        p.fillRect(rect, grad)

        map_rect = QRectF(24, 24, w - 48, h - 72)

        # Lat/Lon grid lines
        p.setPen(QPen(QColor(255, 255, 255, 16), 1.0, Qt.DotLine))
        for i in range(1, 6):
            gy = map_rect.top() + i * (map_rect.height() / 6.0)
            p.drawLine(QPointF(map_rect.left(), gy), QPointF(map_rect.right(), gy))
        for i in range(1, 12):
            gx = map_rect.left() + i * (map_rect.width() / 12.0)
            p.drawLine(QPointF(gx, map_rect.top()), QPointF(gx, map_rect.bottom()))

        # Simplified stylized continent polygons (normalized 0..1 coordinates)
        continents = [
            # North America
            [(0.12, 0.18), (0.28, 0.16), (0.31, 0.34), (0.23, 0.46), (0.15, 0.36)],
            # South America
            [(0.26, 0.50), (0.35, 0.54), (0.33, 0.82), (0.28, 0.85), (0.25, 0.65)],
            # Europe
            [(0.45, 0.18), (0.57, 0.16), (0.58, 0.32), (0.46, 0.34)],
            # Africa
            [(0.45, 0.38), (0.58, 0.38), (0.60, 0.68), (0.52, 0.78), (0.44, 0.54)],
            # Asia
            [(0.58, 0.16), (0.86, 0.18), (0.84, 0.48), (0.68, 0.52), (0.59, 0.36)],
            # Australia / Indonesia
            [(0.74, 0.62), (0.87, 0.62), (0.88, 0.78), (0.75, 0.78)],
        ]
        p.setPen(QPen(QColor("#2A4359"), 1.3))
        p.setBrush(QColor("#172A3A"))
        for poly in continents:
            path = QPainterPath()
            for idx, (nx, ny) in enumerate(poly):
                pt = QPointF(map_rect.left() + nx * map_rect.width(), map_rect.top() + ny * map_rect.height())
                if idx == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
            path.closeSubpath()
            p.drawPath(path)

        # Group GPS photos by rounded coordinate / location label
        self._pin_rects.clear()
        clusters: Dict[str, List[GalleryPhoto]] = {}
        coords: Dict[str, tuple] = {}
        for photo in self.photos:
            if photo.has_gps:
                key = f"{round(photo.gps_lat, 1)},{round(photo.gps_lon, 1)}"
                clusters.setdefault(key, []).append(photo)
                coords[key] = (photo.gps_lat, photo.gps_lon, photo.gps_label or key)
            elif photo.gps_label:
                key = photo.gps_label
                clusters.setdefault(key, []).append(photo)
                # Deterministic fallback position for named places without raw lat/lon
                h_val = abs(hash(key))
                lat = -40.0 + (h_val % 100)
                lon = -120.0 + ((h_val // 100) % 260)
                coords[key] = (lat, lon, photo.gps_label)

        for key, grp in clusters.items():
            lat, lon, lbl = coords[key]
            pt = self._latlon_to_xy(lat, lon, map_rect)
            # Outer glow
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(245, 158, 11, 65))
            p.drawEllipse(pt, 18, 18)
            # Inner pin circle
            p.setBrush(QColor("#F59E0B"))
            p.setPen(QPen(QColor("#0D0E11"), 2.0))
            p.drawEllipse(pt, 11, 11)
            # Count text
            p.setPen(QColor("#0D0E11"))
            p.setFont(QFont("Inter", 8, QFont.Bold))
            pin_r = QRectF(pt.x() - 12, pt.y() - 12, 24, 24)
            p.drawText(pin_r, Qt.AlignCenter, str(len(grp)))

            # Label pill below pin
            p.setPen(QColor("#F4F4F5"))
            p.setFont(QFont("Inter", 8, QFont.DemiBold))
            p.drawText(QRectF(pt.x() - 60, pt.y() + 13, 120, 16), Qt.AlignCenter, lbl[:20])
            self._pin_rects.append((pin_r.adjusted(-6, -6, 6, 6), grp, lbl))

        # Bottom legend bar
        p.setPen(QColor("#969BA5"))
        p.setFont(QFont("Inter", 10))
        gps_count = sum(len(g) for g in clusters.values())
        msg = (
            f"📍 Showing {gps_count} location-tagged photograph(s) across {len(clusters)} location cluster(s). "
            "Click any orange pin to inspect photos, or open any photo to tag its location."
        )
        p.drawText(QRectF(24, h - 40, w - 48, 28), Qt.AlignLeft | Qt.AlignVCenter, msg)
        p.end()


# ==============================================================================
# PHOTO GRID CARD WIDGET (MATCHING MOCKUP)
# ==============================================================================

class GalleryPhotoCard(QFrame):
    """Individual Photo Card inside the Gallery Grid with Heart icon, RAW/JPEG badge, date, size, and 3-dot menu."""

    double_clicked = Signal(object)       # GalleryPhoto
    favorite_toggled = Signal(object)     # GalleryPhoto
    context_action = Signal(str, object)  # (action_name, GalleryPhoto)
    selection_toggled = Signal(str, bool) # (photo_id, selected)

    def __init__(self, photo: GalleryPhoto, is_selected: bool = False, parent=None):
        super().__init__(parent)
        self.photo = photo
        self.is_selected = is_selected
        self.hovered = False
        self.setFixedSize(218, 198)
        self.setCursor(Qt.PointingHandCursor)

        # Load cached thumbnail non-blockingly (<1ms if on disk, placeholder otherwise)
        self.thumb_pix = QPixmap()
        self.needs_async_thumb = False
        if not photo.is_missing:
            pix, is_final = thumbnail_cache.get_cached_or_placeholder_pixmap(photo, 220, 152, radius=0)
            if is_final:
                self.thumb_pix = pix
            else:
                self.needs_async_thumb = True

    def enterEvent(self, event):
        self.hovered = True
        self.update()

    def leaveEvent(self, event):
        self.hovered = False
        self.update()

    def mousePressEvent(self, event):
        pos = event.position()
        # Top-left heart hit box (8..36, 8..36)
        if QRectF(6, 6, 32, 32).contains(pos):
            self.favorite_toggled.emit(self.photo)
            return
        # Bottom-right 3-dot menu hit box
        if QRectF(self.width() - 32, self.height() - 44, 28, 38).contains(pos):
            self._show_menu(event.globalPosition().toPoint())
            return
        if event.button() == Qt.RightButton:
            self._show_menu(event.globalPosition().toPoint())
            return
        if event.button() == Qt.LeftButton:
            if event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
                self.is_selected = not self.is_selected
                self.selection_toggled.emit(self.photo.id, self.is_selected)
                self.update()
            else:
                self.double_clicked.emit(self.photo)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self.photo)

    def _show_menu(self, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #191C22; color: #F4F4F5; border: 1px solid #2F3440; border-radius: 8px; padding: 4px; }"
            "QMenu::item { padding: 6px 18px; border-radius: 5px; font-size: 12px; }"
            "QMenu::item:selected { background-color: #F59E0B; color: #0D0E11; font-weight: 600; }"
        )
        act_open = menu.addAction("Open in Photo Viewer")
        act_fav = menu.addAction("Remove from Favorites" if self.photo.is_favorite else "Add to Favorites ♥")
        act_cmp = menu.addAction("Before & After Compare...")
        menu.addSeparator()
        move_menu = menu.addMenu("Add / Move to Folder")
        for f in storage.get_gallery_folders():
            a = move_menu.addAction(f"📁 {f.name}")
            a.setData(("folder", f.id))
        if self.photo.is_raw:
            act_conv = menu.addAction("Convert RAW → JPEG...")
        else:
            act_conv = None
        menu.addSeparator()
        act_del = menu.addAction("Move to Recently Deleted")

        chosen = menu.exec(global_pos)
        if not chosen:
            return
        if chosen == act_open:
            self.double_clicked.emit(self.photo)
        elif chosen == act_fav:
            self.favorite_toggled.emit(self.photo)
        elif chosen == act_cmp:
            self.context_action.emit("compare", self.photo)
        elif act_conv and chosen == act_conv:
            self.context_action.emit("convert_raw", self.photo)
        elif chosen == act_del:
            self.context_action.emit("delete", self.photo)
        elif chosen.data() and isinstance(chosen.data(), tuple) and chosen.data()[0] == "folder":
            self.context_action.emit(f"folder:{chosen.data()[1]}", self.photo)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        w, h = float(self.width()), float(self.height())
        rect = QRectF(1, 1, w - 2, h - 2)
        img_h = h - 48.0

        card_path = QPainterPath()
        card_path.addRoundedRect(rect, 10, 10)
        p.setClipPath(card_path)

        # Card background
        p.fillRect(rect, QColor("#181B21"))

        # Image region
        img_rect = QRectF(1, 1, w - 2, img_h)
        if not self.thumb_pix.isNull():
            scaled = self.thumb_pix.scaled(int(w), int(img_h), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            sx = max(0, (scaled.width() - int(w)) // 2)
            sy = max(0, (scaled.height() - int(img_h)) // 2)
            p.drawPixmap(1, 1, scaled, sx, sy, int(w - 2), int(img_h))
        else:
            p.fillRect(img_rect, QColor("#121419"))
            icon_name = "warning" if self.photo.is_missing else "photo"
            ic = render_icon(icon_name, 28, "#EF4444" if self.photo.is_missing else "#4B5563").pixmap(28, 28)
            p.drawPixmap(int(w / 2 - 14), int(img_h / 2 - 14), ic)

        # Subtle top vignette for badge legibility
        top_grad = QLinearGradient(0, 0, 0, 42)
        top_grad.setColorAt(0.0, QColor(0, 0, 0, 130))
        top_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(1, 1, w - 2, 42), top_grad)

        # Top-left Heart icon
        heart_icon = "heart_filled" if self.photo.is_favorite else "heart"
        heart_col = "#F59E0B" if self.photo.is_favorite else "#E4E4E7"
        p.drawPixmap(10, 10, render_icon(heart_icon, 16, heart_col).pixmap(16, 16))

        # Top-right Format Badge (RAW / JPEG)
        badge_text = "MISSING" if self.photo.is_missing else self.photo.format_type
        badge_w = 42 if badge_text != "MISSING" else 58
        badge_rect = QRectF(w - badge_w - 9, 9, badge_w, 19)
        p.setPen(Qt.NoPen)
        if self.photo.is_missing:
            p.setBrush(QColor(239, 68, 68, 210))
        elif self.photo.is_raw:
            p.setBrush(QColor(17, 24, 39, 215))
        else:
            p.setBrush(QColor(24, 27, 34, 205))
        p.drawRoundedRect(badge_rect, 4, 4)

        p.setPen(QColor("#F4F4F5"))
        p.setFont(QFont("Inter", 8, QFont.Bold))
        p.drawText(badge_rect, Qt.AlignCenter, badge_text)

        # Bottom metadata bar
        meta_rect = QRectF(1, img_h, w - 2, 48)
        p.fillRect(meta_rect, QColor("#171A20"))

        p.setPen(QColor("#F4F4F5"))
        p.setFont(QFont("Inter", 9, QFont.Bold))
        fname = self.photo.filename
        if len(fname) > 22:
            fname = fname[:19] + "..."
        p.drawText(QRectF(10, img_h + 6, w - 34, 18), Qt.AlignLeft | Qt.AlignVCenter, fname)

        # Formatted date + size (e.g. Oct 15, 2026 • 24.2 MB)
        try:
            dt = datetime.strptime(self.photo.date_taken[:10], "%Y-%m-%d")
            date_disp = dt.strftime("%b %d, %Y")
        except Exception:
            date_disp = self.photo.date_taken[:10]
        sub_str = f"{date_disp} • {format_bytes(self.photo.size_bytes)}"
        p.setPen(QColor("#969BA5"))
        p.setFont(QFont("Inter", 8))
        p.drawText(QRectF(10, img_h + 24, w - 34, 16), Qt.AlignLeft | Qt.AlignVCenter, sub_str)

        # 3-dot vertical menu indicator
        p.setBrush(QColor("#969BA5"))
        p.setPen(Qt.NoPen)
        for dy in (-5, 0, 5):
            p.drawEllipse(QPointF(w - 14, img_h + 24 + dy), 1.3, 1.3)

        # Card border (Orange highlight if favorited, selected, or hovered)
        p.setClipping(False)
        if self.is_selected or self.photo.is_favorite or self.hovered:
            border_pen = QPen(QColor("#F59E0B"), 1.6 if (self.is_selected or self.photo.is_favorite) else 1.2)
        else:
            border_pen = QPen(QColor("#282C35"), 1.0)
        p.setPen(border_pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, 10, 10)
        p.end()


# ==============================================================================
# MAIN GALLERY WORKSPACE VIEW
# ==============================================================================

class GalleryView(QWidget):
    """Complete FRAMED Gallery Workspace combining Left Sidebar, Center Browser, and Right Storage/Activity Column."""

    mode_switch_requested = Signal(str)    # "photo" | "video" | "gallery"
    new_session_requested = Signal()
    drive_settings_requested = Signal()
    theme_menu_requested = Signal(object)  # QPushButton
    settings_requested = Signal()
    fullscreen_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_section: str = "all"  # "all", "favorites", "raw", "jpeg", "memories", "map", "missing", "deleted", "folder:<id>", "smart:<id>"
        self.current_format_pill: str = "all"  # "all", "RAW", "JPEG", "favorites", "recent"
        self.current_sort: str = "newest"
        self.current_view_mode: str = "grid"   # "grid", "list", "compact"
        self.selected_photo_ids: Set[str] = set()
        self.folders_expanded: bool = True
        self.smart_expanded: bool = False
        self.expanded_parent_folders: Set[str] = set()

        # Expand School Pictures by default to match mockup
        for f in storage.get_gallery_folders():
            if f.name == "School Pictures":
                self.expanded_parent_folders.add(f.id)

        self._is_loaded: bool = False
        self._active_cards: Dict[str, GalleryPhotoCard] = {}
        self._thumb_worker: Optional[ThumbnailBatchWorker] = None
        self.page_limit: int = 80
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QWidget#GalleryRoot {
                background-color: #101114;
                color: #F4F4F5;
                font-family: 'Inter', 'Segoe UI', sans-serif;
            }
            QFrame#TopHeader {
                background-color: #131519;
                border-bottom: 1px solid #252830;
            }
            QFrame#LeftSidebar {
                background-color: #141619;
                border-right: 1px solid #252830;
            }
            QFrame#KpiCard, QFrame#RightPanelCard {
                background-color: #181B21;
                border: 1px solid #282C35;
                border-radius: 11px;
            }
            QFrame#StorageTipBox {
                background-color: #1F1B14;
                border: 1px solid #523914;
                border-radius: 8px;
            }
            QLineEdit#GallerySearch {
                background-color: #15181E;
                color: #F4F4F5;
                border: 1px solid #292E38;
                border-radius: 8px;
                padding: 7px 12px;
                font-size: 12px;
            }
            QLineEdit#GallerySearch:focus {
                border-color: #F59E0B;
            }
            QComboBox#SortCombo {
                background-color: #171A20;
                color: #E4E4E7;
                border: 1px solid #2B303B;
                border-radius: 7px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 600;
            }
        """)
        self.setObjectName("GalleryRoot")

        root_v = QVBoxLayout(self)
        root_v.setContentsMargins(0, 0, 0, 0)
        root_v.setSpacing(0)

        # 1. Global Application Header
        self._build_top_header(root_v)

        # 2. Main 3-Column Body (Left Sidebar + Center Workspace + Right Storage/Activity Column)
        body_h = QHBoxLayout()
        body_h.setContentsMargins(0, 0, 0, 0)
        body_h.setSpacing(0)

        self._build_left_sidebar(body_h)
        self._build_center_and_right(body_h)

        root_v.addLayout(body_h, 1)

    # ------------------------------------------------------------------
    # TOP HEADER BAR
    # ------------------------------------------------------------------
    def _build_top_header(self, parent_layout: QVBoxLayout):
        hdr = QFrame()
        hdr.setObjectName("TopHeader")
        hdr.setFixedHeight(58)
        h = QHBoxLayout(hdr)
        h.setContentsMargins(18, 0, 18, 0)
        h.setSpacing(12)

        # Brand identity
        logo_lbl = QLabel()
        logo_lbl.setPixmap(render_icon("brand_frame", 26, "#F59E0B").pixmap(26, 26))
        h.addWidget(logo_lbl)

        brand_v = QVBoxLayout()
        brand_v.setSpacing(0)
        brand_v.setAlignment(Qt.AlignVCenter)
        b_title = QLabel("FRAMED")
        b_title.setStyleSheet("font-size: 15px; font-weight: 800; color: #F4F4F5; letter-spacing: 0.8px;")
        b_sub = QLabel("PHOTOGRAPHER & VIDEOGRAPHER WORKSTATION")
        b_sub.setStyleSheet("font-size: 8px; font-weight: 700; color: #F59E0B; letter-spacing: 0.9px;")
        brand_v.addWidget(b_title)
        brand_v.addWidget(b_sub)
        h.addLayout(brand_v)

        h.addSpacing(18)

        # 3-Mode Segmented Control: Photosort | Videosort | Gallery
        seg_frame = QFrame()
        seg_frame.setStyleSheet(
            "QFrame { background-color: #181B20; border: 1px solid #2A2E37; border-radius: 9px; }"
        )
        seg_h = QHBoxLayout(seg_frame)
        seg_h.setContentsMargins(4, 4, 4, 4)
        seg_h.setSpacing(4)

        btn_photo = QPushButton(" Photosort")
        btn_photo.setIcon(render_icon("photo", 14, "#969BA5"))
        btn_photo.setCursor(Qt.PointingHandCursor)
        btn_photo.setStyleSheet(
            "QPushButton { background: transparent; color: #969BA5; border: none; padding: 5px 13px; font-size: 12px; font-weight: 600; border-radius: 6px; }"
            "QPushButton:hover { color: #F4F4F5; background-color: #20242C; }"
        )
        btn_photo.clicked.connect(lambda: self.mode_switch_requested.emit("photo"))

        btn_video = QPushButton(" Videosort")
        btn_video.setIcon(render_icon("video", 14, "#969BA5"))
        btn_video.setCursor(Qt.PointingHandCursor)
        btn_video.setStyleSheet(btn_photo.styleSheet())
        btn_video.clicked.connect(lambda: self.mode_switch_requested.emit("video"))

        btn_gallery = QPushButton(" Gallery")
        btn_gallery.setIcon(render_icon("gallery", 14, "#F59E0B"))
        btn_gallery.setCursor(Qt.PointingHandCursor)
        btn_gallery.setStyleSheet(
            "QPushButton { background-color: rgba(245, 158, 11, 0.16); color: #F59E0B; "
            "border: 1px solid #F59E0B; padding: 5px 15px; font-size: 12px; font-weight: 700; border-radius: 6px; }"
        )

        seg_h.addWidget(btn_photo)
        seg_h.addWidget(btn_video)
        seg_h.addWidget(btn_gallery)
        h.addWidget(seg_frame)

        h.addStretch()

        # Right side controls matching FRAMED header
        btn_new_sess = QPushButton("+ New Photo Session")
        btn_new_sess.setCursor(Qt.PointingHandCursor)
        btn_new_sess.setStyleSheet(
            "QPushButton { background-color: #F59E0B; color: #0D0E11; border: 1px solid #FBBF24; "
            "border-radius: 7px; padding: 6px 14px; font-size: 12px; font-weight: 700; }"
            "QPushButton:hover { background-color: #FBBF24; }"
        )
        btn_new_sess.clicked.connect(self.new_session_requested.emit)
        h.addWidget(btn_new_sess)

        hdr_btn_style = (
            "QPushButton { background-color: #1B1E24; color: #D4D4D8; border: 1px solid #2C313C; "
            "border-radius: 7px; padding: 6px 11px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background-color: #242932; color: #F4F4F5; }"
        )

        btn_drive = QPushButton(" Google Drive")
        btn_drive.setIcon(render_icon("cloud", 14, "#22C55E"))
        btn_drive.setStyleSheet(hdr_btn_style)
        btn_drive.clicked.connect(self.drive_settings_requested.emit)

        self.btn_theme = QPushButton(" Theme")
        self.btn_theme.setIcon(render_icon("theme", 14, "#D4D4D8"))
        self.btn_theme.setStyleSheet(hdr_btn_style)
        self.btn_theme.clicked.connect(lambda: self.theme_menu_requested.emit(self.btn_theme))

        btn_settings = QPushButton(" Settings")
        btn_settings.setIcon(render_icon("settings", 14, "#D4D4D8"))
        btn_settings.setStyleSheet(hdr_btn_style)
        btn_settings.clicked.connect(self.settings_requested.emit)

        btn_fs = QPushButton(" Full Screen (F11)")
        btn_fs.setIcon(render_icon("fit", 13, "#D4D4D8"))
        btn_fs.setStyleSheet(hdr_btn_style)
        btn_fs.clicked.connect(self.fullscreen_requested.emit)

        for b in (btn_drive, self.btn_theme, btn_settings, btn_fs):
            b.setCursor(Qt.PointingHandCursor)
            h.addWidget(b)

        parent_layout.addWidget(hdr)

    # ------------------------------------------------------------------
    # LEFT SIDEBAR NAVIGATION & FOLDERS
    # ------------------------------------------------------------------
    def _build_left_sidebar(self, parent_layout: QHBoxLayout):
        sidebar = QFrame()
        sidebar.setObjectName("LeftSidebar")
        sidebar.setFixedWidth(226)
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(12, 14, 12, 12)
        sv.setSpacing(6)

        # GALLERY heading + '+' button
        top_row = QHBoxLayout()
        g_lbl = QLabel("GALLERY")
        g_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #969BA5; letter-spacing: 1px;")
        top_row.addWidget(g_lbl)
        top_row.addStretch()

        btn_add_top = QPushButton()
        btn_add_top.setIcon(render_icon("plus", 12, "#E4E4E7"))
        btn_add_top.setFixedSize(24, 24)
        btn_add_top.setCursor(Qt.PointingHandCursor)
        btn_add_top.setToolTip("Create New Gallery Folder")
        btn_add_top.setStyleSheet(
            "QPushButton { background-color: #1F232B; border: 1px solid #303540; border-radius: 6px; padding: 0px; }"
            "QPushButton:hover { border-color: #F59E0B; }"
        )
        btn_add_top.clicked.connect(self._prompt_create_folder)
        top_row.addWidget(btn_add_top)
        sv.addLayout(top_row)

        # Scrollable nav tree container
        self.nav_scroll = QScrollArea()
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFrameShape(QFrame.NoFrame)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_scroll.setStyleSheet("QScrollArea { background: transparent; }")

        self.nav_container = QWidget()
        self.nav_container.setStyleSheet("background: transparent;")
        self.nav_v = QVBoxLayout(self.nav_container)
        self.nav_v.setContentsMargins(0, 4, 0, 4)
        self.nav_v.setSpacing(2)
        self.nav_scroll.setWidget(self.nav_container)
        sv.addWidget(self.nav_scroll, 1)

        # Bottom mini storage card inside sidebar (matching mockup)
        mini_storage = QFrame()
        mini_storage.setStyleSheet(
            "QFrame { background-color: #191C22; border: 1px solid #292E38; border-radius: 9px; }"
        )
        ms_h = QHBoxLayout(mini_storage)
        ms_h.setContentsMargins(10, 8, 10, 8)
        ms_h.setSpacing(10)

        self.mini_donut = StorageDonutWidget(size_px=38, stroke_w=5.0)
        ms_h.addWidget(self.mini_donut)

        ms_v = QVBoxLayout()
        ms_v.setSpacing(1)
        self.mini_storage_val = QLabel("0 B")
        self.mini_storage_val.setStyleSheet("font-size: 13px; font-weight: 800; color: #F4F4F5; border: none;")
        ms_sub = QLabel("Total Storage")
        ms_sub.setStyleSheet("font-size: 10px; color: #969BA5; border: none;")
        ms_v.addWidget(self.mini_storage_val)
        ms_v.addWidget(ms_sub)
        ms_h.addLayout(ms_v, 1)
        sv.addWidget(mini_storage)

        # Bottom Edit Folder & Delete buttons
        bot_btns = QHBoxLayout()
        bot_btns.setSpacing(6)
        btn_edit_f = QPushButton(" Edit Folder")
        btn_edit_f.setIcon(render_icon("edit", 12, "#D4D4D8"))
        btn_edit_f.setCursor(Qt.PointingHandCursor)
        btn_edit_f.setStyleSheet(
            "QPushButton { background-color: #1C2026; color: #D4D4D8; border: 1px solid #2D323E; border-radius: 6px; padding: 6px 8px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background-color: #252A34; }"
        )
        btn_edit_f.clicked.connect(self._prompt_rename_current_folder)

        btn_del_f = QPushButton(" Delete")
        btn_del_f.setIcon(render_icon("trash", 12, "#EF4444"))
        btn_del_f.setCursor(Qt.PointingHandCursor)
        btn_del_f.setStyleSheet(
            "QPushButton { background-color: #241619; color: #F87171; border: 1px solid #5C2126; border-radius: 6px; padding: 6px 8px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background-color: #361C21; }"
        )
        btn_del_f.clicked.connect(self._prompt_delete_current_folder)

        bot_btns.addWidget(btn_edit_f, 1)
        bot_btns.addWidget(btn_del_f, 1)
        sv.addLayout(bot_btns)

        parent_layout.addWidget(sidebar)

    def _rebuild_sidebar_nav(self, stats: dict):
        while self.nav_v.count():
            item = self.nav_v.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        def add_nav_row(section_key: str, label: str, icon_name: str, count_val: Optional[int] = None,
                        indent: int = 0, is_red_badge: bool = False, chevron: str = ""):
            active = (self.current_section == section_key)
            row_btn = QFrame()
            row_btn.setCursor(Qt.PointingHandCursor)
            row_btn.setFixedHeight(31)
            if active:
                row_btn.setStyleSheet(
                    "QFrame { background-color: #221E17; border-left: 3px solid #F59E0B; border-radius: 6px; }"
                )
            else:
                row_btn.setStyleSheet(
                    "QFrame { background: transparent; border-radius: 6px; }"
                    "QFrame:hover { background-color: #1B1E24; }"
                )
            rh = QHBoxLayout(row_btn)
            rh.setContentsMargins(8 + indent, 0, 8, 0)
            rh.setSpacing(8)

            if chevron:
                c_lbl = QLabel(chevron)
                c_lbl.setStyleSheet("color: #969BA5; font-size: 10px; border: none; background: transparent;")
                rh.addWidget(c_lbl)

            ic_col = "#F59E0B" if active or icon_name in ("gallery", "heart", "star", "warning") else "#969BA5"
            if section_key == "missing":
                ic_col = "#F59E0B"
            ic_lbl = QLabel()
            ic_lbl.setPixmap(render_icon(icon_name, 14, ic_col).pixmap(14, 14))
            ic_lbl.setStyleSheet("border: none; background: transparent;")
            rh.addWidget(ic_lbl)

            t_lbl = QLabel(label)
            t_lbl.setStyleSheet(
                f"font-size: 12px; font-weight: {'700' if active else '500'}; "
                f"color: {'#F4F4F5' if active else '#D4D4D8'}; border: none; background: transparent;"
            )
            rh.addWidget(t_lbl, 1)

            if count_val is not None:
                if is_red_badge and count_val > 0:
                    b_lbl = QLabel(str(count_val))
                    b_lbl.setAlignment(Qt.AlignCenter)
                    b_lbl.setFixedSize(20, 18)
                    b_lbl.setStyleSheet(
                        "background-color: #DC2626; color: #FFFFFF; font-size: 10px; font-weight: 700; border-radius: 9px; border: none;"
                    )
                    rh.addWidget(b_lbl)
                else:
                    c_lbl = QLabel(f"{count_val:,}")
                    c_lbl.setStyleSheet("font-size: 11px; color: #969BA5; border: none; background: transparent;")
                    rh.addWidget(c_lbl)

            row_btn.mousePressEvent = lambda e, k=section_key: self._select_section(k)
            self.nav_v.addWidget(row_btn)

        # Primary items
        add_nav_row("all", "All Photos", "gallery", stats["total_photos"])
        add_nav_row("favorites", "Favorites", "heart", stats["favorites_count"])
        add_nav_row("raw", "RAW Files", "folder", stats["raw_count"])
        add_nav_row("jpeg", "JPEG Files", "folder", stats["jpeg_count"])

        # Divider
        div1 = QFrame()
        div1.setFixedHeight(1)
        div1.setStyleSheet("background-color: #232730; margin: 4px 0px;")
        self.nav_v.addWidget(div1)

        # Collapsible Folders header
        f_hdr = QFrame()
        f_hdr.setCursor(Qt.PointingHandCursor)
        f_hdr.setFixedHeight(28)
        fh_l = QHBoxLayout(f_hdr)
        fh_l.setContentsMargins(6, 0, 8, 0)
        fh_l.setSpacing(6)
        chev = "▾" if self.folders_expanded else "▸"
        fh_l.addWidget(QLabel(f"{chev} 📁 Folders"))
        fh_l.addStretch()
        f_hdr.mousePressEvent = lambda e: self._toggle_folders_group()
        self.nav_v.addWidget(f_hdr)

        if self.folders_expanded:
            f_counts = stats.get("folder_counts", {})
            top_folders = storage.get_top_level_gallery_folders()
            for tf in top_folders:
                children = storage.get_gallery_subfolders(tf.id)
                # Sum parent + child counts for display
                total_f_count = f_counts.get(tf.id, 0) + sum(f_counts.get(c.id, 0) for c in children)
                c_sym = ("▾" if tf.id in self.expanded_parent_folders else "▸") if children else ""
                add_nav_row(f"folder:{tf.id}", tf.name, "folder", total_f_count, indent=8, chevron=c_sym)
                if children and tf.id in self.expanded_parent_folders:
                    for ch in children:
                        add_nav_row(f"folder:{ch.id}", ch.name, "folder", f_counts.get(ch.id, 0), indent=24)

            # '+ Create Folder' inline button
            btn_cf = QPushButton("  +   Create Folder")
            btn_cf.setCursor(Qt.PointingHandCursor)
            btn_cf.setStyleSheet(
                "QPushButton { background: transparent; color: #969BA5; border: none; text-align: left; padding: 5px 12px; font-size: 11px; font-weight: 600; }"
                "QPushButton:hover { color: #F59E0B; }"
            )
            btn_cf.clicked.connect(self._prompt_create_folder)
            self.nav_v.addWidget(btn_cf)

        # Divider
        div2 = QFrame()
        div2.setFixedHeight(1)
        div2.setStyleSheet("background-color: #232730; margin: 4px 0px;")
        self.nav_v.addWidget(div2)

        # Smart Albums collapsible
        sa_hdr = QFrame()
        sa_hdr.setCursor(Qt.PointingHandCursor)
        sa_hdr.setFixedHeight(30)
        sah_l = QHBoxLayout(sa_hdr)
        sah_l.setContentsMargins(8, 0, 8, 0)
        sah_l.setSpacing(8)
        ic_sa = QLabel()
        ic_sa.setPixmap(render_icon("star", 14, "#F59E0B").pixmap(14, 14))
        sah_l.addWidget(ic_sa)
        t_sa = QLabel("Smart Albums")
        t_sa.setStyleSheet("font-size: 12px; color: #D4D4D8;")
        sah_l.addWidget(t_sa, 1)
        c_sa = QLabel("▾" if self.smart_expanded else "›")
        c_sa.setStyleSheet("color: #969BA5; font-size: 13px;")
        sah_l.addWidget(c_sa)
        sa_hdr.mousePressEvent = lambda e: self._toggle_smart_group()
        self.nav_v.addWidget(sa_hdr)

        if self.smart_expanded:
            active_photos = [p for p in storage.gallery_photos.values() if not p.is_deleted]
            for sa in storage.get_smart_albums():
                cnt = sum(1 for p in active_photos if sa.matches(p))
                add_nav_row(f"smart:{sa.id}", sa.name, "sparkles", cnt, indent=16)
            btn_new_sa = QPushButton("  +   New Smart Album...")
            btn_new_sa.setCursor(Qt.PointingHandCursor)
            btn_new_sa.setStyleSheet(
                "QPushButton { background: transparent; color: #969BA5; border: none; text-align: left; padding: 4px 20px; font-size: 11px; }"
                "QPushButton:hover { color: #F59E0B; }"
            )
            btn_new_sa.clicked.connect(self._open_smart_album_dialog)
            self.nav_v.addWidget(btn_new_sa)

        add_nav_row("memories", "Memories", "calendar")
        add_nav_row("map", "Map View", "map_pin")
        add_nav_row("missing", "Missing Files", "warning", stats["missing_count"], is_red_badge=True)
        add_nav_row("deleted", "Recently Deleted", "trash", stats["deleted_count"] if stats["deleted_count"] > 0 else None)

        self.nav_v.addStretch()

    # ------------------------------------------------------------------
    # CENTER WORKSPACE & RIGHT STORAGE/ACTIVITY COLUMN
    # ------------------------------------------------------------------
    def _build_center_and_right(self, parent_layout: QHBoxLayout):
        main_area = QWidget()
        mv = QVBoxLayout(main_area)
        mv.setContentsMargins(20, 16, 20, 16)
        mv.setSpacing(14)

        # Row 1: Gallery Title Banner + 3 Top KPI Cards
        self._build_title_and_kpis(mv)

        # Row 2: Search Bar + Format Filter Pills + Sort Dropdown + Grid/List/Compact Switcher + Utility Actions
        self._build_search_and_filters_bar(mv)

        # Row 3: Center Content + Right Storage/Activity Column
        split_h = QHBoxLayout()
        split_h.setSpacing(16)

        # Left/Center Column (5 Feature Cards + Stacked Browser Views)
        center_col = QVBoxLayout()
        center_col.setSpacing(14)

        self._build_quick_feature_cards(center_col)
        self._build_browser_stack(center_col)

        split_h.addLayout(center_col, 1)

        # Right Column (Storage Overview Donut Card + Recent Activity + Organise Your Memories)
        self._build_right_column(split_h)

        mv.addLayout(split_h, 1)
        parent_layout.addWidget(main_area, 1)

    def _build_title_and_kpis(self, parent_layout: QVBoxLayout):
        row = QHBoxLayout()
        row.setSpacing(14)

        # Gallery Icon + Title + Subtitle
        icon_box = QFrame()
        icon_box.setFixedSize(48, 48)
        icon_box.setStyleSheet(
            "QFrame { background-color: rgba(245, 158, 11, 0.14); border: 1px solid rgba(245, 158, 11, 0.45); border-radius: 11px; }"
        )
        ib_l = QVBoxLayout(icon_box)
        ib_l.setContentsMargins(0, 0, 0, 0)
        ib_l.setAlignment(Qt.AlignCenter)
        ic = QLabel()
        ic.setPixmap(render_icon("gallery", 26, "#F59E0B").pixmap(26, 26))
        ic.setStyleSheet("border: none; background: transparent;")
        ib_l.addWidget(ic)
        row.addWidget(icon_box)

        title_v = QVBoxLayout()
        title_v.setSpacing(2)
        self.header_title_lbl = QLabel("Gallery")
        self.header_title_lbl.setStyleSheet("font-size: 25px; font-weight: 800; color: #F4F4F5;")
        self.header_sub_lbl = QLabel("Your photographs, organized and ready to revisit.")
        self.header_sub_lbl.setStyleSheet("font-size: 12px; color: #969BA5;")
        title_v.addWidget(self.header_title_lbl)
        title_v.addWidget(self.header_sub_lbl)
        row.addLayout(title_v)

        row.addSpacing(12)

        # Quick action buttons in Gallery header: Import Photos, Slideshow, Backup, Duplicates
        btn_import = QPushButton(" + Import Photos")
        btn_import.setCursor(Qt.PointingHandCursor)
        btn_import.setStyleSheet(
            "QPushButton { background-color: rgba(245, 158, 11, 0.16); color: #F59E0B; "
            "border: 1px solid #F59E0B; border-radius: 7px; padding: 6px 12px; font-size: 12px; font-weight: 700; }"
            "QPushButton:hover { background-color: #F59E0B; color: #0D0E11; }"
        )
        btn_import.clicked.connect(lambda: self.open_import_dialog())
        row.addWidget(btn_import)

        row.addStretch()

        # 3 KPI Cards: Total Photos, Storage Used, Favorites
        def make_kpi_card(icon_name: str, icon_col: str, sub_label: str):
            card = QFrame()
            card.setObjectName("KpiCard")
            card.setFixedSize(195, 66)
            ch = QHBoxLayout(card)
            ch.setContentsMargins(14, 10, 14, 10)
            ch.setSpacing(12)

            ic_frame = QFrame()
            ic_frame.setFixedSize(36, 36)
            ic_frame.setStyleSheet("background-color: #20242D; border-radius: 8px; border: 1px solid #2E3340;")
            ifl = QVBoxLayout(ic_frame)
            ifl.setContentsMargins(0, 0, 0, 0)
            ifl.setAlignment(Qt.AlignCenter)
            il = QLabel()
            il.setPixmap(render_icon(icon_name, 18, icon_col).pixmap(18, 18))
            il.setStyleSheet("border: none; background: transparent;")
            ifl.addWidget(il)
            ch.addWidget(ic_frame)

            tv = QVBoxLayout()
            tv.setSpacing(1)
            val_lbl = QLabel("0")
            val_lbl.setStyleSheet("font-size: 19px; font-weight: 800; color: #F4F4F5; border: none;")
            s_lbl = QLabel(sub_label)
            s_lbl.setStyleSheet("font-size: 11px; color: #969BA5; border: none;")
            tv.addWidget(val_lbl)
            tv.addWidget(s_lbl)
            ch.addLayout(tv, 1)
            return card, val_lbl

        c1, self.kpi_total_lbl = make_kpi_card("gallery", "#9CA3AF", "Total Photos")
        c2, self.kpi_storage_lbl = make_kpi_card("database", "#9CA3AF", "Storage Used")
        c3, self.kpi_fav_lbl = make_kpi_card("star_filled", "#F59E0B", "Favorites")

        row.addWidget(c1)
        row.addWidget(c2)
        row.addWidget(c3)

        parent_layout.addLayout(row)

    def _build_search_and_filters_bar(self, parent_layout: QVBoxLayout):
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("GallerySearch")
        self.search_input.setPlaceholderText("🔍  Search your photos by filename, folder, camera, date or note...")
        self.search_input.setMinimumWidth(290)
        self.search_input.textChanged.connect(lambda: self.refresh_browser())
        bar.addWidget(self.search_input, 1)

        # Filter pills: All | RAW | JPEG | ♥ Favorites | Recent
        self.pill_buttons: Dict[str, QPushButton] = {}
        pills = [
            ("all", "All"),
            ("RAW", "RAW"),
            ("JPEG", "JPEG"),
            ("favorites", "♥  Favorites"),
            ("recent", "Recent"),
        ]
        for key, label in pills:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=key: self._set_format_pill(k))
            self.pill_buttons[key] = btn
            bar.addWidget(btn)
        self._update_pill_styles()

        # Utility tools: Slideshow, Duplicates, Backup
        util_style = (
            "QPushButton { background-color: #171A20; color: #D4D4D8; border: 1px solid #2B303B; "
            "border-radius: 7px; padding: 6px 10px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { border-color: #F59E0B; color: #F4F4F5; }"
        )
        btn_slide = QPushButton("▶ Slideshow")
        btn_slide.setStyleSheet(util_style)
        btn_slide.setCursor(Qt.PointingHandCursor)
        btn_slide.clicked.connect(self._start_slideshow)
        bar.addWidget(btn_slide)

        btn_dups = QPushButton("Duplicates")
        btn_dups.setStyleSheet(util_style)
        btn_dups.setCursor(Qt.PointingHandCursor)
        btn_dups.clicked.connect(self._open_duplicates_dialog)
        bar.addWidget(btn_dups)

        btn_bk = QPushButton("Backup")
        btn_bk.setStyleSheet(util_style)
        btn_bk.setCursor(Qt.PointingHandCursor)
        btn_bk.clicked.connect(self._open_backup_dialog)
        bar.addWidget(btn_bk)

        # Sort dropdown
        self.sort_combo = QComboBox()
        self.sort_combo.setObjectName("SortCombo")
        self.sort_combo.addItem("Sort by: Newest First", "newest")
        self.sort_combo.addItem("Sort by: Oldest First", "oldest")
        self.sort_combo.addItem("Sort by: Name (A–Z)", "name_asc")
        self.sort_combo.addItem("Sort by: File Size (Largest)", "size_desc")
        self.sort_combo.addItem("Sort by: File Type (RAW/JPEG)", "type")
        self.sort_combo.addItem("Sort by: Favorites First", "favorites")
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        bar.addWidget(self.sort_combo)

        # Grid / List / Compact view switcher
        self.view_btns: Dict[str, QPushButton] = {}
        for v_mode, ic_name in (("grid", "grid"), ("list", "list"), ("compact", "compact")):
            vb = QPushButton()
            vb.setFixedSize(32, 32)
            vb.setCursor(Qt.PointingHandCursor)
            vb.clicked.connect(lambda checked=False, m=v_mode: self._set_view_mode(m))
            self.view_btns[v_mode] = vb
            bar.addWidget(vb)
        self._update_view_btn_styles()

        parent_layout.addLayout(bar)

    def _build_quick_feature_cards(self, parent_layout: QVBoxLayout):
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)

        c_new = QuickFeatureBannerCard("new_album", "New Album", "Create a folder", "plus", "#F59E0B")
        c_new.clicked.connect(self._prompt_create_folder)

        c_mem = QuickFeatureBannerCard("memories", "Memories Timeline", "Relive your moments", "calendar", "#F59E0B")
        c_mem.clicked.connect(lambda: self._select_section("memories"))

        c_fav = QuickFeatureBannerCard("favorites", "Favorites", "Your starred photos", "heart_filled", "#F59E0B")
        c_fav.clicked.connect(lambda: self._select_section("favorites"))

        c_map = QuickFeatureBannerCard("map", "Map View", "Explore by location", "map_pin", "#F59E0B")
        c_map.clicked.connect(lambda: self._select_section("map"))

        c_mis = QuickFeatureBannerCard("missing", "Missing Files", "Find lost photos", "warning", "#F59E0B")
        c_mis.clicked.connect(lambda: self._select_section("missing"))

        for c in (c_new, c_mem, c_fav, c_map, c_mis):
            cards_row.addWidget(c, 1)

        parent_layout.addLayout(cards_row)

    def _build_browser_stack(self, parent_layout: QVBoxLayout):
        # Context action bar when inside Recently Deleted or Missing Files
        self.context_banner = QFrame()
        self.context_banner.setStyleSheet(
            "QFrame { background-color: #1C1F26; border: 1px solid #313744; border-radius: 8px; }"
        )
        self.context_banner.setVisible(False)
        cb_h = QHBoxLayout(self.context_banner)
        cb_h.setContentsMargins(12, 8, 12, 8)
        self.context_banner_lbl = QLabel("")
        self.context_banner_lbl.setStyleSheet("font-size: 12px; color: #E4E4E7; border: none;")
        cb_h.addWidget(self.context_banner_lbl, 1)

        self.btn_ctx_primary = QPushButton("")
        self.btn_ctx_primary.setStyleSheet(
            "QPushButton { background-color: #F59E0B; color: #0D0E11; font-weight: 700; border-radius: 6px; padding: 5px 12px; font-size: 11px; }"
        )
        self.btn_ctx_secondary = QPushButton("")
        self.btn_ctx_secondary.setStyleSheet(
            "QPushButton { background-color: #2A1619; color: #F87171; border: 1px solid #6E232A; font-weight: 600; border-radius: 6px; padding: 5px 12px; font-size: 11px; }"
        )
        cb_h.addWidget(self.btn_ctx_primary)
        cb_h.addWidget(self.btn_ctx_secondary)
        parent_layout.addWidget(self.context_banner)

        # Scrollable main browser area + Map widget stack
        self.browser_stack = QStackedWidget()

        # Page 0: Scrollable Photo Grid / List / Memories Timeline
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.NoFrame)
        self.grid_scroll.setStyleSheet("QScrollArea { background: transparent; }")

        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background: transparent;")
        self.grid_v = QVBoxLayout(self.grid_container)
        self.grid_v.setContentsMargins(0, 0, 4, 8)
        self.grid_v.setSpacing(12)
        self.grid_scroll.setWidget(self.grid_container)
        self.browser_stack.addWidget(self.grid_scroll)

        # Page 1: Interactive Vector World Map View
        self.map_widget = InteractiveWorldMapWidget()
        self.map_widget.photo_selected.connect(self._open_photo_viewer_single)
        self.browser_stack.addWidget(self.map_widget)

        parent_layout.addWidget(self.browser_stack, 1)

    def _build_right_column(self, parent_layout: QHBoxLayout):
        right_w = QWidget()
        right_w.setFixedWidth(282)
        rv = QVBoxLayout(right_w)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(12)

        # 1. Storage Overview Card
        storage_card = QFrame()
        storage_card.setObjectName("RightPanelCard")
        sv = QVBoxLayout(storage_card)
        sv.setContentsMargins(16, 14, 16, 14)
        sv.setSpacing(10)

        sh = QHBoxLayout()
        s_title = QLabel("Storage Overview")
        s_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #F4F4F5; border: none;")
        sh.addWidget(s_title)
        sh.addStretch()
        info_ic = QLabel()
        info_ic.setPixmap(render_icon("info", 14, "#969BA5").pixmap(14, 14))
        info_ic.setToolTip(
            "Deduplicated storage across all indexed photographs.\n"
            "Folders organize references and never duplicate files."
        )
        info_ic.setStyleSheet("border: none;")
        sh.addWidget(info_ic)
        sv.addLayout(sh)

        # Donut + Legend
        donut_row = QHBoxLayout()
        donut_row.setSpacing(14)
        self.main_donut = StorageDonutWidget(size_px=106, stroke_w=13.0)
        donut_row.addWidget(self.main_donut)

        leg_v = QVBoxLayout()
        leg_v.setSpacing(6)
        leg_v.setAlignment(Qt.AlignVCenter)

        def make_legend_row(dot_color: str, name: str):
            lh = QHBoxLayout()
            lh.setSpacing(6)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {dot_color}; font-size: 12px; border: none;")
            n_lbl = QLabel(name)
            n_lbl.setStyleSheet("color: #D4D4D8; font-size: 12px; font-weight: 600; border: none;")
            pct_lbl = QLabel("0%")
            pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pct_lbl.setStyleSheet("color: #F4F4F5; font-size: 12px; font-weight: 700; border: none;")
            lh.addWidget(dot)
            lh.addWidget(n_lbl, 1)
            lh.addWidget(pct_lbl)
            leg_v.addLayout(lh)
            return pct_lbl

        self.leg_jpeg_pct = make_legend_row("#F59E0B", "JPEG")
        self.leg_raw_pct = make_legend_row("#60A5FA", "RAW")
        self.leg_other_pct = make_legend_row("#9CA3AF", "Other")
        donut_row.addLayout(leg_v, 1)
        sv.addLayout(donut_row)

        self.total_storage_center_lbl = QLabel("0 B Total")
        self.total_storage_center_lbl.setAlignment(Qt.AlignCenter)
        self.total_storage_center_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #F4F4F5; border: none;")
        sv.addWidget(self.total_storage_center_lbl)

        # Save more storage! callout box
        tip_box = QFrame()
        tip_box.setObjectName("StorageTipBox")
        tv = QVBoxLayout(tip_box)
        tv.setContentsMargins(12, 10, 12, 10)
        tv.setSpacing(6)

        th = QHBoxLayout()
        bulb = QLabel()
        bulb.setPixmap(render_icon("bulb", 15, "#F59E0B").pixmap(15, 15))
        bulb.setStyleSheet("border: none; background: transparent;")
        th.addWidget(bulb)
        t_head = QLabel("Save more storage!")
        t_head.setStyleSheet("font-size: 12px; font-weight: 700; color: #F59E0B; border: none; background: transparent;")
        th.addWidget(t_head, 1)
        tv.addLayout(th)

        t_desc = QLabel("Convert your RAW files to JPEG to reduce file size.")
        t_desc.setWordWrap(True)
        t_desc.setStyleSheet("font-size: 11px; color: #D4D4D8; border: none; background: transparent;")
        tv.addWidget(t_desc)

        btn_conv_raw = QPushButton("Convert RAW → JPEG")
        btn_conv_raw.setCursor(Qt.PointingHandCursor)
        btn_conv_raw.setStyleSheet(
            "QPushButton { background-color: rgba(245, 158, 11, 0.18); color: #F59E0B; "
            "border: 1px solid #F59E0B; border-radius: 6px; padding: 6px 10px; font-size: 11px; font-weight: 700; }"
            "QPushButton:hover { background-color: #F59E0B; color: #0D0E11; }"
        )
        btn_conv_raw.clicked.connect(lambda: self.open_raw_conversion_dialog())
        tv.addWidget(btn_conv_raw)
        sv.addWidget(tip_box)

        rv.addWidget(storage_card)

        # 2. Recent Activity Card
        act_card = QFrame()
        act_card.setObjectName("RightPanelCard")
        av = QVBoxLayout(act_card)
        av.setContentsMargins(16, 14, 16, 14)
        av.setSpacing(8)

        ah = QHBoxLayout()
        a_title = QLabel("Recent Activity")
        a_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #F4F4F5; border: none;")
        ah.addWidget(a_title)
        ah.addStretch()
        v_all = QLabel("View All →")
        v_all.setStyleSheet("font-size: 11px; color: #969BA5; border: none;")
        ah.addWidget(v_all)
        av.addLayout(ah)

        self.activity_v = QVBoxLayout()
        self.activity_v.setSpacing(8)
        av.addLayout(self.activity_v)
        rv.addWidget(act_card)

        # 3. Organise Your Memories Card
        mem_card = QFrame()
        mem_card.setObjectName("RightPanelCard")
        mh = QHBoxLayout(mem_card)
        mh.setContentsMargins(14, 12, 14, 12)
        mh.setSpacing(12)

        m_ic_box = QFrame()
        m_ic_box.setFixedSize(42, 42)
        m_ic_box.setStyleSheet(
            "background-color: rgba(245, 158, 11, 0.14); border: 1px solid rgba(245, 158, 11, 0.45); border-radius: 9px;"
        )
        mibl = QVBoxLayout(m_ic_box)
        mibl.setContentsMargins(0, 0, 0, 0)
        mibl.setAlignment(Qt.AlignCenter)
        mic = QLabel()
        mic.setPixmap(render_icon("gallery", 22, "#F59E0B").pixmap(22, 22))
        mic.setStyleSheet("border: none; background: transparent;")
        mibl.addWidget(mic)
        mh.addWidget(m_ic_box)

        mv_col = QVBoxLayout()
        mv_col.setSpacing(4)
        mt = QLabel("Organise your memories")
        mt.setStyleSheet("font-size: 12px; font-weight: 700; color: #F4F4F5; border: none;")
        md = QLabel("Browse by date, location or event using the Memories Timeline.")
        md.setWordWrap(True)
        md.setStyleSheet("font-size: 10px; color: #969BA5; border: none;")
        btn_vm = QPushButton("View Memories →")
        btn_vm.setCursor(Qt.PointingHandCursor)
        btn_vm.setFixedWidth(120)
        btn_vm.setStyleSheet(
            "QPushButton { background-color: rgba(245, 158, 11, 0.16); color: #F59E0B; "
            "border: 1px solid #F59E0B; border-radius: 5px; padding: 4px 8px; font-size: 10px; font-weight: 700; }"
            "QPushButton:hover { background-color: #F59E0B; color: #0D0E11; }"
        )
        btn_vm.clicked.connect(lambda: self._select_section("memories"))
        mv_col.addWidget(mt)
        mv_col.addWidget(md)
        mv_col.addWidget(btn_vm)
        mh.addLayout(mv_col, 1)

        rv.addWidget(mem_card)
        rv.addStretch()

        parent_layout.addWidget(right_w)

    # ==================================================================
    # DATA REFRESH & RENDERING
    # ==================================================================

    def refresh_all(self):
        """Recalculates real-time Gallery statistics, sidebar counts, storage donut, activity, and grid."""
        stats = storage.calculate_gallery_statistics()

        # Top KPIs
        self.kpi_total_lbl.setText(f"{stats['total_photos']:,}")
        self.kpi_storage_lbl.setText(format_bytes(stats["total_bytes"]))
        self.kpi_fav_lbl.setText(f"{stats['favorites_count']:,}")

        # Sidebar mini donut + nav
        self.mini_donut.set_percentages(stats["jpeg_percent"], stats["raw_percent"], stats["other_percent"])
        self.mini_storage_val.setText(format_bytes(stats["total_bytes"]))
        self._rebuild_sidebar_nav(stats)

        # Right Storage Overview Card
        self.main_donut.set_percentages(stats["jpeg_percent"], stats["raw_percent"], stats["other_percent"])
        self.leg_jpeg_pct.setText(f"{int(round(stats['jpeg_percent']))}%")
        self.leg_raw_pct.setText(f"{int(round(stats['raw_percent']))}%")
        self.leg_other_pct.setText(f"{int(round(stats['other_percent']))}%")
        self.total_storage_center_lbl.setText(f"{format_bytes(stats['total_bytes'])} Total")

        # Recent Activity Card
        self._rebuild_recent_activity()

        # Center Browser
        self.refresh_browser()

    def _rebuild_recent_activity(self):
        while self.activity_v.count():
            it = self.activity_v.takeAt(0)
            w = it.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        activities = storage.gallery_activities[:3]
        if not activities:
            # Friendly starter entries
            sample_items = [
                ("check_circle", "#22C55E", "Gallery ready for import", "Just now"),
                ("folder", "#F59E0B", "Default memory folders created", "Today"),
                ("star_filled", "#F59E0B", "Smart Albums configured", "Today"),
            ]
        else:
            sample_items = []
            for act in activities:
                if act.action_type in ("import", "convert", "backup"):
                    ic, col = "check_circle", "#22C55E"
                elif act.action_type == "folder":
                    ic, col = "folder", "#F59E0B"
                else:
                    ic, col = "star_filled", "#F59E0B"
                try:
                    dt = datetime.fromisoformat(act.timestamp)
                    time_str = dt.strftime("%b %d, %H:%M")
                except Exception:
                    time_str = "Recently"
                sample_items.append((ic, col, act.title, time_str))

        for ic_name, col_hex, title_txt, time_txt in sample_items:
            row = QHBoxLayout()
            row.setSpacing(10)
            badge = QFrame()
            badge.setFixedSize(28, 28)
            badge.setStyleSheet(f"background-color: #20242D; border-radius: 7px; border: 1px solid #2D323E;")
            bl = QVBoxLayout(badge)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setAlignment(Qt.AlignCenter)
            il = QLabel()
            il.setPixmap(render_icon(ic_name, 14, col_hex).pixmap(14, 14))
            il.setStyleSheet("border: none; background: transparent;")
            bl.addWidget(il)
            row.addWidget(badge)

            tv = QVBoxLayout()
            tv.setSpacing(1)
            t1 = QLabel(title_txt)
            t1.setStyleSheet("font-size: 11px; font-weight: 600; color: #F4F4F5; border: none;")
            t2 = QLabel(time_txt)
            t2.setStyleSheet("font-size: 10px; color: #969BA5; border: none;")
            tv.addWidget(t1)
            tv.addWidget(t2)
            row.addLayout(tv, 1)

            w = QWidget()
            w.setLayout(row)
            self.activity_v.addWidget(w)

    def refresh_browser(self):
        """Refreshes the center photo grid, list, memories timeline, or map view."""
        # Update context banner for Missing Files or Recently Deleted
        self._update_context_banner()

        if self.current_section == "map":
            self.browser_stack.setCurrentIndex(1)
            active = [p for p in storage.gallery_photos.values() if not p.is_deleted]
            self.map_widget.set_photos(active)
            return

        self.browser_stack.setCurrentIndex(0)

        # Clear existing grid widgets
        while self.grid_v.count():
            it = self.grid_v.takeAt(0)
            w = it.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        # Determine query filters
        fmt_filter = None
        section_query = self.current_section
        if self.current_format_pill in ("RAW", "JPEG"):
            fmt_filter = self.current_format_pill
        elif self.current_format_pill == "favorites":
            section_query = "favorites"
        elif self.current_format_pill == "recent":
            section_query = "recent"

        photos = storage.query_gallery_photos(
            section=section_query,
            search_query=self.search_input.text(),
            format_filter=fmt_filter,
            sort_by=self.current_sort,
        )

        if not photos:
            self._render_empty_state()
            return

        if self.current_section == "memories":
            self._render_memories_timeline(photos)
        elif self.current_view_mode == "list":
            self._render_list_view(photos)
        else:
            self._render_grid_view(photos, compact=(self.current_view_mode == "compact"))

        self.grid_v.addStretch()

    def _render_empty_state(self):
        box = QFrame()
        box.setStyleSheet(
            "QFrame { background-color: #16181E; border: 1px dashed #2E3440; border-radius: 12px; }"
        )
        bv = QVBoxLayout(box)
        bv.setContentsMargins(32, 48, 32, 48)
        bv.setSpacing(10)
        bv.setAlignment(Qt.AlignCenter)

        ic = QLabel()
        ic.setPixmap(render_icon("gallery", 42, "#F59E0B").pixmap(42, 42))
        ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet("border: none;")
        bv.addWidget(ic)

        t = QLabel("No Photographs in This View Yet")
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-size: 16px; font-weight: 700; color: #F4F4F5; border: none;")
        bv.addWidget(t)

        sub = QLabel(
            "Import photographs from your computer or add selections from your existing FRAMED Photosort sessions."
        )
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("font-size: 12px; color: #969BA5; border: none;")
        bv.addWidget(sub)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignCenter)
        b_comp = QPushButton("+ Import from Computer")
        b_comp.setCursor(Qt.PointingHandCursor)
        b_comp.setStyleSheet(
            "QPushButton { background-color: #F59E0B; color: #0D0E11; font-weight: 700; border-radius: 7px; padding: 8px 16px; font-size: 12px; }"
        )
        b_comp.clicked.connect(lambda: self.open_import_dialog(initial_tab=0))

        b_sess = QPushButton("Import from FRAMED Sessions")
        b_sess.setCursor(Qt.PointingHandCursor)
        b_sess.setStyleSheet(
            "QPushButton { background-color: #20242D; color: #F4F4F5; border: 1px solid #323846; font-weight: 600; border-radius: 7px; padding: 8px 16px; font-size: 12px; }"
        )
        b_sess.clicked.connect(lambda: self.open_import_dialog(initial_tab=1))

        btn_row.addWidget(b_comp)
        btn_row.addWidget(b_sess)
        bv.addLayout(btn_row)

        self.grid_v.addWidget(box)

    def _render_grid_view(self, photos: List[GalleryPhoto], compact: bool = False):
        if self._thumb_worker and self._thumb_worker.isRunning():
            self._thumb_worker.cancel()
            self._thumb_worker.wait(200)
        self._active_cards.clear()

        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10 if not compact else 6)

        visible_photos = photos[:self.page_limit]
        uncached_photos: List[GalleryPhoto] = []

        cols = 4 if not compact else 5
        for idx, photo in enumerate(visible_photos):
            card = GalleryPhotoCard(photo, is_selected=(photo.id in self.selected_photo_ids))
            if compact:
                card.setFixedSize(172, 162)
            card.double_clicked.connect(lambda p, all_p=photos: self._open_photo_viewer(p, all_p))
            card.favorite_toggled.connect(self._on_card_favorite_toggled)
            card.context_action.connect(self._on_card_context_action)
            card.selection_toggled.connect(self._on_card_selection_toggled)
            grid.addWidget(card, idx // cols, idx % cols)
            self._active_cards[photo.id] = card
            if card.needs_async_thumb:
                uncached_photos.append(photo)

        self.grid_v.addWidget(grid_w)

        if len(photos) > self.page_limit:
            rem = len(photos) - self.page_limit
            btn_more = QPushButton(f"Load More Photographs ({rem:,} remaining)")
            btn_more.setCursor(Qt.PointingHandCursor)
            btn_more.setStyleSheet(
                "QPushButton { background-color: #1C2028; color: #F59E0B; border: 1px solid #F59E0B; "
                "border-radius: 8px; padding: 9px 18px; font-size: 12px; font-weight: 700; }"
                "QPushButton:hover { background-color: #F59E0B; color: #0D0E11; }"
            )
            btn_more.clicked.connect(self._load_more_photos)
            self.grid_v.addWidget(btn_more)

        if uncached_photos:
            self._thumb_worker = ThumbnailBatchWorker(uncached_photos, self)
            self._thumb_worker.thumb_ready.connect(self._on_async_thumb_ready)
            self._thumb_worker.start()

    def _load_more_photos(self):
        self.page_limit += 80
        self.refresh_browser()

    def _on_async_thumb_ready(self, photo_id: str, _thumb_path: str):
        card = self._active_cards.get(photo_id)
        if card:
            card.apply_ready_thumbnail()

    def _render_list_view(self, photos: List[GalleryPhoto]):
        for photo in photos:
            row_frame = QFrame()
            row_frame.setFixedHeight(46)
            row_frame.setCursor(Qt.PointingHandCursor)
            row_frame.setStyleSheet(
                "QFrame { background-color: #171A20; border: 1px solid #262A34; border-radius: 8px; }"
                "QFrame:hover { border-color: #F59E0B; }"
            )
            rh = QHBoxLayout(row_frame)
            rh.setContentsMargins(12, 4, 12, 4)
            rh.setSpacing(12)

            fav_ic = QLabel()
            fav_ic.setPixmap(render_icon("heart_filled" if photo.is_favorite else "heart", 14, "#F59E0B" if photo.is_favorite else "#666D79").pixmap(14, 14))
            fav_ic.setStyleSheet("border: none;")
            rh.addWidget(fav_ic)

            fn_lbl = QLabel(photo.filename)
            fn_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #F4F4F5; border: none;")
            rh.addWidget(fn_lbl, 2)

            fmt_lbl = QLabel(photo.format_type)
            fmt_lbl.setFixedWidth(54)
            fmt_lbl.setAlignment(Qt.AlignCenter)
            fmt_lbl.setStyleSheet(
                f"font-size: 10px; font-weight: 700; color: {'#60A5FA' if photo.is_raw else '#F59E0B'}; "
                "background-color: #20242D; border-radius: 4px; padding: 2px 6px; border: none;"
            )
            rh.addWidget(fmt_lbl)

            dt_lbl = QLabel(photo.date_taken[:10])
            dt_lbl.setStyleSheet("font-size: 11px; color: #969BA5; border: none;")
            rh.addWidget(dt_lbl, 1)

            sz_lbl = QLabel(format_bytes(photo.size_bytes))
            sz_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            sz_lbl.setStyleSheet("font-size: 11px; color: #D4D4D8; border: none;")
            rh.addWidget(sz_lbl, 1)

            row_frame.mouseDoubleClickEvent = lambda e, p=photo, all_p=photos: self._open_photo_viewer(p, all_p)
            self.grid_v.addWidget(row_frame)

    def _render_memories_timeline(self, photos: List[GalleryPhoto]):
        """Groups photographs chronologically by Month & Year with Memories highlights."""
        groups: Dict[str, List[GalleryPhoto]] = {}
        for p in photos:
            try:
                dt = datetime.strptime(p.date_taken[:10], "%Y-%m-%d")
                key = dt.strftime("%B %Y")
            except Exception:
                key = "Undated Memories"
            groups.setdefault(key, []).append(p)

        for period_label, grp_photos in groups.items():
            hdr_frame = QFrame()
            hdr_frame.setStyleSheet("background: transparent;")
            hh = QHBoxLayout(hdr_frame)
            hh.setContentsMargins(2, 8, 2, 2)
            p_lbl = QLabel(f"📅  {period_label}")
            p_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #F59E0B;")
            c_lbl = QLabel(f"{len(grp_photos)} photograph(s)")
            c_lbl.setStyleSheet("font-size: 12px; color: #969BA5;")
            hh.addWidget(p_lbl)
            hh.addSpacing(8)
            hh.addWidget(c_lbl)
            hh.addStretch()
            self.grid_v.addWidget(hdr_frame)

            self._render_grid_view(grp_photos, compact=False)

    # ==================================================================
    # ACTIONS, DIALOGS & HANDLERS
    # ==================================================================

    def _select_section(self, section_key: str):
        # Toggle child folder expansion if clicking a parent folder with children
        if section_key.startswith("folder:"):
            fid = section_key.split(":", 1)[1]
            has_children = bool(storage.get_gallery_subfolders(fid))
            if has_children:
                if self.current_section == section_key:
                    if fid in self.expanded_parent_folders:
                        self.expanded_parent_folders.remove(fid)
                    else:
                        self.expanded_parent_folders.add(fid)
                else:
                    self.expanded_parent_folders.add(fid)

        self.current_section = section_key
        self.refresh_all()

    def _toggle_folders_group(self):
        self.folders_expanded = not self.folders_expanded
        self.refresh_all()

    def _toggle_smart_group(self):
        self.smart_expanded = not self.smart_expanded
        self.refresh_all()

    def _set_format_pill(self, pill_key: str):
        self.current_format_pill = pill_key
        self._update_pill_styles()
        self.refresh_browser()

    def _update_pill_styles(self):
        for k, btn in self.pill_buttons.items():
            if k == self.current_format_pill:
                btn.setStyleSheet(
                    "QPushButton { background-color: #F59E0B; color: #0D0E11; border: 1px solid #FBBF24; "
                    "border-radius: 7px; padding: 6px 13px; font-size: 12px; font-weight: 700; }"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { background-color: #171A20; color: #D4D4D8; border: 1px solid #2B303B; "
                    "border-radius: 7px; padding: 6px 13px; font-size: 12px; font-weight: 600; }"
                    "QPushButton:hover { background-color: #20242D; color: #F4F4F5; }"
                )

    def _set_view_mode(self, mode: str):
        self.current_view_mode = mode
        self._update_view_btn_styles()
        self.refresh_browser()

    def _update_view_btn_styles(self):
        for m, btn in self.view_btns.items():
            active = (m == self.current_view_mode)
            btn.setIcon(render_icon(m, 14, "#0D0E11" if active else "#D4D4D8"))
            if active:
                btn.setStyleSheet(
                    "QPushButton { background-color: #F59E0B; border: 1px solid #FBBF24; border-radius: 7px; }"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { background-color: #171A20; border: 1px solid #2B303B; border-radius: 7px; }"
                    "QPushButton:hover { background-color: #222630; }"
                )

    def _on_sort_changed(self):
        self.current_sort = self.sort_combo.currentData() or "newest"
        self.refresh_browser()

    def _update_context_banner(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                self.btn_ctx_primary.clicked.disconnect()
            except Exception:
                pass
            try:
                self.btn_ctx_secondary.clicked.disconnect()
            except Exception:
                pass

        if self.current_section == "missing":
            self.context_banner.setVisible(True)
            self.context_banner_lbl.setText(
                "⚠ Missing Files Detected: These referenced photographs were moved or renamed outside FRAMED."
            )
            self.btn_ctx_primary.setText("Auto-Scan Folder to Relink...")
            self.btn_ctx_primary.setVisible(True)
            self.btn_ctx_primary.clicked.connect(self._auto_relink_missing_folder)

            self.btn_ctx_secondary.setText("Remove Missing References")
            self.btn_ctx_secondary.setVisible(True)
            self.btn_ctx_secondary.clicked.connect(self._remove_missing_refs)
        elif self.current_section == "deleted":
            self.context_banner.setVisible(True)
            self.context_banner_lbl.setText(
                "🗑 Recently Deleted: Restore photographs back to your Gallery or permanently remove them."
            )
            self.btn_ctx_primary.setText("Restore All Deleted Photos")
            self.btn_ctx_primary.setVisible(True)
            self.btn_ctx_primary.clicked.connect(self._restore_all_deleted)

            self.btn_ctx_secondary.setText("Empty Recently Deleted...")
            self.btn_ctx_secondary.setVisible(True)
            self.btn_ctx_secondary.clicked.connect(self._empty_recently_deleted)
        else:
            self.context_banner.setVisible(False)

    def open_import_dialog(self, initial_tab: int = 0):
        default_fid = None
        if self.current_section.startswith("folder:"):
            default_fid = self.current_section.split(":", 1)[1]
        dlg = GalleryImportDialog(self, default_folder_id=default_fid, initial_tab=initial_tab)
        dlg.import_completed.connect(lambda _rep: self.refresh_all())
        dlg.exec()

    def open_raw_conversion_dialog(self, specific_photos: Optional[List[GalleryPhoto]] = None):
        if specific_photos is None:
            raw_list = [p for p in storage.gallery_photos.values() if p.is_raw and not p.is_deleted and not p.is_missing]
        else:
            raw_list = specific_photos
        if not raw_list:
            QMessageBox.information(
                self,
                "No RAW Photographs Found",
                "Import one or more RAW photographs (.CR2, .CR3, .NEF, .ARW, .DNG, etc.) into Gallery first.",
            )
            return
        dlg = RawConversionDialog(raw_list, self)
        dlg.conversion_completed.connect(self.refresh_all)
        dlg.exec()

    def _prompt_create_folder(self):
        parent_id = None
        prompt_label = "Enter new Gallery folder name (e.g., School Pictures, Gramp's Birthday):"
        if self.current_section.startswith("folder:"):
            curr_fid = self.current_section.split(":", 1)[1]
            curr_f = storage.get_gallery_folder(curr_fid)
            if curr_f and not curr_f.parent_id:
                ans = QMessageBox.question(
                    self,
                    "Folder Placement",
                    f"Create as a nested subfolder inside '{curr_f.name}'?\n(Click 'No' to create a top-level folder.)",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                )
                if ans == QMessageBox.Cancel:
                    return
                if ans == QMessageBox.Yes:
                    parent_id = curr_f.id

        name, ok = QInputDialog.getText(self, "New Gallery Folder", prompt_label)
        if ok and name.strip():
            new_f = storage.create_gallery_folder(name.strip(), parent_id=parent_id)
            if parent_id:
                self.expanded_parent_folders.add(parent_id)
            self.current_section = f"folder:{new_f.id}"
            self.refresh_all()

    def _prompt_rename_current_folder(self):
        if not self.current_section.startswith("folder:"):
            QMessageBox.information(self, "Select a Folder", "Please select a custom folder in the left sidebar first.")
            return
        fid = self.current_section.split(":", 1)[1]
        folder = storage.get_gallery_folder(fid)
        if not folder:
            return
        new_name, ok = QInputDialog.getText(self, "Rename Folder", "New folder name:", text=folder.name)
        if ok and new_name.strip():
            storage.rename_gallery_folder(fid, new_name.strip())
            self.refresh_all()

    def _prompt_delete_current_folder(self):
        if not self.current_section.startswith("folder:"):
            QMessageBox.information(self, "Select a Folder", "Please select a custom folder in the left sidebar to delete.")
            return
        fid = self.current_section.split(":", 1)[1]
        folder = storage.get_gallery_folder(fid)
        if not folder:
            return
        cnt = sum(1 for p in storage.gallery_photos.values() if fid in p.folder_ids and not p.is_deleted)
        dlg = DeleteGalleryFolderDialog(folder, cnt, self)
        if dlg.exec() == QDialog.Accepted:
            storage.delete_gallery_folder(fid, reassign_to_folder_id=dlg.target_folder_id)
            self.current_section = "all"
            self.refresh_all()

    def _on_card_favorite_toggled(self, photo: GalleryPhoto):
        storage.toggle_gallery_favorite(photo.id)
        self.refresh_all()

    def _on_card_selection_toggled(self, photo_id: str, selected: bool):
        if selected:
            self.selected_photo_ids.add(photo_id)
        else:
            self.selected_photo_ids.discard(photo_id)

    def _on_card_context_action(self, action: str, photo: GalleryPhoto):
        if action == "compare":
            dlg = BeforeAfterComparisonDialog(photo, self)
            dlg.exec()
        elif action == "convert_raw":
            self.open_raw_conversion_dialog([photo])
        elif action == "delete":
            storage.soft_delete_photos([photo.id])
            self.refresh_all()
        elif action.startswith("folder:"):
            fid = action.split(":", 1)[1]
            storage.assign_photos_to_folder([photo.id], fid)
            self.refresh_all()

    def _open_photo_viewer(self, photo: GalleryPhoto, all_photos: List[GalleryPhoto]):
        if photo.is_missing:
            ans = QMessageBox.question(
                self,
                "Missing File",
                f"'{photo.filename}' could not be found at:\n{photo.active_path}\n\nWould you like to locate this file manually?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if ans == QMessageBox.Yes:
                new_p, _ = QFileDialog.getOpenFileName(self, f"Locate {photo.filename}")
                if new_p and os.path.exists(new_p):
                    MissingFileRecoveryEngine.reconnect_single_file(photo, new_p)
                    self.refresh_all()
            return
        idx = next((i for i, p in enumerate(all_photos) if p.id == photo.id), 0)
        dlg = GalleryPhotoViewerModal(all_photos, current_index=idx, parent=self)
        dlg.photo_updated.connect(lambda _pid: self.refresh_all())
        dlg.exec()

    def _open_photo_viewer_single(self, photo: GalleryPhoto):
        self._open_photo_viewer(photo, [photo])

    def _start_slideshow(self):
        photos = storage.query_gallery_photos(section=self.current_section, sort_by=self.current_sort)
        if not photos:
            QMessageBox.information(self, "No Photos", "There are no photographs in the current view for a slideshow.")
            return
        dlg = GallerySlideshowModal(photos, self)
        dlg.exec()

    def _open_duplicates_dialog(self):
        dlg = DuplicateFinderDialog(self)
        dlg.duplicates_resolved.connect(self.refresh_all)
        dlg.exec()

    def _open_backup_dialog(self):
        dlg = GalleryBackupDialog(self)
        dlg.exec()
        self.refresh_all()

    def _open_smart_album_dialog(self):
        dlg = SmartAlbumDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.created_album:
            self.smart_expanded = True
            self.current_section = f"smart:{dlg.created_album.id}"
            self.refresh_all()

    def _auto_relink_missing_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Scan for Missing Photographs")
        if not folder:
            return
        missing = [p for p in storage.gallery_photos.values() if p.is_missing and not p.is_deleted]
        res = MissingFileRecoveryEngine.scan_directory_and_reconnect(folder, missing)
        relinked = res.get('reconnected', 0)
        QMessageBox.information(self, "Recovery Complete", f"Successfully relinked {relinked} photograph(s).")
        self.refresh_all()

    def _remove_missing_refs(self):
        missing = [p.id for p in storage.gallery_photos.values() if p.is_missing and not p.is_deleted]
        if not missing:
            return
        storage.permanently_remove_photos(missing, delete_from_disk=False)
        self.refresh_all()

    def _restore_all_deleted(self):
        deleted_ids = [p.id for p in storage.gallery_photos.values() if p.is_deleted]
        if deleted_ids:
            storage.restore_deleted_photos(deleted_ids)
            self.refresh_all()

    def _empty_recently_deleted(self):
        deleted_ids = [p.id for p in storage.gallery_photos.values() if p.is_deleted]
        if not deleted_ids:
            return
        ans = QMessageBox.warning(
            self,
            "Empty Recently Deleted",
            f"Permanently remove {len(deleted_ids)} item(s) from your FRAMED Gallery?\n\n"
            "(Original files referenced outside FRAMED are never deleted from your computer.)",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            storage.permanently_remove_photos(deleted_ids, delete_from_disk=False)
            self.refresh_all()
