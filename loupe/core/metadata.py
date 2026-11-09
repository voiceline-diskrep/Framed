"""EXIF metadata extractor for RAW and JPEG photographic files, including GPS and capture dates."""

import os
from typing import Dict, Any, Optional, Tuple
from datetime import datetime


class MetadataExtractor:
    @staticmethod
    def format_shutter_speed(val) -> str:
        if not val:
            return "—"
        try:
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
            if 0 < sec < 1.0:
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
            dt = datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
            return dt.strftime("%b %d, %Y • %H:%M:%S")
        except Exception:
            return str(val)

    @staticmethod
    def parse_iso_date(val) -> Optional[str]:
        if not val:
            return None
        try:
            s = str(val).strip()
            for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(s[:19] if len(s) >= 19 else s[:10], fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
        except Exception:
            pass
        return None

    @staticmethod
    def _dms_to_decimal(dms_tag, ref_tag) -> Optional[float]:
        """Convert EXIF GPS DMS array [deg, min, sec] and ref ('N','S','E','W') to decimal degrees."""
        if not dms_tag:
            return None
        try:
            vals = getattr(dms_tag, "values", dms_tag)
            if not vals or len(vals) < 3:
                return None

            def _to_float(v) -> float:
                if hasattr(v, "num") and hasattr(v, "den"):
                    return float(v.num) / float(v.den) if v.den != 0 else 0.0
                if isinstance(v, tuple) and len(v) == 2:
                    return float(v[0]) / float(v[1]) if v[1] != 0 else 0.0
                s = str(v).strip()
                if "/" in s:
                    n, d = s.split("/")
                    return float(n) / float(d) if float(d) != 0 else 0.0
                return float(s)

            deg = _to_float(vals[0])
            minutes = _to_float(vals[1])
            seconds = _to_float(vals[2])
            dec = deg + (minutes / 60.0) + (seconds / 3600.0)
            ref = str(ref_tag).strip().upper() if ref_tag else ""
            if ref in ("S", "W"):
                dec = -dec
            return round(dec, 6)
        except Exception:
            return None

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
        """Extract clean, structured EXIF metadata dictionary including GPS and date source."""
        size_b = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        fallback_date = datetime.now().strftime("%Y-%m-%d")
        if os.path.exists(filepath):
            try:
                fallback_date = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%Y-%m-%d")
            except Exception:
                pass

        data: Dict[str, Any] = {
            "make": "—",
            "model": "—",
            "camera": "Unknown Camera",
            "lens": "—",
            "date_taken": "—",
            "iso_date": fallback_date,
            "date_source": "import",
            "iso": "—",
            "shutter_speed": "—",
            "aperture": "—",
            "focal_length": "—",
            "dimensions": "—",
            "width": 0,
            "height": 0,
            "file_size": cls.format_file_size(size_b) if os.path.exists(filepath) else "—",
            "size_bytes": size_b,
            "file_name": os.path.basename(filepath),
            "file_path": filepath,
            "gps_lat": None,
            "gps_lon": None,
            "gps_label": "—",
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
                    parsed_iso = cls.parse_iso_date(dt)
                    if parsed_iso:
                        data["iso_date"] = parsed_iso
                        data["date_source"] = "exif"

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
                    try:
                        data["width"] = int(str(w).strip())
                        data["height"] = int(str(h).strip())
                    except Exception:
                        pass
                    data["dimensions"] = f"{w} × {h}"

                # GPS Extraction
                lat_tag = tags.get("GPS GPSLatitude")
                lat_ref = tags.get("GPS GPSLatitudeRef")
                lon_tag = tags.get("GPS GPSLongitude")
                lon_ref = tags.get("GPS GPSLongitudeRef")
                if lat_tag and lon_tag:
                    lat = cls._dms_to_decimal(lat_tag, lat_ref)
                    lon = cls._dms_to_decimal(lon_tag, lon_ref)
                    if lat is not None and lon is not None:
                        data["gps_lat"] = lat
                        data["gps_lon"] = lon
                        ns = "N" if lat >= 0 else "S"
                        ew = "E" if lon >= 0 else "W"
                        data["gps_label"] = f"{abs(lat):.4f}° {ns}, {abs(lon):.4f}° {ew}"
        except Exception as e:
            print(f"Error in exifread for {filepath}: {e}")

        # If camera or dimensions missing, try Pillow fallback
        if data["camera"] == "Unknown Camera" or data["dimensions"] == "—" or data["width"] == 0:
            try:
                from PIL import Image, ExifTags
                with Image.open(filepath) as img:
                    data["width"] = img.width
                    data["height"] = img.height
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
                            dt_str = str(exif_dict["DateTime"])
                            data["date_taken"] = cls.format_date_time(dt_str)
                            parsed_iso = cls.parse_iso_date(dt_str)
                            if parsed_iso:
                                data["iso_date"] = parsed_iso
                                data["date_source"] = "exif"
            except Exception:
                pass

        return data
