"""Dialog/tray displaying 'Not Accepted' rejected photos with one-click recovery to kept set."""

from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QGridLayout
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from loupe.models import PhotoItem
from loupe.core.decoder import ImageDecoder
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_SUBTLE,
    COLOR_BORDER_DISTINCT, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_STATUS_KEPT, COLOR_STATUS_REJECTED,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon

class RejectedItemCard(QFrame):
    restore_clicked = Signal(str)  # item_id

    def __init__(self, item: PhotoItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 2px;
                padding: 6px;
            }}
            QFrame:hover {{
                border-color: {COLOR_STATUS_REJECTED};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Image preview thumbnail
        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(160, 110)
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        self.thumb_lbl.setStyleSheet(f"background-color: {COLOR_BG_BASE}; border: 1px solid {COLOR_BORDER_SUBTLE};")
        
        # Load thumbnail
        pix = ImageDecoder.decode_thumbnail(item.primary_path, 160)
        if pix:
            self.thumb_lbl.setPixmap(pix)
        else:
            self.thumb_lbl.setText("No Preview")
        layout.addWidget(self.thumb_lbl)

        # Filename
        name_lbl = QLabel(item.base_name)
        name_lbl.setFont(get_mono_font(11, bold=True))
        name_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_lbl)

        # Restore Button
        restore_btn = QPushButton("Restore to Kept")
        restore_btn.setObjectName("keepButton")
        restore_btn.setFont(get_body_font(11, bold=True))
        restore_btn.setIcon(render_icon("restore", 12, "#7BE4A2"))
        restore_btn.clicked.connect(lambda: self.restore_clicked.emit(item.id))
        layout.addWidget(restore_btn)


class NotAcceptedDialog(QDialog):
    """Modal tray showing all rejected photos, allowing quick reversal of accidental clicks."""
    item_restored = Signal(str)  # item_id

    def __init__(self, rejected_items: List[PhotoItem], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Not Accepted Photos — Review & Recovery")
        self.setMinimumSize(740, 560)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")
        self.rejected_items = rejected_items

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        header.setSpacing(12)

        v = QVBoxLayout()
        title = QLabel(f"Not Accepted Photos ({len(self.rejected_items)})")
        title.setFont(get_display_font(18, bold=True))
        sub = QLabel("Review photos moved to Not Accepted. Click 'Restore to Kept' to undo accidental rejections.")
        sub.setFont(get_body_font(12))
        sub.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        v.addWidget(title)
        v.addWidget(sub)
        header.addLayout(v)
        header.addStretch()

        close_btn = QPushButton("Done")
        close_btn.setMinimumHeight(32)
        close_btn.clicked.connect(self.accept)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # Scrollable Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self._populate_grid()

        scroll.setWidget(self.container)
        layout.addWidget(scroll, stretch=1)

    def _populate_grid(self):
        # Clear grid
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.rejected_items:
            empty = QLabel("There are no photos currently marked as Not Accepted.")
            empty.setFont(get_body_font(13))
            empty.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
            self.grid.addWidget(empty, 0, 0)
            return

        cols = 3
        for i, item in enumerate(self.rejected_items):
            card = RejectedItemCard(item)
            card.restore_clicked.connect(self._on_restore)
            r = i // cols
            c = i % cols
            self.grid.addWidget(card, r, c)

    def _on_restore(self, item_id: str):
        self.item_restored.emit(item_id)
        self.rejected_items = [it for it in self.rejected_items if it.id != item_id]
        self._populate_grid()
