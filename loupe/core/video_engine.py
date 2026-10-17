"""Video engine for Framed: metadata extraction, proxy compression (1GB -> ~250MB), and proxy workers."""

import os
import cv2
from typing import Dict, Any, Optional, List
from PySide6.QtCore import QThread, Signal
from loupe.config import get_app_dir
from loupe.models import PhotoItem

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mts", ".m2ts"}

def is_video_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in VIDEO_EXTENSIONS


def get_video_metadata(filepath: str) -> Dict[str, Any]:
    """Extract resolution, duration, FPS, and size from a video file."""
    meta = {
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "duration_seconds": 0.0,
        "total_frames": 0,
        "file_size": 0,
        "formatted_duration": "00:00",
        "resolution_label": "Unknown",
    }
    if not os.path.exists(filepath):
        return meta

    try:
        meta["file_size"] = os.path.getsize(filepath)
        cap = cv2.VideoCapture(filepath)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            meta["width"] = w
            meta["height"] = h
            meta["fps"] = round(fps, 2) if fps > 0 else 24.0
            meta["total_frames"] = total_frames

            if fps > 0 and total_frames > 0:
                dur = total_frames / fps
                meta["duration_seconds"] = round(dur, 2)
                mins = int(dur // 60)
                secs = int(dur % 60)
                meta["formatted_duration"] = f"{mins:02d}:{secs:02d}"

            if w >= 3800:
                meta["resolution_label"] = "4K UHD"
            elif w >= 1900:
                meta["resolution_label"] = "1080p FHD"
            elif w >= 1200:
                meta["resolution_label"] = "720p HD"
            elif w > 0:
                meta["resolution_label"] = f"{w}x{h}"

            cap.release()
    except Exception as e:
        print(f"Error reading video metadata for {filepath}: {e}")

    return meta


def get_proxy_dir(project_id: str) -> str:
    """Return local storage path for session video proxies."""
    p_dir = os.path.join(get_app_dir(), "video_proxies", project_id)
    os.makedirs(p_dir, exist_ok=True)
    return p_dir


def compress_video_to_proxy(src_path: str, dest_path: str, target_max_width: int = 1280, progress_cb=None) -> str:
    """Compress video clip to responsive proxy target (~250MB per 1GB source)."""
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024:
        return dest_path

    # Prefer ffmpeg if available on PATH so audio tracks are preserved
    import shutil
    import subprocess
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            cmd = [
                ffmpeg_bin, "-y", "-i", src_path,
                "-vf", f"scale='min({target_max_width},iw)':-2",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
                "-c:a", "aac", "-b:a", "128k",
                dest_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags, timeout=300)
            if res.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024:
                if progress_cb:
                    progress_cb(1.0)
                return dest_path
        except Exception:
            pass

    cap = cv2.VideoCapture(src_path)
    if not cap.isOpened():
        return src_path

    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    orig_fps = float(cap.get(cv2.CAP_PROP_FPS))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if orig_w <= 0 or orig_h <= 0:
        cap.release()
        return src_path

    # Determine target resolution maintaining aspect ratio
    if orig_w > target_max_width:
        scale = target_max_width / float(orig_w)
        target_w = target_max_width
        target_h = int(orig_h * scale)
    else:
        target_w = orig_w
        target_h = orig_h

    # Ensure even dimensions for video codecs
    target_w = target_w - (target_w % 2)
    target_h = target_h - (target_h % 2)

    target_fps = min(orig_fps if orig_fps > 0 else 24.0, 30.0)

    # Use standard MP4V fourcc
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(dest_path, fourcc, target_fps, (target_w, target_h))

    frame_count = 0
    # Step frame if source FPS is high (e.g. 60 or 120fps -> sample to 30fps)
    frame_step = max(1, int(round(orig_fps / target_fps))) if (orig_fps > target_fps) else 1

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_step == 0:
            if (target_w, target_h) != (orig_w, orig_h):
                resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
            else:
                resized = frame
            out.write(resized)

        frame_count += 1
        if progress_cb and total_frames > 0 and frame_count % 30 == 0:
            progress_cb(min(1.0, frame_count / total_frames))

    cap.release()
    out.release()
    return dest_path


class VideoProxyQueue(QThread):
    """Background worker that generates proxies for all session clips without blocking."""
    clip_proxy_ready = Signal(str, str)  # (item_id, proxy_path)
    overall_progress = Signal(int, int)  # (completed_count, total_count)
    all_proxies_complete = Signal()

    def __init__(self, project_id: str, items: List[PhotoItem], parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.items = items
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        proxy_dir = get_proxy_dir(self.project_id)
        total = len(self.items)

        for idx, item in enumerate(self.items):
            if self._is_cancelled:
                break

            # If already has proxy and exists, notify immediately
            if item.proxy_path and os.path.exists(item.proxy_path):
                self.clip_proxy_ready.emit(item.id, item.proxy_path)
                self.overall_progress.emit(idx + 1, total)
                continue

            src = item.primary_path
            if not src or not os.path.exists(src):
                self.overall_progress.emit(idx + 1, total)
                continue

            stem = os.path.splitext(os.path.basename(src))[0]
            dest_name = f"{item.id[:8]}_{stem}_proxy.mp4"
            dest_path = os.path.join(proxy_dir, dest_name)

            try:
                proxy_path = compress_video_to_proxy(src, dest_path)
                item.proxy_path = proxy_path
                self.clip_proxy_ready.emit(item.id, proxy_path)
            except Exception as e:
                print(f"Failed to generate proxy for {src}: {e}")
                # Fallback to original
                item.proxy_path = src
                self.clip_proxy_ready.emit(item.id, src)

            self.overall_progress.emit(idx + 1, total)

        self.all_proxies_complete.emit()
