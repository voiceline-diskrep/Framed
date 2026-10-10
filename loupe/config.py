"""Configuration manager for Loupe Photo Inspection & Culling Workstation."""

import json
import os
import copy
import psutil
from typing import Dict, Any

DEFAULT_CONFIG: Dict[str, Any] = {
    "ram_budget_gb": 16,
    "key_bindings": {
        "keep": "W",
        "reject": "S",
        "prev": "A",
        "next": "D",
    },
    "start_zoomed_in": False,
    "zoom_start_level": 2.0,  # 200% zoom
    "default_sync_pairs": True,
    "default_export_dir": "",
    "has_completed_tour": False,
    "theme_mode": "dark",
    "auto_check_updates": True,
    "update_manifest_url": "",
    "app_version": "1.0.0",
}

def get_app_dir() -> str:
    """Return the application storage directory in APPDATA or home, migrating from Loupe if needed."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        path = os.path.join(appdata, "FramedWorkstation")
        old_path = os.path.join(appdata, "LoupeWorkstation")
    else:
        path = os.path.join(os.path.expanduser("~"), ".framed_workstation")
        old_path = os.path.join(os.path.expanduser("~"), ".loupe_workstation")

    os.makedirs(path, exist_ok=True)

    # Migrate previous Loupe database and settings if they exist and haven't been copied
    if os.path.exists(old_path):
        import shutil
        for fname in ["database.json", "settings.json"]:
            old_file = os.path.join(old_path, fname)
            new_file = os.path.join(path, fname)
            if os.path.exists(old_file) and not os.path.exists(new_file):
                try:
                    shutil.copy2(old_file, new_file)
                except Exception:
                    pass
    return path

def get_config_path() -> str:
    return os.path.join(get_app_dir(), "settings.json")

def get_total_system_ram_gb() -> int:
    try:
        mem = psutil.virtual_memory()
        return max(4, int(mem.total / (1024 ** 3)))
    except Exception:
        return 16

class ConfigManager:
    def __init__(self):
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        # Calibrate default RAM budget to min(16, total_system_ram // 2)
        total_ram = get_total_system_ram_gb()
        self._config["ram_budget_gb"] = min(16, max(4, total_ram // 2))
        pictures_dir = os.path.join(os.path.expanduser("~"), "Pictures", "Framed Exports")
        self._config["default_export_dir"] = pictures_dir
        self.load()

    def load(self) -> None:
        path = get_config_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        # Merge recursively for key_bindings
                        for k, v in data.items():
                            if k == "key_bindings" and isinstance(v, dict):
                                self._config["key_bindings"].update(v)
                            else:
                                self._config[k] = v
            except Exception as e:
                print(f"Warning: Failed to load config from {path}: {e}")

    def save(self) -> None:
        path = get_config_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save config to {path}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._config[key] = value
        self.save()

    def get_key_binding(self, action: str) -> str:
        return self._config.get("key_bindings", {}).get(action, DEFAULT_CONFIG["key_bindings"].get(action, "W"))

    def set_key_binding(self, action: str, key: str) -> None:
        if "key_bindings" not in self._config:
            self._config["key_bindings"] = {}
        self._config["key_bindings"][action] = key.upper()
        self.save()

    def reset_to_defaults(self) -> None:
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        total_ram = get_total_system_ram_gb()
        self._config["ram_budget_gb"] = min(16, max(4, total_ram // 2))
        self._config["default_export_dir"] = os.path.join(os.path.expanduser("~"), "Pictures", "Loupe Exports")
        self.save()

# Global config instance
config = ConfigManager()
