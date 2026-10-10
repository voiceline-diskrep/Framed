"""Generates a realistic photo shoot with matched RAW and JPEG pairs and embedded EXIF."""

import os
import random
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import piexif

CAMERAS = [
    ("Sony", "ILCE-7RM5", "FE 85mm F1.4 GM II", 85),
    ("Sony", "ILCE-7RM5", "FE 24-70mm F2.8 GM II", 50),
    ("Canon", "EOS R5", "RF 50mm F1.2 L USM", 50),
    ("Canon", "EOS R5", "RF 70-200mm F2.8 L IS USM", 135),
    ("Nikon", "Z8", "NIKKOR Z 85mm f/1.2 S", 85),
]

EXPOSURES = [
    ((1, 2000), (14, 10), 100),
    ((1, 1000), (20, 10), 200),
    ((1, 500), (28, 10), 400),
    ((1, 250), (40, 10), 800),
    ((1, 125), (56, 10), 1600),
]

def generate_sample_shoot(output_dir: str, num_frames: int = 18):
    os.makedirs(output_dir, exist_ok=True)
    base_time = datetime(2026, 10, 8, 14, 15, 0)

    print(f"Generating {num_frames} matched RAW/JPEG photo pairs in {output_dir}...")

    palettes = [
        # Nordic Coastal Sunrise
        ((35, 45, 60), (220, 140, 75), (90, 130, 160)),
        # Editorial Portrait Studio
        ((25, 25, 28), (180, 160, 140), (80, 75, 70)),
        # Architectural Minimal
        ((40, 42, 45), (210, 215, 220), (120, 125, 130)),
        # Autumn Forest
        ((45, 30, 20), (190, 100, 40), (70, 85, 45)),
    ]

    for i in range(1, num_frames + 1):
        stem = f"DSC{8490 + i:05d}"
        make, model, lens, focal_mm = random.choice(CAMERAS)
        exp_time, f_num, iso = random.choice(EXPOSURES)
        frame_time = base_time + timedelta(seconds=i * 14)
        date_str = frame_time.strftime("%Y:%m:%d %H:%M:%S")

        # Pick palette
        bg_col, accent_col, light_col = palettes[i % len(palettes)]

        # Generate realistic graphic texture
        w, h = 1920, 1280
        img = Image.new("RGB", (w, h), color=bg_col)
        draw = ImageDraw.Draw(img)

        # Gradient sky / lighting
        for y in range(0, h, 8):
            ratio = y / h
            r = int(bg_col[0] * (1 - ratio) + accent_col[0] * ratio * 0.4)
            g = int(bg_col[1] * (1 - ratio) + accent_col[1] * ratio * 0.4)
            b = int(bg_col[2] * (1 - ratio) + accent_col[2] * ratio * 0.4)
            draw.rectangle([0, y, w, y + 8], fill=(r, g, b))

        # Optical center circle / focal subject
        cx, cy = int(w * (0.35 + (i % 3) * 0.15)), int(h * 0.45)
        radius = int(220 + (i % 4) * 40)
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=accent_col, outline=light_col, width=4)

        # Geometric composition lines
        draw.line([0, int(h * 0.72), w, int(h * 0.72)], fill=light_col, width=2)
        draw.line([cx, 0, cx, h], fill=(light_col[0], light_col[1], light_col[2]), width=1)

        # Telemetry watermark
        info_text = f"{stem} • {make} {model} • {lens} • ISO {iso} • 1/{int(exp_time[1]/exp_time[0])}s • f/{f_num[0]/f_num[1]:.1f} • {date_str}"
        draw.text((40, h - 60), info_text, fill=(240, 240, 240))

        # Build genuine EXIF dictionary
        zeroth_ifd = {
            piexif.ImageIFD.Make: make,
            piexif.ImageIFD.Model: model,
            piexif.ImageIFD.Software: f"{model} Firmware v2.10",
            piexif.ImageIFD.DateTime: date_str,
        }
        exif_ifd = {
            piexif.ExifIFD.ExposureTime: exp_time,
            piexif.ExifIFD.FNumber: f_num,
            piexif.ExifIFD.ISOSpeedRatings: iso,
            piexif.ExifIFD.DateTimeOriginal: date_str,
            piexif.ExifIFD.FocalLength: (focal_mm * 10, 10),
            piexif.ExifIFD.LensModel: lens,
            piexif.ExifIFD.PixelXDimension: w,
            piexif.ExifIFD.PixelYDimension: h,
        }
        exif_dict = {"0th": zeroth_ifd, "Exif": exif_ifd}
        exif_bytes = piexif.dump(exif_dict)

        # Save JPEG pair
        jpg_path = os.path.join(output_dir, f"{stem}.JPG")
        img.save(jpg_path, format="JPEG", quality=92, exif=exif_bytes)

        # Save companion RAW pair (named .ARW, with genuine EXIF headers)
        raw_path = os.path.join(output_dir, f"{stem}.ARW")
        img.save(raw_path, format="JPEG", quality=98, exif=exif_bytes)

    print(f"Generated {num_frames * 2} files successfully in {output_dir}.")

if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "sample_shoot")
    generate_sample_shoot(os.path.abspath(out))
