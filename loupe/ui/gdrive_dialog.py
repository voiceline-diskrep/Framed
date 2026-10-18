"""Google Drive OAuth setup guide and interactive Cloud Folder Browser / Ingest modal with full telemetry."""

import webbrowser
from typing import Optional, List, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QProgressBar, QFrame, QMessageBox,
    QInputDialog, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal

from loupe.core.gdrive import (
    GoogleDriveClient, GDriveDownloadWorker, parse_gdrive_folder_id, format_eta
)
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BORDER_SUBTLE,
    COLOR_BORDER_DISTINCT, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_STATUS_KEPT, COLOR_STATUS_REJECTED,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon


class GDriveGuideDialog(QDialog):
    """Step-by-step 1-minute guide to getting a Google Cloud OAuth 2.0 client_secret.json."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Google Drive OAuth 2.0 Setup Guide")
        self.setMinimumSize(540, 420)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        badge = QLabel("EXPERIMENTAL • GOOGLE CLOUD OAUTH 2.0")
        badge.setFont(get_mono_font(10, bold=True))
        badge.setStyleSheet(f"color: {COLOR_ACCENT}; letter-spacing: 1px;")
        layout.addWidget(badge)

        title = QLabel("1-Minute Google Drive API Setup")
        title.setFont(get_display_font(18, bold=True))
        layout.addWidget(title)

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
                padding: 16px;
            }}
        """)
        c_layout = QVBoxLayout(card)
        c_layout.setSpacing(10)

        steps_text = (
            "<b>Step 1:</b> Open the Google Cloud Console and create or select a project.<br><br>"
            "<b>Step 2:</b> Enable the <b>Google Drive API</b> in <i>APIs &amp; Services → Library</i>.<br><br>"
            "<b>Step 3:</b> In <i>APIs &amp; Services → OAuth consent screen</i>, choose <b>External</b> "
            "(or Internal) and add your Google email under <b>Test users</b>.<br><br>"
            "<b>Step 4:</b> Go to <i>APIs &amp; Services → Credentials</i>, click "
            "<b>+ Create Credentials → OAuth client ID</b>, choose <b>Desktop app</b>, and click <b>Create</b>.<br><br>"
            "<b>Step 5:</b> Click <b>Download JSON</b> (or copy the Client ID &amp; Client Secret) and load it into Framed Settings!"
        )
        lbl = QLabel(steps_text)
        lbl.setFont(get_body_font(12))
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; line-height: 1.45;")
        c_layout.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_drive_api = QPushButton("1. Enable Google Drive API")
        btn_drive_api.setFont(get_body_font(11, bold=True))
        btn_drive_api.clicked.connect(
            lambda: webbrowser.open("https://console.cloud.google.com/apis/library/drive.googleapis.com")
        )
        btn_row.addWidget(btn_drive_api)

        btn_creds = QPushButton("2. Open Credentials Console")
        btn_creds.setFont(get_body_font(11, bold=True))
        btn_creds.clicked.connect(
            lambda: webbrowser.open("https://console.cloud.google.com/apis/credentials")
        )
        btn_row.addWidget(btn_creds)
        c_layout.addLayout(btn_row)

        layout.addWidget(card, stretch=1)

        footer = QHBoxLayout()
        footer.addStretch()
        btn_close = QPushButton("Got It")
        btn_close.setMinimumHeight(36)
        btn_close.setObjectName("accentButton")
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        layout.addLayout(footer)


class _FolderListWorker(QThread):
    """Background worker to fetch subfolders without blocking UI."""
    folders_loaded = Signal(str, str, list)  # (folder_id, folder_name, subfolders_list)
    load_failed = Signal(str)

    def __init__(self, folder_id: str, client: GoogleDriveClient, parent=None):
        super().__init__(parent)
        self.folder_id = folder_id
        self.client = client

    def run(self):
        try:
            meta = self.client.get_folder_metadata(self.folder_id)
            fname = meta.get("name") or ("My Drive" if self.folder_id == "root" else self.folder_id)
            folders = self.client.list_folders(self.folder_id)
            self.folders_loaded.emit(self.folder_id, fname, folders)
        except Exception as e:
            self.load_failed.emit(str(e))


class GDriveBrowserDialog(QDialog):
    """
    Interactive Google Drive folder browser & cloud downloader dialog.
    mode="import": Browse/paste a Drive folder and download its photos/videos to local cache with full telemetry.
    mode="select_folder": Browse/paste a Drive folder to use as the destination parent for exports.
    """

    def __init__(self, mode: str = "import", media_mode: str = "photo", parent=None):
        super().__init__(parent)
        self.mode = mode  # "import" or "select_folder"
        self.media_mode = media_mode  # "photo" or "video"
        self.client = GoogleDriveClient()

        self.current_folder_id: str = "root"
        self.current_folder_name: str = "My Drive"
        self.nav_stack: List[Tuple[str, str]] = []  # Stack of (folder_id, folder_name)

        self.selected_folder_id: str = "root"
        self.selected_folder_name: str = "My Drive"
        self.downloaded_local_dir: str = ""
        self.downloaded_count: int = 0

        self.list_worker: Optional[_FolderListWorker] = None
        self.dl_worker: Optional[GDriveDownloadWorker] = None

        title_str = (
            f"Import {self.media_mode.capitalize()} Shoot from Google Drive"
            if self.mode == "import"
            else "Select Google Drive Destination Folder"
        )
        self.setWindowTitle(title_str)
        self.setMinimumSize(580, 480)
        self.setStyleSheet(f"background-color: {COLOR_BG_BASE};")

        self._init_ui()
        self._fit_to_available_screen()
        self._navigate_to("root", push_stack=False)

    def _fit_to_available_screen(self):
        try:
            screen = self.screen() or QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                target_w = min(680, max(580, avail.width() - 40))
                target_h = min(620, max(480, avail.height() - 60))
                self.resize(target_w, target_h)
                x = avail.x() + (avail.width() - target_w) // 2
                y = avail.y() + max(10, (avail.height() - target_h) // 2)
                self.move(x, y)
        except Exception:
            pass

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # Header
        top_row = QHBoxLayout()
        v_head = QVBoxLayout()
        v_head.setSpacing(2)
        tag = QLabel("EXPERIMENTAL • GOOGLE DRIVE CLOUD ENGINE")
        tag.setFont(get_mono_font(10, bold=True))
        tag.setStyleSheet(f"color: {COLOR_ACCENT}; letter-spacing: 1px;")
        v_head.addWidget(tag)

        h_lbl = QLabel(
            f"Import {self.media_mode.capitalize()}s from Google Drive"
            if self.mode == "import"
            else "Choose Google Drive Export Folder"
        )
        h_lbl.setFont(get_display_font(17, bold=True))
        v_head.addWidget(h_lbl)
        top_row.addLayout(v_head)
        top_row.addStretch()

        email = self.client.get_user_email()
        if email:
            acct_badge = QLabel(f"● {email}")
            acct_badge.setFont(get_mono_font(10, bold=True))
            acct_badge.setStyleSheet(
                f"color: {COLOR_STATUS_KEPT}; background: {COLOR_BG_ELEVATED}; padding: 4px 10px; border-radius: 3px;"
            )
            top_row.addWidget(acct_badge)

        layout.addLayout(top_row)

        # Direct URL / Folder ID bar
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Paste a Google Drive folder link or ID (or browse folders below)...")
        self.url_edit.setFont(get_body_font(12))
        self.url_edit.setMinimumHeight(36)
        self.url_edit.setStyleSheet(f"""
            QLineEdit {{
                padding: 0 10px;
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
        """)
        url_row.addWidget(self.url_edit, stretch=1)

        btn_go = QPushButton("Open Link")
        btn_go.setFont(get_body_font(11, bold=True))
        btn_go.setMinimumHeight(36)
        btn_go.clicked.connect(self._on_open_link_clicked)
        url_row.addWidget(btn_go)
        layout.addLayout(url_row)

        # Navigation bar (Up, Breadcrumb, New Folder)
        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)

        self.btn_up = QPushButton("Up")
        self.btn_up.setIcon(render_icon("arrow_left", 12, COLOR_TEXT_PRIMARY))
        self.btn_up.setFont(get_body_font(11, bold=True))
        self.btn_up.setEnabled(False)
        self.btn_up.clicked.connect(self._on_up_clicked)
        nav_row.addWidget(self.btn_up)

        self.lbl_breadcrumb = QLabel("📁 My Drive")
        self.lbl_breadcrumb.setFont(get_mono_font(11, bold=True))
        self.lbl_breadcrumb.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")
        nav_row.addWidget(self.lbl_breadcrumb, stretch=1)

        if self.mode == "select_folder":
            self.btn_new_folder = QPushButton("+ New Folder")
            self.btn_new_folder.setFont(get_body_font(11, bold=True))
            self.btn_new_folder.clicked.connect(self._on_create_folder)
            nav_row.addWidget(self.btn_new_folder)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setFont(get_body_font(11))
        self.btn_refresh.clicked.connect(lambda: self._navigate_to(self.current_folder_id, push_stack=False))
        nav_row.addWidget(self.btn_refresh)

        layout.addLayout(nav_row)

        # Folder list widget
        self.folder_list = QListWidget()
        self.folder_list.setFont(get_body_font(12))
        self.folder_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 4px;
                padding: 6px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QListWidget::item {{
                padding: 8px 10px;
                border-radius: 3px;
            }}
            QListWidget::item:selected {{
                background-color: {COLOR_BG_ELEVATED};
                color: {COLOR_ACCENT};
                border: 1px solid {COLOR_ACCENT};
            }}
            QListWidget::item:hover {{
                background-color: {COLOR_BG_ELEVATED};
            }}
        """)
        self.folder_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.folder_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.folder_list, stretch=1)

        hint_lbl = QLabel("Tip: Double-click a folder to open it, or highlight a folder and click the action button below.")
        hint_lbl.setFont(get_body_font(11))
        hint_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        layout.addWidget(hint_lbl)

        # Telemetry Progress Bar Frame (used during import download)
        self.telemetry_frame = QFrame()
        self.telemetry_frame.setStyleSheet(
            f"background-color: {COLOR_BG_ELEVATED}; border: 1px solid {COLOR_BORDER_DISTINCT}; border-radius: 4px; padding: 12px;"
        )
        self.telemetry_frame.setVisible(self.mode == "import")
        tf_layout = QVBoxLayout(self.telemetry_frame)
        tf_layout.setContentsMargins(6, 4, 6, 4)
        tf_layout.setSpacing(6)

        top_tele = QHBoxLayout()
        self.lbl_tele_file = QLabel("Ready to download cloud shoot to local cache.")
        self.lbl_tele_file.setFont(get_mono_font(11, bold=True))
        self.lbl_tele_file.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")
        top_tele.addWidget(self.lbl_tele_file, stretch=1)

        self.lbl_tele_pct = QLabel("0%")
        self.lbl_tele_pct.setFont(get_mono_font(11, bold=True))
        self.lbl_tele_pct.setStyleSheet(f"color: {COLOR_ACCENT};")
        top_tele.addWidget(self.lbl_tele_pct)
        tf_layout.addLayout(top_tele)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        tf_layout.addWidget(self.progress_bar)

        bot_tele = QHBoxLayout()
        self.lbl_tele_stats = QLabel("Speed: -- MB/s  •  ETA: --")
        self.lbl_tele_stats.setFont(get_mono_font(10))
        self.lbl_tele_stats.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        bot_tele.addWidget(self.lbl_tele_stats)

        bot_tele.addStretch()

        self.lbl_tele_count = QLabel("0 / 0 files")
        self.lbl_tele_count.setFont(get_mono_font(10, bold=True))
        self.lbl_tele_count.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        bot_tele.addWidget(self.lbl_tele_count)
        tf_layout.addLayout(bot_tele)

        layout.addWidget(self.telemetry_frame)

        # Footer buttons
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setMinimumHeight(38)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        footer.addWidget(self.btn_cancel)

        footer.addStretch()

        action_label = (
            "Download & Import Folder"
            if self.mode == "import"
            else "Select This Folder"
        )
        self.btn_action = QPushButton(action_label)
        self.btn_action.setObjectName("accentButton")
        self.btn_action.setIcon(render_icon("cloud", 14, "#FFFFFF"))
        self.btn_action.setMinimumHeight(38)
        self.btn_action.setStyleSheet("""
            QPushButton {
                background-color: #D97706;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 13px;
                border: 1px solid #F59E0B;
                border-radius: 4px;
                padding: 0 20px;
            }
            QPushButton:hover {
                background-color: #F59E0B;
                color: #FFFFFF;
            }
            QPushButton:disabled {
                background-color: #2D2214;
                color: #5E6672;
                border-color: #3B414B;
            }
        """)
        self.btn_action.clicked.connect(self._on_action_clicked)
        footer.addWidget(self.btn_action)

        layout.addLayout(footer)

    def _on_open_link_clicked(self):
        raw = self.url_edit.text().strip()
        if not raw:
            return
        try:
            fid = parse_gdrive_folder_id(raw)
            self._navigate_to(fid, push_stack=True)
        except Exception as e:
            QMessageBox.warning(self, "Invalid Google Drive Link", str(e))

    def _navigate_to(self, folder_id: str, push_stack: bool = True):
        if push_stack and self.current_folder_id:
            self.nav_stack.append((self.current_folder_id, self.current_folder_name))
        self.btn_up.setEnabled(len(self.nav_stack) > 0)
        self.folder_list.clear()
        loading_item = QListWidgetItem("Loading folders from Google Drive...")
        loading_item.setFlags(Qt.NoItemFlags)
        self.folder_list.addItem(loading_item)

        self.list_worker = _FolderListWorker(folder_id, self.client, self)
        self.list_worker.folders_loaded.connect(self._on_folders_loaded)
        self.list_worker.load_failed.connect(self._on_folders_failed)
        self.list_worker.start()

    def _on_folders_loaded(self, folder_id: str, folder_name: str, folders: list):
        self.current_folder_id = folder_id
        self.current_folder_name = folder_name
        self.selected_folder_id = folder_id
        self.selected_folder_name = folder_name
        self.lbl_breadcrumb.setText(f"📁 {folder_name}")

        self.folder_list.clear()
        if not folders:
            empty_item = QListWidgetItem("(No subfolders inside this folder — click below to use this folder)")
            empty_item.setFlags(Qt.NoItemFlags)
            self.folder_list.addItem(empty_item)
            return

        for f in folders:
            item = QListWidgetItem(render_icon("folder", 14, COLOR_ACCENT), f.get("name", "Untitled"))
            item.setData(Qt.UserRole, f.get("id"))
            item.setData(Qt.UserRole + 1, f.get("name", "Untitled"))
            self.folder_list.addItem(item)

    def _on_folders_failed(self, err: str):
        self.folder_list.clear()
        err_item = QListWidgetItem(f"Error loading Drive folder: {err}")
        err_item.setFlags(Qt.NoItemFlags)
        self.folder_list.addItem(err_item)

    def _on_up_clicked(self):
        if self.nav_stack:
            prev_id, _ = self.nav_stack.pop()
            self.btn_up.setEnabled(len(self.nav_stack) > 0)
            self._navigate_to(prev_id, push_stack=False)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        fid = item.data(Qt.UserRole)
        if fid:
            self._navigate_to(fid, push_stack=True)

    def _on_selection_changed(self):
        items = self.folder_list.selectedItems()
        if items:
            fid = items[0].data(Qt.UserRole)
            fname = items[0].data(Qt.UserRole + 1)
            if fid:
                self.selected_folder_id = fid
                self.selected_folder_name = fname
                return
        self.selected_folder_id = self.current_folder_id
        self.selected_folder_name = self.current_folder_name

    def _on_create_folder(self):
        name, ok = QInputDialog.getText(self, "New Google Drive Folder", "Folder name:")
        if ok and name.strip():
            try:
                created = self.client.create_folder(name.strip(), self.current_folder_id)
                self._navigate_to(self.current_folder_id, push_stack=False)
                self.selected_folder_id = created["id"]
                self.selected_folder_name = created["name"]
            except Exception as e:
                QMessageBox.warning(self, "Create Folder Error", str(e))

    def _on_action_clicked(self):
        # If user pasted a link in url_edit and didn't click Open Link yet, honor it
        raw_url = self.url_edit.text().strip()
        if raw_url:
            try:
                parsed_id = parse_gdrive_folder_id(raw_url)
                if parsed_id != self.current_folder_id and not self.folder_list.selectedItems():
                    self.selected_folder_id = parsed_id
                    self.selected_folder_name = f"Drive_{parsed_id[:8]}"
            except Exception as e:
                QMessageBox.warning(self, "Invalid Link", str(e))
                return

        if self.mode == "select_folder":
            self.accept()
            return

        # Import mode: start downloading files from selected_folder_id with full telemetry
        self.btn_action.setEnabled(False)
        self.folder_list.setEnabled(False)
        self.url_edit.setEnabled(False)
        self.btn_cancel.setText("Cancel Download")
        self.lbl_tele_file.setText(f"Connecting to '{self.selected_folder_name}'...")

        self.dl_worker = GDriveDownloadWorker(
            folder_id=self.selected_folder_id,
            media_mode=self.media_mode,
            client=self.client,
            parent=self
        )
        self.dl_worker.telemetry_update.connect(self._on_download_telemetry)
        self.dl_worker.download_finished.connect(self._on_download_finished)
        self.dl_worker.download_failed.connect(self._on_download_failed)
        self.dl_worker.start()

    def _on_download_telemetry(
        self, completed: int, total: int, pct: float, speed_mb_s: float, eta_sec: float, cur_file: str
    ):
        self.progress_bar.setValue(int(round(pct)))
        self.lbl_tele_pct.setText(f"{pct:.1f}%")
        self.lbl_tele_file.setText(f"Downloading: {cur_file}")
        self.lbl_tele_stats.setText(f"Speed: {speed_mb_s:.2f} MB/s  •  ETA: {format_eta(eta_sec)}")
        self.lbl_tele_count.setText(f"{completed} / {total} files")

    def _on_download_finished(self, local_dir: str, folder_name: str, count: int):
        self.downloaded_local_dir = local_dir
        self.selected_folder_name = folder_name
        self.downloaded_count = count
        self.progress_bar.setValue(100)
        self.lbl_tele_pct.setText("100%")
        self.lbl_tele_file.setText(f"✓ Downloaded {count} files to local workspace cache!")
        self.lbl_tele_file.setStyleSheet(f"color: {COLOR_STATUS_KEPT};")
        self.accept()

    def _on_download_failed(self, err: str):
        self.btn_action.setEnabled(True)
        self.folder_list.setEnabled(True)
        self.url_edit.setEnabled(True)
        self.btn_cancel.setText("Cancel")
        self.lbl_tele_file.setText(f"Error: {err}")
        self.lbl_tele_file.setStyleSheet(f"color: {COLOR_STATUS_REJECTED};")
        QMessageBox.warning(self, "Google Drive Import Failed", err)

    def _on_cancel_clicked(self):
        if self.dl_worker and self.dl_worker.isRunning():
            self.dl_worker.cancel()
            self.dl_worker.wait(1500)
        self.reject()
