"""Settings dialog for RAM budget, remappable key bindings, zoom-start defaults, and tour restart."""

import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QCheckBox, QSlider, QFrame, QFileDialog, QMessageBox, QWidget, QScrollArea,
    QApplication, QRadioButton, QButtonGroup, QGridLayout
)
from PySide6.QtCore import Qt, Signal
from loupe.config import config, get_total_system_ram_gb
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_SUBTLE,
    COLOR_BORDER_DISTINCT, COLOR_BORDER_FOCUS, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_ACCENT,
    get_display_font, get_body_font, get_mono_font,
    THEMES, THEME_ALIASES, current_theme_id, apply_theme
)
from loupe.ui.icons import render_icon
from loupe.core.updater import CURRENT_VERSION, UpdateCheckWorker
from loupe.ui.update_dialog import UpdateDialog

class KeyBindingEdit(QLineEdit):
    """Input widget that captures single key presses for shortcuts."""
    def __init__(self, key_text: str = "", parent=None):
        super().__init__(key_text, parent)
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignCenter)
        self.setFont(get_mono_font(13, bold=True))
        self.setFixedWidth(50)
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLOR_BG_BASE};
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_BORDER_DISTINCT};
            }}
            QLineEdit:focus {{
                border: 2px solid {COLOR_ACCENT};
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)

    def keyPressEvent(self, event):
        txt = event.text().upper()
        if txt and txt.isprintable():
            self.setText(txt)
        elif event.key() == Qt.Key_Backspace or event.key() == Qt.Key_Delete:
            self.setText("")
        event.accept()


class SettingsDialog(QDialog):
    restart_tour_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Framed Preferences & Configuration")
        self.setMinimumSize(540, 360)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")

        self._init_ui()
        self._fit_to_available_screen()
        self._load_values()

    def _fit_to_available_screen(self):
        try:
            screen = self.screen() or QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                target_w = min(680, max(540, avail.width() - 40))
                target_h = min(620, max(360, avail.height() - 60))
                self.resize(target_w, target_h)
                x = avail.x() + (avail.width() - target_w) // 2
                y = avail.y() + max(10, (avail.height() - target_h) // 2)
                self.move(x, y)
        except Exception:
            self.resize(640, 520)

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_to_available_screen()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        # Header
        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel("Preferences")
        title.setFont(get_display_font(18, bold=True))
        sub = QLabel("Configure memory preloading, ergonomic key bindings, and optical defaults.")
        sub.setFont(get_body_font(12))
        sub.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        header.addWidget(title)
        header.addWidget(sub)
        main_layout.addLayout(header)

        # Scrollable form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        form_layout = QVBoxLayout(container)
        form_layout.setContentsMargins(0, 4, 0, 4)
        form_layout.setSpacing(16)

        # Section 1: Workspace Theme & Appearance
        card_theme = self._create_card()
        l_theme = QVBoxLayout(card_theme)
        l_theme.setSpacing(10)

        t_theme = QLabel("WORKSPACE THEME & APPEARANCE")
        t_theme.setFont(get_mono_font(10, bold=True))
        t_theme.setStyleSheet(f"color: {COLOR_ACCENT};")
        l_theme.addWidget(t_theme)

        desc_theme = QLabel("Select your reference color grade theme. Visual styles update live in real-time.")
        desc_theme.setFont(get_body_font(12))
        desc_theme.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        l_theme.addWidget(desc_theme)

        self.theme_group = QButtonGroup(self)
        self.theme_radios = {}

        grid_theme = QGridLayout()
        grid_theme.setSpacing(10)

        for idx, (t_id, t_def) in enumerate(THEMES.items()):
            row = idx // 2
            col = idx % 2

            t_box = QFrame()
            t_box.setStyleSheet(f"""
                QFrame {{
                    background-color: {COLOR_BG_BASE};
                    border: 1px solid {COLOR_BORDER_DISTINCT};
                    border-radius: 4px;
                }}
            """)
            box_layout = QVBoxLayout(t_box)
            box_layout.setContentsMargins(10, 8, 10, 8)
            box_layout.setSpacing(4)

            top_row = QHBoxLayout()
            rb = QRadioButton(t_def.name)
            rb.setFont(get_body_font(12, bold=True))
            self.theme_group.addButton(rb)
            self.theme_radios[t_id] = rb
            top_row.addWidget(rb, stretch=1)

            # Swatches (Base, Surface, Accent)
            swatch_layout = QHBoxLayout()
            swatch_layout.setSpacing(4)
            for c_key in ["COLOR_BG_BASE", "COLOR_BG_SURFACE", "COLOR_ACCENT"]:
                c_val = t_def.colors[c_key]
                dot = QLabel()
                dot.setFixedSize(14, 14)
                dot.setStyleSheet(f"background-color: {c_val}; border: 1px solid rgba(128,128,128,0.4); border-radius: 7px;")
                swatch_layout.addWidget(dot)
            top_row.addLayout(swatch_layout)
            box_layout.addLayout(top_row)

            lbl_desc = QLabel(t_def.description)
            lbl_desc.setFont(get_body_font(11))
            lbl_desc.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
            lbl_desc.setWordWrap(True)
            box_layout.addWidget(lbl_desc)

            rb.toggled.connect(lambda checked, tid=t_id: self._on_theme_toggled(tid, checked))
            grid_theme.addWidget(t_box, row, col)

        l_theme.addLayout(grid_theme)
        form_layout.addWidget(card_theme)

        # Section 2: RAM Budget
        card_ram = self._create_card()
        l_ram = QVBoxLayout(card_ram)
        l_ram.setSpacing(10)

        t_ram = QLabel("PRELOAD RAM BUDGET")
        t_ram.setFont(get_mono_font(10, bold=True))
        t_ram.setStyleSheet(f"color: {COLOR_ACCENT};")
        l_ram.addWidget(t_ram)

        total_sys = get_total_system_ram_gb()
        desc_ram = QLabel(f"Maximum memory cap for photo caching. Detected system memory: {total_sys} GB.")
        desc_ram.setFont(get_body_font(12))
        desc_ram.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        l_ram.addWidget(desc_ram)

        row_ram = QHBoxLayout()
        self.ram_slider = QSlider(Qt.Horizontal)
        self.ram_slider.setRange(2, max(4, total_sys))
        self.ram_slider.valueChanged.connect(lambda v: self.ram_val_lbl.setText(f"{v} GB"))
        row_ram.addWidget(self.ram_slider, stretch=1)

        self.ram_val_lbl = QLabel("16 GB")
        self.ram_val_lbl.setFont(get_mono_font(12, bold=True))
        self.ram_val_lbl.setFixedWidth(60)
        self.ram_val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_ram.addWidget(self.ram_val_lbl)
        l_ram.addLayout(row_ram)

        form_layout.addWidget(card_ram)

        # Section 2: Key Bindings
        card_keys = self._create_card()
        l_keys = QVBoxLayout(card_keys)
        l_keys.setSpacing(10)

        t_keys = QLabel("KEYBOARD BINDINGS (CLICK BOX & PRESS KEY)")
        t_keys.setFont(get_mono_font(10, bold=True))
        t_keys.setStyleSheet(f"color: {COLOR_ACCENT};")
        l_keys.addWidget(t_keys)

        grid_keys = QVBoxLayout()
        grid_keys.setSpacing(8)

        self.key_keep = self._create_key_row("Keep Photo:", "W", grid_keys)
        self.key_maybe = self._create_key_row("Maybe / Review Later:", "E", grid_keys)
        self.key_reject = self._create_key_row("Move to Not Accepted:", "S", grid_keys)
        self.key_prev = self._create_key_row("Previous Photo:", "A", grid_keys)
        self.key_next = self._create_key_row("Next Photo:", "D", grid_keys)
        l_keys.addLayout(grid_keys)

        form_layout.addWidget(card_keys)

        # Section 3: Loupe & Zoom Defaults
        card_zoom = self._create_card()
        l_zoom = QVBoxLayout(card_zoom)
        l_zoom.setSpacing(10)

        t_zoom = QLabel("OPTICAL LOUPE DEFAULTS")
        t_zoom.setFont(get_mono_font(10, bold=True))
        t_zoom.setStyleSheet(f"color: {COLOR_ACCENT};")
        l_zoom.addWidget(t_zoom)

        self.cb_start_zoomed = QCheckBox("Enable 'Start zoomed in' by default")
        l_zoom.addWidget(self.cb_start_zoomed)

        row_zoom = QHBoxLayout()
        l_zoom_lbl = QLabel("Default Zoom Level:")
        l_zoom_lbl.setFont(get_body_font(12))
        row_zoom.addWidget(l_zoom_lbl)

        self.slider_zoom_lvl = QSlider(Qt.Horizontal)
        self.slider_zoom_lvl.setRange(100, 400)
        self.slider_zoom_lvl.valueChanged.connect(lambda v: self.lbl_zoom_pct.setText(f"{v}%"))
        row_zoom.addWidget(self.slider_zoom_lvl, stretch=1)

        self.lbl_zoom_pct = QLabel("200%")
        self.lbl_zoom_pct.setFont(get_mono_font(12, bold=True))
        self.lbl_zoom_pct.setFixedWidth(50)
        row_zoom.addWidget(self.lbl_zoom_pct)
        l_zoom.addLayout(row_zoom)

        form_layout.addWidget(card_zoom)

        # Section 4: Export Location & Pair Sync
        card_sync = self._create_card()
        l_sync = QVBoxLayout(card_sync)
        l_sync.setSpacing(10)

        t_sync = QLabel("PAIR SYNC & EXPORT LOCATION")
        t_sync.setFont(get_mono_font(10, bold=True))
        t_sync.setStyleSheet(f"color: {COLOR_ACCENT};")
        l_sync.addWidget(t_sync)

        self.cb_sync_pairs = QCheckBox("Default to syncing matching RAW & JPEG pairs")
        l_sync.addWidget(self.cb_sync_pairs)

        l_export = QVBoxLayout()
        l_export.setSpacing(4)
        l_export.addWidget(QLabel("Default Export Destination:"))
        
        row_exp = QHBoxLayout()
        self.edit_export_dir = QLineEdit()
        row_exp.addWidget(self.edit_export_dir, stretch=1)

        btn_browse_exp = QPushButton("Browse")
        btn_browse_exp.clicked.connect(self._browse_export_dir)
        row_exp.addWidget(btn_browse_exp)
        l_export.addLayout(row_exp)
        l_sync.addLayout(l_export)

        form_layout.addWidget(card_sync)

        # Section 5: Guided Tour
        card_tour = self._create_card()
        l_tour = QHBoxLayout(card_tour)
        l_tour.setSpacing(16)

        v_tour = QVBoxLayout()
        t_tour = QLabel("GUIDED TOUR")
        t_tour.setFont(get_mono_font(10, bold=True))
        t_tour.setStyleSheet(f"color: {COLOR_ACCENT};")
        v_tour.addWidget(t_tour)

        d_tour = QLabel("Replay the introductory walkthrough.")
        d_tour.setFont(get_body_font(12))
        d_tour.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        v_tour.addWidget(d_tour)
        l_tour.addLayout(v_tour, stretch=1)

        btn_restart_tour = QPushButton("Restart Tour")
        btn_restart_tour.clicked.connect(self._on_restart_tour)
        l_tour.addWidget(btn_restart_tour)

        form_layout.addWidget(card_tour)

        # Section 6: Software Updates & Auto-Update Feed
        card_update = self._create_card()
        l_update = QVBoxLayout(card_update)
        l_update.setSpacing(10)

        t_update = QLabel("SOFTWARE UPDATES")
        t_update.setFont(get_mono_font(10, bold=True))
        t_update.setStyleSheet(f"color: {COLOR_ACCENT};")
        l_update.addWidget(t_update)

        ver_row = QHBoxLayout()
        lbl_curr_ver = QLabel(f"Current Build: Framed v{CURRENT_VERSION}")
        lbl_curr_ver.setFont(get_body_font(12, bold=True))
        ver_row.addWidget(lbl_curr_ver)
        ver_row.addStretch()

        self.btn_check_update = QPushButton("Check for Updates")
        self.btn_check_update.setIcon(render_icon("export", 12, COLOR_TEXT_PRIMARY))
        self.btn_check_update.clicked.connect(self._on_manual_check_update)
        ver_row.addWidget(self.btn_check_update)
        l_update.addLayout(ver_row)

        self.cb_auto_update = QCheckBox("Automatically check for updates on startup")
        self.cb_auto_update.setFont(get_body_font(12))
        l_update.addWidget(self.cb_auto_update)

        feed_lbl = QLabel("Update Feed URL (JSON manifest or GitHub Releases URL):")
        feed_lbl.setFont(get_body_font(11))
        feed_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        l_update.addWidget(feed_lbl)

        self.edit_update_url = QLineEdit()
        self.edit_update_url.setPlaceholderText("https://example.com/version.json or GitHub repo release URL")
        self.edit_update_url.setFont(get_body_font(12))
        self.edit_update_url.setStyleSheet(f"padding: 6px; background-color: {COLOR_BG_BASE}; border: 1px solid {COLOR_BORDER_DISTINCT};")
        l_update.addWidget(self.edit_update_url)

        self.lbl_update_status = QLabel("")
        self.lbl_update_status.setFont(get_mono_font(11))
        self.lbl_update_status.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        l_update.addWidget(self.lbl_update_status)

        form_layout.addWidget(card_update)

        scroll.setWidget(container)
        main_layout.addWidget(scroll, stretch=1)

        # Footer Buttons
        footer = QHBoxLayout()
        footer.setSpacing(10)

        btn_defaults = QPushButton("Reset to Defaults")
        btn_defaults.clicked.connect(self._reset_defaults)
        footer.addWidget(btn_defaults)

        footer.addStretch()

        btn_save = QPushButton("Save Preferences")
        btn_save.setObjectName("accentButton")
        btn_save.setMinimumHeight(36)
        btn_save.clicked.connect(self._save_values)
        footer.addWidget(btn_save)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setMinimumHeight(36)
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        main_layout.addLayout(footer)

    def _create_card(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 2px;
                padding: 12px;
            }}
        """)
        return frame

    def _create_key_row(self, label: str, default_key: str, parent_layout: QVBoxLayout) -> KeyBindingEdit:
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFont(get_body_font(12))
        row.addWidget(lbl)
        row.addStretch()

        edit = KeyBindingEdit(default_key)
        row.addWidget(edit)
        parent_layout.addLayout(row)
        return edit

    def _on_theme_toggled(self, theme_id: str, checked: bool):
        if checked:
            apply_theme(theme_id)

    def _load_values(self):
        saved_theme = config.get("theme", "dark_amber")
        saved_theme = THEME_ALIASES.get(saved_theme, saved_theme)
        if saved_theme in self.theme_radios:
            self.theme_radios[saved_theme].setChecked(True)

        ram_gb = config.get("ram_budget_gb", 16)
        self.ram_slider.setValue(ram_gb)
        self.ram_val_lbl.setText(f"{ram_gb} GB")

        self.key_keep.setText(config.get_key_binding("keep"))
        self.key_maybe.setText(config.get_key_binding("maybe", "E"))
        self.key_reject.setText(config.get_key_binding("reject"))
        self.key_prev.setText(config.get_key_binding("prev"))
        self.key_next.setText(config.get_key_binding("next"))

        self.cb_start_zoomed.setChecked(config.get("start_zoomed_in", False))
        lvl = int(config.get("zoom_start_level", 2.0) * 100)
        self.slider_zoom_lvl.setValue(lvl)
        self.lbl_zoom_pct.setText(f"{lvl}%")

        self.cb_sync_pairs.setChecked(config.get("default_sync_pairs", True))
        self.edit_export_dir.setText(config.get("default_export_dir", ""))

        self.cb_auto_update.setChecked(config.get("auto_check_updates", True))
        self.edit_update_url.setText(config.get("update_manifest_url", ""))

    def _browse_export_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Default Export Location")
        if d:
            self.edit_export_dir.setText(d)

    def _save_values(self):
        config.set("theme", current_theme_id)
        config.set("ram_budget_gb", self.ram_slider.value())
        config.set_key_binding("keep", self.key_keep.text().strip() or "W")
        config.set_key_binding("maybe", self.key_maybe.text().strip() or "E")
        config.set_key_binding("reject", self.key_reject.text().strip() or "S")
        config.set_key_binding("prev", self.key_prev.text().strip() or "A")
        config.set_key_binding("next", self.key_next.text().strip() or "D")

        config.set("start_zoomed_in", self.cb_start_zoomed.isChecked())
        config.set("zoom_start_level", self.slider_zoom_lvl.value() / 100.0)
        config.set("default_sync_pairs", self.cb_sync_pairs.isChecked())
        config.set("default_export_dir", self.edit_export_dir.text().strip())

        config.set("auto_check_updates", self.cb_auto_update.isChecked())
        config.set("update_manifest_url", self.edit_update_url.text().strip())

        self.accept()

    def _on_manual_check_update(self):
        url = self.edit_update_url.text().strip()
        if not url:
            QMessageBox.information(
                self, "Configure Update URL",
                "Please enter an Update Feed URL (such as a GitHub Release URL or your hosted version.json link) to check for updates."
            )
            return

        self.btn_check_update.setEnabled(False)
        self.lbl_update_status.setText("Checking for updates...")
        self.update_checker = UpdateCheckWorker(url, self)
        self.update_checker.check_finished.connect(self._on_manual_check_result)
        self.update_checker.start()

    def _on_manual_check_result(self, has_update: bool, info, error_msg: str):
        self.btn_check_update.setEnabled(True)
        if error_msg:
            self.lbl_update_status.setText(f"Error checking update: {error_msg}")
            QMessageBox.warning(self, "Update Check Error", f"Could not check for updates:\n{error_msg}")
        elif has_update and info:
            self.lbl_update_status.setText(f"New version v{info.version} available!")
            dlg = UpdateDialog(info, self)
            dlg.exec()
        else:
            self.lbl_update_status.setText(f"Framed is up to date (v{CURRENT_VERSION}).")
            QMessageBox.information(self, "Up to Date", f"You are running the latest version of Framed (v{CURRENT_VERSION}).")

    def _reset_defaults(self):
        confirm = QMessageBox.question(
            self, "Reset Preferences", "Reset all preferences to initial defaults?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            config.reset_to_defaults()
            apply_theme("dark_amber")
            self._load_values()

    def _on_restart_tour(self):
        config.set("has_completed_tour", False)
        self.restart_tour_requested.emit()
        self.accept()
