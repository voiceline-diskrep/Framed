"""Data models for Loupe Photo Inspection & Culling Workstation."""

import os
import uuid
import dataclasses
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any

@dataclass
class PhotoItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    base_name: str = ""
    raw_path: Optional[str] = None
    jpeg_path: Optional[str] = None
    primary_path: str = ""
    raw_size: int = 0
    jpeg_size: int = 0
    status: str = "pending"  # "pending", "kept"/"selected", "maybe"/"similar", "rejected"/"unselected"
    metadata: Dict[str, Any] = field(default_factory=dict)
    proxy_path: Optional[str] = None
    duration_seconds: float = 0.0
    is_video: bool = False

    @property
    def total_size_bytes(self) -> int:
        return self.raw_size + self.jpeg_size

    @property
    def has_both(self) -> bool:
        return bool(self.raw_path and self.jpeg_path)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PhotoItem":
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class Folder:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Personal"
    parent_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Folder":
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class Project:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled Session"
    folder_id: str = "default"
    source_dir: str = ""
    format_mode: str = "both"  # "raw_only", "jpeg_only", "both"
    sync_pairs: bool = True
    ram_allocation_mb: int = 2048
    batch_size: int = 16
    shoot_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_opened_at: str = field(default_factory=lambda: datetime.now().isoformat())
    current_index: int = 0
    items: List[PhotoItem] = field(default_factory=list)
    edited_result_dir: str = ""
    edited_files: List[str] = field(default_factory=list)
    media_type: str = "photo"  # "photo" or "video"
    view_uncompressed: bool = False
    is_match_mode: bool = False
    max_selected_count: int = 0
    preview_mode: str = "raw"  # "raw" or "jpeg"
    link_to_raw: bool = True

    @property
    def edited_count(self) -> int:
        if self.edited_files:
            return len(self.edited_files)
        if self.edited_result_dir and os.path.exists(self.edited_result_dir):
            try:
                return len([f for f in os.listdir(self.edited_result_dir) if os.path.isfile(os.path.join(self.edited_result_dir, f))])
            except Exception:
                return 0
        return 0

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def selected_count(self) -> int:
        return sum(1 for item in self.items if item.status in ("kept", "selected"))

    @property
    def similar_count(self) -> int:
        return sum(1 for item in self.items if item.status in ("similar", "maybe"))

    @property
    def maybe_count(self) -> int:
        return sum(1 for item in self.items if item.status in ("maybe", "similar"))

    @property
    def unselected_count(self) -> int:
        return sum(1 for item in self.items if item.status in ("rejected", "unselected"))

    @property
    def kept_count(self) -> int:
        return self.selected_count

    @property
    def rejected_count(self) -> int:
        return self.unselected_count

    @property
    def pending_count(self) -> int:
        return sum(1 for item in self.items if item.status == "pending")

    @property
    def progress_percent(self) -> int:
        if not self.items:
            return 0
        culled = sum(1 for item in self.items if item.status != "pending")
        return int((culled / len(self.items)) * 100)

    @property
    def status_label(self) -> str:
        if not self.items:
            return "Empty Session"
        culled = sum(1 for item in self.items if item.status != "pending")
        if culled == 0:
            return "Unstarted"
        if culled == len(self.items):
            return "Completed"
        term = "sorted" if self.media_type == "video" else "culled"
        return f"In Progress ({culled}/{len(self.items)} {term})"

    @property
    def is_over_quota(self) -> bool:
        return bool(self.is_match_mode and self.max_selected_count > 0 and self.selected_count > self.max_selected_count)

    @property
    def quota_remaining(self) -> int:
        if not self.is_match_mode or self.max_selected_count <= 0:
            return 0
        return max(0, self.max_selected_count - self.selected_count)

    def get_workspace_name(self) -> str:
        """Returns the human-readable name of the workspace folder this project belongs to (including parent path if nested)."""
        try:
            from loupe.storage import storage
            if self.folder_id:
                path = storage.get_folder_path(self.folder_id)
                if path:
                    return path
                folder = storage.get_folder_by_id(self.folder_id)
                if folder and folder.name.strip():
                    return folder.name.strip()
            # If not assigned or not found, prefer "Personal"
            all_folders = storage.get_folders()
            for f in all_folders:
                if f.name.strip().lower() == "personal":
                    return f.name.strip()
            if all_folders:
                return all_folders[0].name.strip()
        except Exception:
            pass
        return "Personal"

    def get_workspace_parts(self) -> List[str]:
        """Returns the list of folder names in hierarchy order, e.g. ['Commercial', 'Brand Deals']."""
        try:
            from loupe.storage import storage
            if self.folder_id:
                parts = storage.get_folder_parts(self.folder_id)
                if parts:
                    return parts
        except Exception:
            pass
        return ["Personal"]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["items"] = [item.to_dict() for item in self.items]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        data_copy = dict(data)
        items_data = data_copy.pop("items", [])
        items = [PhotoItem.from_dict(i) for i in items_data]
        valid_fields = {f.name for f in dataclasses.fields(cls) if f.name != "items"}
        filtered = {k: v for k, v in data_copy.items() if k in valid_fields}
        return cls(items=items, **filtered)
