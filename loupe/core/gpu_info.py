"""GPU VRAM detection utilities with Windows 64-bit Registry, DXGI/CIM fallback, and safe defaults."""

import ctypes
import json
import os
import platform
import subprocess
from dataclasses import dataclass
from typing import Optional


_VIDEO_CLASS_KEY = r"SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


@dataclass
class GPUInfo:
    """Detected GPU memory capabilities."""
    name: str
    total_vram_mb: int
    available_vram_mb: int
    is_dedicated: bool


def format_memory_mb(val_mb: int) -> str:
    """Format a memory size in MB into a human-readable string."""
    val_mb = max(0, int(val_mb))
    if val_mb >= 1024:
        gb = val_mb / 1024.0
        if gb.is_integer():
            return f"{int(gb)} GB ({val_mb:,} MB)"
        return f"{gb:.1f} GB ({val_mb:,} MB)"
    return f"{val_mb:,} MB"


def _parse_reg_bytes_or_int(value) -> int:
    """Convert a Windows registry QWORD/DWORD/REG_BINARY value into an integer byte count."""
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, (bytes, bytearray)):
        if not value:
            return 0
        return int.from_bytes(value, byteorder="little", signed=False)
    return 0


def _estimate_available_vram_mb(total_mb: int) -> int:
    """Estimate usable VRAM after reserving ~512 MB (or 15%) for OS/compositor."""
    if total_mb <= 0:
        return 0
    reserve = max(256, min(1024, int(total_mb * 0.15)))
    return max(0, total_mb - reserve)


def _is_likely_dedicated(name: str, total_mb: int) -> bool:
    """Heuristic to distinguish discrete/dedicated GPUs from basic/software adapters."""
    lower = (name or "").lower()
    if total_mb < 512:
        return False
    if "microsoft basic" in lower or "remote display" in lower or "llvmpipe" in lower:
        return False
    return total_mb >= 1024 or any(v in lower for v in ("nvidia", "geforce", "rtx", "gtx", "quadro", "radeon rx", "arc"))


def _detect_via_windows_registry() -> Optional[GPUInfo]:
    """Read 64-bit HardwareInformation.qwMemorySize from Windows Display Adapter Registry keys."""
    if platform.system() != "Windows":
        return None
    try:
        import winreg
    except ImportError:
        return None

    best: Optional[GPUInfo] = None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _VIDEO_CLASS_KEY) as class_key:
            idx = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(class_key, idx)
                    idx += 1
                except OSError:
                    break

                if not subkey_name.isdigit():
                    continue

                try:
                    with winreg.OpenKey(class_key, subkey_name) as subkey:
                        raw_bytes = 0
                        for val_name in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                            try:
                                val, _ = winreg.QueryValueEx(subkey, val_name)
                                parsed = _parse_reg_bytes_or_int(val)
                                if parsed > 0:
                                    raw_bytes = parsed
                                    break
                            except OSError:
                                continue

                        if raw_bytes <= 0:
                            continue

                        name = ""
                        for name_val in ("DriverDesc", "HardwareInformation.AdapterString"):
                            try:
                                v, _ = winreg.QueryValueEx(subkey, name_val)
                                if isinstance(v, str) and v.strip():
                                    name = v.strip()
                                    break
                            except OSError:
                                continue
                        if not name:
                            name = "Dedicated GPU"

                        total_mb = int(raw_bytes // (1024 * 1024))
                        if total_mb <= 0:
                            continue

                        dedicated = _is_likely_dedicated(name, total_mb)
                        candidate = GPUInfo(
                            name=name,
                            total_vram_mb=total_mb,
                            available_vram_mb=_estimate_available_vram_mb(total_mb),
                            is_dedicated=dedicated,
                        )
                        if best is None or (candidate.is_dedicated and not best.is_dedicated) or (
                            candidate.is_dedicated == best.is_dedicated and candidate.total_vram_mb > best.total_vram_mb
                        ):
                            best = candidate
                except OSError:
                    continue
    except OSError:
        return None

    return best


def _detect_via_dxgi() -> Optional[GPUInfo]:
    """Fallback GPU detection via Windows DXGI ctypes (CreateDXGIFactory1 -> EnumAdapters1)."""
    if platform.system() != "Windows":
        return None
    try:
        dxgi = ctypes.windll.dxgi

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        class LUID(ctypes.Structure):
            _fields_ = [("LowPart", ctypes.c_uint32), ("HighPart", ctypes.c_int32)]

        class DXGI_ADAPTER_DESC1(ctypes.Structure):
            _fields_ = [
                ("Description", ctypes.c_wchar * 128),
                ("VendorId", ctypes.c_uint32),
                ("DeviceId", ctypes.c_uint32),
                ("SubSysId", ctypes.c_uint32),
                ("Revision", ctypes.c_uint32),
                ("DedicatedVideoMemory", ctypes.c_size_t),
                ("DedicatedSystemMemory", ctypes.c_size_t),
                ("SharedSystemMemory", ctypes.c_size_t),
                ("AdapterLuid", LUID),
                ("Flags", ctypes.c_uint32),
            ]

        # IID_IDXGIFactory1 = {770aae78-f26f-4dba-a829-253c83d1b387}
        iid_factory1 = GUID(
            0x770AAE78, 0xF26F, 0x4DBA,
            (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87),
        )
        factory_ptr = ctypes.c_void_p()
        hr = dxgi.CreateDXGIFactory1(ctypes.byref(iid_factory1), ctypes.byref(factory_ptr))
        if hr != 0 or not factory_ptr.value:
            return None

        def _vtable_fn(com_ptr, index, restype, *argtypes):
            vtable = ctypes.cast(com_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
            return proto(vtable[index])

        release_factory = _vtable_fn(factory_ptr, 2, ctypes.c_ulong)
        enum_adapters1 = _vtable_fn(factory_ptr, 12, ctypes.c_long, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))

        best: Optional[GPUInfo] = None
        try:
            idx = 0
            while True:
                adapter_ptr = ctypes.c_void_p()
                res = enum_adapters1(factory_ptr, idx, ctypes.byref(adapter_ptr))
                idx += 1
                if res != 0 or not adapter_ptr.value:
                    break
                release_adapter = _vtable_fn(adapter_ptr, 2, ctypes.c_ulong)
                get_desc1 = _vtable_fn(adapter_ptr, 10, ctypes.c_long, ctypes.POINTER(DXGI_ADAPTER_DESC1))
                try:
                    desc = DXGI_ADAPTER_DESC1()
                    if get_desc1(adapter_ptr, ctypes.byref(desc)) == 0:
                        # Skip software adapters (DXGI_ADAPTER_FLAG_SOFTWARE = 2)
                        if desc.Flags & 2:
                            continue
                        total_mb = int(desc.DedicatedVideoMemory // (1024 * 1024))
                        if total_mb <= 0:
                            continue
                        name = desc.Description.strip() or "GPU Adapter"
                        dedicated = _is_likely_dedicated(name, total_mb)
                        candidate = GPUInfo(
                            name=name,
                            total_vram_mb=total_mb,
                            available_vram_mb=_estimate_available_vram_mb(total_mb),
                            is_dedicated=dedicated,
                        )
                        if best is None or candidate.total_vram_mb > best.total_vram_mb:
                            best = candidate
                finally:
                    release_adapter(adapter_ptr)
        finally:
            release_factory(factory_ptr)

        return best
    except Exception:
        return None


def _detect_via_cim() -> Optional[GPUInfo]:
    """Fallback GPU detection via PowerShell Win32_VideoController (32-bit AdapterRAM capped at ~4 GB)."""
    if platform.system() != "Windows":
        return None
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json",
            ],
            capture_output=True,
            text=True,
            timeout=2.5,
            creationflags=creationflags,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        data = json.loads(proc.stdout)
        entries = data if isinstance(data, list) else [data]
        best: Optional[GPUInfo] = None
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            ram_bytes = int(entry.get("AdapterRAM") or 0)
            total_mb = ram_bytes // (1024 * 1024)
            if total_mb <= 0:
                continue
            name = str(entry.get("Name") or "GPU Adapter").strip()
            dedicated = _is_likely_dedicated(name, total_mb)
            candidate = GPUInfo(
                name=name,
                total_vram_mb=total_mb,
                available_vram_mb=_estimate_available_vram_mb(total_mb),
                is_dedicated=dedicated,
            )
            if best is None or candidate.total_vram_mb > best.total_vram_mb:
                best = candidate
        return best
    except Exception:
        return None


def detect_gpu_vram() -> GPUInfo:
    """Detect the primary GPU and its VRAM capacity safely across Windows and non-Windows platforms."""
    for detector in (_detect_via_windows_registry, _detect_via_dxgi, _detect_via_cim):
        try:
            info = detector()
            if info is not None and info.total_vram_mb > 0:
                return info
        except Exception:
            continue

    return GPUInfo(
        name="Integrated / Software Fallback",
        total_vram_mb=0,
        available_vram_mb=0,
        is_dedicated=False,
    )


def get_total_vram_gb() -> int:
    """Return total detected GPU VRAM in whole GB (0 if no VRAM detected)."""
    try:
        info = detect_gpu_vram()
        if info.total_vram_mb <= 0:
            return 0
        return max(1, round(info.total_vram_mb / 1024.0))
    except Exception:
        return 0
