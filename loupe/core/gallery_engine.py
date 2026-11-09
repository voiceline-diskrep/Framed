"""Core backend engines for the FRAMED Gallery System:
- Format identification (RAW, JPEG, PNG/TIFF/WebP)
- Persistent + in-memory Thumbnail Cache
- Photo Import Engine (Computer files/folders + FRAMED Sessions, Copy vs Reference, Duplicate Detection)
- RAW-to-JPEG Conversion Engine (LibRaw/Pillow processing, EXIF preservation, space savings)
- Missing File Recovery Engine (Hash + Size + Metadata verification)
- Duplicate Photo Finder (Cryptographic SHA-256 exact match + Perceptual dHash similarity)
- Gallery Backup Manager (Verified backup with SHA-256 integrity checks)
"""

import os
import shutil
import hashlib
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from PySide6.QtCore import Qt, QThread, Signal, QRectF, QSize
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QLinearGradient, QPainterPath, QPen, QImageReader
)

from loupe.models import GalleryPhoto, GalleryFolder, BackupRecord, Project
from loupe.storage import storage
from loupe.core.decoder import ImageDecoder, RAW_EXTENSIONS, JPEG_EXTENSIONS
from loupe.core.metadata import MetadataExtractor
from loupe.ui.icons import render_icon
from loupe.ui.theme import COLOR_ACCENT, COLOR_BORDER_DISTINCT

OTHER_IMAGE_EXTENSIONS = {".png", ".tif", ".tiff", ".webp", ".bmp"}
ALL_SUPPORTED_GALLERY_EXTENSIONS = RAW_EXTENSIONS | JPEG_EXTENSIONS | OTHER_IMAGE_EXTENSIONS
ALL_GALLERY_EXTS = ALL_SUPPORTED_GALLERY_EXTENSIONS

# In-memory QPixmap cache for Gallery thumbnails
_GALLERY_PIXMAP_CACHE: Dict[str, QPixmap] = {}


def classify_image_format(filepath: str) -> Optional[str]:
    """Returns 'RAW', 'JPEG', 'OTHER', or None if unsupported."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in RAW_EXTENSIONS:
        return "RAW"
    if ext in JPEG_EXTENSIONS:
        return "JPEG"
    if ext in OTHER_IMAGE_EXTENSIONS:
        return "OTHER"
    return None


def compute_file_sha256(filepath: str, max_bytes: int = 0) -> str:
    """Computes cryptographic SHA-256 hash of a file."""
    if not filepath or not os.path.exists(filepath):
        return ""
    h = hashlib.sha256()
    try:
        read_so_far = 0
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
                if max_bytes > 0:
                    read_so_far += len(chunk)
                    if read_so_far >= max_bytes:
                        break
        return h.hexdigest()
    except Exception:
        return ""


def compute_perceptual_dhash(filepath: str) -> str:
    """Computes a 64-bit difference hash (dHash) as a 16-char hex string for visual similarity detection."""
    if not filepath or not os.path.exists(filepath):
        return ""
    try:
        from PIL import Image
        ext = os.path.splitext(filepath)[1].lower()
        if ext in RAW_EXTENSIONS:
            qimg, _ = ImageDecoder.decode_to_qimage(filepath)
            if not qimg or qimg.isNull():
                return ""
            small = qimg.scaled(9, 8, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            bits = 0
            for y in range(8):
                for x in range(8):
                    left = QColor(small.pixel(x, y)).lightness()
                    right = QColor(small.pixel(x + 1, y)).lightness()
                    bits = (bits << 1) | (1 if left > right else 0)
            return f"{bits:016x}"
        else:
            with Image.open(filepath) as img:
                gray = img.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
                pixels = list(gray.getdata())
                bits = 0
                for row in range(8):
                    offset = row * 9
                    for col in range(8):
                        bits = (bits << 1) | (1 if pixels[offset + col] > pixels[offset + col + 1] else 0)
                return f"{bits:016x}"
    except Exception:
        return ""


def hamming_distance_hex(hash1: str, hash2: str) -> int:
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return 64
    try:
        v1 = int(hash1, 16)
        v2 = int(hash2, 16)
        return bin(v1 ^ v2).count("1")
    except Exception:
        return 64


class GalleryThumbnailCache:
    """Generates and caches Gallery photo thumbnails without loading full-res images into memory simultaneously."""

    @staticmethod
    def clear_memory_cache():
        _GALLERY_PIXMAP_CACHE.clear()

    @classmethod
    def get_thumbnail_pixmap(cls, photo: GalleryPhoto, width: int = 240, height: int = 150, radius: int = 8) -> QPixmap:
        cache_key = f"{photo.id}_{width}_{height}_{radius}_{photo.is_missing}"
        if cache_key in _GALLERY_PIXMAP_CACHE:
            return _GALLERY_PIXMAP_CACHE[cache_key]

        path = photo.active_path
        qimg = None

        if path and os.path.exists(path):
            # 1. Check persistent disk thumbnail first
            thumb_file = photo.thumbnail_path
            if not thumb_file:
                thumb_file = os.path.join(storage.gallery_thumbs_dir, f"{photo.id}.jpg")

            if os.path.exists(thumb_file):
                reader = QImageReader(thumb_file)
                qimg = reader.read()

            # 2. Decode and cache to disk if not yet cached
            if not qimg or qimg.isNull():
                try:
                    ext = os.path.splitext(path)[1].lower()
                    if ext not in RAW_EXTENSIONS:
                        reader = QImageReader(path)
                        reader.setAutoTransform(True)
                        qimg = reader.read()
                    if not qimg or qimg.isNull():
                        qimg, _ = ImageDecoder.decode_to_qimage(path)

                    if qimg and not qimg.isNull():
                        # Save a 480px preview on disk for instant future loads
                        preview_scaled = qimg.scaled(480, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        try:
                            os.makedirs(storage.gallery_thumbs_dir, exist_ok=True)
                            preview_scaled.save(thumb_file, "JPG", 85)
                            photo.thumbnail_path = thumb_file
                        except Exception:
                            pass
                except Exception:
                    qimg = None

        if qimg and not qimg.isNull():
            scaled = qimg.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x_off = max(0, (scaled.width() - width) // 2)
            y_off = max(0, (scaled.height() - height) // 2)
            cropped = scaled.copy(x_off, y_off, width, height)

            rounded = QPixmap(width, height)
            rounded.fill(Qt.transparent)
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.Antialiasing, True)
            if radius > 0:
                clip = QPainterPath()
                clip.addRoundedRect(0, 0, width, height, radius, radius)
                painter.setClipPath(clip)
            painter.drawImage(0, 0, cropped)
            painter.end()
            _GALLERY_PIXMAP_CACHE[cache_key] = rounded
            return rounded

        # Fallback placeholder (Missing file or unpreviewable format)
        placeholder = QPixmap(width, height)
        placeholder.fill(Qt.transparent)
        painter = QPainter(placeholder)
        painter.setRenderHint(QPainter.Antialiasing, True)
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, width, height, radius, radius)
        grad = QLinearGradient(0, 0, width, height)
        grad.setColorAt(0, QColor("#20242D"))
        grad.setColorAt(1, QColor("#13151A"))
        painter.fillPath(clip, grad)

        icon_name = "warning" if (photo.is_missing or not os.path.exists(path or "")) else "photo"
        icon_col = "#EF4444" if icon_name == "warning" else COLOR_ACCENT
        ic_sz = min(32, min(width, height) - 8)
        ic_pix = render_icon(icon_name, ic_sz, icon_col).pixmap(ic_sz, ic_sz)
        painter.drawPixmap((width - ic_sz) // 2, (height - ic_sz) // 2, ic_pix)

        painter.setPen(QPen(QColor(COLOR_BORDER_DISTINCT), 1))
        painter.drawRoundedRect(QRectF(0.5, 0.5, width - 1, height - 1), radius, radius)
        painter.end()

        _GALLERY_PIXMAP_CACHE[cache_key] = placeholder
        return placeholder


class GalleryImporter:
    """Synchronous and worker-friendly photo import methods with duplicate detection and RAW/JPEG pairing."""

    @staticmethod
    def scan_paths_for_images(paths: List[str], recursive: bool = True) -> List[str]:
        found: List[str] = []
        seen = set()
        for p in paths:
            if not p or not os.path.exists(p):
                continue
            if os.path.isfile(p):
                if classify_image_format(p) is not None:
                    norm = os.path.normcase(os.path.abspath(p))
                    if norm not in seen:
                        seen.add(norm)
                        found.append(os.path.abspath(p))
            elif os.path.isdir(p):
                if recursive:
                    for root, _, files in os.walk(p):
                        for fn in sorted(files):
                            fp = os.path.join(root, fn)
                            if classify_image_format(fp) is not None:
                                norm = os.path.normcase(os.path.abspath(fp))
                                if norm not in seen:
                                    seen.add(norm)
                                    found.append(os.path.abspath(fp))
                else:
                    for fn in sorted(os.listdir(p)):
                        fp = os.path.join(p, fn)
                        if os.path.isfile(fp) and classify_image_format(fp) is not None:
                            norm = os.path.normcase(os.path.abspath(fp))
                            if norm not in seen:
                                seen.add(norm)
                                found.append(os.path.abspath(fp))
        return found

    @classmethod
    def import_files(
        cls,
        filepaths: List[str],
        copy_to_gallery: bool = False,
        target_folder_id: Optional[str] = None,
        skip_duplicates: bool = True,
        source_session_id: Optional[str] = None,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """Imports a list of image filepaths into Gallery.
        Never moves, overwrites, or deletes original files."""
        detected = len(filepaths)
        imported = 0
        skipped = 0
        errors = 0
        imported_photos: List[GalleryPhoto] = []

        # Index existing active photos for duplicate detection
        existing_paths = set()
        existing_hashes: Dict[str, GalleryPhoto] = {}
        for ep in storage.get_active_gallery_photos():
            if ep.original_path:
                existing_paths.add(os.path.normcase(os.path.abspath(ep.original_path)))
            if ep.managed_path:
                existing_paths.add(os.path.normcase(os.path.abspath(ep.managed_path)))
            if ep.file_hash:
                existing_hashes[ep.file_hash] = ep

        for idx, fp in enumerate(filepaths):
            if progress_callback:
                progress_callback(idx + 1, detected, os.path.basename(fp))

            if not fp or not os.path.exists(fp):
                errors += 1
                continue

            fmt = classify_image_format(fp)
            if fmt is None:
                skipped += 1
                continue

            abs_fp = os.path.abspath(fp)
            norm_fp = os.path.normcase(abs_fp)
            f_hash = compute_file_sha256(abs_fp)

            if skip_duplicates:
                if norm_fp in existing_paths or (f_hash and f_hash in existing_hashes):
                    # If target_folder_id is given and photo already exists, ensure it's associated with target_folder_id
                    if target_folder_id and f_hash in existing_hashes:
                        existing_p = existing_hashes[f_hash]
                        if target_folder_id not in existing_p.folder_ids:
                            existing_p.folder_ids.append(target_folder_id)
                    skipped += 1
                    continue

            try:
                managed_dest = None
                if copy_to_gallery:
                    os.makedirs(storage.gallery_managed_dir, exist_ok=True)
                    base_fn = os.path.basename(abs_fp)
                    candidate = os.path.join(storage.gallery_managed_dir, base_fn)
                    if os.path.exists(candidate):
                        stem, ext_part = os.path.splitext(base_fn)
                        candidate = os.path.join(
                            storage.gallery_managed_dir,
                            f"{stem}_{f_hash[:8] if f_hash else idx}{ext_part}"
                        )
                    shutil.copy2(abs_fp, candidate)
                    managed_dest = candidate

                meta = MetadataExtractor.extract(managed_dest or abs_fp)
                p_hash = compute_perceptual_dhash(managed_dest or abs_fp)
                ext_str = os.path.splitext(abs_fp)[1].upper()

                photo = GalleryPhoto(
                    filename=os.path.basename(abs_fp),
                    original_path=abs_fp,
                    managed_path=managed_dest,
                    is_managed=bool(copy_to_gallery and managed_dest),
                    format_type=fmt,
                    ext=ext_str,
                    size_bytes=int(meta.get("size_bytes", os.path.getsize(abs_fp))),
                    width=int(meta.get("width", 0)),
                    height=int(meta.get("height", 0)),
                    capture_date=meta.get("iso_date", datetime.now().strftime("%Y-%m-%d")),
                    capture_datetime=meta.get("date_taken", "—"),
                    date_source=meta.get("date_source", "import"),
                    folder_ids=[target_folder_id] if target_folder_id else [],
                    camera_make=meta.get("make", "—"),
                    camera_model=meta.get("model", "—"),
                    camera=meta.get("camera", "Unknown Camera"),
                    lens=meta.get("lens", "—"),
                    iso=meta.get("iso", "—"),
                    shutter_speed=meta.get("shutter_speed", "—"),
                    aperture=meta.get("aperture", "—"),
                    focal_length=meta.get("focal_length", "—"),
                    gps_lat=meta.get("gps_lat"),
                    gps_lon=meta.get("gps_lon"),
                    file_hash=f_hash,
                    perceptual_hash=p_hash,
                    source_session_id=source_session_id,
                )

                storage.add_gallery_photo(photo, save_now=False)
                imported_photos.append(photo)
                existing_paths.add(norm_fp)
                if f_hash:
                    existing_hashes[f_hash] = photo
                imported += 1
            except Exception as e:
                print(f"[GalleryImporter] Error importing {fp}: {e}")
                errors += 1

        # Automatically link RAW+JPEG pairs sharing base filename & capture date
        cls._auto_pair_raw_and_jpeg()

        if imported > 0:
            storage.log_gallery_activity("import", f"Imported {imported} photo(s)", save_now=False)
        storage.save()

        return {
            "detected": detected,
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "photos": imported_photos,
        }

    @classmethod
    def import_from_project_session(
        cls,
        project: Project,
        scope: str = "selected",  # "selected", "edited", "all"
        copy_to_gallery: bool = False,
        create_session_folder: bool = True,
        target_folder_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Imports photographs from an existing FRAMED Photosort session into Gallery."""
        folder_id = target_folder_id
        if create_session_folder and not folder_id:
            # Find or create a folder with the session's name under 'Projects' or top-level
            existing_f = next(
                (f for f in storage.get_gallery_folders() if f.name.lower() == project.name.strip().lower()),
                None
            )
            if existing_f:
                folder_id = existing_f.id
            else:
                parent_proj = next(
                    (f for f in storage.get_gallery_folders() if f.name.lower() == "projects"),
                    None
                )
                created = storage.create_gallery_folder(
                    project.name.strip(),
                    parent_id=parent_proj.id if parent_proj else None
                )
                folder_id = created.id

        paths_to_import: List[str] = []
        if scope == "edited":
            if project.edited_result_dir and os.path.exists(project.edited_result_dir):
                paths_to_import.extend(cls.scan_paths_for_images([project.edited_result_dir], recursive=False))
            for ef in project.edited_files:
                if os.path.exists(ef):
                    paths_to_import.append(ef)
        else:
            for item in project.items:
                if getattr(item, "is_video", False):
                    continue
                if scope == "selected" and item.status not in ("kept", "selected"):
                    continue
                if item.raw_path and os.path.exists(item.raw_path):
                    paths_to_import.append(item.raw_path)
                if item.jpeg_path and os.path.exists(item.jpeg_path):
                    paths_to_import.append(item.jpeg_path)
                elif item.primary_path and os.path.exists(item.primary_path):
                    paths_to_import.append(item.primary_path)

        res = cls.import_files(
            paths_to_import,
            copy_to_gallery=copy_to_gallery,
            target_folder_id=folder_id,
            skip_duplicates=True,
            source_session_id=project.id,
        )
        res["folder_id"] = folder_id
        return res

    @staticmethod
    def _auto_pair_raw_and_jpeg():
        """Associates RAW and JPEG photos when reliable matching base name and directory/date exist."""
        active = storage.get_active_gallery_photos()
        by_stem: Dict[Tuple[str, str], List[GalleryPhoto]] = {}
        for p in active:
            stem = os.path.splitext(p.filename)[0].lower()
            key = (stem, p.capture_date)
            by_stem.setdefault(key, []).append(p)

        for _, group in by_stem.items():
            raws = [p for p in group if p.format_type == "RAW"]
            jpegs = [p for p in group if p.format_type == "JPEG"]
            if raws and jpegs:
                r_photo = raws[0]
                j_photo = jpegs[0]
                if not r_photo.paired_jpeg_path:
                    r_photo.paired_jpeg_path = j_photo.active_path
                    r_photo.paired_size_bytes = j_photo.size_bytes
                if not j_photo.paired_raw_path:
                    j_photo.paired_raw_path = r_photo.active_path


class GalleryImportWorker(QThread):
    """Background worker for non-blocking Gallery photo importing."""
    progress = Signal(int, int, str)  # (current, total, filename)
    finished_import = Signal(dict)

    def __init__(
        self,
        filepaths: List[str],
        copy_to_gallery: bool = False,
        target_folder_id: Optional[str] = None,
        skip_duplicates: bool = True,
        parent=None
    ):
        super().__init__(parent)
        self.filepaths = filepaths
        self.copy_to_gallery = copy_to_gallery
        self.target_folder_id = target_folder_id
        self.skip_duplicates = skip_duplicates

    def run(self):
        res = GalleryImporter.import_files(
            self.filepaths,
            copy_to_gallery=self.copy_to_gallery,
            target_folder_id=self.target_folder_id,
            skip_duplicates=self.skip_duplicates,
            progress_callback=lambda c, t, fn: self.progress.emit(c, t, fn),
        )
        self.finished_import.emit(res)


class RawToJpegConverter:
    """Dedicated RAW-to-JPEG conversion engine with quality, resizing, metadata preservation, and space calculations."""

    @classmethod
    def estimate_savings(cls, raw_photos: List[GalleryPhoto], quality: int = 88, max_dimension: Optional[int] = None) -> Dict[str, Any]:
        raw_bytes = sum(max(0, p.size_bytes) for p in raw_photos)
        est_jpeg = sum(cls.estimate_jpeg_size(max(0, p.size_bytes), quality, max_dimension) for p in raw_photos)
        saved = max(0, raw_bytes - est_jpeg)
        pct = round((saved / raw_bytes) * 100, 1) if raw_bytes > 0 else 0.0
        return {
            "count": len(raw_photos),
            "raw_bytes": raw_bytes,
            "estimated_jpeg_bytes": est_jpeg,
            "estimated_savings_bytes": saved,
            "savings_percent": pct,
        }

    @staticmethod
    def estimate_jpeg_size(raw_size_bytes: int, quality: int = 92, max_dimension: Optional[int] = None) -> int:
        """Provides a realistic estimate of output JPEG size from RAW byte size and quality setting."""
        # Typical camera RAW (25-45 MB) compresses to ~12-22% at Q92, ~8% at Q80, ~28% at Q100
        q_factor = 0.04 + (max(10, min(100, quality)) / 100.0) ** 2.2 * 0.22
        if max_dimension and max_dimension > 0:
            if max_dimension <= 1920:
                q_factor *= 0.35
            elif max_dimension <= 2560:
                q_factor *= 0.55
            elif max_dimension <= 3840:
                q_factor *= 0.75
        return max(16384, int(raw_size_bytes * q_factor))

    @classmethod
    def convert_single_raw(
        cls,
        raw_photo: GalleryPhoto,
        output_dir: str,
        quality: int = 92,
        filename_suffix: str = "",
        max_dimension: Optional[int] = None,
        skip_existing: bool = True,
        add_converted_to_gallery: bool = True,
    ) -> Tuple[bool, str, int]:
        """Converts a single RAW GalleryPhoto into a processed JPEG file.
        Never modifies or deletes the original RAW file.
        Returns: (success, output_jpeg_path_or_error, output_bytes)"""
        src_path = raw_photo.active_path
        if not src_path or not os.path.exists(src_path):
            return False, "Source RAW file is missing.", 0

        os.makedirs(output_dir, exist_ok=True)
        stem = os.path.splitext(raw_photo.filename)[0]
        out_name = f"{stem}{filename_suffix}.jpg"
        out_path = os.path.join(output_dir, out_name)

        if os.path.abspath(out_path) == os.path.abspath(src_path):
            out_path = os.path.join(output_dir, f"{stem}_converted.jpg")

        if skip_existing and os.path.exists(out_path):
            out_sz = os.path.getsize(out_path)
            raw_photo.paired_jpeg_path = out_path
            raw_photo.paired_size_bytes = out_sz
            return True, out_path, out_sz

        try:
            from PIL import Image
            qimg, _ = ImageDecoder.decode_to_qimage(src_path)
            if not qimg or qimg.isNull():
                return False, f"Failed to decode RAW data from {raw_photo.filename}", 0

            if max_dimension and max_dimension > 0:
                if qimg.width() > max_dimension or qimg.height() > max_dimension:
                    qimg = qimg.scaled(max_dimension, max_dimension, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # Convert QImage to PIL Image for high-quality JPEG encoding + EXIF preservation
            qimg_rgb = qimg.convertToFormat(QImage.Format_RGB888)
            w, h = qimg_rgb.width(), qimg_rgb.height()
            ptr = qimg_rgb.constBits()
            bytes_per_line = qimg_rgb.bytesPerLine()
            raw_bytes = bytes(ptr)
            pil_img = Image.frombuffer("RGB", (w, h), raw_bytes, "raw", "RGB", bytes_per_line, 1)

            # Preserve basic EXIF if source had readable EXIF via Pillow
            exif_bytes = None
            try:
                with Image.open(src_path) as src_pil:
                    exif_bytes = src_pil.info.get("exif")
            except Exception:
                exif_bytes = None

            save_kwargs = {"format": "JPEG", "quality": max(10, min(100, int(quality))), "optimize": True}
            if exif_bytes:
                save_kwargs["exif"] = exif_bytes

            pil_img.save(out_path, **save_kwargs)
            out_sz = os.path.getsize(out_path)

            # Pair with original RAW photo
            raw_photo.paired_jpeg_path = out_path
            raw_photo.paired_size_bytes = out_sz

            if add_converted_to_gallery:
                # Check if already in gallery
                norm_out = os.path.normcase(os.path.abspath(out_path))
                already = any(
                    os.path.normcase(os.path.abspath(p.active_path)) == norm_out
                    for p in storage.get_active_gallery_photos() if p.active_path
                )
                if not already:
                    new_jpeg = GalleryPhoto(
                        filename=os.path.basename(out_path),
                        original_path=out_path,
                        managed_path=out_path if output_dir == storage.gallery_managed_dir else None,
                        paired_raw_path=src_path,
                        is_managed=(output_dir == storage.gallery_managed_dir),
                        format_type="JPEG",
                        ext=".JPG",
                        size_bytes=out_sz,
                        width=w,
                        height=h,
                        capture_date=raw_photo.capture_date,
                        capture_datetime=raw_photo.capture_datetime,
                        date_source=raw_photo.date_source,
                        folder_ids=list(raw_photo.folder_ids),
                        is_favorite=raw_photo.is_favorite,
                        rating=raw_photo.rating,
                        color_label=raw_photo.color_label,
                        camera_make=raw_photo.camera_make,
                        camera_model=raw_photo.camera_model,
                        camera=raw_photo.camera,
                        lens=raw_photo.lens,
                        iso=raw_photo.iso,
                        shutter_speed=raw_photo.shutter_speed,
                        aperture=raw_photo.aperture,
                        focal_length=raw_photo.focal_length,
                        gps_lat=raw_photo.gps_lat,
                        gps_lon=raw_photo.gps_lon,
                        location_name=raw_photo.location_name,
                        file_hash=compute_file_sha256(out_path),
                        perceptual_hash=compute_perceptual_dhash(out_path),
                    )
                    storage.add_gallery_photo(new_jpeg, save_now=False)

            return True, out_path, out_sz
        except Exception as e:
            return False, str(e), 0

    @classmethod
    def convert_batch(
        cls,
        raw_photos: List[GalleryPhoto],
        output_dir: str,
        quality: int = 92,
        filename_suffix: str = "",
        max_dimension: Optional[int] = None,
        skip_existing: bool = True,
        add_converted_to_gallery: bool = True,
        progress_callback=None,
        cancel_check=None,
    ) -> Dict[str, Any]:
        total = len(raw_photos)
        completed = 0
        failed = 0
        original_total_bytes = 0
        output_total_bytes = 0
        converted_paths: List[str] = []
        failed_files: List[Tuple[str, str]] = []

        for idx, rp in enumerate(raw_photos):
            if cancel_check and cancel_check():
                break
            if progress_callback:
                progress_callback(idx + 1, total, rp.filename, completed, failed)

            ok, res_str, out_sz = cls.convert_single_raw(
                rp,
                output_dir=output_dir,
                quality=quality,
                filename_suffix=filename_suffix,
                max_dimension=max_dimension,
                skip_existing=skip_existing,
                add_converted_to_gallery=add_converted_to_gallery,
            )
            if ok:
                completed += 1
                original_total_bytes += rp.size_bytes
                output_total_bytes += out_sz
                converted_paths.append(res_str)
            else:
                failed += 1
                failed_files.append((rp.filename, res_str))

        if completed > 0:
            storage.log_gallery_activity(
                "convert",
                f"Converted {completed} RAW photo(s) to JPEG",
                save_now=False
            )
            storage.save()

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "original_bytes": original_total_bytes,
            "output_bytes": output_total_bytes,
            "saved_bytes": max(0, original_total_bytes - output_total_bytes),
            "converted_paths": converted_paths,
            "failed_files": failed_files,
        }


class RawConversionWorker(QThread):
    """Background worker for RAW-to-JPEG batch conversion with cancellation support."""
    progress = Signal(int, int, str, int, int)  # (current_idx, total, filename, completed, failed)
    finished_conversion = Signal(dict)

    def __init__(
        self,
        raw_photos: List[GalleryPhoto],
        output_dir: str,
        quality: int = 92,
        filename_suffix: str = "",
        max_dimension: Optional[int] = None,
        skip_existing: bool = True,
        add_converted_to_gallery: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.raw_photos = raw_photos
        self.output_dir = output_dir
        self.quality = quality
        self.filename_suffix = filename_suffix
        self.max_dimension = max_dimension
        self.skip_existing = skip_existing
        self.add_converted_to_gallery = add_converted_to_gallery
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        res = RawToJpegConverter.convert_batch(
            self.raw_photos,
            output_dir=self.output_dir,
            quality=self.quality,
            filename_suffix=self.filename_suffix,
            max_dimension=self.max_dimension,
            skip_existing=self.skip_existing,
            add_converted_to_gallery=self.add_converted_to_gallery,
            progress_callback=lambda c, t, fn, comp, fail: self.progress.emit(c, t, fn, comp, fail),
            cancel_check=lambda: self._cancelled,
        )
        res["cancelled"] = self._cancelled
        self.finished_conversion.emit(res)


class MissingFileRecoveryEngine:
    """Safely locates and reconnects missing Gallery files using SHA-256 hash, size, filename, and metadata."""

    @staticmethod
    def reconnect_single_file(photo: GalleryPhoto, candidate_path: str) -> Tuple[bool, str]:
        if not candidate_path or not os.path.exists(candidate_path) or not os.path.isfile(candidate_path):
            return False, "Selected file does not exist."

        cand_size = os.path.getsize(candidate_path)
        cand_hash = compute_file_sha256(candidate_path)

        # Verify hash if original hash was recorded
        if photo.file_hash and cand_hash and photo.file_hash != cand_hash:
            return False, (
                f"File verification failed: SHA-256 hash of '{os.path.basename(candidate_path)}' "
                f"does not match the original photograph '{photo.filename}'."
            )

        # If no hash was stored, verify exact byte size and extension
        if not photo.file_hash and photo.size_bytes > 0 and cand_size != photo.size_bytes:
            return False, (
                f"File size mismatch ({MetadataExtractor.format_file_size(cand_size)} vs "
                f"expected {MetadataExtractor.format_file_size(photo.size_bytes)})."
            )

        photo.original_path = os.path.abspath(candidate_path)
        if photo.is_managed:
            photo.managed_path = os.path.abspath(candidate_path)
        photo.is_missing = False
        if cand_hash:
            photo.file_hash = cand_hash
        storage.save()
        return True, "Successfully reconnected photograph."

    @classmethod
    def scan_directory_and_reconnect(cls, search_dir: str, missing_photos: Optional[List[GalleryPhoto]] = None) -> Dict[str, Any]:
        """Scans search_dir recursively and reconnects missing photos only when unambiguous verification succeeds.
        Never relies on filename alone when multiple matches exist."""
        if missing_photos is None:
            missing_photos = storage.get_missing_gallery_photos()

        if not search_dir or not os.path.exists(search_dir):
            return {"reconnected": 0, "ambiguous": 0, "unmatched": len(missing_photos)}

        candidate_files = GalleryImporter.scan_paths_for_images([search_dir], recursive=True)

        # Index candidates by size and filename
        by_size: Dict[int, List[str]] = {}
        by_name: Dict[str, List[str]] = {}
        for cf in candidate_files:
            try:
                sz = os.path.getsize(cf)
                by_size.setdefault(sz, []).append(cf)
                by_name.setdefault(os.path.basename(cf).lower(), []).append(cf)
            except Exception:
                pass

        reconnected = 0
        ambiguous = 0
        unmatched = 0

        for mp in missing_photos:
            matched_path = None

            # 1. Exact SHA-256 + Size match (gold standard)
            if mp.file_hash and mp.size_bytes in by_size:
                for cand in by_size[mp.size_bytes]:
                    if compute_file_sha256(cand) == mp.file_hash:
                        matched_path = cand
                        break

            # 2. If still not found and mp has file_hash, check candidates with same filename
            if not matched_path and mp.file_hash:
                for cand in by_name.get(mp.filename.lower(), []):
                    if compute_file_sha256(cand) == mp.file_hash:
                        matched_path = cand
                        break

            # 3. Fallback when file_hash wasn't recorded: require BOTH exact filename AND exact size,
            # and ensure there is ONLY ONE such matching candidate (no ambiguity)
            if not matched_path and not mp.file_hash:
                name_cands = [
                    c for c in by_name.get(mp.filename.lower(), [])
                    if os.path.getsize(c) == mp.size_bytes
                ]
                if len(name_cands) == 1:
                    matched_path = name_cands[0]
                elif len(name_cands) > 1:
                    ambiguous += 1
                    continue

            if matched_path:
                mp.original_path = os.path.abspath(matched_path)
                if mp.is_managed:
                    mp.managed_path = os.path.abspath(matched_path)
                mp.is_missing = False
                reconnected += 1
            else:
                unmatched += 1

        if reconnected > 0:
            storage.log_gallery_activity("import", f"Reconnected {reconnected} missing photo(s)", save_now=False)
            storage.save()

        return {
            "reconnected": reconnected,
            "ambiguous": ambiguous,
            "unmatched": unmatched,
        }


class DuplicateFinderEngine:
    """Detects Exact Duplicates (SHA-256) and Visually Similar Photos (Perceptual dHash)."""

    @staticmethod
    def find_duplicates(include_similar: bool = True, max_hamming: int = 8) -> Dict[str, List[List[GalleryPhoto]]]:
        """Returns {'exact': [[p1, p2], ...], 'similar': [[p3, p4], ...]}."""
        active = [p for p in storage.get_active_gallery_photos() if not p.is_missing]

        # Ensure hashes are populated
        for p in active:
            if not p.file_hash and os.path.exists(p.active_path):
                p.file_hash = compute_file_sha256(p.active_path)
            if include_similar and not p.perceptual_hash and os.path.exists(p.active_path):
                p.perceptual_hash = compute_perceptual_dhash(p.active_path)

        # 1. Exact duplicates by SHA-256
        by_sha: Dict[str, List[GalleryPhoto]] = {}
        for p in active:
            if p.file_hash:
                by_sha.setdefault(p.file_hash, []).append(p)

        exact_groups: List[List[GalleryPhoto]] = []
        exact_member_ids = set()
        for sha, group in by_sha.items():
            if len(group) > 1:
                exact_groups.append(group)
                for p in group:
                    exact_member_ids.add(p.id)

        # 2. Visually similar photos (excluding pairs already grouped as exact duplicates)
        similar_groups: List[List[GalleryPhoto]] = []
        if include_similar:
            remaining = [p for p in active if p.perceptual_hash]
            visited = set()
            for i, p1 in enumerate(remaining):
                if p1.id in visited:
                    continue
                sim_group = [p1]
                for j in range(i + 1, len(remaining)):
                    p2 = remaining[j]
                    if p2.id in visited:
                        continue
                    # Skip if they have identical SHA (already in exact_groups)
                    if p1.file_hash and p1.file_hash == p2.file_hash:
                        continue
                    dist = hamming_distance_hex(p1.perceptual_hash, p2.perceptual_hash)
                    if dist <= max_hamming:
                        sim_group.append(p2)
                        visited.add(p2.id)
                if len(sim_group) > 1:
                    visited.add(p1.id)
                    similar_groups.append(sim_group)

        return {
            "exact": exact_groups,
            "similar": similar_groups,
        }


class GalleryBackupEngine:
    """Backs up Gallery photographs to a target drive/directory with SHA-256 verification."""

    @staticmethod
    def run_backup(
        destination_root: str,
        include_referenced: bool = True,
        verify_hashes: bool = True,
        progress_callback=None,
    ) -> Dict[str, Any]:
        if not destination_root:
            return {"success": False, "error": "No backup destination selected.", "completed": 0, "failed": 0}

        # Check if drive/root exists and is writable
        drive, _ = os.path.splitdrive(os.path.abspath(destination_root))
        if drive and not os.path.exists(drive + os.sep):
            return {
                "success": False,
                "error": f"Destination drive ({drive}) is disconnected or unavailable.",
                "completed": 0,
                "failed": 0,
            }

        try:
            backup_base = os.path.join(destination_root, "FRAMED_Gallery_Backup")
            managed_target = os.path.join(backup_base, "Gallery_Managed")
            referenced_target = os.path.join(backup_base, "Referenced_Originals")
            os.makedirs(managed_target, exist_ok=True)
            if include_referenced:
                os.makedirs(referenced_target, exist_ok=True)
        except Exception as e:
            return {"success": False, "error": f"Cannot write to destination drive: {e}", "completed": 0, "failed": 0}

        active = storage.get_active_gallery_photos()
        candidates = [
            p for p in active
            if (p.is_managed or include_referenced) and p.active_path and os.path.exists(p.active_path)
        ]

        total = len(candidates)
        completed = 0
        failed = 0
        total_bytes = 0

        for idx, p in enumerate(candidates):
            if progress_callback:
                progress_callback(idx + 1, total, p.filename)

            src = p.active_path
            sub_dir = managed_target if p.is_managed else referenced_target
            # Organize inside folder subfolder if assigned
            if p.folder_ids and p.folder_ids[0] in storage.gallery_folders:
                rel_folder = storage.get_gallery_folder_path(p.folder_ids[0]).replace(" / ", os.sep)
                dest_folder = os.path.join(sub_dir, rel_folder)
            else:
                dest_folder = os.path.join(sub_dir, "All_Photos")

            try:
                os.makedirs(dest_folder, exist_ok=True)
                dest_file = os.path.join(dest_folder, p.filename)
                shutil.copy2(src, dest_file)

                if verify_hashes:
                    src_hash = p.file_hash or compute_file_sha256(src)
                    dst_hash = compute_file_sha256(dest_file)
                    if src_hash != dst_hash:
                        failed += 1
                        continue

                completed += 1
                total_bytes += os.path.getsize(dest_file)
            except Exception:
                failed += 1

        # Also back up gallery metadata index JSON
        try:
            manifest_path = os.path.join(backup_base, "gallery_metadata_backup.json")
            shutil.copy2(storage.db_path, manifest_path)
        except Exception:
            pass

        rec = BackupRecord(
            destination_dir=destination_root,
            files_completed=completed,
            files_failed=failed,
            total_bytes=total_bytes,
            included_referenced=include_referenced,
            verified=verify_hashes,
        )
        storage.backup_records.insert(0, rec)
        storage.log_gallery_activity("backup", f"Backed up {completed} photo(s) to {destination_root}", save_now=False)
        storage.save()

        return {
            "success": True,
            "completed": completed,
            "failed": failed,
            "total_bytes": total_bytes,
            "record": rec,
        }


# Convenience singleton & aliases for UI components
thumbnail_cache = GalleryThumbnailCache()
GalleryImporter.scan_paths = GalleryImporter.scan_paths_for_images
GalleryImporter.import_from_session = lambda project, include_mode="selected", import_mode="reference": GalleryImporter.import_from_project_session(
    project, scope=include_mode, copy_to_gallery=(import_mode == "copy")
)
