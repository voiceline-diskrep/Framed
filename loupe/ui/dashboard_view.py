"""Dashboard (main menu) view displaying working folders, projects, dates, and dual-mode Photo/Video switching.
Completely redesigned with Apple & Adobe workstation aesthetics, Studio Pro theme, live KPI summary cards,
instant search & filter pills, cover photo thumbnails, and misty mountain sidebar art.
"""

import os
import shutil
import math
from typing import Optional, List, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QScrollArea, QFrame, QInputDialog,
    QMessageBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
    QLineEdit, QComboBox, QMenu, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QGraphicsDropShadowEffect, QStyledItemDelegate, QCheckBox,
    QStyle, QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QDate, QSize, QPoint, QRectF, QPointF, QTimer
from PySide6.QtGui import (
    QPainter, QColor, QLinearGradient, QPainterPath, QPen, QBrush,
    QPixmap, QImage, QImageReader, QFont
)
from loupe.models import Folder, Project, PhotoItem
from loupe.storage import storage
from loupe.config import config
from loupe.ui import theme as theme_mod
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BG_HOVER, COLOR_BG_ACTIVE,
    COLOR_BORDER_SUBTLE, COLOR_BORDER_DISTINCT, COLOR_BORDER_FOCUS,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
    COLOR_ACCENT, COLOR_ACCENT_HOVER, COLOR_ACCENT_PRESSED,
    COLOR_STATUS_KEPT, COLOR_STATUS_REJECTED, COLOR_STATUS_MAYBE, COLOR_STATUS_PENDING,
    get_display_font, get_body_font, get_mono_font,
    THEMES, current_theme_id, apply_theme, theme_manager, is_current_theme_light
)
from loupe.ui.icons import render_icon
from loupe.ui.batch_export_dialog import BatchExportDialog


# In-memory thumbnail cover cache for snappy scrolling
_COVER_CACHE: Dict[str, QPixmap] = {}


def get_session_cover_pixmap(project: Project, width: int = 120, height: int = 80) -> QPixmap:
    """Returns a smoothly scaled, rounded cover photo thumbnail for a session, with fallback placeholder.
    Guarantees 100% full cover without letterbox black borders across portrait and landscape orientations."""
    cache_key = f"{project.id}_{width}_{height}"
    if cache_key in _COVER_CACHE:
        return _COVER_CACHE[cache_key]

    hero_path = None
    if project.items:
        # Prefer kept/selected
        for it in project.items:
            if it.status in ("kept", "selected"):
                p = it.jpeg_path or it.primary_path or it.raw_path
                if p and os.path.exists(p):
                    hero_path = p
                    break
        # Fallback to first existing item
        if not hero_path:
            for it in project.items:
                p = it.jpeg_path or it.primary_path or it.raw_path
                if p and os.path.exists(p):
                    hero_path = p
                    break

    pixmap = None
    if hero_path:
        try:
            reader = QImageReader(hero_path)
            reader.setAutoTransform(True)
            qimg = reader.read()
            if not qimg.isNull():
                scaled = qimg.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                x_off = max(0, (scaled.width() - width) // 2)
                y_off = max(0, (scaled.height() - height) // 2)
                cropped = scaled.copy(x_off, y_off, width, height)

                rounded = QPixmap(width, height)
                rounded.fill(Qt.transparent)
                painter = QPainter(rounded)
                painter.setRenderHint(QPainter.Antialiasing, True)
                path = QPainterPath()
                path.addRoundedRect(0, 0, width, height, 8, 8)
                painter.setClipPath(path)
                painter.drawImage(0, 0, cropped)
                # Subtle inner border
                painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
                painter.drawRoundedRect(QRectF(0.5, 0.5, width - 1, height - 1), 8, 8)
                painter.end()
                pixmap = rounded
        except Exception:
            pixmap = None

    if not pixmap or pixmap.isNull():
        # High-end camera aperture placeholder
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)

        path = QPainterPath()
        path.addRoundedRect(0, 0, width, height, 8, 8)
        grad = QLinearGradient(0, 0, width, height)
        grad.setColorAt(0, QColor("#1E222A"))
        grad.setColorAt(1, QColor("#121418"))
        painter.fillPath(path, grad)

        # Aperture icon centered
        icon_size = min(30, min(width, height) - 6)
        ap_icon = render_icon("aperture", icon_size, COLOR_ACCENT)
        icon_pix = ap_icon.pixmap(icon_size, icon_size)
        painter.drawPixmap((width - icon_size) // 2, (height - icon_size) // 2, icon_pix)

        painter.setPen(QPen(QColor(COLOR_BORDER_DISTINCT), 1))
        painter.drawRoundedRect(QRectF(0.5, 0.5, width - 1, height - 1), 8, 8)
        painter.end()

    _COVER_CACHE[cache_key] = pixmap
    return pixmap


def make_sparkline_pixmap(color_hex: str, points: list, width: int = 90, height: int = 36) -> QPixmap:
    """Draws a smooth anti-aliased bezier curve with gradient fill for KPI cards."""
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    color = QColor(color_hex)
    pen = QPen(color, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)

    if not points or len(points) < 2:
        points = [10, 15, 12, 20, 18, 25]

    step = width / (len(points) - 1)
    min_v, max_v = min(points), max(points)
    span = (max_v - min_v) if max_v != min_v else 1.0

    coords = []
    for i, val in enumerate(points):
        x = i * step
        norm = (val - min_v) / span
        y = height - 5 - (norm * (height - 12))
        coords.append(QPointF(x, y))

    path = QPainterPath()
    path.moveTo(coords[0])
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        cx1 = (p1.x() + p2.x()) / 2
        cy1 = p1.y()
        cx2 = (p1.x() + p2.x()) / 2
        cy2 = p2.y()
        path.cubicTo(QPointF(cx1, cy1), QPointF(cx2, cy2), p2)

    painter.drawPath(path)

    # Fill subtle glowing gradient underneath curve
    fill_path = QPainterPath(path)
    fill_path.lineTo(width, height)
    fill_path.lineTo(0, height)
    fill_path.closeSubpath()

    grad = QLinearGradient(0, 0, 0, height)
    c_top = QColor(color)
    c_top.setAlpha(40)
    grad.setColorAt(0, c_top)
    c_bottom = QColor(color)
    c_bottom.setAlpha(0)
    grad.setColorAt(1, c_bottom)

    painter.fillPath(fill_path, grad)
    painter.end()
    return pixmap


class FolderTreeDelegate(QStyledItemDelegate):
    """Custom delegate for the workspace folder tree to paint the active accent pill ONLY on column 0,
    completely preventing duplicate vertical accent borders from rendering on column 1 count badges."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if (option.state & QStyle.State_Selected) and index.column() == 0:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(COLOR_ACCENT))
            r = option.rect
            painter.drawRoundedRect(r.x(), r.y() + 4, 3, r.height() - 8, 1.5, 1.5)
            painter.restore()


class SidebarWidget(QFrame):
    """Left sidebar widget featuring high-contrast alpine mountain artwork with moonlight rim lighting."""

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w = float(self.width())
        h = float(self.height())

        # Render dramatic, clearly visible mountain silhouette in the bottom corner
        mountain_h = min(310.0, h * 0.45)
        base_y = h - mountain_h

        # Layer 1: Distant alpine peaks
        path1 = QPainterPath()
        path1.moveTo(0, h)
        path1.lineTo(0, base_y + 60)
        path1.lineTo(w * 0.18, base_y + 20)
        path1.lineTo(w * 0.35, base_y + 45)
        path1.lineTo(w * 0.58, base_y + 5)
        path1.lineTo(w * 0.76, base_y + 35)
        path1.lineTo(w, base_y + 25)
        path1.lineTo(w, h)
        path1.closeSubpath()

        grad1 = QLinearGradient(0, base_y, 0, h)
        grad1.setColorAt(0, QColor(58, 72, 92, 160))
        grad1.setColorAt(0.5, QColor(32, 40, 52, 200))
        grad1.setColorAt(1.0, QColor(18, 22, 28, 240))
        painter.fillPath(path1, grad1)

        # Moonlight rim light on layer 1
        pen1 = QPen(QColor(180, 205, 235, 120), 1.2)
        painter.setPen(pen1)
        painter.drawLine(QPointF(0, base_y + 60), QPointF(w * 0.18, base_y + 20))
        painter.drawLine(QPointF(w * 0.18, base_y + 20), QPointF(w * 0.35, base_y + 45))
        painter.drawLine(QPointF(w * 0.35, base_y + 45), QPointF(w * 0.58, base_y + 5))
        painter.drawLine(QPointF(w * 0.58, base_y + 5), QPointF(w * 0.76, base_y + 35))
        painter.drawLine(QPointF(w * 0.76, base_y + 35), QPointF(w, base_y + 25))

        # Layer 2: Mid crags
        path2 = QPainterPath()
        path2.moveTo(0, h)
        path2.lineTo(0, base_y + 110)
        path2.lineTo(w * 0.28, base_y + 65)
        path2.lineTo(w * 0.48, base_y + 95)
        path2.lineTo(w * 0.82, base_y + 48)
        path2.lineTo(w, base_y + 75)
        path2.lineTo(w, h)
        path2.closeSubpath()

        grad2 = QLinearGradient(0, base_y + 50, 0, h)
        grad2.setColorAt(0, QColor(42, 52, 66, 210))
        grad2.setColorAt(0.7, QColor(24, 28, 36, 240))
        grad2.setColorAt(1.0, QColor(14, 16, 20, 255))
        painter.fillPath(path2, grad2)

        pen2 = QPen(QColor(150, 175, 205, 90), 1.0)
        painter.setPen(pen2)
        painter.drawLine(QPointF(0, base_y + 110), QPointF(w * 0.28, base_y + 65))
        painter.drawLine(QPointF(w * 0.28, base_y + 65), QPointF(w * 0.48, base_y + 95))
        painter.drawLine(QPointF(w * 0.48, base_y + 95), QPointF(w * 0.82, base_y + 48))
        painter.drawLine(QPointF(w * 0.82, base_y + 48), QPointF(w, base_y + 75))

        # Layer 3: Near rugged ridge
        path3 = QPainterPath()
        path3.moveTo(0, h)
        path3.lineTo(0, base_y + 160)
        path3.lineTo(w * 0.42, base_y + 115)
        path3.lineTo(w * 0.70, base_y + 145)
        path3.lineTo(w, base_y + 120)
        path3.lineTo(w, h)
        path3.closeSubpath()

        grad3 = QLinearGradient(0, base_y + 100, 0, h)
        grad3.setColorAt(0, QColor(28, 34, 44, 245))
        grad3.setColorAt(1.0, QColor(10, 12, 16, 255))
        painter.fillPath(path3, grad3)

        pen3 = QPen(QColor(130, 150, 180, 60), 0.8)
        painter.setPen(pen3)
        painter.drawLine(QPointF(0, base_y + 160), QPointF(w * 0.42, base_y + 115))
        painter.drawLine(QPointF(w * 0.42, base_y + 115), QPointF(w * 0.70, base_y + 145))
        painter.drawLine(QPointF(w * 0.70, base_y + 145), QPointF(w, base_y + 120))
        painter.end()


class KPICardWidget(QFrame):
    """Clean, spacious 10px rounded KPI summary card with live counter, elevated icon box, and crisp typography."""

    def __init__(self, title: str, count_str: str, icon_name: str, color_hex: str, spark_data: Optional[list] = None, parent=None):
        super().__init__(parent)
        self.color_hex = color_hex
        self.setObjectName("kpiCardFrame")
        self.setMinimumHeight(74)
        self.setStyleSheet(f"""
            QFrame#kpiCardFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 10px;
                padding: 10px 14px;
            }}
            QFrame#kpiCardFrame:hover {{
                border-color: {COLOR_BORDER_FOCUS};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(14)

        # Left: Icon inside rounded square
        icon_box = QLabel()
        icon_box.setFixedSize(38, 38)
        icon_box.setStyleSheet(f"""
            background-color: {COLOR_BG_ELEVATED};
            border: 1px solid {COLOR_BORDER_SUBTLE};
            border-radius: 8px;
        """)
        icon_box.setAlignment(Qt.AlignCenter)
        icon_box.setPixmap(render_icon(icon_name, 18, color_hex).pixmap(18, 18))
        layout.addWidget(icon_box)

        # Middle: Big Count + Label
        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)
        text_layout.setAlignment(Qt.AlignVCenter)

        self.count_lbl = QLabel(count_str)
        self.count_lbl.setFont(get_display_font(22, bold=True))
        self.count_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; background: transparent;")
        text_layout.addWidget(self.count_lbl)

        self.title_lbl = QLabel(title)
        self.title_lbl.setFont(get_body_font(12))
        self.title_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; background: transparent;")
        text_layout.addWidget(self.title_lbl)

        layout.addLayout(text_layout)
        layout.addStretch()

    def set_data(self, count_str: str, spark_data: Optional[list] = None):
        self.count_lbl.setText(count_str)


class DashboardKPICards(QWidget):
    """Horizontal container displaying the 4 KPI summary cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.card_sessions = KPICardWidget("Sessions", "0", "folder", COLOR_ACCENT, [2, 3, 5, 4, 7, 6, 8])
        self.card_photos = KPICardWidget("Photos", "0", "photo", "#38BDF8", [40, 80, 120, 95, 180, 240, 310])
        self.card_videos = KPICardWidget("Videos", "0", "video", "#A78BFA", [5, 8, 12, 10, 18, 15, 22])
        self.card_completed = KPICardWidget("Completed", "0", "check_circle", "#22C55E", [1, 2, 2, 3, 4, 5, 6])

        layout.addWidget(self.card_sessions)
        layout.addWidget(self.card_photos)
        layout.addWidget(self.card_videos)
        layout.addWidget(self.card_completed)

    def update_from_projects(self, projects: List[Project]):
        total_sessions = len(projects)
        total_photos = sum(p.total_count for p in projects if getattr(p, "media_type", "photo") != "video")
        total_videos = sum(p.total_count for p in projects if getattr(p, "media_type", "photo") == "video")
        total_completed = sum(1 for p in projects if "Completed" in getattr(p, "status_label", ""))

        self.card_sessions.set_data(str(total_sessions))
        self.card_photos.set_data(f"{total_photos:,}")
        self.card_videos.set_data(f"{total_videos:,}")
        self.card_completed.set_data(str(total_completed))


class DashboardModalOverlay(QWidget):
    """Semi-transparent in-app modal overlay hosting creation, edit, and deletion dialogs natively."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self.setObjectName("DashboardModalOverlay")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(20, 20, 20, 20)
        outer_layout.setAlignment(Qt.AlignCenter)

        self.card = QFrame(self)
        self.card.setObjectName("inAppModalCard")
        self.card.setFixedWidth(480)
        self.card.setStyleSheet(f"""
            QFrame#inAppModalCard {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 14px;
            }}
            QLineEdit, QComboBox, QDateEdit {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(26, 24, 26, 24)
        self.card_layout.setSpacing(14)

        outer_layout.addWidget(self.card)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 12, 16, 220))

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.pos()):
            self.hide()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def _clear_card(self):
        while self.card_layout.count():
            item = self.card_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            l = item.layout()
            if l:
                while l.count():
                    sub = l.takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

    def show_create_folder(self, on_created, default_parent_id=None):
        self._clear_card()

        h_row = QHBoxLayout()
        title_text = "Create Subfolder" if default_parent_id else "Create Workspace Folder"
        title = QLabel(title_text)
        title.setFont(get_display_font(15, bold=True))
        h_row.addWidget(title)
        h_row.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(24, 24)
        btn_x.setStyleSheet(f"border: none; color: {COLOR_TEXT_MUTED}; font-size: 14px; font-weight: bold;")
        btn_x.clicked.connect(self.hide)
        h_row.addWidget(btn_x)
        self.card_layout.addLayout(h_row)

        desc = QLabel("Enter a name for your workspace folder or subfolder:")
        desc.setFont(get_body_font(12))
        desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; line-height: 1.4;")
        desc.setWordWrap(True)
        self.card_layout.addWidget(desc)

        edit = QLineEdit()
        edit.setPlaceholderText("Folder Name (e.g. Commercial, Brand A, Matchday 1)...")
        edit.setMinimumHeight(38)
        self.card_layout.addWidget(edit)

        parent_lbl = QLabel("Parent Location (Optional):")
        parent_lbl.setFont(get_body_font(11))
        parent_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; margin-top: 4px;")
        self.card_layout.addWidget(parent_lbl)

        parent_combo = QComboBox()
        parent_combo.setMinimumHeight(38)
        parent_combo.addItem("None (Top-Level Workspace Folder)", None)
        folders_with_depth = storage.get_folders_with_depth()
        sel_idx = 0
        for i, (f, depth) in enumerate(folders_with_depth):
            indent = "    " * depth + ("└─ " if depth > 0 else "")
            parent_combo.addItem(f"{indent}{f.name}", f.id)
            if default_parent_id and f.id == default_parent_id:
                sel_idx = i + 1
        parent_combo.setCurrentIndex(sel_idx)
        self.card_layout.addWidget(parent_combo)

        b_row = QHBoxLayout()
        b_row.setSpacing(10)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(get_body_font(12))
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 7px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        btn_cancel.clicked.connect(self.hide)
        b_row.addWidget(btn_cancel)

        b_row.addStretch()

        btn_confirm = QPushButton("Create")
        btn_confirm.setObjectName("accentButton")
        btn_confirm.setFont(get_body_font(12, bold=True))
        btn_confirm.setMinimumHeight(36)
        btn_confirm.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_ACCENT};
                color: #FFFFFF;
                font-weight: 700;
                font-size: 12px;
                border: 1px solid {COLOR_ACCENT_HOVER};
                border-radius: 7px;
                padding: 0 18px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_ACCENT_HOVER};
            }}
        """)

        def _submit():
            val = edit.text().strip()
            chosen_parent = parent_combo.currentData()
            if val:
                self.hide()
                on_created(val, chosen_parent)

        btn_confirm.clicked.connect(_submit)
        edit.returnPressed.connect(_submit)
        b_row.addWidget(btn_confirm)

        self.card_layout.addLayout(b_row)

        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        edit.setFocus()

    def show_rename_folder(self, current_name, on_renamed):
        self._clear_card()

        h_row = QHBoxLayout()
        title = QLabel("Rename Workspace Folder")
        title.setFont(get_display_font(15, bold=True))
        h_row.addWidget(title)
        h_row.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(24, 24)
        btn_x.setStyleSheet(f"border: none; color: {COLOR_TEXT_MUTED}; font-size: 14px; font-weight: bold;")
        btn_x.clicked.connect(self.hide)
        h_row.addWidget(btn_x)
        self.card_layout.addLayout(h_row)

        desc = QLabel("Enter a new name for this workspace folder:")
        desc.setFont(get_body_font(12))
        desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        self.card_layout.addWidget(desc)

        edit = QLineEdit(current_name)
        edit.setMinimumHeight(38)
        self.card_layout.addWidget(edit)

        b_row = QHBoxLayout()
        b_row.setSpacing(10)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(get_body_font(12))
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 7px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        btn_cancel.clicked.connect(self.hide)
        b_row.addWidget(btn_cancel)

        b_row.addStretch()

        btn_confirm = QPushButton("Save Name")
        btn_confirm.setObjectName("accentButton")
        btn_confirm.setFont(get_body_font(12, bold=True))
        btn_confirm.setMinimumHeight(36)
        btn_confirm.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_ACCENT};
                color: #FFFFFF;
                font-weight: 700;
                font-size: 12px;
                border: 1px solid {COLOR_ACCENT_HOVER};
                border-radius: 7px;
                padding: 0 18px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_ACCENT_HOVER};
            }}
        """)

        def _submit():
            val = edit.text().strip()
            if val:
                self.hide()
                on_renamed(val)

        btn_confirm.clicked.connect(_submit)
        edit.returnPressed.connect(_submit)
        b_row.addWidget(btn_confirm)

        self.card_layout.addLayout(b_row)

        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        edit.setFocus()
        edit.selectAll()

    def show_edit_project(self, project, on_saved):
        self._clear_card()

        h_row = QHBoxLayout()
        title = QLabel("Edit Session Details")
        title.setFont(get_display_font(15, bold=True))
        h_row.addWidget(title)
        h_row.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(24, 24)
        btn_x.setStyleSheet(f"border: none; color: {COLOR_TEXT_MUTED}; font-size: 14px; font-weight: bold;")
        btn_x.clicked.connect(self.hide)
        h_row.addWidget(btn_x)
        self.card_layout.addLayout(h_row)

        self.card_layout.addWidget(QLabel("Session Name:"))
        name_edit = QLineEdit(project.name)
        name_edit.setMinimumHeight(38)
        self.card_layout.addWidget(name_edit)

        self.card_layout.addWidget(QLabel("Assigned Workspace Folder:"))
        combo = QComboBox()
        combo.setMinimumHeight(38)
        folders_with_depth = storage.get_folders_with_depth()
        sel_idx = 0
        for i, (f, depth) in enumerate(folders_with_depth):
            indent = "    " * depth + ("└─ " if depth > 0 else "")
            combo.addItem(f"{indent}{f.name}", f.id)
            if f.id == project.folder_id:
                sel_idx = i
        combo.setCurrentIndex(sel_idx)
        self.card_layout.addWidget(combo)

        self.card_layout.addWidget(QLabel("Shoot Date:"))
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("yyyy-MM-dd")
        date_edit.setMinimumHeight(38)
        qd = QDate.fromString(project.shoot_date, "yyyy-MM-dd")
        if not qd.isValid():
            qd = QDate.currentDate()
        date_edit.setDate(qd)
        self.card_layout.addWidget(date_edit)

        b_row = QHBoxLayout()
        b_row.setSpacing(10)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(get_body_font(12))
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 7px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        btn_cancel.clicked.connect(self.hide)
        b_row.addWidget(btn_cancel)

        b_row.addStretch()

        btn_confirm = QPushButton("Save Changes")
        btn_confirm.setObjectName("accentButton")
        btn_confirm.setFont(get_body_font(12, bold=True))
        btn_confirm.setMinimumHeight(36)
        btn_confirm.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_ACCENT};
                color: #FFFFFF;
                font-weight: 700;
                font-size: 12px;
                border: 1px solid {COLOR_ACCENT_HOVER};
                border-radius: 7px;
                padding: 0 18px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_ACCENT_HOVER};
            }}
        """)

        def _submit():
            n = name_edit.text().strip()
            fid = combo.currentData()
            d = date_edit.date().toString("yyyy-MM-dd")
            self.hide()
            on_saved(n, fid, d)

        btn_confirm.clicked.connect(_submit)
        name_edit.returnPressed.connect(_submit)
        b_row.addWidget(btn_confirm)

        self.card_layout.addLayout(b_row)

        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        name_edit.setFocus()
        name_edit.selectAll()

    def show_edit_folder_project(self, current_folder_id, on_saved):
        self._clear_card()

        h_row = QHBoxLayout()
        title = QLabel("Edit Folder / Move Session")
        title.setFont(get_display_font(15, bold=True))
        h_row.addWidget(title)
        h_row.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(24, 24)
        btn_x.setStyleSheet(f"border: none; color: {COLOR_TEXT_MUTED}; font-size: 14px; font-weight: bold;")
        btn_x.clicked.connect(self.hide)
        h_row.addWidget(btn_x)
        self.card_layout.addLayout(h_row)

        folder = storage.get_folder_by_id(current_folder_id)
        current_name = folder.name if folder else "Personal"

        self.card_layout.addWidget(QLabel("Folder Name:"))
        name_edit = QLineEdit(current_name)
        name_edit.setMinimumHeight(38)
        self.card_layout.addWidget(name_edit)

        self.card_layout.addWidget(QLabel("Move this session to another folder:"))
        combo = QComboBox()
        combo.setMinimumHeight(38)
        folders_with_depth = storage.get_folders_with_depth()
        sel_idx = 0
        for i, (f, depth) in enumerate(folders_with_depth):
            indent = "    " * depth + ("└─ " if depth > 0 else "")
            combo.addItem(f"{indent}{f.name}", f.id)
            if f.id == current_folder_id:
                sel_idx = i
        combo.setCurrentIndex(sel_idx)
        self.card_layout.addWidget(combo)

        b_row = QHBoxLayout()
        b_row.setSpacing(10)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(get_body_font(12))
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 7px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        btn_cancel.clicked.connect(self.hide)
        b_row.addWidget(btn_cancel)

        b_row.addStretch()

        btn_confirm = QPushButton("Save Changes")
        btn_confirm.setObjectName("accentButton")
        btn_confirm.setFont(get_body_font(12, bold=True))
        btn_confirm.setMinimumHeight(36)
        btn_confirm.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_ACCENT};
                color: #FFFFFF;
                font-weight: 700;
                font-size: 12px;
                border: 1px solid {COLOR_ACCENT_HOVER};
                border-radius: 7px;
                padding: 0 18px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_ACCENT_HOVER};
            }}
        """)

        def _submit():
            n = name_edit.text().strip()
            fid = combo.currentData()
            self.hide()
            on_saved(n, fid)

        btn_confirm.clicked.connect(_submit)
        name_edit.returnPressed.connect(_submit)
        b_row.addWidget(btn_confirm)

        self.card_layout.addLayout(b_row)

        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        name_edit.setFocus()

    def show_edit_date(self, current_date_str, on_saved):
        self._clear_card()

        h_row = QHBoxLayout()
        title = QLabel("Edit Shoot Date")
        title.setFont(get_display_font(15, bold=True))
        h_row.addWidget(title)
        h_row.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(24, 24)
        btn_x.setStyleSheet(f"border: none; color: {COLOR_TEXT_MUTED}; font-size: 14px; font-weight: bold;")
        btn_x.clicked.connect(self.hide)
        h_row.addWidget(btn_x)
        self.card_layout.addLayout(h_row)

        self.card_layout.addWidget(QLabel("Select Date:"))
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("yyyy-MM-dd")
        date_edit.setMinimumHeight(38)
        qd = QDate.fromString(current_date_str, "yyyy-MM-dd")
        if not qd.isValid():
            qd = QDate.currentDate()
        date_edit.setDate(qd)
        self.card_layout.addWidget(date_edit)

        b_row = QHBoxLayout()
        b_row.setSpacing(10)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(get_body_font(12))
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 7px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        btn_cancel.clicked.connect(self.hide)
        b_row.addWidget(btn_cancel)

        b_row.addStretch()

        btn_confirm = QPushButton("Save Date")
        btn_confirm.setObjectName("accentButton")
        btn_confirm.setFont(get_body_font(12, bold=True))
        btn_confirm.setMinimumHeight(36)
        btn_confirm.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_ACCENT};
                color: #FFFFFF;
                font-weight: 700;
                font-size: 12px;
                border: 1px solid {COLOR_ACCENT_HOVER};
                border-radius: 7px;
                padding: 0 18px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_ACCENT_HOVER};
            }}
        """)

        def _submit():
            d = date_edit.date().toString("yyyy-MM-dd")
            self.hide()
            on_saved(d)

        btn_confirm.clicked.connect(_submit)
        b_row.addWidget(btn_confirm)

        self.card_layout.addLayout(b_row)

        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()

    def show_confirm_delete(self, title, message, on_confirmed, confirm_text="Delete", is_destructive=True):
        self._clear_card()

        h_row = QHBoxLayout()
        t_lbl = QLabel(title)
        t_lbl.setFont(get_display_font(15, bold=True))
        h_row.addWidget(t_lbl)
        h_row.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(24, 24)
        btn_x.setStyleSheet(f"border: none; color: {COLOR_TEXT_MUTED}; font-size: 14px; font-weight: bold;")
        btn_x.clicked.connect(self.hide)
        h_row.addWidget(btn_x)
        self.card_layout.addLayout(h_row)

        desc = QLabel(message)
        desc.setFont(get_body_font(12))
        desc.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; line-height: 1.4;")
        desc.setWordWrap(True)
        self.card_layout.addWidget(desc)

        b_row = QHBoxLayout()
        b_row.setSpacing(10)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(get_body_font(12))
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px;
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 7px;
                color: {COLOR_TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        btn_cancel.clicked.connect(self.hide)
        b_row.addWidget(btn_cancel)

        b_row.addStretch()

        btn_confirm = QPushButton(confirm_text)
        self.btn_confirm = btn_confirm
        btn_confirm.setFont(get_body_font(12, bold=True))
        btn_confirm.setMinimumHeight(36)
        
        if is_destructive:
            btn_confirm.setEnabled(False)
            btn_confirm.setText(f"{confirm_text} (5s)")
            btn_confirm.setStyleSheet("""
                QPushButton {
                    background-color: #EF4444;
                    color: #FFFFFF;
                    font-weight: 700;
                    border: 1px solid #DC2626;
                    border-radius: 7px;
                    padding: 0 18px;
                }
                QPushButton:hover {
                    background-color: #DC2626;
                }
                QPushButton:disabled {
                    background-color: #2E1B1E;
                    color: #7F5559;
                    border: 1px solid #4D262B;
                }
            """)
            countdown = 5
            self._del_timer = QTimer(self)
            def _tick():
                nonlocal countdown
                countdown -= 1
                if countdown > 0:
                    btn_confirm.setText(f"{confirm_text} ({countdown}s)")
                else:
                    self._del_timer.stop()
                    btn_confirm.setEnabled(True)
                    btn_confirm.setText(confirm_text)
            self._del_timer.timeout.connect(_tick)
            self._del_timer.start(1000)
        else:
            btn_confirm.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_ACCENT};
                    color: #FFFFFF;
                    font-weight: 700;
                    border: 1px solid {COLOR_ACCENT_HOVER};
                    border-radius: 7px;
                    padding: 0 18px;
                }}
            """)

        def _cancel_overlay():
            if hasattr(self, "_del_timer") and self._del_timer.isActive():
                self._del_timer.stop()
            self.hide()

        btn_cancel.clicked.disconnect()
        btn_cancel.clicked.connect(_cancel_overlay)
        btn_x.clicked.disconnect()
        btn_x.clicked.connect(_cancel_overlay)

        def _submit():
            if hasattr(self, "_del_timer") and self._del_timer.isActive():
                self._del_timer.stop()
            self.hide()
            on_confirmed()

        btn_confirm.clicked.connect(_submit)
        b_row.addWidget(btn_confirm)

        self.card_layout.addLayout(b_row)

        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()


class ProjectCard(QFrame):
    """Workstation project card supporting List, Grid, and Compact layout modes with real cover photo previews."""
    resume_clicked = Signal(str)  # project_id
    export_clicked = Signal(str)  # project_id
    delete_clicked = Signal(str)  # project_id
    date_changed = Signal(str, str) # project_id, new_date
    refresh_requested = Signal()
    edit_requested = Signal(object) # Project
    edit_folder_requested = Signal(object) # Project
    edit_date_requested = Signal(object) # Project
    selection_toggled = Signal(str, bool) # project_id, is_selected

    def __init__(self, project: Project, view_mode: str = "list", parent=None):
        super().__init__(parent)
        self.project = project
        self.view_mode = view_mode
        self.is_selected: bool = False
        self.setObjectName("projectCardFrame")

        if view_mode == "compact":
            self._init_compact_ui()
        elif view_mode == "grid":
            self._init_grid_ui()
        else:
            self._init_list_ui()

    def _init_compact_ui(self):
        self.setStyleSheet(f"""
            QFrame#projectCardFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 6px;
            }}
            QFrame#projectCardFrame:hover {{
                border-color: {COLOR_ACCENT};
                background-color: {COLOR_BG_ELEVATED};
            }}
            QFrame#projectCardFrame QLabel {{
                background-color: transparent;
            }}
            QPushButton:pressed {{
                padding-top: 2px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(10)

        self.select_cb = QCheckBox()
        self.select_cb.setCursor(Qt.PointingHandCursor)
        self.select_cb.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 15px;
                height: 15px;
                border-radius: 3px;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                background: {COLOR_BG_ELEVATED};
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLOR_ACCENT};
                border-color: {COLOR_ACCENT};
            }}
        """)
        self.select_cb.toggled.connect(self._on_select_toggled)
        layout.addWidget(self.select_cb)

        # Mini thumbnail
        thumb = QLabel()
        thumb.setFixedSize(28, 28)
        thumb.setStyleSheet("border-radius: 4px;")
        thumb.setPixmap(get_session_cover_pixmap(self.project, 28, 28))
        layout.addWidget(thumb)

        # Name
        name_lbl = QLabel(self.project.name)
        name_lbl.setFont(get_body_font(12, bold=True))
        name_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")
        layout.addWidget(name_lbl)

        # Type badge
        is_vid = getattr(self.project, "media_type", "photo") == "video"
        type_badge = QLabel("VIDEO" if is_vid else "PHOTO")
        type_badge.setFont(get_mono_font(9, bold=True))
        t_color = "#F59E0B" if is_vid else "#22C55E"
        t_bg = "#2D2214" if is_vid else "#142E1F"
        type_badge.setStyleSheet(f"color: {t_color}; background-color: {t_bg}; padding: 1px 6px; border-radius: 3px;")
        layout.addWidget(type_badge)

        # Folder
        folder_lbl = QLabel(self.project.get_workspace_name())
        folder_lbl.setFont(get_mono_font(11))
        folder_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        layout.addWidget(folder_lbl)

        # Date
        date_lbl = QLabel(self.project.shoot_date)
        date_lbl.setFont(get_body_font(11))
        date_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        layout.addWidget(date_lbl)

        # Count
        count_lbl = QLabel(f"{self.project.total_count} items")
        count_lbl.setFont(get_mono_font(11))
        count_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        layout.addWidget(count_lbl)

        # Status
        status_text = self.project.status_label
        s_color = COLOR_STATUS_KEPT if "Completed" in status_text else (COLOR_ACCENT if "Progress" in status_text else COLOR_TEXT_MUTED)
        s_bg = "#142E1F" if "Completed" in status_text else ("#2D2214" if "Progress" in status_text else COLOR_BG_BASE)
        status_badge = QLabel(status_text)
        status_badge.setFont(get_mono_font(10, bold=True))
        status_badge.setStyleSheet(f"color: {s_color}; background-color: {s_bg}; padding: 1px 6px; border-radius: 3px;")
        layout.addWidget(status_badge)

        layout.addStretch()

        # Resume button
        btn_text = "Resume Video" if is_vid else "Resume"
        icon_name = "arrow_right" if is_vid else "loupe"
        res_btn = QPushButton(f" {btn_text}")
        res_btn.setIcon(render_icon(icon_name, 11, COLOR_ACCENT))
        res_btn.setFont(get_body_font(11, bold=True))
        res_btn.setMinimumHeight(26)
        res_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_ACCENT};
                border-radius: 4px;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_ACCENT};
                color: #FFFFFF;
            }}
        """)
        res_btn.clicked.connect(lambda checked=False, pid=self.project.id: self.resume_clicked.emit(pid))
        layout.addWidget(res_btn)

        # Export button
        exp_btn = QPushButton()
        exp_btn.setIcon(render_icon("export", 11, COLOR_TEXT_PRIMARY))
        exp_btn.setToolTip("Export Session")
        exp_btn.setFixedSize(26, 26)
        exp_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_BG_HOVER};
                border-color: {COLOR_TEXT_SECONDARY};
            }}
        """)
        exp_btn.clicked.connect(lambda checked=False, pid=self.project.id: self.export_clicked.emit(pid))
        layout.addWidget(exp_btn)

        # Delete button
        del_btn = QPushButton()
        del_btn.setIcon(render_icon("trash", 11, COLOR_STATUS_REJECTED))
        del_btn.setToolTip("Delete Session")
        del_btn.setFixedSize(26, 26)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #3F1D1D;
                border-color: {COLOR_STATUS_REJECTED};
            }}
        """)
        del_btn.clicked.connect(lambda checked=False, pid=self.project.id: self.delete_clicked.emit(pid))
        layout.addWidget(del_btn)

    def _init_grid_ui(self):
        self.setStyleSheet(f"""
            QFrame#projectCardFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 10px;
                padding: 0px;
            }}
            QFrame#projectCardFrame:hover {{
                border-color: {COLOR_ACCENT};
                background-color: {COLOR_BG_ELEVATED};
            }}
            QFrame#projectCardFrame QLabel {{
                background-color: transparent;
            }}
            QPushButton:pressed {{
                padding-top: 2px;
            }}
        """)
        self.setMinimumWidth(240)
        self.setMaximumWidth(360)
        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(8)

        # Top: 240x130 Cover Thumbnail
        thumb = QLabel()
        thumb.setMinimumHeight(130)
        thumb.setMaximumHeight(160)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet("border-radius: 8px;")
        thumb.setPixmap(get_session_cover_pixmap(self.project, 260, 140))
        card_layout.addWidget(thumb)

        # Title & Type Row
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.select_cb = QCheckBox()
        self.select_cb.setCursor(Qt.PointingHandCursor)
        self.select_cb.setToolTip("Select session for bulk actions")
        self.select_cb.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                background: {COLOR_BG_ELEVATED};
            }}
            QCheckBox::indicator:hover {{
                border-color: {COLOR_ACCENT};
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLOR_ACCENT};
                border-color: {COLOR_ACCENT};
            }}
        """)
        self.select_cb.toggled.connect(self._on_select_toggled)
        title_row.addWidget(self.select_cb)
        name_lbl = QLabel(self.project.name)
        name_lbl.setFont(get_display_font(14, bold=True))
        name_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")
        title_row.addWidget(name_lbl)

        is_vid = getattr(self.project, "media_type", "photo") == "video"
        type_badge = QLabel("VIDEO" if is_vid else "PHOTO")
        type_badge.setFont(get_mono_font(9, bold=True))
        t_color = "#F59E0B" if is_vid else "#22C55E"
        t_bg = "#2D2214" if is_vid else "#142E1F"
        type_badge.setStyleSheet(f"color: {t_color}; background-color: {t_bg}; padding: 2px 6px; border-radius: 4px;")
        title_row.addWidget(type_badge)
        title_row.addStretch()
        card_layout.addLayout(title_row)

        # Folder & Date Row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        f_lbl = QLabel(f"📁 {self.project.get_workspace_name()}")
        f_lbl.setFont(get_mono_font(11))
        f_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        meta_row.addWidget(f_lbl)

        d_lbl = QLabel(f"📅 {self.project.shoot_date}")
        d_lbl.setFont(get_body_font(11))
        d_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        meta_row.addWidget(d_lbl)
        meta_row.addStretch()
        card_layout.addLayout(meta_row)

        # Status & Count Row
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_text = self.project.status_label
        s_color = COLOR_STATUS_KEPT if "Completed" in status_text else (COLOR_ACCENT if "Progress" in status_text else COLOR_TEXT_MUTED)
        s_bg = "#142E1F" if "Completed" in status_text else ("#2D2214" if "Progress" in status_text else COLOR_BG_BASE)
        s_badge = QLabel(status_text)
        s_badge.setFont(get_mono_font(10, bold=True))
        s_badge.setStyleSheet(f"color: {s_color}; background-color: {s_bg}; padding: 2px 6px; border-radius: 4px;")
        status_row.addWidget(s_badge)

        cnt_lbl = QLabel(f"{self.project.total_count} items")
        cnt_lbl.setFont(get_mono_font(11))
        cnt_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        status_row.addWidget(cnt_lbl)
        status_row.addStretch()
        card_layout.addLayout(status_row)

        card_layout.addSpacing(4)

        # Action Buttons
        btn_text = "Resume Video Sort" if is_vid else "Resume Culling"
        icon_name = "arrow_right" if is_vid else "loupe"
        res_btn = QPushButton(f" {btn_text}")
        res_btn.setIcon(render_icon(icon_name, 11, COLOR_ACCENT))
        res_btn.setFont(get_body_font(11, bold=True))
        res_btn.setMinimumHeight(30)
        res_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_ACCENT};
                border-radius: 6px;
                padding: 0 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: {COLOR_ACCENT};
                color: #FFFFFF;
            }}
        """)
        res_btn.clicked.connect(lambda checked=False, pid=self.project.id: self.resume_clicked.emit(pid))
        card_layout.addWidget(res_btn)

        act_row = QHBoxLayout()
        act_row.setSpacing(6)
        exp_btn = QPushButton(" Export")
        exp_btn.setIcon(render_icon("export", 11, COLOR_TEXT_PRIMARY))
        exp_btn.setFont(get_body_font(11))
        exp_btn.setMinimumHeight(28)
        exp_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 6px;
                padding: 0 8px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_BG_HOVER};
                border-color: {COLOR_TEXT_SECONDARY};
            }}
        """)
        exp_btn.clicked.connect(lambda checked=False, pid=self.project.id: self.export_clicked.emit(pid))
        act_row.addWidget(exp_btn, stretch=1)

        del_btn = QPushButton()
        del_btn.setIcon(render_icon("trash", 11, COLOR_STATUS_REJECTED))
        del_btn.setToolTip("Delete Session")
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #3F1D1D;
                border-color: {COLOR_STATUS_REJECTED};
            }}
        """)
        del_btn.clicked.connect(lambda checked=False, pid=self.project.id: self.delete_clicked.emit(pid))
        act_row.addWidget(del_btn)
        card_layout.addLayout(act_row)

    def _on_select_toggled(self, checked: bool):
        self.is_selected = checked
        self._update_card_selection_style()
        self.selection_toggled.emit(self.project.id, checked)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        if hasattr(self, "select_cb"):
            self.select_cb.blockSignals(True)
            self.select_cb.setChecked(selected)
            self.select_cb.blockSignals(False)
        self._update_card_selection_style()

    def _update_card_selection_style(self):
        if self.is_selected:
            self.setStyleSheet(f"""
                QFrame#projectCardFrame {{
                    background-color: {COLOR_BG_ACTIVE};
                    border: 1.5px solid {COLOR_ACCENT};
                    border-radius: {'6px' if self.view_mode == 'compact' else '10px'};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame#projectCardFrame {{
                    background-color: {COLOR_BG_SURFACE};
                    border: 1px solid {COLOR_BORDER_DISTINCT};
                    border-radius: {'6px' if self.view_mode == 'compact' else '10px'};
                }}
                QFrame#projectCardFrame:hover {{
                    border-color: {COLOR_ACCENT};
                    background-color: {COLOR_BG_ELEVATED};
                }}
            """)

    def _init_list_ui(self):
        project = self.project
        self.setStyleSheet(f"""
            QFrame#projectCardFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 10px;
                padding: 6px;
            }}
            QFrame#projectCardFrame:hover {{
                border-color: {COLOR_ACCENT};
                background-color: {COLOR_BG_ELEVATED};
            }}
            QFrame#projectCardFrame QLabel {{
                background-color: transparent;
            }}
            QPushButton:pressed {{
                padding-top: 2px;
            }}
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 16, 12)
        main_layout.setSpacing(14)

        # Checkbox for multi-select
        self.select_cb = QCheckBox()
        self.select_cb.setCursor(Qt.PointingHandCursor)
        self.select_cb.setToolTip("Select session for bulk actions")
        self.select_cb.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                background: {COLOR_BG_ELEVATED};
            }}
            QCheckBox::indicator:hover {{
                border-color: {COLOR_ACCENT};
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLOR_ACCENT};
                border-color: {COLOR_ACCENT};
            }}
        """)
        self.select_cb.toggled.connect(self._on_select_toggled)
        main_layout.addWidget(self.select_cb)

        # 1. Left: Cover Thumbnail (120x80)
        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(120, 80)
        self.thumb_lbl.setStyleSheet("background: transparent; border-radius: 8px;")
        self.thumb_lbl.setPixmap(get_session_cover_pixmap(project, 120, 80))
        main_layout.addWidget(self.thumb_lbl)

        # 2. Center: Metadata Stack
        details_layout = QVBoxLayout()
        details_layout.setSpacing(6)
        details_layout.setAlignment(Qt.AlignVCenter)

        # Row 1: Session Name + Media Badge + Sync Badge + Edit
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_lbl = QLabel(project.name)
        title_lbl.setFont(get_display_font(15, bold=True))
        title_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")
        title_row.addWidget(title_lbl)

        is_vid = getattr(project, "media_type", "photo") == "video"
        type_badge = QLabel("• VIDEO" if is_vid else "• PHOTO")
        type_badge.setFont(get_mono_font(10, bold=True))
        is_light = is_current_theme_light()
        if is_vid:
            type_badge.setStyleSheet("color: #F59E0B; background-color: #2D2214; padding: 2px 8px; border: 1px solid #754B1A; border-radius: 4px;")
        else:
            type_badge.setStyleSheet("color: #22C55E; background-color: #142E1F; padding: 2px 8px; border: 1px solid #1E5C38; border-radius: 4px;")
        title_row.addWidget(type_badge)

        if getattr(project, "sync_pairs", False) and getattr(project, "format_mode", "") == "both":
            pair_badge = QLabel("Synced Pairs")
            pair_badge.setFont(get_body_font(10))
            pair_badge.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; background-color: {COLOR_BG_ELEVATED}; padding: 2px 8px; border: 1px solid {COLOR_BORDER_SUBTLE}; border-radius: 4px;")
            title_row.addWidget(pair_badge)

        edit_session_btn = QPushButton("Edit")
        edit_session_btn.setIcon(render_icon("edit", 11, COLOR_TEXT_SECONDARY))
        edit_session_btn.setFont(get_body_font(11))
        edit_session_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 2px 8px;
                color: {COLOR_TEXT_SECONDARY};
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_SUBTLE};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                border-color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_HOVER};
            }}
        """)
        edit_session_btn.setToolTip("Edit session name, folder, and date")
        edit_session_btn.clicked.connect(self._on_edit_session)
        title_row.addWidget(edit_session_btn)

        title_row.addStretch()
        details_layout.addLayout(title_row)

        # Row 2: Folder Info + Shoot Date
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(12)

        folder_name = project.get_workspace_name()
        f_icon_lbl = QLabel()
        f_icon_lbl.setPixmap(render_icon("folder", 12, COLOR_TEXT_MUTED).pixmap(12, 12))
        meta_layout.addWidget(f_icon_lbl)

        folder_lbl = QLabel(folder_name)
        folder_lbl.setFont(get_mono_font(12))
        folder_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        meta_layout.addWidget(folder_lbl)

        edit_folder_btn = QPushButton("Edit Folder")
        edit_folder_btn.setIcon(render_icon("edit", 10, COLOR_ACCENT))
        edit_folder_btn.setFont(get_body_font(10))
        edit_folder_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 1px 7px;
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_BORDER_SUBTLE};
                background-color: transparent;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
                background-color: {COLOR_BG_HOVER};
            }}
        """)
        edit_folder_btn.clicked.connect(self._on_edit_folder)
        meta_layout.addWidget(edit_folder_btn)

        c_icon_lbl = QLabel()
        c_icon_lbl.setPixmap(render_icon("calendar", 12, COLOR_TEXT_MUTED).pixmap(12, 12))
        meta_layout.addWidget(c_icon_lbl)

        # Format date human-readable like 'October 15, 2026'
        qd = QDate.fromString(project.shoot_date, "yyyy-MM-dd")
        display_date = qd.toString("MMMM d, yyyy") if qd.isValid() else project.shoot_date
        date_lbl = QLabel(display_date)
        date_lbl.setFont(get_body_font(11))
        date_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        meta_layout.addWidget(date_lbl)

        edit_date_btn = QPushButton("Change Date")
        edit_date_btn.setFont(get_body_font(10))
        edit_date_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 1px 7px;
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_BORDER_SUBTLE};
                background-color: transparent;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
                background-color: {COLOR_BG_HOVER};
            }}
        """)
        edit_date_btn.clicked.connect(self._on_edit_date)
        meta_layout.addWidget(edit_date_btn)

        meta_layout.addStretch()
        details_layout.addLayout(meta_layout)

        # Row 3: Status badge & format
        status_layout = QHBoxLayout()
        status_layout.setSpacing(10)

        status_text = project.status_label
        if "Completed" in status_text:
            s_color = COLOR_STATUS_KEPT
            s_bg = "#142E1F" if not is_light else "#DCFCE7"
            s_border = "#1E5C38" if not is_light else "#86EFAC"
            prefix = "✓ "
        elif "Progress" in status_text:
            s_color = COLOR_ACCENT
            s_bg = "#2D2214" if not is_light else "#FEF3C7"
            s_border = "#754B1A" if not is_light else "#FCD34D"
            prefix = "⚡ "
        else:
            s_color = COLOR_TEXT_MUTED
            s_bg = COLOR_BG_BASE
            s_border = COLOR_BORDER_SUBTLE
            prefix = "○ "

        status_badge = QLabel(f"{prefix}{status_text}")
        status_badge.setFont(get_mono_font(11, bold=True))
        status_badge.setStyleSheet(f"color: {s_color}; background-color: {s_bg}; padding: 2px 8px; border: 1px solid {s_border}; border-radius: 4px;")
        status_layout.addWidget(status_badge)

        if is_vid:
            format_info = f"• {project.selected_count} Selected • {project.similar_count} Similar • {project.total_count} Clips"
        else:
            format_info = f"• {project.format_mode.replace('_', ' ').upper()} • {project.total_count} Frames"

        info_lbl = QLabel(format_info)
        info_lbl.setFont(get_body_font(12))
        info_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        status_layout.addWidget(info_lbl)

        status_layout.addStretch()
        details_layout.addLayout(status_layout)

        # Row 4: LRC Edited Results (Photo mode)
        if not is_vid:
            edited_layout = QHBoxLayout()
            edited_layout.setSpacing(10)

            edited_count = project.edited_count
            if edited_count > 0:
                edited_badge = QLabel(f"✓ {edited_count} photo(s) in 'edited result'")
                edited_badge.setFont(get_mono_font(11, bold=True))
                edited_badge.setStyleSheet(f"color: {COLOR_ACCENT}; background-color: #261E14; padding: 2px 8px; border: 1px solid #754B1A; border-radius: 4px;")
                edited_layout.addWidget(edited_badge)

                add_more_btn = QPushButton(" Add Files")
                add_more_btn.setIcon(render_icon("plus", 11, COLOR_TEXT_PRIMARY))
                add_more_btn.setFont(get_body_font(10))
                add_more_btn.setStyleSheet(f"""
                    QPushButton {{
                        padding: 2px 8px;
                        color: {COLOR_TEXT_PRIMARY};
                        border: 1px solid {COLOR_BORDER_DISTINCT};
                        background-color: {COLOR_BG_ELEVATED};
                        border-radius: 4px;
                    }}
                    QPushButton:hover {{
                        border-color: {COLOR_ACCENT};
                        color: {COLOR_ACCENT};
                    }}
                """)
                add_more_btn.clicked.connect(self._on_add_edited_files)
                edited_layout.addWidget(add_more_btn)

                open_folder_btn = QPushButton("Open Folder")
                open_folder_btn.setIcon(render_icon("folder", 11, COLOR_ACCENT))
                open_folder_btn.setFont(get_body_font(10))
                open_folder_btn.setStyleSheet(f"""
                    QPushButton {{
                        padding: 2px 8px;
                        color: {COLOR_ACCENT};
                        border: 1px solid {COLOR_ACCENT};
                        background-color: #221A12;
                        border-radius: 4px;
                        font-weight: 600;
                    }}
                    QPushButton:hover {{
                        background-color: {COLOR_ACCENT};
                        color: #FFFFFF;
                    }}
                """)
                open_folder_btn.clicked.connect(self._on_open_edited_folder)
                edited_layout.addWidget(open_folder_btn)
            else:
                edited_hint = QLabel("Edited Result:")
                edited_hint.setFont(get_mono_font(11))
                edited_hint.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
                edited_layout.addWidget(edited_hint)

                add_btn = QPushButton(" Add Files (LRC)")
                add_btn.setIcon(render_icon("plus", 11, COLOR_ACCENT))
                add_btn.setFont(get_body_font(10))
                add_btn.setStyleSheet(f"""
                    QPushButton {{
                        padding: 2px 8px;
                        color: {COLOR_ACCENT};
                        border: 1px solid {COLOR_BORDER_DISTINCT};
                        background-color: {COLOR_BG_ELEVATED};
                        border-radius: 4px;
                    }}
                    QPushButton:hover {{
                        border-color: {COLOR_ACCENT};
                        background-color: {COLOR_BG_HOVER};
                    }}
                """)
                add_btn.clicked.connect(self._on_add_edited_files)
                edited_layout.addWidget(add_btn)

            edited_layout.addStretch()
            details_layout.addLayout(edited_layout)

        main_layout.addLayout(details_layout, stretch=1)

        # 3. Right: Stacked Action Buttons matching mockup perfectly
        actions_vlayout = QVBoxLayout()
        actions_vlayout.setSpacing(6)
        actions_vlayout.setAlignment(Qt.AlignVCenter)

        btn_text = "Resume Video Sort" if is_vid else "Resume Culling"
        icon_name = "arrow_right" if is_vid else "loupe"

        self.resume_btn = QPushButton(f"  {btn_text}")
        self.resume_btn.setObjectName("resumeCullButton")
        self.resume_btn.setIcon(render_icon(icon_name, 12, COLOR_ACCENT))
        self.resume_btn.setFont(get_body_font(11, bold=True))
        self.resume_btn.setMinimumHeight(32)
        self.resume_btn.setStyleSheet(f"""
            QPushButton#resumeCullButton {{
                background-color: transparent;
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_ACCENT};
                border-radius: 6px;
                padding: 0 14px;
                font-weight: 700;
            }}
            QPushButton#resumeCullButton:hover {{
                background-color: {COLOR_ACCENT};
                color: #FFFFFF;
            }}
        """)
        self.resume_btn.clicked.connect(lambda checked=False, pid=project.id: self.resume_clicked.emit(pid))
        actions_vlayout.addWidget(self.resume_btn)

        bottom_actions = QHBoxLayout()
        bottom_actions.setSpacing(6)

        self.export_btn = QPushButton(" Export")
        self.export_btn.setIcon(render_icon("export", 12, COLOR_TEXT_PRIMARY))
        self.export_btn.setFont(get_body_font(11))
        self.export_btn.setMinimumHeight(30)
        self.export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 6px;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_BG_HOVER};
                border-color: {COLOR_TEXT_SECONDARY};
            }}
        """)
        self.export_btn.clicked.connect(lambda checked=False, pid=project.id: self.export_clicked.emit(pid))
        bottom_actions.addWidget(self.export_btn, stretch=1)

        self.del_btn = QPushButton()
        self.del_btn.setIcon(render_icon("trash", 12, COLOR_STATUS_REJECTED))
        self.del_btn.setToolTip("Delete Session")
        self.del_btn.setFixedSize(30, 30)
        self.del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #3F1D1D;
                border-color: {COLOR_STATUS_REJECTED};
            }}
        """)
        self.del_btn.clicked.connect(lambda checked=False, pid=project.id: self.delete_clicked.emit(pid))
        bottom_actions.addWidget(self.del_btn)

        actions_vlayout.addLayout(bottom_actions)
        main_layout.addLayout(actions_vlayout)

    def _on_edit_session(self):
        self.edit_requested.emit(self.project)

    def _on_edit_folder(self):
        self.edit_folder_requested.emit(self.project)

    def _on_edit_date(self):
        self.edit_date_requested.emit(self.project)

    def _on_add_edited_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Lightroom Classic Edited Photos",
            "",
            "Images (*.jpg *.jpeg *.png *.tif *.tiff);;All Files (*.*)"
        )
        if not files:
            return

        proj_folder_name = self.project.name.strip().replace(" ", "_")
        dest_dir = os.path.join(storage.data_dir, "projects", proj_folder_name, "edited result")
        os.makedirs(dest_dir, exist_ok=True)

        copied = 0
        for f in files:
            try:
                shutil.copy2(f, dest_dir)
                copied += 1
            except Exception as e:
                print(f"[ProjectCard] Error copying edited file {f}: {e}")

        if copied > 0:
            self.refresh_requested.emit()

    def _on_open_edited_folder(self):
        proj_folder_name = self.project.name.strip().replace(" ", "_")
        dest_dir = os.path.join(storage.data_dir, "projects", proj_folder_name, "edited result")
        if os.path.exists(dest_dir):
            if os.name == "nt":
                os.startfile(dest_dir)
            else:
                import subprocess
                subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", dest_dir])
        else:
            QMessageBox.warning(self, "Folder Not Found", "The 'edited result' folder does not exist yet. Click 'Add Files' first.")


class DashboardView(QWidget):
    """Main Dashboard with dual Photo/Video mode switching, live KPI cards, real-time search/filter bar, and nested folders."""
    new_session_requested = Signal()
    open_project_requested = Signal(str)  # project_id
    export_project_requested = Signal(str) # project_id
    open_settings_requested = Signal()
    fullscreen_requested = Signal()
    media_mode_changed = Signal(str)      # "photo" or "video"
    gallery_requested = Signal()
    resume_culling_queue_requested = Signal(list)  # List[str] project_ids
    batch_export_requested = Signal(list)          # List[Project] projects

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_folder_id: Optional[str] = None
        self.current_media_mode: str = "photo"  # "photo" or "video"
        self.search_query: str = ""
        self.active_status_filter: str = "All"  # All, Photos, Videos, Completed, In Progress
        self.current_view_mode: str = "list"  # "list", "grid", or "compact"
        self.selected_project_ids = set()
        self._current_rendered_cards = {}
        self._init_ui()
        self._setup_bulk_bar()
        self.modal_overlay = DashboardModalOverlay(self)
        self.refresh()
        theme_manager.theme_changed.connect(self._on_theme_changed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "modal_overlay") and self.modal_overlay:
            self.modal_overlay.setGeometry(self.rect())
        if hasattr(self, "bulk_bar"):
            self._position_bulk_bar()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Top Header Bar
        self.header_bar = QFrame()
        self.header_bar.setObjectName("dashboardHeaderBar")
        self.header_bar.setStyleSheet(f"""
            QFrame#dashboardHeaderBar {{
                background-color: {COLOR_BG_SURFACE};
                border-bottom: 1px solid {COLOR_BORDER_DISTINCT};
            }}
        """)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(24, 12, 24, 12)
        header_layout.setSpacing(16)

        # App Brand
        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(10)
        self.brand_icon_lbl = QLabel()
        self.brand_icon_lbl.setPixmap(render_icon("brand_frame", 22, COLOR_ACCENT).pixmap(22, 22))
        brand_layout.addWidget(self.brand_icon_lbl)

        brand_text_layout = QVBoxLayout()
        brand_text_layout.setSpacing(1)
        self.brand_title = QLabel("FRAMED")
        self.brand_title.setFont(get_display_font(18, bold=True))
        self.brand_title.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; letter-spacing: 2px;")
        self.brand_sub = QLabel("PHOTOGRAPHER & VIDEOGRAPHER WORKSTATION")
        self.brand_sub.setFont(get_mono_font(9, bold=True))
        self.brand_sub.setStyleSheet(f"color: {COLOR_ACCENT}; letter-spacing: 1px;")
        brand_text_layout.addWidget(self.brand_title)
        brand_text_layout.addWidget(self.brand_sub)
        brand_layout.addLayout(brand_text_layout)
        header_layout.addLayout(brand_layout)

        # Mode Switcher (Photosort | Videosort)
        self.mode_switcher_frame = QFrame()
        self.mode_switcher_frame.setObjectName("modeSwitcherFrame")
        self.mode_switcher_frame.setStyleSheet(f"""
            QFrame#modeSwitcherFrame {{
                background-color: {COLOR_BG_BASE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 8px;
            }}
        """)
        ms_layout = QHBoxLayout(self.mode_switcher_frame)
        ms_layout.setContentsMargins(3, 3, 3, 3)
        ms_layout.setSpacing(4)

        self.btn_mode_photo = QPushButton(" Photosort")
        self.btn_mode_photo.setIcon(render_icon("photo", 13, COLOR_ACCENT))
        self.btn_mode_photo.setFont(get_mono_font(11, bold=True))
        self.btn_mode_photo.clicked.connect(lambda: self._set_media_mode("photo"))
        ms_layout.addWidget(self.btn_mode_photo)

        self.btn_mode_video = QPushButton(" Videosort")
        self.btn_mode_video.setIcon(render_icon("video", 13, COLOR_TEXT_MUTED))
        self.btn_mode_video.setFont(get_mono_font(11, bold=True))
        self.btn_mode_video.clicked.connect(lambda: self._set_media_mode("video"))
        ms_layout.addWidget(self.btn_mode_video)

        self.btn_mode_gallery = QPushButton(" Gallery")
        self.btn_mode_gallery.setIcon(render_icon("gallery", 13, COLOR_TEXT_MUTED))
        self.btn_mode_gallery.setFont(get_mono_font(11, bold=True))
        self.btn_mode_gallery.clicked.connect(self.gallery_requested.emit)
        ms_layout.addWidget(self.btn_mode_gallery)

        header_layout.addWidget(self.mode_switcher_frame)
        self._update_mode_switcher_styles()

        header_layout.addStretch()

        # Action Buttons
        self.new_session_btn = QPushButton("+ New Photo Session")
        self.new_session_btn.setObjectName("accentPillButton")
        self.new_session_btn.setFont(get_body_font(12, bold=True))
        self.new_session_btn.setMinimumHeight(36)
        self.new_session_btn.setStyleSheet(f"""
            QPushButton#accentPillButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COLOR_ACCENT}, stop:1 {COLOR_ACCENT_PRESSED});
                color: #FFFFFF;
                border: 1px solid {COLOR_ACCENT_HOVER};
                border-radius: 8px;
                padding: 0 18px;
                font-weight: 700;
            }}
            QPushButton#accentPillButton:hover {{
                background: {COLOR_ACCENT_HOVER};
            }}
        """)
        self.new_session_btn.clicked.connect(self.new_session_requested.emit)
        header_layout.addWidget(self.new_session_btn)

        self.gdrive_btn = QPushButton("Google Drive")
        self.gdrive_btn.setIcon(render_icon("cloud", 14, COLOR_ACCENT))
        self.gdrive_btn.setFont(get_body_font(11))
        self.gdrive_btn.setMinimumHeight(36)
        self.gdrive_btn.setStyleSheet(self._get_header_btn_style())
        self.gdrive_btn.clicked.connect(self._open_gdrive_manager)
        header_layout.addWidget(self.gdrive_btn)

        self.theme_btn = QPushButton("Theme")
        self.theme_btn.setIcon(render_icon("palette", 14, COLOR_ACCENT))
        self.theme_btn.setFont(get_body_font(11))
        self.theme_btn.setMinimumHeight(36)
        self.theme_btn.setStyleSheet(self._get_header_btn_style())
        self.theme_btn.clicked.connect(self._open_theme_menu)
        header_layout.addWidget(self.theme_btn)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setIcon(render_icon("settings", 14, COLOR_TEXT_PRIMARY))
        self.settings_btn.setFont(get_body_font(11))
        self.settings_btn.setMinimumHeight(36)
        self.settings_btn.setStyleSheet(self._get_header_btn_style())
        self.settings_btn.clicked.connect(self.open_settings_requested.emit)
        header_layout.addWidget(self.settings_btn)

        self.fullscreen_btn = QPushButton("Full Screen (F11)")
        self.fullscreen_btn.setIcon(render_icon("fit", 13, COLOR_TEXT_PRIMARY))
        self.fullscreen_btn.setFont(get_body_font(11))
        self.fullscreen_btn.setMinimumHeight(36)
        self.fullscreen_btn.setStyleSheet(self._get_header_btn_style())
        self.fullscreen_btn.clicked.connect(self.fullscreen_requested.emit)
        header_layout.addWidget(self.fullscreen_btn)

        root_layout.addWidget(self.header_bar)

        # 2. Main Content Split: Left Sidebar + Right Workspace
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Left Sidebar (Folders + Misty Mountain Art)
        self.sidebar = SidebarWidget()
        self.sidebar.setObjectName("dashboardSidebar")
        self.sidebar.setFixedWidth(290)
        self.sidebar.setStyleSheet(f"""
            QFrame#dashboardSidebar {{
                background-color: {COLOR_BG_SURFACE};
                border-right: 1px solid {COLOR_BORDER_DISTINCT};
            }}
        """)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 20, 16, 16)
        sidebar_layout.setSpacing(14)

        sidebar_title_layout = QHBoxLayout()
        self.sidebar_title = QLabel("WORKSPACE FOLDERS")
        self.sidebar_title.setFont(get_mono_font(10, bold=True))
        self.sidebar_title.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; letter-spacing: 1.5px;")
        sidebar_title_layout.addWidget(self.sidebar_title)
        sidebar_title_layout.addStretch()

        self.add_folder_btn = QPushButton()
        self.add_folder_btn.setIcon(render_icon("plus", 12, COLOR_TEXT_PRIMARY))
        self.add_folder_btn.setToolTip("Create New Folder (e.g. School, Weddings, Personal)")
        self.add_folder_btn.setFixedSize(26, 26)
        self.add_folder_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
                background-color: {COLOR_BG_HOVER};
            }}
        """)
        self.add_folder_btn.clicked.connect(self._create_new_folder)
        sidebar_title_layout.addWidget(self.add_folder_btn)
        sidebar_layout.addLayout(sidebar_title_layout)

        # Folder Tree Widget (2 columns: 0=Name, 1=Count Badge)
        self.folder_tree = QTreeWidget()
        self.folder_tree.count = self.folder_tree.topLevelItemCount
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setColumnCount(2)
        self.folder_tree.header().setStretchLastSection(False)
        self.folder_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.folder_tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.folder_tree.setColumnWidth(1, 46)
        self.folder_tree.setIndentation(14)
        self.folder_tree.setRootIsDecorated(True)
        self.folder_tree.setAnimated(True)
        self.folder_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folder_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.folder_tree.itemClicked.connect(self._on_tree_item_clicked)
        self.folder_list = self.folder_tree  # alias for backward compatibility
        self.folder_tree.setItemDelegate(FolderTreeDelegate(self.folder_tree))
        self.folder_tree.setStyleSheet(self._get_tree_style())
        sidebar_layout.addWidget(self.folder_tree, stretch=1)

        # Bottom Sidebar Action Buttons
        folder_actions_layout = QHBoxLayout()
        folder_actions_layout.setSpacing(6)

        self.add_subfolder_btn = QPushButton(" Subfolder")
        self.add_subfolder_btn.setIcon(render_icon("plus", 11, COLOR_TEXT_PRIMARY))
        self.add_subfolder_btn.setFont(get_body_font(11))
        self.add_subfolder_btn.setStyleSheet(self._get_sidebar_btn_style())
        self.add_subfolder_btn.clicked.connect(lambda: self._create_new_subfolder())
        self.add_subfolder_btn.setEnabled(False)
        folder_actions_layout.addWidget(self.add_subfolder_btn)

        self.rename_folder_btn = QPushButton("Rename")
        self.rename_folder_btn.setIcon(render_icon("edit", 11, COLOR_TEXT_PRIMARY))
        self.rename_folder_btn.setFont(get_body_font(11))
        self.rename_folder_btn.setStyleSheet(self._get_sidebar_btn_style())
        self.rename_folder_btn.clicked.connect(self._rename_selected_folder)
        folder_actions_layout.addWidget(self.rename_folder_btn)

        self.delete_folder_btn = QPushButton("Delete")
        self.delete_folder_btn.setIcon(render_icon("trash", 11, COLOR_STATUS_REJECTED))
        self.delete_folder_btn.setFont(get_body_font(11))
        self.delete_folder_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 6px;
                color: {COLOR_STATUS_REJECTED};
                padding: 5px 10px;
            }}
            QPushButton:hover {{
                background-color: #3F1D1D;
                border-color: {COLOR_STATUS_REJECTED};
            }}
        """)
        self.delete_folder_btn.clicked.connect(self._delete_selected_folder)
        folder_actions_layout.addWidget(self.delete_folder_btn)

        sidebar_layout.addLayout(folder_actions_layout)
        content_layout.addWidget(self.sidebar)

        # Right Area: Projects + KPI Summary + Filter Bar
        self.right_area = QWidget()
        self.right_area.setObjectName("dashboardRightArea")
        self.right_area.setStyleSheet(f"""
            QWidget#dashboardRightArea {{
                background-color: {COLOR_BG_BASE};
            }}
            QLabel {{
                background-color: transparent;
            }}
        """)
        right_layout = QVBoxLayout(self.right_area)
        right_layout.setContentsMargins(32, 22, 32, 20)
        right_layout.setSpacing(18)

        # Top KPI Summary Cards Row
        self.kpi_cards = DashboardKPICards()
        right_layout.addWidget(self.kpi_cards)

        # Row 1: Folder Title, Subtitle, and Folder Action Buttons
        title_row = QHBoxLayout()
        title_row.setSpacing(14)
        title_row.setAlignment(Qt.AlignVCenter)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.folder_title_lbl = QLabel("Commercial")
        self.folder_title_lbl.setFont(get_display_font(22, bold=True))
        self.folder_title_lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")
        title_box.addWidget(self.folder_title_lbl)

        self.folder_desc_lbl = QLabel("Your commercial photography sessions")
        self.folder_desc_lbl.setFont(get_body_font(12))
        self.folder_desc_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        title_box.addWidget(self.folder_desc_lbl)
        title_row.addLayout(title_box)

        title_row.addStretch()

        # Header subfolder / edit folder buttons
        self.header_add_subfolder_btn = QPushButton("+ Subfolder")
        self.header_add_subfolder_btn.setIcon(render_icon("plus", 11, COLOR_ACCENT))
        self.header_add_subfolder_btn.setFont(get_body_font(11))
        self.header_add_subfolder_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 5px 14px;
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_BORDER_SUBTLE};
                background-color: transparent;
                border-radius: 6px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
                background-color: {COLOR_BG_HOVER};
            }}
            QPushButton:pressed {{
                padding-top: 2px;
            }}
        """)
        self.header_add_subfolder_btn.clicked.connect(lambda: self._create_new_subfolder())
        self.header_add_subfolder_btn.setVisible(False)
        title_row.addWidget(self.header_add_subfolder_btn)

        self.header_edit_folder_btn = QPushButton("Edit Folder")
        self.header_edit_folder_btn.setIcon(render_icon("edit", 11, COLOR_ACCENT))
        self.header_edit_folder_btn.setFont(get_body_font(11))
        self.header_edit_folder_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 5px 14px;
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_BORDER_SUBTLE};
                background-color: transparent;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
                background-color: {COLOR_BG_HOVER};
            }}
            QPushButton:pressed {{
                padding-top: 2px;
            }}
        """)
        self.header_edit_folder_btn.clicked.connect(self._rename_selected_folder)
        self.header_edit_folder_btn.setVisible(False)
        title_row.addWidget(self.header_edit_folder_btn)

        right_layout.addLayout(title_row)

        # Row 2: Search, Filter Pills, and View Switcher Toolbar
        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(12)
        toolbar_row.setAlignment(Qt.AlignVCenter)

        # Real-time search field
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search sessions...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(200)
        self.search_edit.setMaximumWidth(320)
        self.search_edit.setMinimumHeight(34)
        self.search_edit.setFont(get_body_font(12))
        self.search_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 8px;
                padding: 0 12px;
            }}
            QLineEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        toolbar_row.addWidget(self.search_edit)

        self.btn_select_toggle = QPushButton("Select All")
        self.btn_select_toggle.setIcon(render_icon("check", 11, COLOR_TEXT_SECONDARY))
        self.btn_select_toggle.setFont(get_body_font(11))
        self.btn_select_toggle.setMinimumHeight(34)
        self.btn_select_toggle.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_TEXT_SECONDARY};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 8px;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                border-color: {COLOR_ACCENT};
            }}
        """)
        self.btn_select_toggle.clicked.connect(self._toggle_select_all)
        toolbar_row.addWidget(self.btn_select_toggle)

        toolbar_row.addStretch()

        # Status filter pills
        self.filter_pills_frame = QFrame()
        self.filter_pills_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 8px;
            }}
            QPushButton:pressed {{
                padding-top: 2px;
            }}
        """)
        fp_layout = QHBoxLayout(self.filter_pills_frame)
        fp_layout.setContentsMargins(3, 3, 3, 3)
        fp_layout.setSpacing(4)

        self.filter_buttons = {}
        for f_name in ["All", "Photos", "Videos", "Completed", "In Progress"]:
            btn = QPushButton(f_name)
            btn.setFont(get_body_font(11))
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False, fn=f_name: self._set_status_filter(fn))
            fp_layout.addWidget(btn)
            self.filter_buttons[f_name] = btn

        toolbar_row.addWidget(self.filter_pills_frame)
        self._update_filter_pill_styles()

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Plain)
        sep.setFixedWidth(1)
        sep.setFixedHeight(20)
        sep.setStyleSheet(f"background-color: {COLOR_BORDER_DISTINCT}; border: none;")
        toolbar_row.addWidget(sep)

        # View Mode switcher buttons (Grid, List, Compact)
        self.view_switcher_frame = QFrame()
        self.view_switcher_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 8px;
            }}
            QPushButton:pressed {{
                padding-top: 2px;
            }}
        """)
        vs_layout = QHBoxLayout(self.view_switcher_frame)
        vs_layout.setContentsMargins(2, 2, 2, 2)
        vs_layout.setSpacing(2)

        self.btn_view_grid = QPushButton()
        self.btn_view_grid.setIcon(render_icon("grid", 13, COLOR_TEXT_MUTED))
        self.btn_view_grid.setFixedSize(28, 28)
        self.btn_view_grid.setToolTip("Grid View")
        self.btn_view_grid.setStyleSheet("border: none; border-radius: 5px;")
        self.btn_view_grid.clicked.connect(lambda: self._set_view_mode("grid"))
        vs_layout.addWidget(self.btn_view_grid)

        self.btn_view_list = QPushButton()
        self.btn_view_list.setIcon(render_icon("list", 13, COLOR_ACCENT))
        self.btn_view_list.setFixedSize(28, 28)
        self.btn_view_list.setToolTip("List View")
        self.btn_view_list.setStyleSheet(f"border: 1px solid {COLOR_ACCENT}; background: {COLOR_BG_ACTIVE}; border-radius: 5px;")
        self.btn_view_list.clicked.connect(lambda: self._set_view_mode("list"))
        vs_layout.addWidget(self.btn_view_list)

        self.btn_view_compact = QPushButton()
        self.btn_view_compact.setIcon(render_icon("compact", 13, COLOR_TEXT_MUTED))
        self.btn_view_compact.setFixedSize(28, 28)
        self.btn_view_compact.setToolTip("Compact Table View")
        self.btn_view_compact.setStyleSheet("border: none; border-radius: 5px;")
        self.btn_view_compact.clicked.connect(lambda: self._set_view_mode("compact"))
        vs_layout.addWidget(self.btn_view_compact)

        toolbar_row.addWidget(self.view_switcher_frame)
        right_layout.addLayout(toolbar_row)

        # Scrollable projects container
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.projects_container = QWidget()
        self.projects_layout = QVBoxLayout(self.projects_container)
        self.projects_layout.setContentsMargins(0, 0, 0, 0)
        self.projects_layout.setSpacing(12)
        self.projects_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.projects_container)
        right_layout.addWidget(self.scroll_area, stretch=1)

        content_layout.addWidget(self.right_area, stretch=1)
        root_layout.addLayout(content_layout, stretch=1)

    def _get_header_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 8px;
                padding: 0 14px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
                color: {COLOR_ACCENT};
                background-color: {COLOR_BG_HOVER};
            }}
        """

    def _get_sidebar_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
                background-color: {COLOR_BG_HOVER};
            }}
        """

    def _get_tree_style(self) -> str:
        return f"""
            QTreeWidget {{
                background-color: transparent;
                border: none;
                outline: 0;
            }}
            QTreeWidget::item {{
                padding: 7px 8px;
                border-radius: 6px;
                color: {COLOR_TEXT_PRIMARY};
                margin-bottom: 2px;
            }}
            QTreeWidget::item:hover {{
                background-color: {COLOR_BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                background-color: {COLOR_BG_ELEVATED};
                font-weight: 600;
                color: {COLOR_TEXT_PRIMARY};
            }}
        """

    def _set_media_mode(self, mode: str):
        if self.current_media_mode != mode:
            self.current_media_mode = mode
            self._update_mode_switcher_styles()
            self.new_session_btn.setText("+ New Photo Session" if mode == "photo" else "+ New Video Session")
            self.media_mode_changed.emit(mode)
            self._load_projects_for_selection()

    def _set_status_filter(self, filter_name: str):
        self.active_status_filter = filter_name
        self._update_filter_pill_styles()
        self._load_projects_for_selection()

    def _on_search_text_changed(self, text: str):
        self.search_query = text.strip().lower()
        self._load_projects_for_selection()

    def _update_filter_pill_styles(self):
        active_style = f"""
            QPushButton {{
                background-color: {COLOR_BG_ACTIVE};
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_ACCENT};
                border-radius: 6px;
                padding: 4px 10px;
                font-weight: 700;
            }}
        """
        inactive_style = f"""
            QPushButton {{
                background-color: transparent;
                color: {COLOR_TEXT_MUTED};
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 4px 10px;
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """
        for name, btn in self.filter_buttons.items():
            btn.setStyleSheet(active_style if name == self.active_status_filter else inactive_style)

    def _update_mode_switcher_styles(self):
        active_style = f"""
            QPushButton {{
                background-color: {COLOR_BG_ACTIVE};
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_ACCENT};
                border-radius: 6px;
                padding: 5px 14px;
                font-weight: 700;
            }}
        """
        inactive_style = f"""
            QPushButton {{
                background-color: transparent;
                color: {COLOR_TEXT_MUTED};
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 5px 14px;
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """
        if self.current_media_mode == "photo":
            self.btn_mode_photo.setStyleSheet(active_style)
            self.btn_mode_photo.setIcon(render_icon("photo", 13, COLOR_ACCENT))
            self.btn_mode_video.setStyleSheet(inactive_style)
            self.btn_mode_video.setIcon(render_icon("video", 13, COLOR_TEXT_MUTED))
        else:
            self.btn_mode_photo.setStyleSheet(inactive_style)
            self.btn_mode_photo.setIcon(render_icon("photo", 13, COLOR_TEXT_MUTED))
            self.btn_mode_video.setStyleSheet(active_style)
            self.btn_mode_video.setIcon(render_icon("video", 13, COLOR_ACCENT))
        if hasattr(self, "btn_mode_gallery"):
            self.btn_mode_gallery.setStyleSheet(inactive_style)
            self.btn_mode_gallery.setIcon(render_icon("gallery", 13, COLOR_TEXT_MUTED))

    def _apply_dynamic_styles(self):
        if hasattr(self, "header_bar"):
            self.header_bar.setStyleSheet(f"""
                QFrame#dashboardHeaderBar {{
                    background-color: {COLOR_BG_SURFACE};
                    border-bottom: 1px solid {COLOR_BORDER_DISTINCT};
                }}
            """)
        if hasattr(self, "sidebar"):
            self.sidebar.setStyleSheet(f"""
                QFrame#dashboardSidebar {{
                    background-color: {COLOR_BG_SURFACE};
                    border-right: 1px solid {COLOR_BORDER_DISTINCT};
                }}
            """)
        if hasattr(self, "folder_tree"):
            self.folder_tree.setStyleSheet(self._get_tree_style())
        if hasattr(self, "right_area"):
            self.right_area.setStyleSheet(f"""
                QWidget#dashboardRightArea {{
                    background-color: {COLOR_BG_BASE};
                }}
                QLabel {{
                    background-color: transparent;
                }}
            """)
        if hasattr(self, "brand_icon_lbl"):
            self.brand_icon_lbl.setPixmap(render_icon("brand_frame", 22, COLOR_ACCENT).pixmap(22, 22))
        if hasattr(self, "brand_sub"):
            self.brand_sub.setStyleSheet(f"color: {COLOR_ACCENT}; letter-spacing: 1px;")
        if hasattr(self, "theme_btn"):
            self.theme_btn.setIcon(render_icon("palette", 14, COLOR_ACCENT))
        if hasattr(self, "gdrive_btn"):
            self.gdrive_btn.setIcon(render_icon("cloud", 14, COLOR_ACCENT))
        if hasattr(self, "settings_btn"):
            self.settings_btn.setIcon(render_icon("settings", 14, COLOR_TEXT_PRIMARY))
        if hasattr(self, "fullscreen_btn"):
            self.fullscreen_btn.setIcon(render_icon("fit", 13, COLOR_TEXT_PRIMARY))
        if hasattr(self, "add_folder_btn"):
            self.add_folder_btn.setIcon(render_icon("plus", 12, COLOR_TEXT_PRIMARY))
        if hasattr(self, "new_session_btn"):
            self.new_session_btn.setStyleSheet(f"""
                QPushButton#accentPillButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COLOR_ACCENT}, stop:1 {COLOR_ACCENT_PRESSED});
                    color: #FFFFFF;
                    border: 1px solid {COLOR_ACCENT_HOVER};
                    border-radius: 8px;
                    padding: 0 18px;
                    font-weight: 700;
                }}
                QPushButton#accentPillButton:hover {{
                    background: {COLOR_ACCENT_HOVER};
                }}
            """)

        self.refresh_cloud_status()

    def _open_theme_menu(self):
        active_tid = getattr(theme_mod, "current_theme_id", config.get("theme", "studio_pro"))
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                padding: 6px;
                border-radius: 8px;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 12px;
                color: {COLOR_TEXT_PRIMARY};
                font-size: 12px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_ACCENT};
            }}
        """)
        for t_id, t_def in THEMES.items():
            prefix = "✓  " if t_id == active_tid else "     "
            action = menu.addAction(f"{prefix}{t_def.name}")
            action.triggered.connect(lambda checked=False, tid=t_id: self._set_quick_theme(tid))
        menu.exec(self.theme_btn.mapToGlobal(QPoint(0, self.theme_btn.height() + 2)))

    def _set_quick_theme(self, theme_id: str):
        apply_theme(theme_id)

    def _on_theme_changed(self, theme_id: str):
        self._apply_dynamic_styles()
        self._update_mode_switcher_styles()
        self._update_filter_pill_styles()
        self.refresh()

    def _open_gdrive_manager(self):
        from loupe.ui.gdrive_dialog import GDriveManagerDialog
        dlg = GDriveManagerDialog(self)
        dlg.exec()
        self.refresh_cloud_status()

    def refresh_cloud_status(self):
        if not hasattr(self, "gdrive_btn"):
            return
        try:
            from loupe.core.gdrive import GoogleDriveClient
            client = GoogleDriveClient()
            if client.is_authenticated():
                email = client.get_authenticated_email() or "Connected"
                short = email.split("@")[0] if "@" in email else email
                self.gdrive_btn.setText(f"Drive ({short})")
                is_light = is_current_theme_light()
                cloud_bg = "#DCFCE7" if is_light else "#162B1D"
                cloud_border = "#22C55E" if is_light else "#10B981"
                cloud_fg = "#15803D" if is_light else "#6EE7B7"
                self.gdrive_btn.setStyleSheet(f"""
                    QPushButton {{
                        padding: 0 14px;
                        background-color: {cloud_bg};
                        border: 1px solid {cloud_border};
                        border-radius: 8px;
                        color: {cloud_fg};
                        font-weight: 600;
                    }}
                """)
            else:
                self.gdrive_btn.setText("Google Drive")
                self.gdrive_btn.setStyleSheet(self._get_header_btn_style())
        except Exception:
            pass

    def refresh(self):
        """Reload folders and projects from storage."""
        self.folder_tree.clear()

        mode = self.current_media_mode
        all_projects = storage.get_projects(media_type=mode)
        total_all_count = len(all_projects)

        all_item = QTreeWidgetItem(["All Projects", str(total_all_count)])
        all_item.setData(0, Qt.UserRole, "__ALL__")
        all_item.setIcon(0, render_icon("home", 14, COLOR_ACCENT))
        all_item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
        all_item.setForeground(1, QColor(COLOR_TEXT_MUTED))
        self.folder_tree.addTopLevelItem(all_item)

        target_item = all_item

        def _add_branch(parent_tree_item, folder_model):
            nonlocal target_item
            f_count = len(storage.get_projects(folder_model.id, media_type=mode))
            b_item = QTreeWidgetItem([folder_model.name, str(f_count)])
            b_item.setData(0, Qt.UserRole, folder_model.id)
            b_item.setIcon(0, render_icon("folder", 14, COLOR_TEXT_SECONDARY))
            b_item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            b_item.setForeground(1, QColor(COLOR_TEXT_MUTED))
            parent_tree_item.addChild(b_item)
            if self.selected_folder_id == folder_model.id:
                target_item = b_item
            for sub in storage.get_subfolders(folder_model.id):
                _add_branch(b_item, sub)

        top_folders = storage.get_top_level_folders()
        for f in top_folders:
            f_count = len(storage.get_projects(f.id, media_type=mode))
            f_item = QTreeWidgetItem([f.name, str(f_count)])
            f_item.setData(0, Qt.UserRole, f.id)
            f_item.setIcon(0, render_icon("folder", 14, COLOR_TEXT_SECONDARY))
            f_item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            f_item.setForeground(1, QColor(COLOR_TEXT_MUTED))
            self.folder_tree.addTopLevelItem(f_item)
            if self.selected_folder_id == f.id:
                target_item = f_item
            for sub in storage.get_subfolders(f.id):
                _add_branch(f_item, sub)

        self.folder_tree.expandAll()
        self.folder_tree.setCurrentItem(target_item)
        self._load_projects_for_selection()

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int = 0):
        if not item:
            return
        fid = item.data(0, Qt.UserRole)
        self.selected_folder_id = None if fid == "__ALL__" else fid
        self._load_projects_for_selection()

    def _on_folder_selected(self, item):
        if isinstance(item, QTreeWidgetItem):
            self._on_tree_item_clicked(item, 0)
        elif hasattr(item, "data"):
            fid = item.data(Qt.UserRole)
            self.selected_folder_id = None if fid == "__ALL__" else fid
            self._load_projects_for_selection()

    def _on_tree_context_menu(self, pos: QPoint):
        item = self.folder_tree.itemAt(pos)
        fid = item.data(0, Qt.UserRole) if item else None

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                padding: 4px;
                border-radius: 8px;
            }}
            QMenu::item {{
                padding: 6px 16px;
                color: {COLOR_TEXT_PRIMARY};
                font-size: 12px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_ACCENT};
            }}
        """)

        act_new_folder = menu.addAction("+ New Top-Level Folder")
        act_new_folder.triggered.connect(self._create_new_folder)

        if fid and fid != "__ALL__":
            folder = storage.get_folder_by_id(fid)
            f_name = folder.name if folder else "Folder"

            act_new_sub = menu.addAction(f"+ New Subfolder in '{f_name}'")
            act_new_sub.triggered.connect(lambda: self._create_new_subfolder(parent_id=fid))

            menu.addSeparator()

            act_rename = menu.addAction(f"Rename '{f_name}'")
            def _do_rename():
                self.selected_folder_id = fid
                self._rename_selected_folder()
            act_rename.triggered.connect(_do_rename)

            act_delete = menu.addAction(f"Delete '{f_name}'")
            def _do_delete():
                self.selected_folder_id = fid
                self._delete_selected_folder()
            act_delete.triggered.connect(_do_delete)

        menu.exec(self.folder_tree.mapToGlobal(pos))

    def _load_projects_for_selection(self):
        self._current_rendered_cards.clear()
        while self.projects_layout.count():
            child = self.projects_layout.takeAt(0)
            if child.widget():
                w = child.widget()
                w.setParent(None)
                w.deleteLater()
            elif child.layout():
                sub_l = child.layout()
                while sub_l.count():
                    sc = sub_l.takeAt(0)
                    if sc.widget():
                        sw = sc.widget()
                        sw.setParent(None)
                        sw.deleteLater()

        mode = self.current_media_mode
        if self.selected_folder_id:
            folder = storage.get_folder_by_id(self.selected_folder_id)
            parts = storage.get_folder_parts(self.selected_folder_id)
            breadcrumb = "Projects  ›  " + "  ›  ".join(parts) if parts else (folder.name if folder else "Folder")
            self.folder_title_lbl.setText(breadcrumb)
            f_name = folder.name if folder else "Folder"
            self.folder_desc_lbl.setText(f"Your {f_name.lower()} sessions")
            self.header_add_subfolder_btn.setVisible(True)
            self.header_edit_folder_btn.setVisible(True)
            self.add_subfolder_btn.setEnabled(True)
            self.rename_folder_btn.setEnabled(True)
            self.delete_folder_btn.setEnabled(True)
            base_projects = storage.get_projects(self.selected_folder_id, media_type=mode)
        else:
            self.folder_title_lbl.setText("All Projects")
            self.folder_desc_lbl.setText("All ongoing photo and video sessions")
            self.header_add_subfolder_btn.setVisible(False)
            self.header_edit_folder_btn.setVisible(False)
            self.add_subfolder_btn.setEnabled(False)
            self.rename_folder_btn.setEnabled(False)
            self.delete_folder_btn.setEnabled(False)
            base_projects = storage.get_projects(media_type=mode)

        # Update KPI Summary Cards with the active set
        self.kpi_cards.update_from_projects(base_projects)

        # Apply Instant Client-side Filters (Search query + Status Filter)
        projects = base_projects
        if self.search_query:
            projects = [p for p in projects if self.search_query in p.name.lower() or self.search_query in p.shoot_date.lower()]

        if self.active_status_filter == "Photos":
            projects = [p for p in projects if getattr(p, "media_type", "photo") != "video"]
        elif self.active_status_filter == "Videos":
            projects = [p for p in projects if getattr(p, "media_type", "photo") == "video"]
        elif self.active_status_filter == "Completed":
            projects = [p for p in projects if "Completed" in getattr(p, "status_label", "")]
        elif self.active_status_filter == "In Progress":
            projects = [p for p in projects if "Progress" in getattr(p, "status_label", "")]

        count = len(projects)
        term = "video session" if mode == "video" else "photo session"

        if count == 0:
            empty_box = QFrame()
            empty_box.setObjectName("emptyBoxFrame")
            empty_box.setStyleSheet(f"""
                QFrame#emptyBoxFrame {{
                    background-color: {COLOR_BG_SURFACE};
                    border: 1px dashed {COLOR_BORDER_DISTINCT};
                    border-radius: 10px;
                    padding: 44px;
                }}
            """)
            empty_layout = QVBoxLayout(empty_box)
            empty_layout.setAlignment(Qt.AlignCenter)
            empty_layout.setSpacing(14)

            msg_text = f"No {mode} sorting sessions in this folder yet."
            if self.search_query:
                msg_text = f"No sessions match '{self.search_query}'."
            msg = QLabel(msg_text)
            msg.setFont(get_body_font(14))
            msg.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
            empty_layout.addWidget(msg, alignment=Qt.AlignCenter)

            if not self.search_query:
                btn_label = f"Create First {mode.capitalize()} Session"
                create_btn = QPushButton(btn_label)
                create_btn.setObjectName("accentButton")
                create_btn.setIcon(render_icon("plus", 14, "#FFFFFF"))
                create_btn.setMinimumHeight(38)
                create_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {COLOR_ACCENT};
                        color: #FFFFFF;
                        font-weight: 700;
                        font-size: 13px;
                        border: 1px solid {COLOR_ACCENT_HOVER};
                        border-radius: 8px;
                        padding: 8px 22px;
                    }}
                    QPushButton:hover {{
                        background-color: {COLOR_ACCENT_HOVER};
                    }}
                """)
                create_btn.clicked.connect(self.new_session_requested.emit)
                empty_layout.addWidget(create_btn, alignment=Qt.AlignCenter)

            self.projects_layout.addWidget(empty_box)
        else:
            if self.current_view_mode == "grid":
                grid_widget = QWidget()
                grid_layout = QGridLayout(grid_widget)
                grid_layout.setContentsMargins(0, 0, 0, 0)
                grid_layout.setSpacing(14)
                grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

                cols = 3
                for i, proj in enumerate(projects):
                    card = ProjectCard(proj, view_mode="grid")
                    self._connect_card_signals(card)
                    grid_layout.addWidget(card, i // cols, i % cols)

                self.projects_layout.addWidget(grid_widget)
            else:
                spacing = 4 if self.current_view_mode == "compact" else 12
                self.projects_layout.setSpacing(spacing)
                for proj in projects:
                    card = ProjectCard(proj, view_mode=self.current_view_mode)
                    self._connect_card_signals(card)
                    self.projects_layout.addWidget(card)

    def _connect_card_signals(self, card: ProjectCard):
        card.selection_toggled.connect(self._on_card_selection_toggled)
        if card.project.id in self.selected_project_ids:
            card.set_selected(True)
        self._current_rendered_cards[card.project.id] = card
        card.resume_clicked.connect(self.open_project_requested.emit)
        card.export_clicked.connect(self.export_project_requested.emit)
        card.delete_clicked.connect(self._on_delete_project)
        card.date_changed.connect(self._on_project_date_changed)
        card.refresh_requested.connect(self.refresh)
        card.edit_requested.connect(self._on_edit_project_modal)
        card.edit_folder_requested.connect(self._on_edit_folder_modal)
        card.edit_date_requested.connect(self._on_edit_date_modal)

    def _set_view_mode(self, mode: str):
        if self.current_view_mode != mode:
            self.current_view_mode = mode
            self._update_view_mode_styles()
            self._load_projects_for_selection()

    def _update_view_mode_styles(self):
        active_style = f"border: 1px solid {COLOR_ACCENT}; background: {COLOR_BG_ACTIVE}; border-radius: 5px;"
        inactive_style = "border: none; background: transparent; border-radius: 5px;"

        self.btn_view_grid.setStyleSheet(active_style if self.current_view_mode == 'grid' else inactive_style)
        self.btn_view_grid.setIcon(render_icon('grid', 13, COLOR_ACCENT if self.current_view_mode == 'grid' else COLOR_TEXT_MUTED))

        self.btn_view_list.setStyleSheet(active_style if self.current_view_mode == 'list' else inactive_style)
        self.btn_view_list.setIcon(render_icon('list', 13, COLOR_ACCENT if self.current_view_mode == 'list' else COLOR_TEXT_MUTED))

        self.btn_view_compact.setStyleSheet(active_style if self.current_view_mode == 'compact' else inactive_style)
        self.btn_view_compact.setIcon(render_icon('compact', 13, COLOR_ACCENT if self.current_view_mode == 'compact' else COLOR_TEXT_MUTED))

    def _on_edit_project_modal(self, proj: Project):
        def _saved(name, folder_id, shoot_date):
            if name:
                storage.update_project_name(proj.id, name)
            if folder_id:
                storage.update_project_folder(proj.id, folder_id)
            if shoot_date:
                storage.update_project_date(proj.id, shoot_date)
            self.refresh()
        self.modal_overlay.show_edit_project(proj, _saved)

    def _on_edit_folder_modal(self, proj: Project):
        def _saved(new_name, target_folder_id):
            if new_name:
                storage.rename_folder(proj.folder_id, new_name)
            if target_folder_id and target_folder_id != proj.folder_id:
                storage.update_project_folder(proj.id, target_folder_id)
            self.refresh()
        self.modal_overlay.show_edit_folder_project(proj.folder_id, _saved)

    def _on_edit_date_modal(self, proj: Project):
        def _saved(new_date):
            storage.update_project_date(proj.id, new_date)
            self.refresh()
        self.modal_overlay.show_edit_date(proj.shoot_date, _saved)

    def _create_new_folder(self):
        def _created(name, parent_id=None):
            new_f = storage.create_folder(name, parent_id=parent_id)
            self.selected_folder_id = new_f.id
            self.refresh()
        self.modal_overlay.show_create_folder(_created, default_parent_id=None)

    def _create_new_subfolder(self, parent_id=None):
        target_pid = parent_id if parent_id is not None else self.selected_folder_id
        def _created(name, chosen_parent_id):
            new_f = storage.create_folder(name, parent_id=chosen_parent_id)
            self.selected_folder_id = new_f.id
            self.refresh()
        self.modal_overlay.show_create_folder(_created, default_parent_id=target_pid)

    def _rename_selected_folder(self):
        if not self.selected_folder_id:
            return
        folder = storage.get_folder_by_id(self.selected_folder_id)
        if not folder:
            return
        def _renamed(new_name):
            storage.rename_folder(folder.id, new_name)
            self.refresh()
        self.modal_overlay.show_rename_folder(folder.name, _renamed)

    def _delete_selected_folder(self):
        if not self.selected_folder_id:
            return
        folder = storage.get_folder_by_id(self.selected_folder_id)
        if not folder:
            return
        subs = storage.get_subfolders(folder.id)
        sub_info = f" and its {len(subs)} subfolder(s)" if subs else ""
        def _confirmed():
            storage.delete_folder(folder.id)
            self.selected_folder_id = None
            self.refresh()
        self.modal_overlay.show_confirm_delete(
            "Delete Workspace Folder",
            f"Are you sure you want to delete folder '{folder.name}'{sub_info}?\nAll sessions inside will be preserved in top-level workspace.",
            _confirmed,
            confirm_text="Delete Folder",
            is_destructive=True
        )

    def _on_delete_project(self, project_id: str):
        proj = storage.get_project_by_id(project_id)
        if not proj:
            return
        def _confirmed():
            storage.delete_project(project_id)
            self._load_projects_for_selection()
        self.modal_overlay.show_confirm_delete(
            "Delete Session",
            f"Delete session '{proj.name}'?\nOriginal media on disk will never be touched.",
            _confirmed,
            confirm_text="Delete Session",
            is_destructive=True
        )

    def _setup_bulk_bar(self):
        self.bulk_bar = QFrame(self.right_area)
        self.bulk_bar.setObjectName("floatingBulkBar")
        self.bulk_bar.setFixedHeight(50)
        self.bulk_bar.setStyleSheet(f"""
            QFrame#floatingBulkBar {{
                background-color: #171A21;
                border: 1.5px solid {COLOR_ACCENT};
                border-radius: 25px;
            }}
        """)
        bb_layout = QHBoxLayout(self.bulk_bar)
        bb_layout.setContentsMargins(16, 6, 16, 6)
        bb_layout.setSpacing(12)

        self.bulk_count_lbl = QLabel("0 Selected")
        self.bulk_count_lbl.setFont(get_body_font(12, bold=True))
        self.bulk_count_lbl.setStyleSheet(f"color: {COLOR_ACCENT};")
        bb_layout.addWidget(self.bulk_count_lbl)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setFixedWidth(1)
        sep1.setFixedHeight(20)
        sep1.setStyleSheet(f"background-color: {COLOR_BORDER_DISTINCT};")
        bb_layout.addWidget(sep1)

        self.btn_bulk_resume = QPushButton(" ▶  Resume Culling All")
        self.btn_bulk_resume.setFont(get_body_font(11, bold=True))
        self.btn_bulk_resume.setCursor(Qt.PointingHandCursor)
        self.btn_bulk_resume.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 14px;
                padding: 5px 14px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
                color: {COLOR_ACCENT};
            }}
        """)
        self.btn_bulk_resume.clicked.connect(self._on_bulk_resume_all)
        bb_layout.addWidget(self.btn_bulk_resume)

        self.btn_bulk_export = QPushButton(" 📤  Export All in Order")
        self.btn_bulk_export.setFont(get_body_font(11, bold=True))
        self.btn_bulk_export.setCursor(Qt.PointingHandCursor)
        self.btn_bulk_export.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COLOR_ACCENT}, stop:1 {COLOR_ACCENT_PRESSED});
                color: #FFFFFF;
                border: 1px solid {COLOR_ACCENT_HOVER};
                border-radius: 14px;
                padding: 5px 16px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: {COLOR_ACCENT_HOVER};
            }}
        """)
        self.btn_bulk_export.clicked.connect(self._on_bulk_export_all)
        bb_layout.addWidget(self.btn_bulk_export)

        self.btn_bulk_move = QPushButton(" 📁  Move to Folder")
        self.btn_bulk_move.setFont(get_body_font(11))
        self.btn_bulk_move.setCursor(Qt.PointingHandCursor)
        self.btn_bulk_move.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 14px;
                padding: 5px 14px;
            }}
            QPushButton:hover {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        self.btn_bulk_move.clicked.connect(self._on_bulk_move)
        bb_layout.addWidget(self.btn_bulk_move)

        self.btn_bulk_del = QPushButton(" 🗑  Delete All")
        self.btn_bulk_del.setFont(get_body_font(11, bold=True))
        self.btn_bulk_del.setCursor(Qt.PointingHandCursor)
        self.btn_bulk_del.setStyleSheet("""
            QPushButton {
                background-color: #331A1D;
                color: #F87171;
                border: 1px solid #7F1D1D;
                border-radius: 14px;
                padding: 5px 14px;
            }
            QPushButton:hover {
                background-color: #4A2227;
                border-color: #EF4444;
            }
        """)
        self.btn_bulk_del.clicked.connect(self._on_bulk_delete_all)
        bb_layout.addWidget(self.btn_bulk_del)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setFixedWidth(1)
        sep2.setFixedHeight(20)
        sep2.setStyleSheet(f"background-color: {COLOR_BORDER_DISTINCT};")
        bb_layout.addWidget(sep2)

        self.btn_bulk_deselect = QPushButton("✕ Deselect")
        self.btn_bulk_deselect.setFont(get_body_font(11))
        self.btn_bulk_deselect.setCursor(Qt.PointingHandCursor)
        self.btn_bulk_deselect.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLOR_TEXT_MUTED};
                border: none;
                padding: 5px 10px;
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
            }}
        """)
        self.btn_bulk_deselect.clicked.connect(self._deselect_all)
        bb_layout.addWidget(self.btn_bulk_deselect)

        self.bulk_bar.setVisible(False)

    def _position_bulk_bar(self):
        if hasattr(self, "bulk_bar") and hasattr(self, "right_area"):
            rw = self.right_area.width()
            rh = self.right_area.height()
            bar_w = min(720, max(500, rw - 60))
            self.bulk_bar.setFixedWidth(bar_w)
            bx = (rw - bar_w) // 2
            by = rh - 66
            self.bulk_bar.move(bx, by)

    def _update_bulk_bar(self):
        cnt = len(self.selected_project_ids)
        if cnt > 0:
            self.bulk_count_lbl.setText(f"✓  {cnt} Selected")
            self._position_bulk_bar()
            self.bulk_bar.setVisible(True)
            self.bulk_bar.raise_()
            if hasattr(self, "btn_select_toggle"):
                self.btn_select_toggle.setText("Deselect All")
        else:
            self.bulk_bar.setVisible(False)
            if hasattr(self, "btn_select_toggle"):
                self.btn_select_toggle.setText("Select All")

    def _on_card_selection_toggled(self, project_id: str, is_selected: bool):
        if is_selected:
            self.selected_project_ids.add(project_id)
        else:
            self.selected_project_ids.discard(project_id)
        self._update_bulk_bar()

    def _get_current_filtered_projects(self) -> list:
        mode = self.current_media_mode
        if self.selected_folder_id:
            base = storage.get_projects(self.selected_folder_id, media_type=mode)
        else:
            base = storage.get_projects(media_type=mode)
        if self.search_query:
            base = [p for p in base if self.search_query in p.name.lower() or self.search_query in p.shoot_date.lower()]
        if self.active_status_filter == "Photos":
            base = [p for p in base if getattr(p, "media_type", "photo") != "video"]
        elif self.active_status_filter == "Videos":
            base = [p for p in base if getattr(p, "media_type", "photo") == "video"]
        elif self.active_status_filter == "Completed":
            base = [p for p in base if "Completed" in getattr(p, "status_label", "")]
        elif self.active_status_filter == "In Progress":
            base = [p for p in base if "Progress" in getattr(p, "status_label", "")]
        return base

    def _toggle_select_all(self):
        curr_projs = self._get_current_filtered_projects()
        all_ids = {p.id for p in curr_projs}
        if self.selected_project_ids >= all_ids and len(all_ids) > 0:
            self._deselect_all()
        else:
            self.selected_project_ids |= all_ids
            for pid, card in self._current_rendered_cards.items():
                card.set_selected(pid in self.selected_project_ids)
            self._update_bulk_bar()

    def _deselect_all(self):
        self.selected_project_ids.clear()
        for card in self._current_rendered_cards.values():
            card.set_selected(False)
        self._update_bulk_bar()

    def _on_bulk_resume_all(self):
        ordered_pids = [p.id for p in self._get_current_filtered_projects() if p.id in self.selected_project_ids]
        if not ordered_pids:
            return
        self.resume_culling_queue_requested.emit(ordered_pids)

    def _on_bulk_export_all(self):
        ordered_projs = [p for p in self._get_current_filtered_projects() if p.id in self.selected_project_ids]
        if not ordered_projs:
            return
        dlg = BatchExportDialog(ordered_projs, self)
        dlg.exec()

    def _on_bulk_move(self):
        if not self.selected_project_ids:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                padding: 6px;
                border-radius: 8px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                color: {COLOR_TEXT_PRIMARY};
                font-size: 12px;
            }}
            QMenu::item:selected {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_ACCENT};
            }}
        """)
        act_root = menu.addAction("📁 Top-Level Workspace (No Folder)")
        act_root.triggered.connect(lambda: self._execute_bulk_move(None))
        menu.addSeparator()
        for f in storage.get_folders():
            act = menu.addAction(f"📁 {f.name}")
            act.triggered.connect(lambda checked=False, fid=f.id: self._execute_bulk_move(fid))
        menu.exec(QCursor.pos())

    def _execute_bulk_move(self, target_folder_id: Optional[str]):
        for pid in list(self.selected_project_ids):
            storage.update_project_folder(pid, target_folder_id)
        self._deselect_all()
        self.refresh()

    def _on_bulk_delete_all(self):
        cnt = len(self.selected_project_ids)
        if cnt == 0:
            return
        def _confirmed():
            for pid in list(self.selected_project_ids):
                storage.delete_project(pid)
            self._deselect_all()
            self.refresh()

        self.modal_overlay.show_confirm_delete(
            title=f"Delete {cnt} Sessions",
            message=f"Are you sure you want to delete {cnt} selected session(s)?\n\nOriginal photos and video files on disk will NEVER be touched.",
            on_confirmed=_confirmed,
            confirm_text=f"Delete {cnt} Sessions",
            is_destructive=True
        )

    def _on_project_date_changed(self, project_id: str, new_date: str):
        storage.update_project_date(project_id, new_date)
        self._load_projects_for_selection()
