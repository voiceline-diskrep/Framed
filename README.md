# FRAMED — Photographer's Inspection & Culling Workstation

> **Visual Direction:** Dark graphite and warm amber darkroom inspection workstation built for long, fatigue-free culling sessions with high-density typographic utility and optical precision.

Framed is a dedicated Windows desktop application designed specifically for professional photographers to cull and review high-volume photo shoots with zero lag, optical accuracy, and non-destructive file handling.

---

## Key Features

### 1. Optical Precision & RAW Decoding Engine
- **Universal RAW Support**: Decodes raw sensor files from all major camera brands (`.CR2`, `.CR3`, `.NEF`, `.ARW`, `.RAF`, `.ORF`, `.RW2`, `.DNG`, `.PEF`, `.SRW`) using **LibRaw** (`rawpy`).
- **Full-Resolution Decoded Viewport**: Never shows compressed or blurry thumbnail proxies in the inspection canvas. Every frame renders at native sensor resolution.
- **Sub-Pixel Pan & Smooth Zoom**: Zoom to cursor with mouse wheel, pinch, or keyboard. Instant shortcuts for **Fit to Window (`F`)** and **100% Actual Pixels (`Z`)**.
- **Inspection Loupe ("Start zoomed in")**: Automatically opens every frame at a user-defined zoom level (e.g. 200%) aligned to the top-left quadrant for instant eye/focus sharpness inspection without pressing zoom each time.

### 2. High-Throughput Memory Preloader
- **Session Preload Buffer**: Allocates a RAM budget (default 50% of the session size, capped by user preference) to decode full-resolution photos ahead of navigation.
- **Batch Boundary Pause Overlay**: When navigating to the boundary of a buffer (e.g., reaching frame 16 of a 16-frame buffer), Loupe displays a pause overlay with live decode speed (`142 MB/s`) and estimated time remaining (`ETA: 1.8s`) while keeping the UI responsive.
- **Direction-Aware Background Prefetching**: Prefetches subsequent photos in the direction you are actively moving (forward or backward).

### 3. Ergonomic Culling & Reversibility
- **Default Muscle-Memory Shortcuts** (Fully remappable in Settings):
  - `W`: **Keep Photo** (Marks as Kept in Sage Green, advances to next)
  - `S`: **Move to Not Accepted** (Marks as Rejected in Cinnabar Red, advances to next)
  - `A`: **Previous Photo**
  - `D`: **Next Photo**
  - `Ctrl+Z`: **Undo** last decision
  - `Escape`: Pauses session and returns to dashboard
- **Accidental Click Recovery**: Open the **"Not Accepted"** tray from the telemetry panel to view all rejected photos and restore any frame back to the Kept set with one click.

### 4. Workspace Management & Editable Shoots
- **Real Working Folders**: Create custom folders (e.g., `School`, `Weddings`, `Personal`, `Commercial`). Folders persist and filter your active projects.
- **Editable Shoot Dates**: Change shoot dates directly on any project card.
- **Non-Destructive Session State**: Pressing `Escape` or returning to Dashboard saves your exact frame index, decisions, and buffer settings. Resume anytime exactly where you left off.

### 5. Pair Synchronization (RAW + JPEG)
- Matches corresponding RAW and JPEG files sharing the same stem (`IMG_4012.CR3` and `IMG_4012.JPG`).
- With **Sync ON**, rejecting or keeping one automatically updates its companion file.
- **Sync never deletes your original files.**

### 6. Two-Folder Structured Export
When you click **Export**, Loupe creates a structured destination folder named after the project:
```
<ExportDestination>/
  └── <ProjectName>/
        ├── Selected/
        │     ├── RAW/     (Kept camera RAW originals)
        │     └── JPEG/    (Kept JPEG originals)
        └── Unselected/
              ├── RAW/     (Rejected camera RAW originals)
              └── JPEG/    (Rejected JPEG originals)
```
- Safe file copy using `shutil.copy2` preserving timestamps and metadata.
- **Never moves or deletes source files.**

### 7. First Launch Guided Tour
- On first launch, a skippable 5-step guided tour introduces the workspace, culling shortcuts, optical loupe, and structured export.
- Includes a "Skip" option on every step.
- Can be restarted anytime from Preferences.

---

## Tech Stack & Architectural Decisions

| Layer | Technology | Rationale |
| :--- | :--- | :--- |
| **GUI Framework** | **PySide6 (Qt 6.11)** | Hardware-accelerated graphics view (`QGraphicsView`) with sub-pixel panning, smooth zoom, native Windows windowing, and rich typographic control. |
| **RAW Engine** | **rawpy (LibRaw 0.21)** | Industry standard C++ library for decoding all proprietary camera RAW formats (Canon CR2/CR3, Nikon NEF, Sony ARW, Fuji RAF, Olympus ORF, Panasonic RW2, Adobe DNG) directly into RGB numpy arrays. |
| **Image Core** | **Pillow (PIL 12.3)** | Fast JPEG, PNG, and TIFF decoding with automatic EXIF orientation transposition (`ImageOps.exif_transpose`). |
| **EXIF Telemetry** | **exifread & piexif** | Deep extraction of photographic metadata: Camera Make, Model, Lens Model, ISO, Shutter Speed, Aperture, Focal Length, and Timestamps. |
| **Memory Metrics**| **psutil** | Accurate physical RAM detection and live transfer speed / ETA telemetry. |
| **Packaging** | **PyInstaller 6.22** | Self-contained Windows binary bundling Python runtime, Qt DLLs, and LibRaw C++ libraries into `dist/Loupe`. |
| **Installer** | **Inno Setup 6.7** | Compiles a standard Windows setup `.exe` installer (`Loupe-Setup-v1.0.exe`) with Desktop/Start Menu shortcuts and clean uninstallation. |

---

## Building and Running

### 1. Run from Source
```powershell
# Navigate to the project root
cd c:\Users\russell\Documents\sideprojects\loupe

# Run with Python
python main.py
```

### 2. Run Automated Test Suite
```powershell
python tests/test_loupe.py
```

### 3. Generate Sample Photo Shoot (for testing)
```powershell
python tests/generate_sample_shoot.py
```

### 4. Build the Standalone Windows Installer
```powershell
python installer/build_installer.py
```
This produces:
- Standalone distribution: `dist/Loupe/Loupe.exe`
- Single Windows installer: `installer/Output/Loupe-Setup-v1.0.exe` (42.99 MB)

---

## Design System & Typography

- **Display Typeface**: *Space Grotesk* (Bold, architectural display titles)
- **Body Typeface**: *Plus Jakarta Sans* (Legible, low-fatigue UI labels)
- **Telemetry Typeface**: *IBM Plex Mono* (Tabular numeric alignment for ISO, shutter, aperture, and speeds)
- **Palette**:
  - Darkroom Base: `#101113`
  - Slate Surface: `#17191C`
  - Elevated Loupe Frame: `#202327`
  - Subtle Border: `#282C33`
  - High-Contrast Border: `#3B414B`
  - Safety Amber Accent: `#E59533`
  - Forest Sage (Kept): `#3EA66A`
  - Cinnabar Red (Not Accepted): `#D44747`
- **Keyboard Navigation**: Explicit `:focus` rings (`2px solid #E59533`), `:hover`, `:pressed`, and `:disabled` states on all interactive controls.
