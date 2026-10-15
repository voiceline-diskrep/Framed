"""Dedicated video culling & review workstation view: hardware playback, zero RAM preloading, W/S/X decisions, and uncompressed toggle."""

import os
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSlider, QStackedWidget, QMessageBox, QCheckBox, QMenu, QDialog
)
from PySide6.QtCore import Qt, Signal, QUrl, QTime
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from loupe.models import Project, PhotoItem
from loupe.storage import storage
from loupe.core.video_engine import get_video_metadata, VideoProxyQueue
from loupe.ui.finish_session_dialog import FinishSessionDialog
from loupe.ui.theme import (
    COLOR_BG_BASE, COLOR_BG_SURFACE, COLOR_BG_ELEVATED, COLOR_BG_HOVER,
    COLOR_BORDER_SUBTLE, COLOR_BORDER_DISTINCT, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_ACCENT,
    COLOR_STATUS_KEPT, COLOR_STATUS_REJECTED,
    get_display_font, get_body_font, get_mono_font
)
from loupe.ui.icons import render_icon

class VideoReviewView(QWidget):
    """Utilitarian video review interface with fast switching, no RAM load, and proxy/original toggle."""
    back_to_dashboard = Signal()
    export_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Optional[Project] = None
        self.current_item: Optional[PhotoItem] = None
        self.view_uncompressed: bool = False
        self.proxy_queue: Optional[VideoProxyQueue] = None

        self._init_player()
        self._init_ui()

    def _init_player(self):
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.8)

        self.player.positionChanged.connect(self._on_player_position_changed)
        self.player.durationChanged.connect(self._on_player_duration_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Top Header Bar
        header = QFrame()
        header.setFixedHeight(54)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border-bottom: 1px solid {COLOR_BORDER_DISTINCT};
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 8, 20, 8)
        h_layout.setSpacing(14)

        # Back to Dashboard
        self.btn_back = QPushButton(" Dashboard")
        self.btn_back.setIcon(render_icon("arrow_left", 14, COLOR_TEXT_PRIMARY))
        self.btn_back.setStyleSheet(f"border: 1px solid {COLOR_BORDER_SUBTLE}; padding: 6px 12px;")
        self.btn_back.clicked.connect(self._confirm_exit_to_dashboard)
        h_layout.addWidget(self.btn_back)

        # Finish Session (Green) Button
        self.btn_finish = QPushButton(" Finish Session")
        self.btn_finish.setObjectName("finishButton")
        self.btn_finish.setIcon(render_icon("check", 14, "#FFFFFF"))
        self.btn_finish.clicked.connect(self._handle_finish_session)
        self.btn_finish.setVisible(False)
        h_layout.addWidget(self.btn_finish)

        # Mode Badge
        mode_badge = QLabel("VIDEO SORT")
        mode_badge.setFont(get_mono_font(10, bold=True))
        mode_badge.setStyleSheet(f"color: {COLOR_ACCENT}; background-color: #2D2214; padding: 4px 8px; border: 1px solid #754B1A; border-radius: 2px;")
        h_layout.addWidget(mode_badge)

        # Session & Clip counter
        self.lbl_title = QLabel("Session Title")
        self.lbl_title.setFont(get_display_font(14, bold=True))
        h_layout.addWidget(self.lbl_title)

        self.lbl_counter = QLabel("Clip 0 / 0")
        self.lbl_counter.setFont(get_mono_font(12))
        self.lbl_counter.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        h_layout.addWidget(self.lbl_counter)

        h_layout.addStretch()

        # Options: View with No Compression Toggle
        self.cb_no_compression = QCheckBox("View with No Compression")
        self.cb_no_compression.setFont(get_body_font(12))
        self.cb_no_compression.setToolTip("Toggle between fast ~250MB proxy and original full-resolution clip")
        self.cb_no_compression.toggled.connect(self._on_no_compression_toggled)
        h_layout.addWidget(self.cb_no_compression)

        # Export Button
        self.btn_export = QPushButton("Export Results")
        self.btn_export.setIcon(render_icon("export", 14, COLOR_TEXT_PRIMARY))
        self.btn_export.setStyleSheet(f"border: 1px solid {COLOR_BORDER_DISTINCT}; padding: 6px 14px;")
        self.btn_export.clicked.connect(lambda: self.export_requested.emit(self.project.id if self.project else ""))
        h_layout.addWidget(self.btn_export)

        main_layout.addWidget(header)

        # 2. Main Content (Video Viewport + Telemetry Panel)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Left: Video Player Area
        player_container = QWidget()
        player_layout = QVBoxLayout(player_container)
        player_layout.setContentsMargins(24, 20, 24, 16)
        player_layout.setSpacing(12)

        # Video Surface Widget
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet(f"background-color: {COLOR_BG_BASE}; border: 1px solid {COLOR_BORDER_DISTINCT}; border-radius: 2px;")
        self.player.setVideoOutput(self.video_widget)
        player_layout.addWidget(self.video_widget, stretch=1)

        # Floating Video Controls Bar
        controls_frame = QFrame()
        controls_frame.setFixedHeight(48)
        controls_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
            }}
        """)
        c_layout = QHBoxLayout(controls_frame)
        c_layout.setContentsMargins(14, 6, 14, 6)
        c_layout.setSpacing(12)

        # Play/Pause Button
        self.btn_play = QPushButton()
        self.btn_play.setIcon(render_icon("arrow_right", 14, COLOR_ACCENT))
        self.btn_play.setFixedSize(32, 32)
        self.btn_play.clicked.connect(self._toggle_playback)
        c_layout.addWidget(self.btn_play)

        # Scrubber Slider
        self.slider_timeline = QSlider(Qt.Horizontal)
        self.slider_timeline.setRange(0, 1000)
        self.slider_timeline.sliderMoved.connect(self._on_seek_slider_moved)
        self.slider_timeline.sliderPressed.connect(lambda: self.player.pause())
        c_layout.addWidget(self.slider_timeline, stretch=1)

        # Timestamp Label
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setFont(get_mono_font(11))
        self.lbl_time.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        c_layout.addWidget(self.lbl_time)

        # Active Stream Badge (Proxy vs Original)
        self.lbl_stream_source = QLabel("PROXY (COMPRESSED)")
        self.lbl_stream_source.setFont(get_mono_font(10, bold=True))
        self.lbl_stream_source.setStyleSheet(f"color: {COLOR_ACCENT}; background-color: #2D2214; padding: 2px 6px; border: 1px solid #754B1A;")
        c_layout.addWidget(self.lbl_stream_source)

        player_layout.addWidget(controls_frame)

        # 3. Decision Action Bar (W, S, X)
        action_bar = QFrame()
        action_bar.setFixedHeight(56)
        action_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border: 1px solid {COLOR_BORDER_DISTINCT};
                border-radius: 3px;
            }}
        """)
        act_layout = QHBoxLayout(action_bar)
        act_layout.setContentsMargins(16, 8, 16, 8)
        act_layout.setSpacing(16)

        # Navigation buttons
        self.btn_prev = QPushButton("Previous [A]")
        self.btn_prev.setIcon(render_icon("arrow_left", 12, COLOR_TEXT_PRIMARY))
        self.btn_prev.clicked.connect(self._prev_clip)
        act_layout.addWidget(self.btn_prev)

        act_layout.addStretch()

        # Decision buttons
        self.btn_select = QPushButton("Selected [W]")
        self.btn_select.setIcon(render_icon("check", 14, "#7BE4A2"))
        self.btn_select.setStyleSheet(f"""
            QPushButton {{
                background-color: #1A3323;
                color: #7BE4A2;
                border: 1px solid {COLOR_STATUS_KEPT};
                font-weight: 700;
                padding: 8px 18px;
            }}
            QPushButton:hover {{
                background-color: #244631;
            }}
        """)
        self.btn_select.clicked.connect(self.mark_selected)
        act_layout.addWidget(self.btn_select)

        self.btn_similar = QPushButton("Similar [S]")
        self.btn_similar.setIcon(render_icon("folder", 14, "#5BC0DE"))
        self.btn_similar.setStyleSheet(f"""
            QPushButton {{
                background-color: #172D3D;
                color: #5BC0DE;
                border: 1px solid #337AB7;
                font-weight: 700;
                padding: 8px 18px;
            }}
            QPushButton:hover {{
                background-color: #204159;
            }}
        """)
        self.btn_similar.clicked.connect(self.mark_similar)
        act_layout.addWidget(self.btn_similar)

        self.btn_unselect = QPushButton("Unselected [X]")
        self.btn_unselect.setIcon(render_icon("cross", 14, COLOR_STATUS_REJECTED))
        self.btn_unselect.setStyleSheet(f"""
            QPushButton {{
                background-color: #331A1D;
                color: #F87171;
                border: 1px solid {COLOR_STATUS_REJECTED};
                font-weight: 700;
                padding: 8px 18px;
            }}
            QPushButton:hover {{
                background-color: #4A2227;
            }}
        """)
        self.btn_unselect.clicked.connect(self.mark_unselected)
        act_layout.addWidget(self.btn_unselect)

        act_layout.addStretch()

        self.btn_next = QPushButton("Next [D]")
        self.btn_next.setIcon(render_icon("arrow_right", 12, COLOR_TEXT_PRIMARY))
        self.btn_next.clicked.connect(self._next_clip)
        act_layout.addWidget(self.btn_next)

        player_layout.addWidget(action_bar)
        body.addWidget(player_container, stretch=1)

        # Right: Video Telemetry Side Panel
        telemetry_panel = QFrame()
        telemetry_panel.setFixedWidth(290)
        telemetry_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SURFACE};
                border-left: 1px solid {COLOR_BORDER_DISTINCT};
            }}
        """)
        t_layout = QVBoxLayout(telemetry_panel)
        t_layout.setContentsMargins(18, 20, 18, 20)
        t_layout.setSpacing(16)

        t_title = QLabel("CLIP TELEMETRY")
        t_title.setFont(get_mono_font(11, bold=True))
        t_title.setStyleSheet(f"color: {COLOR_ACCENT}; letter-spacing: 1px;")
        t_layout.addWidget(t_title)

        # Decision Status Badge
        self.lbl_decision_badge = QLabel("PENDING")
        self.lbl_decision_badge.setFont(get_mono_font(12, bold=True))
        self.lbl_decision_badge.setAlignment(Qt.AlignCenter)
        self.lbl_decision_badge.setFixedHeight(34)
        self.lbl_decision_badge.setStyleSheet(f"background-color: {COLOR_BG_ELEVATED}; color: {COLOR_TEXT_MUTED}; border: 1px solid {COLOR_BORDER_SUBTLE};")
        t_layout.addWidget(self.lbl_decision_badge)

        # Metadata Card
        meta_card = QFrame()
        meta_card.setStyleSheet(f"background-color: {COLOR_BG_ELEVATED}; border: 1px solid {COLOR_BORDER_SUBTLE}; padding: 10px; border-radius: 2px;")
        m_card_layout = QVBoxLayout(meta_card)
        m_card_layout.setSpacing(8)

        self.lbl_clip_name = QLabel("—")
        self.lbl_clip_name.setFont(get_mono_font(12, bold=True))
        self.lbl_clip_name.setWordWrap(True)
        m_card_layout.addWidget(self.lbl_clip_name)

        self.lbl_meta_res = QLabel("Resolution: —")
        self.lbl_meta_res.setFont(get_body_font(11))
        m_card_layout.addWidget(self.lbl_meta_res)

        self.lbl_meta_fps = QLabel("FPS: —")
        self.lbl_meta_fps.setFont(get_body_font(11))
        m_card_layout.addWidget(self.lbl_meta_fps)

        self.lbl_meta_dur = QLabel("Duration: —")
        self.lbl_meta_dur.setFont(get_body_font(11))
        m_card_layout.addWidget(self.lbl_meta_dur)

        self.lbl_meta_size = QLabel("Source Size: —")
        self.lbl_meta_size.setFont(get_body_font(11))
        m_card_layout.addWidget(self.lbl_meta_size)

        self.lbl_proxy_size = QLabel("Proxy Size: —")
        self.lbl_proxy_size.setFont(get_body_font(11))
        self.lbl_proxy_size.setStyleSheet(f"color: {COLOR_ACCENT};")
        m_card_layout.addWidget(self.lbl_proxy_size)

        t_layout.addWidget(meta_card)

        # Quick Key Reference
        keys_card = QFrame()
        keys_card.setStyleSheet(f"background-color: {COLOR_BG_ELEVATED}; border: 1px solid {COLOR_BORDER_SUBTLE}; padding: 10px; border-radius: 2px;")
        k_layout = QVBoxLayout(keys_card)
        k_layout.setSpacing(6)

        k_title = QLabel("KEYS")
        k_title.setFont(get_mono_font(10, bold=True))
        k_title.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        k_layout.addWidget(k_title)

        for key, desc in [("W", "Accept / Selected"), ("S", "Similar / Alternative"), ("X", "Move to Unselected"), ("A / D", "Prev / Next Clip"), ("Space", "Play / Pause")]:
            row = QHBoxLayout()
            klbl = QLabel(key)
            klbl.setFont(get_mono_font(11, bold=True))
            klbl.setStyleSheet(f"color: {COLOR_ACCENT};")
            row.addWidget(klbl)
            dlbl = QLabel(desc)
            dlbl.setFont(get_body_font(11))
            dlbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
            row.addWidget(dlbl)
            row.addStretch()
            k_layout.addLayout(row)

        t_layout.addWidget(keys_card)
        t_layout.addStretch()

        body.addWidget(telemetry_panel)
        main_layout.addLayout(body, stretch=1)

    def load_project(self, project: Project):
        """Load a video project session without preloading into RAM."""
        self.project = project
        self.lbl_title.setText(project.name)

        if not self.project.items:
            self.lbl_counter.setText("No video clips")
            return

        # Start background proxy generation queue
        if self.proxy_queue:
            self.proxy_queue.cancel()
        self.proxy_queue = VideoProxyQueue(self.project.id, self.project.items, self)
        self.proxy_queue.clip_proxy_ready.connect(self._on_clip_proxy_ready)
        self.proxy_queue.start()

        # Load first item
        idx = max(0, min(self.project.current_index, len(self.project.items) - 1))
        self._navigate_to_index(idx)

    def _navigate_to_index(self, index: int):
        if not self.project or not self.project.items:
            return

        if 0 <= index < len(self.project.items):
            self.project.current_index = index
            self.current_item = self.project.items[index]
            storage.save_project(self.project)
            self._display_current_clip()

    def _display_current_clip(self):
        if not self.current_item:
            return

        total = len(self.project.items)
        curr = self.project.current_index + 1
        self.lbl_counter.setText(f"Clip {curr} / {total}")

        # Choose playback source: proxy vs original
        source_to_play = self.current_item.primary_path
        if not self.view_uncompressed and self.current_item.proxy_path and os.path.exists(self.current_item.proxy_path):
            source_to_play = self.current_item.proxy_path
            self.lbl_stream_source.setText("PROXY (~250MB)")
            self.lbl_stream_source.setStyleSheet(f"color: {COLOR_ACCENT}; background-color: #2D2214; padding: 2px 6px; border: 1px solid #754B1A;")
        else:
            self.lbl_stream_source.setText("ORIGINAL (UNCOMPRESSED)")
            self.lbl_stream_source.setStyleSheet("color: #7BE4A2; background-color: #1A3323; padding: 2px 6px; border: 1px solid #2E7D32;")

        # Set media source
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(source_to_play))
        self.player.play()

        # Update telemetry
        meta = get_video_metadata(self.current_item.primary_path)
        self.lbl_clip_name.setText(os.path.basename(self.current_item.primary_path))
        self.lbl_meta_res.setText(f"Resolution: {meta['resolution_label']} ({meta['width']}x{meta['height']})")
        self.lbl_meta_fps.setText(f"FPS: {meta['fps']} fps")
        self.lbl_meta_dur.setText(f"Duration: {meta['formatted_duration']}")
        
        orig_mb = meta['file_size'] / (1024 * 1024)
        self.lbl_meta_size.setText(f"Source Size: {orig_mb:.1f} MB")

        if self.current_item.proxy_path and os.path.exists(self.current_item.proxy_path):
            proxy_mb = os.path.getsize(self.current_item.proxy_path) / (1024 * 1024)
            self.lbl_proxy_size.setText(f"Proxy Size: {proxy_mb:.1f} MB")
        else:
            self.lbl_proxy_size.setText("Proxy: Compressing...")

        self._update_decision_badge()

    def _update_decision_badge(self):
        st = self.current_item.status if self.current_item else "pending"
        if st in ("selected", "kept"):
            self.lbl_decision_badge.setText("✓ SELECTED (ACCEPTED)")
            self.lbl_decision_badge.setStyleSheet("background-color: #1A3323; color: #7BE4A2; border: 1px solid #2E7D32; font-weight: bold;")
        elif st == "similar":
            self.lbl_decision_badge.setText("~ SIMILAR (ALTERNATIVE)")
            self.lbl_decision_badge.setStyleSheet("background-color: #172D3D; color: #5BC0DE; border: 1px solid #337AB7; font-weight: bold;")
        elif st in ("unselected", "rejected"):
            self.lbl_decision_badge.setText("✗ UNSELECTED")
            self.lbl_decision_badge.setStyleSheet(f"background-color: #331A1D; color: #F87171; border: 1px solid {COLOR_STATUS_REJECTED}; font-weight: bold;")
        else:
            self.lbl_decision_badge.setText("PENDING REVIEW")
            self.lbl_decision_badge.setStyleSheet(f"background-color: {COLOR_BG_ELEVATED}; color: {COLOR_TEXT_MUTED}; border: 1px solid {COLOR_BORDER_SUBTLE};")

        all_done = bool(self.project and len(self.project.items) > 0 and self.project.pending_count == 0)
        self.btn_finish.setVisible(all_done)

    def _handle_finish_session(self):
        if not self.project:
            return
        dlg = FinishSessionDialog(self.project, self)
        if dlg.exec() == QDialog.Accepted:
            if dlg.choice == FinishSessionDialog.FINISH_NOW:
                self.player.stop()
                storage.save_project(self.project)
                self.back_to_dashboard.emit()
            elif dlg.choice == FinishSessionDialog.FINISH_AND_EXPORT:
                self.player.stop()
                storage.save_project(self.project)
                self.export_requested.emit(self.project.id)

    def _on_no_compression_toggled(self, checked: bool):
        self.view_uncompressed = checked
        curr_pos = self.player.position()
        self._display_current_clip()
        self.player.setPosition(curr_pos)

    def _on_clip_proxy_ready(self, item_id: str, proxy_path: str):
        if self.current_item and self.current_item.id == item_id:
            if not self.view_uncompressed:
                curr_pos = self.player.position()
                self._display_current_clip()
                self.player.setPosition(curr_pos)

    def mark_selected(self):
        """Action W: Mark current clip as Accepted / Selected and advance."""
        if self.current_item:
            self.current_item.status = "selected"
            self._update_decision_badge()
            self._next_clip()

    def mark_similar(self):
        """Action S: Mark current clip as Similar / Alternative and advance."""
        if self.current_item:
            self.current_item.status = "similar"
            self._update_decision_badge()
            self._next_clip()

    def mark_unselected(self):
        """Action X: Move current clip into the Unselected folder and advance."""
        if self.current_item:
            self.current_item.status = "unselected"
            self._update_decision_badge()
            self._next_clip()

    def _prev_clip(self):
        if self.project and self.project.current_index > 0:
            self._navigate_to_index(self.project.current_index - 1)

    def _next_clip(self):
        if self.project and self.project.current_index < len(self.project.items) - 1:
            self._navigate_to_index(self.project.current_index + 1)

    def _toggle_playback(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlayingState:
            self.btn_play.setIcon(render_icon("settings", 12, COLOR_TEXT_PRIMARY)) # pause representation
        else:
            self.btn_play.setIcon(render_icon("arrow_right", 14, COLOR_ACCENT))

    def _on_player_position_changed(self, position_ms: int):
        dur = self.player.duration()
        if dur > 0:
            self.slider_timeline.blockSignals(True)
            self.slider_timeline.setValue(int((position_ms / dur) * 1000))
            self.slider_timeline.blockSignals(False)

        curr_t = QTime(0, 0).addMSecs(position_ms).toString("mm:ss")
        dur_t = QTime(0, 0).addMSecs(dur).toString("mm:ss")
        self.lbl_time.setText(f"{curr_t} / {dur_t}")

    def _on_player_duration_changed(self, duration_ms: int):
        self._on_player_position_changed(self.player.position())

    def _on_seek_slider_moved(self, value: int):
        dur = self.player.duration()
        if dur > 0:
            target_ms = int((value / 1000.0) * dur)
            self.player.setPosition(target_ms)

    def _confirm_exit_to_dashboard(self):
        self.player.stop()
        if self.proxy_queue:
            self.proxy_queue.cancel()
        self.back_to_dashboard.emit()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_A:
            self._prev_clip()
        elif key == Qt.Key_D:
            self._next_clip()
        elif key == Qt.Key_W:
            self.mark_selected()
        elif key == Qt.Key_S:
            self.mark_similar()
        elif key == Qt.Key_X:
            self.mark_unselected()
        elif key == Qt.Key_Space:
            self._toggle_playback()
        elif key == Qt.Key_Escape:
            self._confirm_exit_to_dashboard()
        elif key == Qt.Key_Left:
            self.player.setPosition(max(0, self.player.position() - 5000))
        elif key == Qt.Key_Right:
            self.player.setPosition(min(self.player.duration(), self.player.position() + 5000))
        elif key == Qt.Key_F11:
            win = self.window()
            if hasattr(win, "toggle_fullscreen"):
                win.toggle_fullscreen()
            event.accept()
        else:
            super().keyPressEvent(event)
