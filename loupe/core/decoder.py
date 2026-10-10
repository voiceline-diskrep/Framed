"""Image decoding engine supporting LibRaw (rawpy) and Pillow for full-resolution rendering."""

import os
from typing import Tuple, Optional
import numpy as np
from PIL import Image, ImageOps
from PySide6.QtGui import QImage, QPixmap

RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf",
    ".rw2", ".dng", ".pef", ".srw", ".kdc", ".mrw", ".dcr"
}

JPEG_EXTENSIONS = {".jpg", ".jpeg"}

class ImageDecoder:
    """Decodes full-resolution camera RAW and JPEG images into PySide6 QImage buffers."""

    @staticmethod
    def is_raw_file(filepath: str) -> bool:
        ext = os.path.splitext(filepath)[1].lower()
        return ext in RAW_EXTENSIONS

    @staticmethod
    def is_jpeg_file(filepath: str) -> bool:
        ext = os.path.splitext(filepath)[1].lower()
        return ext in JPEG_EXTENSIONS

    @classmethod
    def decode_to_qimage(cls, filepath: str) -> Tuple[Optional[QImage], int]:
        """
        Decodes the full-resolution image from disk.
        Returns: (QImage, approximate_memory_bytes)
        """
        if not os.path.exists(filepath):
            return None, 0

        ext = os.path.splitext(filepath)[1].lower()

        # Try rawpy for RAW formats
        if ext in RAW_EXTENSIONS:
            try:
                import rawpy
                with rawpy.imread(filepath) as raw:
                    # Postprocess at full resolution with camera white balance
                    rgb: np.ndarray = raw.postprocess(
                        use_camera_wb=True,
                        half_size=False,
                        no_auto_bright=False,
                        output_color=rawpy.ColorSpace.sRGB,
                        user_flip=None  # Use camera orientation
                    )
                    h, w, c = rgb.shape
                    bytes_per_line = c * w
                    # QImage with Format_RGB888
                    # Make a deep copy to decouple from numpy buffer
                    qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
                    mem_cost = h * bytes_per_line
                    return qimg, mem_cost
            except Exception as e:
                # Fall back to Pillow in case LibRaw fails or synthetic test file
                pass

        # Use Pillow for JPEG / fallback
        try:
            with Image.open(filepath) as img:
                # Apply orientation from EXIF
                img = ImageOps.exif_transpose(img)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                
                w, h = img.size
                data = img.tobytes("raw", "RGB")
                qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
                mem_cost = w * h * 3
                return qimg, mem_cost
        except Exception as e:
            print(f"Error decoding image {filepath}: {e}")
            return None, 0

    @classmethod
    def decode_thumbnail(cls, filepath: str, max_size: int = 300) -> Optional[QPixmap]:
        """Generate a fast thumbnail for tray or list preview."""
        qimg, _ = cls.decode_to_qimage(filepath)
        if qimg and not qimg.isNull():
            pixmap = QPixmap.fromImage(qimg)
            from PySide6.QtCore import Qt
            return pixmap.scaled(max_size, max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return None
