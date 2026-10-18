"""Automatic update system for Framed: manifest check, downloader, and Inno Setup silent upgrade."""

import os
import sys
import json
import urllib.request
import urllib.error
import tempfile
import subprocess
import re
from dataclasses import dataclass
from typing import Optional, Tuple
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication
from loupe.config import config

CURRENT_VERSION = "1.3.0-experimental"

@dataclass
class UpdateInfo:
    version: str
    download_url: str
    release_notes: str = ""
    pub_date: str = ""
    is_prerelease: bool = False


def parse_version_tuple(v_str: str) -> Tuple[int, ...]:
    """Parse version string like 'v1.2.3' or 'v1.3.0-experimental' into numeric tuple (1, 3, 0)."""
    cleaned = v_str.strip().lstrip("vV")
    parts = []
    for p in cleaned.split("."):
        m = re.match(r"(\d+)", p.strip())
        if m:
            parts.append(int(m.group(1)))
        else:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def is_newer_version(remote_ver: str, local_ver: str = CURRENT_VERSION) -> bool:
    """Returns True if remote_ver is strictly greater than local_ver."""
    return parse_version_tuple(remote_ver) > parse_version_tuple(local_ver)


def fetch_update_info(manifest_url: str, include_prereleases: Optional[bool] = None) -> UpdateInfo:
    """Fetch update information from a JSON URL, GitHub Releases API, or local file."""
    if not manifest_url:
        raise ValueError("No update manifest URL configured.")

    if include_prereleases is None:
        include_prereleases = bool(config.get("experimental_mode", False))

    effective_url = manifest_url.strip()
    if include_prereleases and effective_url.endswith("/releases/latest"):
        effective_url = effective_url[:-len("/latest")]

    # Support local testing file path
    if os.path.exists(effective_url):
        with open(effective_url, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        req = urllib.request.Request(
            effective_url,
            headers={"User-Agent": f"Framed-Workstation/{CURRENT_VERSION}"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

    # If GitHub /releases endpoint returns a list of releases (used when experimental/pre-releases enabled)
    if isinstance(data, list):
        chosen = None
        for rel in data:
            if not isinstance(rel, dict) or rel.get("draft", False):
                continue
            if not include_prereleases and rel.get("prerelease", False):
                continue
            chosen = rel
            break
        if not chosen:
            raise ValueError("No matching releases found in repository.")
        data = chosen

    # GitHub Releases API format handling
    if isinstance(data, dict) and "tag_name" in data and "assets" in data:
        ver = data.get("tag_name", "").lstrip("vV")
        notes = data.get("body", "No release notes provided.")
        is_pre = bool(data.get("prerelease", False))
        download_url = ""
        for asset in data.get("assets", []):
            name = asset.get("name", "").lower()
            if name.endswith(".exe"):
                download_url = asset.get("browser_download_url", "")
                break
        if not download_url:
            raise ValueError("No executable installer (.exe) found in release assets.")
        return UpdateInfo(version=ver, download_url=download_url, release_notes=notes, is_prerelease=is_pre)

    # Standard Framed manifest format: { "version": "1.1.0", "download_url": "...", "release_notes": "..." }
    ver = data.get("version", "")
    dl_url = data.get("download_url", "")
    notes = data.get("release_notes", "")
    date = data.get("release_date", "")
    is_pre = bool(data.get("prerelease", False))

    if not ver or not dl_url:
        raise ValueError("Invalid manifest: 'version' and 'download_url' are required.")

    return UpdateInfo(version=ver, download_url=dl_url, release_notes=notes, pub_date=date, is_prerelease=is_pre)


class UpdateCheckWorker(QThread):
    """Background worker to check for updates without freezing the GUI."""
    check_finished = Signal(bool, object, str)  # (has_update, UpdateInfo or None, error_message)

    def __init__(self, manifest_url: str, parent=None, include_prereleases: Optional[bool] = None):
        super().__init__(parent)
        self.manifest_url = manifest_url.strip()
        self.include_prereleases = include_prereleases

    def run(self):
        if not self.manifest_url:
            self.check_finished.emit(False, None, "No update feed URL configured.")
            return
        try:
            info = fetch_update_info(self.manifest_url, include_prereleases=self.include_prereleases)
            has_update = is_newer_version(info.version, CURRENT_VERSION)
            self.check_finished.emit(has_update, info, "")
        except Exception as e:
            self.check_finished.emit(False, None, str(e))


class UpdateDownloadWorker(QThread):
    """Background worker to download the update installer with progress reporting."""
    progress_changed = Signal(int, int, float)  # (downloaded_bytes, total_bytes, percent)
    download_finished = Signal(bool, str, str)  # (success, file_path, error_message)

    def __init__(self, download_url: str, parent=None):
        super().__init__(parent)
        self.download_url = download_url.strip()
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            dest_dir = tempfile.gettempdir()
            dest_path = os.path.join(dest_dir, "Framed-Setup-Update.exe")

            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": f"Framed-Workstation/{CURRENT_VERSION}"}
            )

            with urllib.request.urlopen(req, timeout=30) as response, open(dest_path, "wb") as out_file:
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 65536

                while not self._is_cancelled:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    pct = (downloaded / total_size * 100.0) if total_size > 0 else 0.0
                    self.progress_changed.emit(downloaded, total_size, pct)

            if self._is_cancelled:
                self.download_finished.emit(False, "", "Download cancelled.")
                return

            self.download_finished.emit(True, dest_path, "")
        except Exception as e:
            self.download_finished.emit(False, "", str(e))


def apply_update_and_restart(installer_path: str) -> None:
    """Execute Inno Setup installer in silent mode with restart flags, then exit."""
    if not os.path.exists(installer_path):
        raise FileNotFoundError(f"Installer not found at: {installer_path}")

    # Launch installer with Inno Setup flags:
    # /SILENT : Shows minimal progress dialog without wizard pages
    # /CLOSEAPPLICATIONS : Instructs installer to close Framed processes cleanly
    # /RESTARTAPPLICATIONS : Automatically launches Framed after update completes
    cmd = [
        installer_path,
        "/SILENT",
        "/SUPPRESSMSGBOXES",
        "/CLOSEAPPLICATIONS",
        "/RESTARTAPPLICATIONS"
    ]
    subprocess.Popen(cmd, creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0)
    QApplication.quit()
    sys.exit(0)
