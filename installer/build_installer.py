"""Automated build pipeline: PyInstaller -> Inno Setup -> Framed-Setup-v1.0.exe."""

import os
import sys
import shutil
import subprocess
import hashlib

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SPEC_FILE = os.path.join(BASE_DIR, "framed.spec")
ISS_FILE = os.path.join(BASE_DIR, "installer", "framed.iss")
DIST_DIR = os.path.join(BASE_DIR, "dist", "Framed")
OUTPUT_DIR = os.path.join(BASE_DIR, "installer", "Output")

INNO_COMPILERS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\iscc.exe"),
    r"C:\Program Files (x86)\Inno Setup 6\iscc.exe",
    r"C:\Program Files\Inno Setup 6\iscc.exe",
]

def find_iscc() -> str:
    for path in INNO_COMPILERS:
        if os.path.exists(path):
            return path
    # Try PATH
    cmd = shutil.which("iscc")
    if cmd:
        return cmd
    raise FileNotFoundError("Inno Setup compiler (iscc.exe) not found.")

def calculate_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def build():
    print("=" * 60)
    print("  FRAMED WORKSTATION — PACKAGING PIPELINE")
    print("=" * 60)

    # Step 1: Run PyInstaller
    print("\n[1/2] Bundling executable with PyInstaller...")
    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        SPEC_FILE,
        "--noconfirm",
        "--clean"
    ]
    subprocess.check_call(pyinstaller_cmd, cwd=BASE_DIR)

    if not os.path.exists(os.path.join(DIST_DIR, "Framed.exe")):
        raise RuntimeError("PyInstaller build failed: Framed.exe not found in dist/Framed.")
    print("PyInstaller bundle generated successfully at:", DIST_DIR)

    # Step 2: Compile with Inno Setup
    print("\n[2/2] Compiling Windows installer with Inno Setup...")
    iscc_path = find_iscc()
    print("Using Inno Setup Compiler:", iscc_path)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    iscc_cmd = [iscc_path, ISS_FILE]
    subprocess.check_call(iscc_cmd, cwd=os.path.join(BASE_DIR, "installer"))

    setup_exes = [os.path.join(OUTPUT_DIR, f) for f in os.listdir(OUTPUT_DIR) if f.startswith("Framed-Setup") and f.endswith(".exe")]
    if not setup_exes:
        raise RuntimeError("Inno Setup compilation failed: Setup executable not found.")
    setup_exe = max(setup_exes, key=os.path.getmtime)

    size_mb = os.path.getsize(setup_exe) / (1024 * 1024)
    sha256 = calculate_sha256(setup_exe)

    print("\n" + "=" * 60)
    print("  BUILD COMPLETE!")
    print(f"  Installer: {setup_exe}")
    print(f"  Size:      {size_mb:.2f} MB")
    print(f"  SHA-256:   {sha256}")
    print("=" * 60)

if __name__ == "__main__":
    build()
