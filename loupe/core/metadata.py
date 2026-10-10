"""EXIF metadata extractor for RAW and JPEG photographic files."""

import os
from typing import Dict, Any, Optional
from datetime import datetime

class MetadataExtractor:
    @staticmethod
    def format_shutter_speed(val) -> str:
        if not val:
            return "—"
        try:
            # val could be a fraction like 1/1000 or a float
            s = str(val).strip()
            if "/" in s:
                num, den = s.split("/")
                fnum, fden = float(num), float(den)
                if fnum == 1:
                    return f"1/{int(fden)}s"
                sec = fnum / fden
                if sec < 1.0:
                    return f"1/{int(round(1.0 / sec))}s"
                return f"{sec:.1f}s"
            sec = float(s)
            if sec < 1.0 and sec > 0:
                return f"1/{int(round(1.0 / sec))}s"
            return f"{sec:.1f}s"
        except Exception:
            return str(val)

    @staticmethod
    def format_aperture(val) -> str:
        if not val:
            return "—"
        try:
            s = str(val).strip()
            if "/" in s:
                num, den = s.split("/")
                fnum, fden = float(num), float(den)
                fval = fnum / fden
            else:
                fval = float(s)
            return f"f/{fval:.1f}" if fval % 1 != 0 else f"f/{int(fval)}"
        except Exception:
            return f"f/{val}"

    @staticmethod
    def format_focal_length(val) -> str:
        if not val:
            return "—"
        try:
            s = str(val).strip()
            if "/" in s:
                num, den = s.split("/")
                fl = float(num) / float(den)
            else:
                fl = float(s)
            return f"{int(fl)}mm" if fl.is_integer() else f"{fl:.1f}mm"
        except Exception:
            return f"{val}mm"

    @staticmethod
    def format_date_time(val) -> str:
        if not val:
            return "—"
        try:
            s = str(val).strip()
            # Standard EXIF date format is YYYY:MM:DD HH:MM:SS
            dt = datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
            return dt.strftime("%b %d, %Y • %H:%M:%S")
        except Exception:
            return str(val)

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    @classmethod
    def extract(cls, filepath: str) -> Dict[str, Any]:
        """Extract clean, structured EXIF metadata dictionary."""
        data: Dict[str, Any] = {
            "make": "—",
            "model": "—",
            "camera": "Unknown Camera",
            "lens": "—",
            "date_taken": "—",
            "iso": "—",
            "shutter_speed": "—",
            "aperture": "—",
            "focal_length": "—",
            "dimensions": "—",
            "file_size": cls.format_file_size(os.path.getsize(filepath)) if os.path.exists(filepath) else "—",
            "file_name": os.path.basename(filepath),
            "file_path": filepath,
        }

        if not os.path.exists(filepath):
            return data

        # Try exifread first
        try:
            import exifread
            with open(filepath, "rb") as f:
                tags = exifread.process_file(f, details=False, stop_tag="UNDEF")
                
                make = str(tags.get("Image Make", "")).strip()
                model = str(tags.get("Image Model", "")).strip()
                if make and make != "—":
                    data["make"] = make
                if model and model != "—":
                    data["model"] = model
                if make or model:
                    if make and make.lower() in model.lower():
                        data["camera"] = model
                    else:
                        data["camera"] = f"{make} {model}".strip()

                lens = str(tags.get("EXIF LensModel", tags.get("Image LensModel", ""))).strip()
                if lens and lens != "—":
                    data["lens"] = lens

                dt = str(tags.get("EXIF DateTimeOriginal", tags.get("Image DateTime", ""))).strip()
                if dt:
                    data["date_taken"] = cls.format_date_time(dt)

                iso = tags.get("EXIF ISOSpeedRatings", tags.get("EXIF PhotographicSensitivity"))
                if iso:
                    data["iso"] = f"ISO {iso}"

                shutter = tags.get("EXIF ExposureTime")
                if shutter:
                    data["shutter_speed"] = cls.format_shutter_speed(shutter)

                fnum = tags.get("EXIF FNumber")
                if fnum:
                    data["aperture"] = cls.format_aperture(fnum)

                fl = tags.get("EXIF FocalLength")
                if fl:
                    data["focal_length"] = cls.format_focal_length(fl)

                w = tags.get("EXIF ExifImageWidth", tags.get("Image ImageWidth"))
                h = tags.get("EXIF ExifImageLength", tags.get("Image ImageLength"))
                if w and h:
                    data["dimensions"] = f"{w} × {h}"
        except Exception as e:
            print(f"Error in exifread for {filepath}: {e}")

        # If camera or dimensions missing, try Pillow fallback
        if data["camera"] == "Unknown Camera" or data["dimensions"] == "—":
            try:
                from PIL import Image, ExifTags
                with Image.open(filepath) as img:
                    if data["dimensions"] == "—":
                        data["dimensions"] = f"{img.width} × {img.height}"
                    exif = img.getexif()
                    if exif:
                        exif_dict = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
                        if data["make"] == "—" and "Make" in exif_dict:
                            data["make"] = str(exif_dict["Make"]).strip()
                        if data["model"] == "—" and "Model" in exif_dict:
                            data["model"] = str(exif_dict["Model"]).strip()
                        if data["camera"] == "Unknown Camera" and (data["make"] != "—" or data["model"] != "—"):
                            data["camera"] = f"{data['make']} {data['model']}".strip()
                        if data["date_taken"] == "—" and "DateTime" in exif_dict:
                            data["date_taken"] = cls.format_date_time(exif_dict["DateTime"])
            except Exception:
                pass

        return data
