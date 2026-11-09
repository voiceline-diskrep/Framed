"""Dialogs and modals for the FRAMED Complete Gallery System."""

import os
from datetime import datetime
from typing import List, Optional, Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QRadioButton, QButtonGroup, QComboBox,
    QCheckBox, QProgressBar, QFileDialog, QListWidget, QListWidgetItem,
    QFrame, QScrollArea, QSlider, QSpinBox, QLineEdit, QTextEdit,
    QMessageBox, QStackedWidget, QSplitter, QSizePolicy, QGridLayout
)
from PySide6.QtCore import Qt, Signal, QTimer, QPoint, QSize
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QPen, QKeySequence, QShortcut

from ..models import GalleryPhoto, GalleryFolder, SmartAlbum
from ..storage import storage, format_bytes
from ..core.gallery_engine import (
    GalleryImporter, GalleryImportWorker,
    RawToJpegConverter, RawConversionWorker,
    MissingFileRecoveryEngine, DuplicateFinderEngine,
    GalleryBackupEngine, ALL_GALLERY_EXTS
)
from .icons import render_icon


DIALOG_STYLE = """
QDialog {
    background-color: #14161A;
    color: #F4F4F5;
    font-family: 'Inter', 'Segoe UI', sans-serif;
}
QLabel {
    color: #F4F4F5;
}
QFrame#CardFrame {
    background-color: #191C22;
    border: 1px solid #2A2E37;
    border-radius: 10px;
}
QFrame#WarningFrame1 {
    background-color: #231C12;
    border: 1px solid #F59E0B;
    border-radius: 10px;
}
QFrame#WarningFrame2 {
    background-color: #261619;
    border: 1px solid #EF4444;
    border-radius: 10px;
}
QPushButton {
    background-color: #20242C;
    color: #E4E4E7;
    border: 1px solid #303540;
    border-radius: 7px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #282D37;
    border-color: #454C59;
}
QPushButton#PrimaryBtn {
    background-color: #F59E0B;
    color: #0D0E11;
    border: 1px solid #FBBF24;
    font-weight: 700;
}
QPushButton#PrimaryBtn:hover {
    background-color: #FBBF24;
}
QPushButton#DangerBtn {
    background-color: #2C1619;
    color: #F87171;
    border: 1px solid #7F1D1D;
}
QPushButton#DangerBtn:hover {
    background-color: #3F1D21;
}
QLineEdit, QComboBox, QSpinBox, QTextEdit, QListWidget {
    background-color: #101216;
    color: #F4F4F5;
    border: 1px solid #2C303A;
    border-radius: 7px;
    padding: 6px 10px;
    font-size: 12px;
}
QTabWidget::pane {
    border: 1px solid #2A2E37;
    border-radius: 8px;
    background-color: #16181D;
}
QTabBar::tab {
    background-color: #121418;
    color: #969BA5;
    border: 1px solid #2A2E37;
    padding: 8px 16px;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    margin-right: 4px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background-color: #191C22;
    color: #F59E0B;
    border-bottom-color: #191C22;
}
QProgressBar {
    background-color: #101216;
    border: 1px solid #2C303A;
    border-radius: 6px;
    text-align: center;
    color: #F4F4F5;
    height: 18px;
}
QProgressBar::chunk {
    background-color: #F59E0B;
    border-radius: 5px;
}
"""


def _load_preview_pixmap(filepath: str, max_w: int = 1200, max_h: int = 900) -> QPixmap:
    """Safely loads a high-res preview for both standard images and RAW files."""
    if not filepath or not os.path.exists(filepath):
        return QPixmap()
    pix = QPixmap(filepath)
    if not pix.isNull():
        return pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    try:
        from PIL import Image, ImageOps
        ext = os.path.splitext(filepath)[1].lower()
        img = None
        if ext in {".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2", ".pef", ".raf"}:
            try:
                import rawpy
                import io
                with rawpy.imread(filepath) as raw:
                    try:
                        thumb = raw.extract_thumb()
                        if thumb.format == rawpy.ThumbFormat.JPEG:
                            img = Image.open(io.BytesIO(thumb.data))
                    except Exception:
                        pass
                    if img is None:
                        rgb = raw.postprocess(use_camera_wb=True, half_size=True)
                        img = Image.fromarray(rgb)
            except Exception:
                pass
        if img is None:
            img = Image.open(filepath)
        img = ImageOps.exif_transpose(img)
        img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888).copy()
        return QPixmap.fromImage(qimg)
    except Exception:
        return QPixmap()


# ==============================================================================
# 1. PHOTO IMPORT DIALOG (Computer + FRAMED Sessions)
# ==============================================================================

class GalleryImportDialog(QDialog):
    """Comprehensive Import Dialog supporting Computer Files/Folders and FRAMED Sessions."""

    import_completed = Signal(object)  # Emits ImportReport

    def __init__(self, parent=None, default_folder_id: Optional[str] = None, initial_tab: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Import Photographs into FRAMED Gallery")
        self.resize(720, 620)
        self.setStyleSheet(DIALOG_STYLE)

        self.selected_paths: List[str] = []
        self.worker: Optional[GalleryImportWorker] = None
        self.default_folder_id = default_folder_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title
        hdr = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(render_icon("gallery", 24, "#F59E0B").pixmap(24, 24))
        hdr.addWidget(icon_lbl)
        title_box = QVBoxLayout()
        t_lbl = QLabel("Import Photographs")
        t_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #F4F4F5;")
        s_lbl = QLabel("Add photographs from your computer or existing FRAMED culling sessions.")
        s_lbl.setStyleSheet("font-size: 12px; color: #969BA5;")
        title_box.addWidget(t_lbl)
        title_box.addWidget(s_lbl)
        hdr.addLayout(title_box, 1)
        layout.addLayout(hdr)

        # Tabs
        self.tabs = QTabWidget()
        self._build_computer_tab()
        self._build_sessions_tab()
        self.tabs.setCurrentIndex(initial_tab)
        layout.addWidget(self.tabs, 1)

        # Common Import Method & Target Folder card
        opts_card = QFrame()
        opts_card.setObjectName("CardFrame")
        opts_layout = QVBoxLayout(opts_card)
        opts_layout.setContentsMargins(14, 12, 14, 12)
        opts_layout.setSpacing(8)

        m_lbl = QLabel("Storage & Import Method")
        m_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #F59E0B;")
        opts_layout.addWidget(m_lbl)

        self.rb_ref = QRadioButton(
            "B. Reference Original Location (Recommended — indexes photos in place without duplicating files)"
        )
        self.rb_copy = QRadioButton(
            "A. Copy into FRAMED Gallery (Creates a managed copy inside FRAMED storage; original files stay untouched)"
        )
        self.rb_ref.setChecked(True)
        opts_layout.addWidget(self.rb_ref)
        opts_layout.addWidget(self.rb_copy)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Target Gallery Folder:"))
        self.folder_combo = QComboBox()
        self.folder_combo.addItem("All Photos (No specific folder)", None)
        for f in storage.get_gallery_folders():
            prefix = "    ↳ " if f.parent_id else "📁 "
            self.folder_combo.addItem(f"{prefix}{f.name}", f.id)
            if default_folder_id and f.id == default_folder_id:
                self.folder_combo.setCurrentIndex(self.folder_combo.count() - 1)
        row2.addWidget(self.folder_combo, 1)

        self.chk_skip_dups = QCheckBox("Detect & skip duplicates automatically")
        self.chk_skip_dups.setChecked(True)
        row2.addWidget(self.chk_skip_dups)
        opts_layout.addLayout(row2)
        layout.addWidget(opts_card)

        # Progress bar & status
        self.status_lbl = QLabel("Ready to import. Original files are never moved, overwritten, or deleted.")
        self.status_lbl.setStyleSheet("font-size: 12px; color: #969BA5;")
        layout.addWidget(self.status_lbl)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Footer buttons
        footer = QHBoxLayout()
        footer.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_import = QPushButton("Start Import")
        self.btn_import.setObjectName("PrimaryBtn")
        self.btn_import.clicked.connect(self._start_import)
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_import)
        layout.addLayout(footer)

    def _build_computer_tab(self):
        tab = QWidget()
        v = QVBoxLayout(tab)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        btn_row = QHBoxLayout()
        btn_files = QPushButton("Select Photo Files (RAW / JPEG / PNG / TIFF)...")
        btn_files.clicked.connect(self._pick_files)
        btn_folder = QPushButton("Select Entire Folder...")
        btn_folder.clicked.connect(self._pick_folder)
        btn_clear = QPushButton("Clear List")
        btn_clear.clicked.connect(self._clear_files)
        btn_row.addWidget(btn_files)
        btn_row.addWidget(btn_folder)
        btn_row.addWidget(btn_clear)
        v.addLayout(btn_row)

        self.files_list = QListWidget()
        v.addWidget(self.files_list, 1)

        self.comp_summary = QLabel("0 files queued for import.")
        self.comp_summary.setStyleSheet("color: #969BA5; font-size: 12px;")
        v.addWidget(self.comp_summary)

        self.tabs.addTab(tab, "Import from Computer")

    def _build_sessions_tab(self):
        tab = QWidget()
        v = QVBoxLayout(tab)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        top = QHBoxLayout()
        top.addWidget(QLabel("Select Photosort Session:"))
        self.session_combo = QComboBox()
        self.photo_sessions = [s for s in storage.sessions if getattr(s, "media_type", "photo") == "photo"]
        for s in self.photo_sessions:
            self.session_combo.addItem(f"{s.name} ({len(s.items)} frames • {s.shoot_date})", s.id)
        self.session_combo.currentIndexChanged.connect(self._refresh_session_preview)
        top.addWidget(self.session_combo, 1)
        v.addLayout(top)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Include:"))
        self.sess_filter_group = QButtonGroup(self)
        self.rb_sess_selected = QRadioButton("Selected / Kept Photos Only")
        self.rb_sess_edited = QRadioButton("Edited Results (LRC) Only")
        self.rb_sess_all = QRadioButton("All Supported Session Photographs")
        self.rb_sess_selected.setChecked(True)
        for rb in (self.rb_sess_selected, self.rb_sess_edited, self.rb_sess_all):
            self.sess_filter_group.addButton(rb)
            rb.toggled.connect(self._refresh_session_preview)
            filter_row.addWidget(rb)
        filter_row.addStretch()
        v.addLayout(filter_row)

        self.session_files_list = QListWidget()
        v.addWidget(self.session_files_list, 1)

        self.sess_summary = QLabel("")
        self.sess_summary.setStyleSheet("color: #969BA5; font-size: 12px;")
        v.addWidget(self.sess_summary)

        self._refresh_session_preview()
        self.tabs.addTab(tab, "Import from FRAMED Sessions")

    def _pick_files(self):
        exts = " ".join(f"*{e}" for e in sorted(ALL_GALLERY_EXTS))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Photographs", "", f"Photographs ({exts});;All Files (*.*)"
        )
        if files:
            for f in files:
                if f not in self.selected_paths:
                    self.selected_paths.append(f)
            self._update_comp_list()

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Import")
        if folder:
            found = GalleryImporter.scan_paths([folder])
            for f in found:
                if f not in self.selected_paths:
                    self.selected_paths.append(f)
            self._update_comp_list()

    def _clear_files(self):
        self.selected_paths.clear()
        self._update_comp_list()

    def _update_comp_list(self):
        self.files_list.clear()
        for p in self.selected_paths[:500]:
            self.files_list.addItem(p)
        if len(self.selected_paths) > 500:
            self.files_list.addItem(f"... and {len(self.selected_paths) - 500} more files")
        self.comp_summary.setText(f"{len(self.selected_paths):,} photograph(s) detected and ready to import.")

    def _refresh_session_preview(self):
        self.session_files_list.clear()
        idx = self.session_combo.currentIndex()
        if idx < 0 or idx >= len(self.photo_sessions):
            self.sess_summary.setText("No Photosort sessions available.")
            return
        session = self.photo_sessions[idx]
        files: List[str] = []
        if self.rb_sess_edited.isChecked():
            for p in getattr(session, "edited_files", []):
                if p and os.path.exists(p):
                    files.append(p)
        else:
            only_sel = self.rb_sess_selected.isChecked()
            for item in session.items:
                if only_sel and item.status not in ("kept", "selected"):
                    continue
                if item.jpeg_path and os.path.exists(item.jpeg_path):
                    files.append(item.jpeg_path)
                if item.raw_path and os.path.exists(item.raw_path):
                    files.append(item.raw_path)

        for f in files:
            lw_item = QListWidgetItem(f"{os.path.basename(f)}  —  {f}")
            lw_item.setData(Qt.UserRole, f)
            lw_item.setCheckState(Qt.Checked)
            self.session_files_list.addItem(lw_item)

        self.sess_summary.setText(f"{len(files):,} file(s) matched in session '{session.name}'. Uncheck any file to exclude it.")

    def _start_import(self):
        import_mode = "copy" if self.rb_copy.isChecked() else "reference"
        folder_id = self.folder_combo.currentData()
        folder_ids = [folder_id] if folder_id else []
        skip_dups = self.chk_skip_dups.isChecked()

        if self.tabs.currentIndex() == 0:
            if not self.selected_paths:
                QMessageBox.information(self, "No Files Selected", "Please select one or more photographs or a folder first.")
                return
            paths = list(self.selected_paths)
            source_type = "computer"
            source_session_id = ""
        else:
            idx = self.session_combo.currentIndex()
            if idx < 0 or idx >= len(self.photo_sessions):
                return
            session = self.photo_sessions[idx]
            paths = []
            for i in range(self.session_files_list.count()):
                it = self.session_files_list.item(i)
                if it.checkState() == Qt.Checked:
                    paths.append(it.data(Qt.UserRole))
            if not paths:
                QMessageBox.information(self, "No Session Files", "No checked photographs to import from this session.")
                return
            source_type = "session"
            source_session_id = session.id

        self.btn_import.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        self.worker = GalleryImportWorker(
            filepaths=paths,
            copy_to_gallery=(import_mode == "copy"),
            target_folder_id=folder_id,
            skip_duplicates=skip_dups,
            parent=self,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_import.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, current: int, total: int, filename: str):
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(current)
        self.status_lbl.setText(f"Importing ({current}/{total}): {filename}")

    def _on_finished(self, report: dict):
        self.btn_import.setEnabled(True)
        det = report.get("detected", 0)
        imp = report.get("imported", 0)
        skp = report.get("skipped", 0)
        err = report.get("errors", 0)
        self.status_lbl.setText(
            f"Done! Detected: {det} | Imported: {imp} | Skipped (Duplicates): {skp} | Errors: {err}"
        )
        self.import_completed.emit(report)
        QMessageBox.information(
            self,
            "Import Complete",
            f"Files Detected: {det}\n"
            f"Files Imported: {imp}\n"
            f"Duplicates Skipped: {skp}\n"
            f"Import Errors: {err}",
        )
        self.accept()


# ==============================================================================
# 2. RAW-TO-JPEG STORAGE SAVER DIALOG (WITH MANDATORY 2-STAGE WARNING)
# ==============================================================================

class RawConversionDialog(QDialog):
    """RAW-to-JPEG conversion wizard with educational explanation and mandatory 2-stage warning."""

    conversion_completed = Signal()

    def __init__(self, raw_photos: List[GalleryPhoto], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Storage Saver — Convert RAW Photographs to JPEG")
        self.resize(680, 560)
        self.setStyleSheet(DIALOG_STYLE)

        self.raw_photos = [p for p in raw_photos if p.is_raw and not p.is_missing and not p.is_deleted]
        self.worker: Optional[RawConversionWorker] = None
        self.last_report = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        self.stack = QStackedWidget()
        self._build_page0_settings()
        self._build_page1_warning1()
        self._build_page2_warning2()
        self._build_page3_progress_and_summary()
        layout.addWidget(self.stack, 1)

        self._update_estimate()

    def _build_page0_settings(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(14)

        title = QLabel("💡 Save Storage by Converting RAW Photographs to Processed JPEGs")
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #F59E0B;")
        v.addWidget(title)

        edu_card = QFrame()
        edu_card.setObjectName("CardFrame")
        edu_v = QVBoxLayout(edu_card)
        edu_lbl = QLabel(
            "<b>Why are RAW files so large?</b><br>"
            "RAW files store uncompressed sensor data directly from your camera (often 20–50 MB per photo) "
            "for maximum editing latitude.<br><br>"
            "<b>When is JPEG ideal?</b><br>"
            "Processed JPEG photographs look vibrant immediately, are universally shareable, and typically "
            "reduce file size by <b>70%–85%</b> for everyday viewing and memories."
        )
        edu_lbl.setWordWrap(True)
        edu_lbl.setStyleSheet("font-size: 12px; color: #D4D4D8; line-height: 1.4;")
        edu_v.addWidget(edu_lbl)
        v.addWidget(edu_card)

        # Settings card
        cfg_card = QFrame()
        cfg_card.setObjectName("CardFrame")
        grid = QGridLayout(cfg_card)
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setSpacing(10)

        grid.addWidget(QLabel("JPEG Quality Preset:"), 0, 0)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Maximum Quality (95%)", 95)
        self.preset_combo.addItem("High Quality — Recommended (88%)", 88)
        self.preset_combo.addItem("Balanced Storage Saver (80%)", 80)
        self.preset_combo.setCurrentIndex(1)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        grid.addWidget(self.preset_combo, 0, 1)

        grid.addWidget(QLabel("Custom Quality (1–100):"), 1, 0)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(50, 100)
        self.quality_spin.setValue(88)
        self.quality_spin.valueChanged.connect(self._update_estimate)
        grid.addWidget(self.quality_spin, 1, 1)

        grid.addWidget(QLabel("Resolution Resize:"), 2, 0)
        self.resize_combo = QComboBox()
        self.resize_combo.addItem("Original Resolution (Full Megapixels)", None)
        self.resize_combo.addItem("4K Long Edge (3840 px)", 3840)
        self.resize_combo.addItem("2K / QHD Long Edge (2560 px)", 2560)
        self.resize_combo.currentIndexChanged.connect(self._update_estimate)
        grid.addWidget(self.resize_combo, 2, 1)

        self.chk_exif = QCheckBox("Preserve camera EXIF metadata & capture date")
        self.chk_exif.setChecked(True)
        grid.addWidget(self.chk_exif, 3, 0, 1, 2)

        self.chk_add_gallery = QCheckBox("Add converted JPEGs to Gallery & pair with original RAWs (for Before/After comparison)")
        self.chk_add_gallery.setChecked(True)
        grid.addWidget(self.chk_add_gallery, 4, 0, 1, 2)

        v.addWidget(cfg_card)

        # Estimate box
        self.est_lbl = QLabel("")
        self.est_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #22C55E;")
        v.addWidget(self.est_lbl)

        v.addStretch()
        btns = QHBoxLayout()
        btns.addStretch()
        b_cancel = QPushButton("Cancel")
        b_cancel.clicked.connect(self.reject)
        self.btn_next_stage1 = QPushButton("Continue to Safety Review →")
        self.btn_next_stage1.setObjectName("PrimaryBtn")
        self.btn_next_stage1.clicked.connect(self._go_to_warning_stage1)
        btns.addWidget(b_cancel)
        btns.addWidget(self.btn_next_stage1)
        v.addLayout(btns)

        self.stack.addWidget(page)

    def _build_page1_warning1(self):
        """Warning Stage 1 — Educational Explanation."""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(16)

        badge = QLabel("STAGE 1 OF 2 • EDUCATIONAL SAFETY NOTICE")
        badge.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        v.addWidget(badge)

        title = QLabel("Before You Convert Your RAW Photos")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #F4F4F5;")
        v.addWidget(title)

        card = QFrame()
        card.setObjectName("WarningFrame1")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(18, 18, 18, 18)
        cv.setSpacing(10)

        msg = QLabel(
            "Please review what converting RAW photographs to JPEG means:\n\n"
            "• RAW files contain uncompressed camera sensor data with maximum dynamic range.\n"
            "• JPEG files are processed, compressed 8-bit images that use significantly less storage.\n"
            "• Converting to JPEG reduces future extreme highlight/shadow recovery flexibility compared to RAW.\n"
            "• By default, FRAMED keeps your original RAW files completely untouched and creates new JPEG files alongside them."
        )
        msg.setWordWrap(True)
        msg.setStyleSheet("font-size: 13px; color: #F4F4F5;")
        cv.addWidget(msg)

        self.stage1_stats_lbl = QLabel("")
        self.stage1_stats_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #FBBF24; margin-top: 8px;")
        cv.addWidget(self.stage1_stats_lbl)

        v.addWidget(card)
        v.addStretch()

        btns = QHBoxLayout()
        b_cancel = QPushButton("Cancel")
        b_cancel.clicked.connect(self.reject)
        btns.addWidget(b_cancel)
        btns.addStretch()
        b_cont = QPushButton("I Understand — Continue")
        b_cont.setObjectName("PrimaryBtn")
        b_cont.clicked.connect(self._go_to_warning_stage2)
        btns.addWidget(b_cont)
        v.addLayout(btns)

        self.stack.addWidget(page)

    def _build_page2_warning2(self):
        """Warning Stage 2 — Final Confirmation."""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(16)

        badge = QLabel("STAGE 2 OF 2 • FINAL CONFIRMATION")
        badge.setStyleSheet("color: #EF4444; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        v.addWidget(badge)

        title = QLabel("Confirm RAW Conversion")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #F4F4F5;")
        v.addWidget(title)

        card = QFrame()
        card.setObjectName("WarningFrame2")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(18, 18, 18, 18)
        cv.setSpacing(12)

        self.stage2_details_lbl = QLabel("")
        self.stage2_details_lbl.setWordWrap(True)
        self.stage2_details_lbl.setStyleSheet("font-size: 13px; color: #F4F4F5;")
        cv.addWidget(self.stage2_details_lbl)

        safety_lbl = QLabel(
            "\"FRAMED will create new JPEG files from your RAW photographs. "
            "Your original RAW files will remain untouched.\""
        )
        safety_lbl.setWordWrap(True)
        safety_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #22C55E; "
            "background-color: #122117; padding: 12px; border-radius: 8px; border: 1px solid #15803D;"
        )
        cv.addWidget(safety_lbl)

        v.addWidget(card)
        v.addStretch()

        btns = QHBoxLayout()
        b_back = QPushButton("← Go Back")
        b_back.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        btns.addWidget(b_back)
        btns.addStretch()
        self.btn_confirm_convert = QPushButton("Confirm & Convert")
        self.btn_confirm_convert.setObjectName("PrimaryBtn")
        self.btn_confirm_convert.clicked.connect(self._execute_conversion)
        btns.addWidget(self.btn_confirm_convert)
        v.addLayout(btns)

        self.stack.addWidget(page)

    def _build_page3_progress_and_summary(self):
        """Conversion Progress and Post-Conversion Summary."""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(14)

        self.conv_title = QLabel("Converting RAW Photographs...")
        self.conv_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #F59E0B;")
        v.addWidget(self.conv_title)

        self.conv_progress = QProgressBar()
        v.addWidget(self.conv_progress)

        self.conv_status = QLabel("Preparing RAW decoder...")
        self.conv_status.setStyleSheet("font-size: 12px; color: #969BA5;")
        v.addWidget(self.conv_status)

        self.summary_card = QFrame()
        self.summary_card.setObjectName("CardFrame")
        self.summary_card.setVisible(False)
        sv = QVBoxLayout(self.summary_card)
        sv.setContentsMargins(16, 16, 16, 16)
        sv.setSpacing(10)

        self.summary_text = QLabel("")
        self.summary_text.setWordWrap(True)
        self.summary_text.setStyleSheet("font-size: 13px; color: #F4F4F5;")
        sv.addWidget(self.summary_text)

        # Optional user-initiated reclaim space button
        self.btn_move_raws_deleted = QPushButton(
            "Optional: Move Original RAWs to 'Recently Deleted' to Reclaim Disk Space Now"
        )
        self.btn_move_raws_deleted.setObjectName("DangerBtn")
        self.btn_move_raws_deleted.clicked.connect(self._move_raws_to_deleted)
        sv.addWidget(self.btn_move_raws_deleted)

        v.addWidget(self.summary_card)
        v.addStretch()

        self.done_btns = QHBoxLayout()
        self.done_btns.addStretch()
        self.btn_view_converted = QPushButton("View Converted Photos")
        self.btn_view_converted.setObjectName("PrimaryBtn")
        self.btn_view_converted.setVisible(False)
        self.btn_view_converted.clicked.connect(self.accept)
        self.done_btns.addWidget(self.btn_view_converted)
        v.addLayout(self.done_btns)

        self.stack.addWidget(page)

    def _on_preset_changed(self):
        q = self.preset_combo.currentData()
        if q:
            self.quality_spin.setValue(q)

    def _update_estimate(self):
        est = RawToJpegConverter.estimate_savings(self.raw_photos, self.quality_spin.value())
        self.est_lbl.setText(
            f"Selected: {est['count']} RAW photo(s)  •  "
            f"Current RAW Size: {format_bytes(est['raw_bytes'])}  →  "
            f"Est. JPEG Size: {format_bytes(est['estimated_jpeg_bytes'])}  "
            f"(Saves ~{format_bytes(est['estimated_savings_bytes'])} / {est['savings_percent']}%)"
        )
        self.btn_next_stage1.setEnabled(est["count"] > 0)

    def _go_to_warning_stage1(self):
        est = RawToJpegConverter.estimate_savings(self.raw_photos, self.quality_spin.value())
        self.stage1_stats_lbl.setText(
            f"• Number of RAW files selected: {est['count']}\n"
            f"• Current RAW storage size: {format_bytes(est['raw_bytes'])}\n"
            f"• Estimated JPEG output size: {format_bytes(est['estimated_jpeg_bytes'])}\n"
            f"• Estimated storage savings: {format_bytes(est['estimated_savings_bytes'])} ({est['savings_percent']}%)"
        )
        self.stack.setCurrentIndex(1)

    def _go_to_warning_stage2(self):
        est = RawToJpegConverter.estimate_savings(self.raw_photos, self.quality_spin.value())
        out_dir = os.path.join(storage.gallery_converted_dir, "Converted_JPEG")
        resize_val = self.resize_combo.currentData()
        resize_str = f"{resize_val}px Long Edge" if resize_val else "Original Full Resolution"
        self.stage2_details_lbl.setText(
            f"<b>Exact Conversion Parameters:</b><br>"
            f"• <b>Files to Convert:</b> {est['count']} RAW photograph(s)<br>"
            f"• <b>Output Folder:</b> {out_dir}<br>"
            f"• <b>JPEG Quality Setting:</b> {self.quality_spin.value()}% ({resize_str})<br>"
            f"• <b>Preserve EXIF Metadata:</b> {'Yes' if self.chk_exif.isChecked() else 'No'}<br>"
            f"• <b>Original RAW Files:</b> Kept untouched & paired with new JPEGs"
        )
        self.stack.setCurrentIndex(2)

    def _execute_conversion(self):
        self.stack.setCurrentIndex(3)
        self.conv_progress.setMaximum(max(1, len(self.raw_photos)))
        self.conv_progress.setValue(0)
        out_dir = os.path.join(storage.gallery_converted_dir, "Converted_JPEG")

        self.worker = RawConversionWorker(
            raw_photos=self.raw_photos,
            output_dir=out_dir,
            quality=self.quality_spin.value(),
            max_dimension=self.resize_combo.currentData(),
            add_converted_to_gallery=self.chk_add_gallery.isChecked(),
            parent=self,
        )
        self.worker.progress.connect(self._on_conv_progress)
        self.worker.finished_conversion.connect(self._on_conv_finished)
        self.worker.start()

    def _on_conv_progress(self, current: int, total: int, filename: str, completed: int = 0, failed: int = 0):
        self.conv_progress.setMaximum(max(1, total))
        self.conv_progress.setValue(current)
        self.conv_status.setText(f"Converting ({current}/{total}): {filename}")

    def _on_conv_finished(self, report: dict):
        self.last_report = report
        out_dir = os.path.join(storage.gallery_converted_dir, "Converted_JPEG")
        self.conv_title.setText("✓ RAW-to-JPEG Conversion Complete")
        self.conv_status.setText(f"Output saved to: {out_dir}")
        self.summary_card.setVisible(True)
        self.btn_view_converted.setVisible(True)

        self.summary_text.setText(
            f"<b>Conversion Summary:</b><br>"
            f"• <b>Files Converted:</b> {report.get('completed', 0)} / {report.get('total', 0)}<br>"
            f"• <b>Original RAW Size:</b> {format_bytes(report.get('original_bytes', 0))}<br>"
            f"• <b>New JPEG Size:</b> {format_bytes(report.get('output_bytes', 0))}<br>"
            f"• <b>Storage Reduction:</b> <span style='color:#22C55E;font-weight:700;'>"
            f"{format_bytes(report.get('saved_bytes', 0))} smaller</span><br>"
            f"• <b>Failed Files:</b> {report.get('failed', 0)}"
        )
        self.conversion_completed.emit()

    def _move_raws_to_deleted(self):
        ids = [p.id for p in self.raw_photos]
        count = storage.soft_delete_photos(ids)
        self.btn_move_raws_deleted.setEnabled(False)
        self.btn_move_raws_deleted.setText(f"✓ Moved {count} Original RAW(s) to Recently Deleted")
        self.conversion_completed.emit()


# ==============================================================================
# 3. DELETE GALLERY FOLDER DIALOG (SAFE PHOTO PRESERVATION)
# ==============================================================================

class DeleteGalleryFolderDialog(QDialog):
    """Asks where photographs inside a Gallery folder should go before deleting the folder."""

    def __init__(self, folder: GalleryFolder, photo_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Delete Folder '{folder.name}'")
        self.resize(480, 280)
        self.setStyleSheet(DIALOG_STYLE)
        self.target_folder_id: Optional[str] = None

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        t = QLabel(f"Delete Gallery Folder \"{folder.name}\"?")
        t.setStyleSheet("font-size: 16px; font-weight: 700;")
        v.addWidget(t)

        info = QLabel(
            f"This folder organizes {photo_count} photograph(s).\n"
            "Deleting a Gallery folder NEVER deletes your photographs from disk or from FRAMED.\n\n"
            "Where should the photographs in this folder go?"
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 12px; color: #D4D4D8;")
        v.addWidget(info)

        self.combo = QComboBox()
        self.combo.addItem("Keep in 'All Photos' (Remove folder tag only)", None)
        for f in storage.get_gallery_folders():
            if f.id != folder.id:
                self.combo.addItem(f"Move to folder: {f.name}", f.id)
        v.addWidget(self.combo)

        v.addStretch()
        btns = QHBoxLayout()
        btns.addStretch()
        b_cancel = QPushButton("Cancel")
        b_cancel.clicked.connect(self.reject)
        
        self.b_del = QPushButton("Delete Folder Safely (5s)")
        self.b_del.setObjectName("DangerBtn")
        self.b_del.setEnabled(False)
        self.b_del.setStyleSheet("""
            QPushButton#DangerBtn:disabled {
                background-color: #2E1B1E;
                color: #7F5559;
                border: 1px solid #4D262B;
            }
        """)
        self.b_del.clicked.connect(self._confirm)
        
        self.countdown = 5
        self.del_timer = QTimer(self)
        self.del_timer.timeout.connect(self._on_del_tick)
        self.del_timer.start(1000)

        btns.addWidget(b_cancel)
        btns.addWidget(self.b_del)
        v.addLayout(btns)

    def _on_del_tick(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.b_del.setText(f"Delete Folder Safely ({self.countdown}s)")
        else:
            self.del_timer.stop()
            self.b_del.setEnabled(True)
            self.b_del.setText("Delete Folder Safely")

    def _confirm(self):
        if hasattr(self, "del_timer") and self.del_timer.isActive():
            self.del_timer.stop()
        self.target_folder_id = self.combo.currentData()
        self.accept()

    def reject(self):
        if hasattr(self, "del_timer") and self.del_timer.isActive():
            self.del_timer.stop()
        super().reject()

    def closeEvent(self, event):
        if hasattr(self, "del_timer") and self.del_timer.isActive():
            self.del_timer.stop()
        super().closeEvent(event)


# ==============================================================================
# 4. LARGE PHOTO VIEWER + EXPANDABLE EXIF METADATA INSPECTOR
# ==============================================================================

class ZoomableImageCanvas(QWidget):
    """Smooth zoom & pan canvas for Gallery Photo Viewer and Before/After comparison."""

    zoom_changed = Signal(float)
    pan_changed = Signal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self._pixmap = QPixmap()
        self._zoom = 1.0
        self._pan = QPoint(0, 0)
        self._dragging = False
        self._last_pos = QPoint()

    def set_pixmap(self, pix: QPixmap, reset_view: bool = True):
        self._pixmap = pix
        if reset_view:
            self._zoom = 1.0
            self._pan = QPoint(0, 0)
        self.update()

    def set_sync_state(self, zoom: float, pan: QPoint):
        self._zoom = zoom
        self._pan = pan
        self.update()

    def set_zoom(self, zoom: float):
        self._zoom = max(0.25, min(6.0, zoom))
        self.zoom_changed.emit(self._zoom)
        self.update()

    def reset_fit(self):
        self._zoom = 1.0
        self._pan = QPoint(0, 0)
        self.zoom_changed.emit(self._zoom)
        self.pan_changed.emit(self._pan)
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else (1 / 1.15)
        self.set_zoom(self._zoom * factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_pos = event.pos()

    def mouseMoveEvent(self, event):
        if self._dragging:
            diff = event.pos() - self._last_pos
            self._last_pos = event.pos()
            self._pan += diff
            self.pan_changed.emit(self._pan)
            self.update()

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#0C0D10"))

        if self._pixmap.isNull():
            p.setPen(QColor("#666D79"))
            p.drawText(self.rect(), Qt.AlignCenter, "Preview Unavailable")
            p.end()
            return

        scaled_w = int(self._pixmap.width() * self._zoom)
        scaled_h = int(self._pixmap.height() * self._zoom)
        # Fit inside widget at zoom=1.0
        base_scale = min(
            (self.width() - 24) / max(1, self._pixmap.width()),
            (self.height() - 24) / max(1, self._pixmap.height()),
        )
        draw_w = int(self._pixmap.width() * base_scale * self._zoom)
        draw_h = int(self._pixmap.height() * base_scale * self._zoom)

        cx = (self.width() - draw_w) // 2 + self._pan.x()
        cy = (self.height() - draw_h) // 2 + self._pan.y()
        p.drawPixmap(cx, cy, draw_w, draw_h, self._pixmap)
        p.end()


class GalleryPhotoViewerModal(QDialog):
    """Full-featured Photo Viewer with Zoom, Favorite/Star/Color Rating, and EXIF Metadata Inspector."""

    photo_updated = Signal(str)  # photo_id
    compare_requested = Signal(object)  # GalleryPhoto

    def __init__(self, photos: List[GalleryPhoto], current_index: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FRAMED Gallery — Photo Viewer & Metadata Inspector")
        self.resize(1180, 760)
        self.setStyleSheet(DIALOG_STYLE)

        self.photos = photos
        self.index = max(0, min(current_index, len(photos) - 1))

        main_v = QVBoxLayout(self)
        main_v.setContentsMargins(14, 14, 14, 14)
        main_v.setSpacing(10)

        # Top toolbar
        top = QHBoxLayout()
        self.title_lbl = QLabel("")
        self.title_lbl.setStyleSheet("font-size: 15px; font-weight: 700;")
        top.addWidget(self.title_lbl)
        top.addStretch()

        btn_prev = QPushButton("← Prev")
        btn_prev.clicked.connect(self._prev_photo)
        btn_next = QPushButton("Next →")
        btn_next.clicked.connect(self._next_photo)
        btn_zoom_in = QPushButton("Zoom +")
        btn_zoom_in.clicked.connect(lambda: self.canvas.set_zoom(self.canvas._zoom * 1.25))
        btn_zoom_out = QPushButton("Zoom −")
        btn_zoom_out.clicked.connect(lambda: self.canvas.set_zoom(self.canvas._zoom / 1.25))
        btn_fit = QPushButton("Fit")
        btn_fit.clicked.connect(lambda: self.canvas.reset_fit())

        self.btn_fav = QPushButton("♥ Favorite")
        self.btn_fav.clicked.connect(self._toggle_fav)

        self.btn_compare = QPushButton("Before / After Compare")
        self.btn_compare.clicked.connect(self._open_compare)

        self.btn_toggle_meta = QPushButton("Metadata Inspector")
        self.btn_toggle_meta.setCheckable(True)
        self.btn_toggle_meta.setChecked(True)
        self.btn_toggle_meta.toggled.connect(lambda checked: self.meta_panel.setVisible(checked))

        for b in (btn_prev, btn_next, btn_zoom_out, btn_fit, btn_zoom_in, self.btn_fav, self.btn_compare, self.btn_toggle_meta):
            top.addWidget(b)
        main_v.addLayout(top)

        # Center area: Canvas + Right Metadata Inspector
        center = QHBoxLayout()
        self.canvas = ZoomableImageCanvas()
        center.addWidget(self.canvas, 1)

        self.meta_panel = QFrame()
        self.meta_panel.setObjectName("CardFrame")
        self.meta_panel.setFixedWidth(320)
        mv = QVBoxLayout(self.meta_panel)
        mv.setContentsMargins(14, 14, 14, 14)
        mv.setSpacing(8)

        m_hdr = QLabel("PHOTOGRAPH METADATA")
        m_hdr.setStyleSheet("font-size: 11px; font-weight: 700; color: #F59E0B; letter-spacing: 1px;")
        mv.addWidget(m_hdr)

        self.meta_text = QLabel("")
        self.meta_text.setWordWrap(True)
        self.meta_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.meta_text.setStyleSheet("font-size: 12px; color: #E4E4E7; line-height: 1.45;")
        mv.addWidget(self.meta_text)

        # Rating & Color Label controls
        mv.addWidget(QLabel("Star Rating (1–5):"))
        self.rating_combo = QComboBox()
        for r in range(6):
            stars = "★" * r + "☆" * (5 - r) if r > 0 else "No Rating"
            self.rating_combo.addItem(stars, r)
        self.rating_combo.currentIndexChanged.connect(self._save_annotations)
        mv.addWidget(self.rating_combo)

        mv.addWidget(QLabel("Color Label:"))
        self.color_combo = QComboBox()
        for c_name in ("none", "red", "yellow", "green", "blue", "purple"):
            self.color_combo.addItem(c_name.capitalize(), c_name)
        self.color_combo.currentIndexChanged.connect(self._save_annotations)
        mv.addWidget(self.color_combo)

        mv.addWidget(QLabel("Location Label (GPS):"))
        self.gps_edit = QLineEdit()
        self.gps_edit.setPlaceholderText("e.g., Tokyo, Japan or Bali Beach")
        self.gps_edit.editingFinished.connect(self._save_annotations)
        mv.addWidget(self.gps_edit)

        mv.addWidget(QLabel("Photographer Notes:"))
        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(70)
        self.notes_edit.textChanged.connect(self._save_annotations)
        mv.addWidget(self.notes_edit)

        mv.addStretch()
        center.addWidget(self.meta_panel)
        main_v.addLayout(center, 1)

        # Keyboard shortcuts
        QShortcut(QKeySequence(Qt.Key_Left), self, self._prev_photo)
        QShortcut(QKeySequence(Qt.Key_Right), self, self._next_photo)
        QShortcut(QKeySequence("F"), self, self._toggle_fav)

        self._loading = False
        self._load_current()

    @property
    def current_photo(self) -> Optional[GalleryPhoto]:
        if 0 <= self.index < len(self.photos):
            return self.photos[self.index]
        return None

    def _load_current(self):
        p = self.current_photo
        if not p:
            return
        self._loading = True
        self.title_lbl.setText(f"{p.filename}   ({self.index + 1} of {len(self.photos)})   [{p.format_type}]")
        pix = _load_preview_pixmap(p.active_path, 1400, 1000)
        self.canvas.set_pixmap(pix, reset_view=True)

        self.btn_fav.setText("♥ Favorited" if p.is_favorite else "♡ Favorite")
        self.btn_fav.setStyleSheet(
            "background-color: #F59E0B; color: #0D0E11; font-weight: 700;" if p.is_favorite else ""
        )

        folders_names = [f.name for f in storage.get_gallery_folders() if f.id in p.folder_ids]
        folder_str = ", ".join(folders_names) if folders_names else "All Photos"
        storage_mode = "FRAMED Managed Copy" if p.is_managed else "Referenced Original Location"

        self.meta_text.setText(
            f"<b>File Name:</b> {p.filename}<br>"
            f"<b>Format:</b> {p.format_type} ({p.extension.upper()})<br>"
            f"<b>File Size:</b> {format_bytes(p.size_bytes)}<br>"
            f"<b>Dimensions:</b> {p.dimensions_str}<br>"
            f"<b>Date Taken:</b> {p.date_taken}<br>"
            f"<b>Camera:</b> {p.camera_model}<br>"
            f"<b>Lens:</b> {p.lens}<br>"
            f"<b>ISO:</b> {p.iso}  •  <b>Aperture:</b> {p.aperture}<br>"
            f"<b>Shutter:</b> {p.shutter_speed}  •  <b>Focal:</b> {p.focal_length}<br>"
            f"<b>Folders:</b> {folder_str}<br>"
            f"<b>Storage Mode:</b> {storage_mode}<br>"
            f"<b>Path:</b> <span style='color:#969BA5;font-size:11px;'>{p.active_path}</span>"
        )

        self.rating_combo.setCurrentIndex(max(0, min(5, p.rating)))
        c_idx = self.color_combo.findData(p.color_label)
        self.color_combo.setCurrentIndex(c_idx if c_idx >= 0 else 0)
        self.gps_edit.setText(p.gps_label or "")
        self.notes_edit.setPlainText(p.notes or "")
        self._loading = False

    def _prev_photo(self):
        if self.index > 0:
            self.index -= 1
            self._load_current()

    def _next_photo(self):
        if self.index < len(self.photos) - 1:
            self.index += 1
            self._load_current()

    def _toggle_fav(self):
        p = self.current_photo
        if not p:
            return
        storage.toggle_gallery_favorite(p.id)
        self._load_current()
        self.photo_updated.emit(p.id)

    def _save_annotations(self):
        if self._loading:
            return
        p = self.current_photo
        if not p:
            return
        p.rating = self.rating_combo.currentData() or 0
        p.color_label = self.color_combo.currentData() or "none"
        p.gps_label = self.gps_edit.text().strip()
        p.notes = self.notes_edit.toPlainText().strip()
        storage.save()
        self.photo_updated.emit(p.id)

    def _open_compare(self):
        p = self.current_photo
        if p:
            dlg = BeforeAfterComparisonDialog(p, self)
            dlg.exec()


# ==============================================================================
# 5. BEFORE & AFTER COMPARISON DIALOG (SYNCHRONIZED ZOOM/PAN)
# ==============================================================================

class BeforeAfterComparisonDialog(QDialog):
    """Side-by-side synchronized comparison for RAW vs JPEG or Original vs Edited."""

    def __init__(self, photo: GalleryPhoto, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Before & After Comparison — {photo.filename}")
        self.resize(1220, 740)
        self.setStyleSheet(DIALOG_STYLE)
        self.photo = photo

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        top = QHBoxLayout()
        lbl = QLabel("⇄ Synchronized Before & After Comparison (Scroll to zoom both, drag to pan both)")
        lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #F59E0B;")
        top.addWidget(lbl)
        top.addStretch()

        btn_pick_second = QPushButton("Choose Comparison Photo...")
        btn_pick_second.clicked.connect(self._pick_comparison_file)
        btn_reset = QPushButton("Reset Zoom / Fit")
        btn_reset.clicked.connect(self._reset_both)
        top.addWidget(btn_pick_second)
        top.addWidget(btn_reset)
        v.addLayout(top)

        # Side by side canvases
        split = QHBoxLayout()
        left_box = QVBoxLayout()
        self.left_hdr = QLabel("")
        self.left_hdr.setStyleSheet("font-size: 13px; font-weight: 700; color: #60A5FA;")
        self.left_canvas = ZoomableImageCanvas()
        left_box.addWidget(self.left_hdr)
        left_box.addWidget(self.left_canvas, 1)

        right_box = QVBoxLayout()
        self.right_hdr = QLabel("")
        self.right_hdr.setStyleSheet("font-size: 13px; font-weight: 700; color: #F59E0B;")
        self.right_canvas = ZoomableImageCanvas()
        right_box.addWidget(self.right_hdr)
        right_box.addWidget(self.right_canvas, 1)

        split.addLayout(left_box, 1)
        split.addLayout(right_box, 1)
        v.addLayout(split, 1)

        # Synchronize zoom & pan
        self.left_canvas.zoom_changed.connect(lambda z: self.right_canvas.set_sync_state(z, self.left_canvas._pan))
        self.left_canvas.pan_changed.connect(lambda p: self.right_canvas.set_sync_state(self.left_canvas._zoom, p))
        self.right_canvas.zoom_changed.connect(lambda z: self.left_canvas.set_sync_state(z, self.right_canvas._pan))
        self.right_canvas.pan_changed.connect(lambda p: self.left_canvas.set_sync_state(self.right_canvas._zoom, p))

        self._load_pair()

    def _load_pair(self):
        left_path = self.photo.paired_raw_path if self.photo.paired_raw_path and os.path.exists(self.photo.paired_raw_path) else self.photo.active_path
        right_path = self.photo.paired_jpeg_path if self.photo.paired_jpeg_path and os.path.exists(self.photo.paired_jpeg_path) else self.photo.active_path

        l_size = format_bytes(os.path.getsize(left_path)) if left_path and os.path.exists(left_path) else "0 B"
        r_size = format_bytes(os.path.getsize(right_path)) if right_path and os.path.exists(right_path) else "0 B"

        self.left_hdr.setText(f"BEFORE (Original / RAW): {os.path.basename(left_path)} ({l_size})")
        self.right_hdr.setText(f"AFTER (Processed / JPEG): {os.path.basename(right_path)} ({r_size})")

        self.left_canvas.set_pixmap(_load_preview_pixmap(left_path, 1200, 900))
        self.right_canvas.set_pixmap(_load_preview_pixmap(right_path, 1200, 900))

    def _pick_comparison_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Second Image to Compare")
        if f and os.path.exists(f):
            self.photo.paired_jpeg_path = f
            storage.save()
            self._load_pair()

    def _reset_both(self):
        self.left_canvas.reset_fit()
        self.right_canvas.reset_fit()


# ==============================================================================
# 6. SLIDESHOW MODE MODAL
# ==============================================================================

class GallerySlideshowModal(QDialog):
    """Full-screen capable slideshow presentation for memories and albums."""

    def __init__(self, photos: List[GalleryPhoto], parent=None):
        super().__init__(parent)
        self.setWindowTitle("FRAMED Gallery — Slideshow")
        self.resize(1280, 800)
        self.setStyleSheet(DIALOG_STYLE + "QDialog { background-color: #07080A; }")
        self.photos = [p for p in photos if not p.is_missing]
        self.index = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next)

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)

        self.canvas = ZoomableImageCanvas()
        v.addWidget(self.canvas, 1)

        ctrl = QHBoxLayout()
        self.caption_lbl = QLabel("")
        self.caption_lbl.setStyleSheet("font-size: 14px; font-weight: 600; color: #F4F4F5;")
        ctrl.addWidget(self.caption_lbl)
        ctrl.addStretch()

        btn_prev = QPushButton("⏮ Prev")
        btn_prev.clicked.connect(self._prev)
        self.btn_play = QPushButton("⏸ Pause")
        self.btn_play.setObjectName("PrimaryBtn")
        self.btn_play.clicked.connect(self._toggle_play)
        btn_next = QPushButton("Next ⏭")
        btn_next.clicked.connect(self._next)

        ctrl.addWidget(QLabel("Speed:"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItem("3 seconds", 3000)
        self.speed_combo.addItem("5 seconds", 5000)
        self.speed_combo.addItem("8 seconds", 8000)
        self.speed_combo.currentIndexChanged.connect(self._update_speed)

        btn_exit = QPushButton("Exit Slideshow (Esc)")
        btn_exit.clicked.connect(self.reject)

        for w in (btn_prev, self.btn_play, btn_next, self.speed_combo, btn_exit):
            ctrl.addWidget(w)
        v.addLayout(ctrl)

        QShortcut(QKeySequence(Qt.Key_Space), self, self._toggle_play)
        QShortcut(QKeySequence(Qt.Key_Left), self, self._prev)
        QShortcut(QKeySequence(Qt.Key_Right), self, self._next)

        self._show_current()
        self.timer.start(3000)

    def _show_current(self):
        if not self.photos:
            return
        p = self.photos[self.index]
        self.canvas.set_pixmap(_load_preview_pixmap(p.active_path, 1600, 1100))
        self.caption_lbl.setText(f"{p.filename}   •   {p.date_taken}   ({self.index + 1}/{len(self.photos)})")

    def _next(self):
        if not self.photos:
            return
        self.index = (self.index + 1) % len(self.photos)
        self._show_current()

    def _prev(self):
        if not self.photos:
            return
        self.index = (self.index - 1) % len(self.photos)
        self._show_current()

    def _toggle_play(self):
        if self.timer.isActive():
            self.timer.stop()
            self.btn_play.setText("▶ Play")
        else:
            self.timer.start(self.speed_combo.currentData())
            self.btn_play.setText("⏸ Pause")

    def _update_speed(self):
        if self.timer.isActive():
            self.timer.start(self.speed_combo.currentData())


# ==============================================================================
# 7. DUPLICATE FINDER, MISSING FILE RECOVERY, BACKUP & SMART ALBUM DIALOGS
# ==============================================================================

class DuplicateFinderDialog(QDialog):
    """Scans Gallery for exact SHA-256 duplicates, RAW+JPEG pairs, and visually similar photos."""

    duplicates_resolved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Duplicate & Similar Photo Finder")
        self.resize(740, 520)
        self.setStyleSheet(DIALOG_STYLE)

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        t = QLabel("Duplicate & Similar Photograph Inspector")
        t.setStyleSheet("font-size: 17px; font-weight: 700; color: #F59E0B;")
        v.addWidget(t)

        sub = QLabel("FRAMED never deletes duplicates automatically. Review matches below and choose what to move to Recently Deleted.")
        sub.setStyleSheet("font-size: 12px; color: #969BA5;")
        v.addWidget(sub)

        self.list_widget = QListWidget()
        v.addWidget(self.list_widget, 1)

        btns = QHBoxLayout()
        btn_scan = QPushButton("Rescan Gallery")
        btn_scan.clicked.connect(self._scan)
        self.btn_remove_checked = QPushButton("Move Checked Duplicates to Recently Deleted")
        self.btn_remove_checked.setObjectName("DangerBtn")
        self.btn_remove_checked.clicked.connect(self._remove_checked)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btns.addWidget(btn_scan)
        btns.addStretch()
        btns.addWidget(self.btn_remove_checked)
        btns.addWidget(btn_close)
        v.addLayout(btns)

        self._scan()

    def _scan(self):
        self.list_widget.clear()
        res = DuplicateFinderEngine.find_duplicates(include_similar=True)
        exact_groups = res.get("exact", [])
        sim_groups = res.get("similar", [])
        if not exact_groups and not sim_groups:
            self.list_widget.addItem("✓ No exact or visual duplicates found in your Gallery.")
            return
        for grp in exact_groups:
            hdr = QListWidgetItem(f"── Exact SHA-256 Duplicate ({len(grp)} files) ──")
            hdr.setFlags(Qt.ItemIsEnabled)
            hdr.setForeground(QColor("#F59E0B"))
            self.list_widget.addItem(hdr)
            for idx, p in enumerate(grp):
                item = QListWidgetItem(f"    {p.filename}  ({format_bytes(p.size_bytes)})  —  {p.active_path}")
                item.setData(Qt.UserRole, p.id)
                item.setCheckState(Qt.Checked if idx > 0 else Qt.Unchecked)
                self.list_widget.addItem(item)
        for grp in sim_groups:
            hdr = QListWidgetItem(f"── Visually Similar Group ({len(grp)} files) ──")
            hdr.setFlags(Qt.ItemIsEnabled)
            hdr.setForeground(QColor("#60A5FA"))
            self.list_widget.addItem(hdr)
            for p in grp:
                item = QListWidgetItem(f"    {p.filename}  ({format_bytes(p.size_bytes)})  —  {p.active_path}")
                item.setData(Qt.UserRole, p.id)
                item.setCheckState(Qt.Unchecked)
                self.list_widget.addItem(item)

    def _remove_checked(self):
        ids = []
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            pid = it.data(Qt.UserRole)
            if pid and it.checkState() == Qt.Checked:
                ids.append(pid)
        if not ids:
            QMessageBox.information(self, "No Duplicates Checked", "Check one or more duplicate items first.")
            return
        storage.soft_delete_photos(ids)
        self.duplicates_resolved.emit()
        self._scan()


class GalleryBackupDialog(QDialog):
    """Exports a verified Gallery Backup & Archive with manifest.json."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gallery Backup & Archive Center")
        self.resize(580, 380)
        self.setStyleSheet(DIALOG_STYLE)

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        t = QLabel("Backup & Archive Your Gallery")
        t.setStyleSheet("font-size: 17px; font-weight: 700; color: #F59E0B;")
        v.addWidget(t)

        last_bk = storage.backup_records[0] if storage.backup_records else None
        last_str = (
            f"Last Backup: {last_bk.timestamp[:16].replace('T', ' ')} → {last_bk.destination_dir} ({last_bk.files_completed} photos)"
            if last_bk else "No backups recorded yet."
        )
        self.last_lbl = QLabel(last_str)
        self.last_lbl.setStyleSheet("font-size: 12px; color: #22C55E;")
        v.addWidget(self.last_lbl)

        self.chk_raw = QCheckBox("Include RAW Photographs")
        self.chk_raw.setChecked(True)
        self.chk_jpeg = QCheckBox("Include JPEG & Other Photographs")
        self.chk_jpeg.setChecked(True)
        v.addWidget(self.chk_raw)
        v.addWidget(self.chk_jpeg)

        v.addStretch()
        btns = QHBoxLayout()
        btns.addStretch()
        b_cancel = QPushButton("Close")
        b_cancel.clicked.connect(self.reject)
        b_run = QPushButton("Choose Destination & Run Backup...")
        b_run.setObjectName("PrimaryBtn")
        b_run.clicked.connect(self._run_backup)
        btns.addWidget(b_cancel)
        btns.addWidget(b_run)
        v.addLayout(btns)

    def _run_backup(self):
        dest = QFileDialog.getExistingDirectory(self, "Select Backup Destination Folder")
        if not dest:
            return
        res = GalleryBackupEngine.run_backup(destination_root=dest, include_referenced=True, verify_hashes=True)
        QMessageBox.information(
            self,
            "Backup Verified & Completed",
            f"Backed up {res.get('completed', 0)} photographs ({format_bytes(res.get('total_bytes', 0))}) to:\n{dest}",
        )
        self.accept()


class SmartAlbumDialog(QDialog):
    """Creates a custom rule-based Smart Album."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Smart Album")
        self.resize(460, 340)
        self.setStyleSheet(DIALOG_STYLE)
        self.created_album: Optional[SmartAlbum] = None

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(10)

        t = QLabel("New Rule-Based Smart Album")
        t.setStyleSheet("font-size: 16px; font-weight: 700; color: #F59E0B;")
        v.addWidget(t)

        v.addWidget(QLabel("Smart Album Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., Canon 5-Star RAWs or Large Files > 20MB")
        v.addWidget(self.name_edit)

        grid = QGridLayout()
        grid.addWidget(QLabel("Format Filter:"), 0, 0)
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItem("Any Format", None)
        self.fmt_combo.addItem("RAW Files Only", "RAW")
        self.fmt_combo.addItem("JPEG Files Only", "JPEG")
        grid.addWidget(self.fmt_combo, 0, 1)

        grid.addWidget(QLabel("Minimum Star Rating:"), 1, 0)
        self.rating_spin = QSpinBox()
        self.rating_spin.setRange(0, 5)
        grid.addWidget(self.rating_spin, 1, 1)

        grid.addWidget(QLabel("Minimum File Size (MB):"), 2, 0)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(0, 500)
        grid.addWidget(self.size_spin, 2, 1)

        grid.addWidget(QLabel("Camera Contains:"), 3, 0)
        self.cam_edit = QLineEdit()
        self.cam_edit.setPlaceholderText("Optional camera model keyword")
        grid.addWidget(self.cam_edit, 3, 1)

        v.addLayout(grid)
        self.chk_fav = QCheckBox("Must be marked as Favorite (♥)")
        v.addWidget(self.chk_fav)

        v.addStretch()
        btns = QHBoxLayout()
        btns.addStretch()
        b_cancel = QPushButton("Cancel")
        b_cancel.clicked.connect(self.reject)
        b_save = QPushButton("Create Smart Album")
        b_save.setObjectName("PrimaryBtn")
        b_save.clicked.connect(self._create)
        btns.addWidget(b_cancel)
        btns.addWidget(b_save)
        v.addLayout(btns)

    def _create(self):
        name = self.name_edit.text().strip()
        if not name:
            return
        rules = {}
        if self.fmt_combo.currentData():
            rules["format_type"] = self.fmt_combo.currentData()
        if self.rating_spin.value() > 0:
            rules["min_rating"] = self.rating_spin.value()
        if self.size_spin.value() > 0:
            rules["min_size_mb"] = self.size_spin.value()
        if self.cam_edit.text().strip():
            rules["camera_contains"] = self.cam_edit.text().strip()
        if self.chk_fav.isChecked():
            rules["is_favorite"] = True

        self.created_album = storage.create_smart_album(name, rules)
        self.accept()
