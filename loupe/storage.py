"""Persistent storage engine for Loupe folders, projects, and the Complete Gallery System."""

import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from loupe.config import get_app_dir
from loupe.models import (
    Folder, Project, GalleryFolder, GalleryPhoto, SmartAlbum,
    GalleryActivity, BackupRecord
)


def format_bytes(size_bytes: int) -> str:
    """Formats byte counts into human-readable KB / MB / GB strings."""
    b = max(0, int(size_bytes or 0))
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    if b < 1024 * 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    return f"{b / (1024 * 1024 * 1024):.1f} GB"


class StorageManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path if db_path else os.path.join(get_app_dir(), "database.json")
        self.folders: Dict[str, Folder] = {}
        self.projects: Dict[str, Project] = {}
        # Gallery collections
        self.gallery_folders: Dict[str, GalleryFolder] = {}
        self.gallery_photos: Dict[str, GalleryPhoto] = {}
        self.smart_albums: Dict[str, SmartAlbum] = {}
        self.gallery_activities: List[GalleryActivity] = []
        self.backup_records: List[BackupRecord] = []
        self.load()

    @property
    def data_dir(self) -> str:
        return os.path.dirname(self.db_path)

    @property
    def gallery_managed_dir(self) -> str:
        d = os.path.join(self.data_dir, "gallery_media")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def gallery_thumbs_dir(self) -> str:
        d = os.path.join(self.data_dir, "gallery_thumbnails")
        os.makedirs(d, exist_ok=True)
        return d

    def load(self) -> None:
        self.folders.clear()
        self.projects.clear()
        self.gallery_folders.clear()
        self.gallery_photos.clear()
        self.smart_albums.clear()
        self.gallery_activities.clear()
        self.backup_records.clear()

        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for f_data in data.get("folders", []):
                        f_obj = Folder.from_dict(f_data)
                        self.folders[f_obj.id] = f_obj
                    for p_data in data.get("projects", []):
                        p_obj = Project.from_dict(p_data)
                        self.projects[p_obj.id] = p_obj
                    for gf_data in data.get("gallery_folders", []):
                        gf_obj = GalleryFolder.from_dict(gf_data)
                        self.gallery_folders[gf_obj.id] = gf_obj
                    for gp_data in data.get("gallery_photos", []):
                        gp_obj = GalleryPhoto.from_dict(gp_data)
                        self.gallery_photos[gp_obj.id] = gp_obj
                    for sa_data in data.get("smart_albums", []):
                        sa_obj = SmartAlbum.from_dict(sa_data)
                        self.smart_albums[sa_obj.id] = sa_obj
                    for act_data in data.get("gallery_activities", []):
                        self.gallery_activities.append(GalleryActivity.from_dict(act_data))
                    for br_data in data.get("backup_records", []):
                        self.backup_records.append(BackupRecord.from_dict(br_data))

                if not self.gallery_folders and not self.smart_albums:
                    self._seed_gallery_defaults(save_after=False)
                return
            except Exception as e:
                print(f"Error loading database from {self.db_path}: {e}")

        # Seed with initial folders if completely fresh
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        personal = Folder(id="folder_personal", name="Personal")
        work = Folder(id="folder_work", name="Work")
        for f in (personal, work):
            self.folders[f.id] = f
        self._seed_gallery_defaults(save_after=False)
        self.save()

    def _seed_gallery_defaults(self, save_after: bool = True) -> None:
        if not self.gallery_folders:
            f_personal = GalleryFolder(id="gf_personal", name="Personal")
            f_school = GalleryFolder(id="gf_school", name="School")
            f_work = GalleryFolder(id="gf_work", name="Work")
            for gf in (f_personal, f_school, f_work):
                self.gallery_folders[gf.id] = gf

        if not self.smart_albums:
            builtins = [
                SmartAlbum(id="sa_raw", name="All RAW Photographs", rules={"format_type": "RAW"}, is_builtin=True),
                SmartAlbum(id="sa_jpeg", name="All JPEG Photographs", rules={"format_type": "JPEG"}, is_builtin=True),
                SmartAlbum(id="sa_2026", name="Photos from 2026", rules={"year": "2026"}, is_builtin=True),
                SmartAlbum(id="sa_5star", name="Five-Star Masterpieces", rules={"min_rating": 5}, is_builtin=True),
                SmartAlbum(id="sa_fav", name="All Favorites", rules={"is_favorite": True}, is_builtin=True),
                SmartAlbum(id="sa_large", name="Large Files (>15 MB)", rules={"min_size_mb": 15}, is_builtin=True),
                SmartAlbum(id="sa_unrated", name="Unrated Photos", rules={"unrated_only": True}, is_builtin=True),
            ]
            for sa in builtins:
                self.smart_albums[sa.id] = sa

        if save_after:
            self.save()

    def save(self) -> None:
        data = {
            "folders": [f.to_dict() for f in self.folders.values()],
            "projects": [p.to_dict() for p in self.projects.values()],
            "gallery_folders": [gf.to_dict() for gf in self.gallery_folders.values()],
            "gallery_photos": [gp.to_dict() for gp in self.gallery_photos.values()],
            "smart_albums": [sa.to_dict() for sa in self.smart_albums.values()],
            "gallery_activities": [a.to_dict() for a in self.gallery_activities[:100]],
            "backup_records": [b.to_dict() for b in self.backup_records[:50]],
        }
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving database to {self.db_path}: {e}")

    # ==========================================================================
    # WORKSPACE FOLDER & PROJECT OPERATIONS (Photosort / Videosort)
    # ==========================================================================
    def get_folders(self) -> List[Folder]:
        return sorted(list(self.folders.values()), key=lambda f: f.name.lower())

    def get_folder_by_id(self, folder_id: str) -> Optional[Folder]:
        if not folder_id:
            return None
        f = self.folders.get(folder_id)
        if not f and os.path.exists(self.db_path):
            self.load()
            f = self.folders.get(folder_id)
        return f

    def create_folder(self, name: str, parent_id: Optional[str] = None) -> Folder:
        folder = Folder(name=name.strip(), parent_id=parent_id)
        self.folders[folder.id] = folder
        self.save()
        return folder

    def get_top_level_folders(self) -> List[Folder]:
        folders = [f for f in self.folders.values() if not f.parent_id or f.parent_id not in self.folders]
        return sorted(folders, key=lambda f: f.name.lower())

    def get_subfolders(self, parent_id: str) -> List[Folder]:
        folders = [f for f in self.folders.values() if getattr(f, "parent_id", None) == parent_id]
        return sorted(folders, key=lambda f: f.name.lower())

    def get_folder_ancestry(self, folder_id: str) -> List[Folder]:
        """Returns the ancestor chain from root down to this folder."""
        if folder_id not in self.folders and os.path.exists(self.db_path):
            self.load()
        chain = []
        visited = set()
        curr_id = folder_id
        while curr_id and curr_id in self.folders and curr_id not in visited:
            visited.add(curr_id)
            f = self.folders[curr_id]
            chain.append(f)
            curr_id = getattr(f, "parent_id", None)
        chain.reverse()
        return chain

    def get_folder_path(self, folder_id: str) -> str:
        chain = self.get_folder_ancestry(folder_id)
        return " / ".join(f.name.strip() for f in chain) if chain else ""

    def get_folder_parts(self, folder_id: str) -> List[str]:
        chain = self.get_folder_ancestry(folder_id)
        return [f.name.strip() for f in chain] if chain else []

    def get_folder_descendant_ids(self, folder_id: str) -> List[str]:
        """Returns all descendant folder IDs recursively."""
        descendants = []
        for sub in self.get_subfolders(folder_id):
            descendants.append(sub.id)
            descendants.extend(self.get_folder_descendant_ids(sub.id))
        return descendants

    def get_folders_with_depth(self) -> List[Any]:
        """Returns flattened list of (folder, depth) ordered hierarchically for trees & dropdowns."""
        result = []
        def _walk(parent_id: Optional[str], depth: int):
            if parent_id is None:
                subs = self.get_top_level_folders()
            else:
                subs = self.get_subfolders(parent_id)
            for f in subs:
                result.append((f, depth))
                _walk(f.id, depth + 1)
        _walk(None, 0)
        return result

    def rename_folder(self, folder_id: str, new_name: str) -> Optional[Folder]:
        folder = self.folders.get(folder_id)
        if folder:
            folder.name = new_name.strip()
            self.save()
        return folder

    def update_folder_parent(self, folder_id: str, new_parent_id: Optional[str]) -> bool:
        folder = self.folders.get(folder_id)
        if not folder or folder_id == new_parent_id:
            return False
        if new_parent_id and new_parent_id in self.get_folder_descendant_ids(folder_id):
            return False
        folder.parent_id = new_parent_id
        self.save()
        return True

    def delete_folder(self, folder_id: str) -> bool:
        if folder_id in self.folders:
            descendant_ids = set(self.get_folder_descendant_ids(folder_id))
            all_to_remove = descendant_ids | {folder_id}

            other_folders = [fid for fid in self.folders if fid not in all_to_remove]
            fallback_id = other_folders[0] if other_folders else "folder_personal"
            for project in self.projects.values():
                if project.folder_id in all_to_remove:
                    project.folder_id = fallback_id

            for fid in all_to_remove:
                if fid in self.folders:
                    del self.folders[fid]
            self.save()
            return True
        return False

    def get_projects(self, folder_id: Optional[str] = None, media_type: Optional[str] = None) -> List[Project]:
        projs = list(self.projects.values())
        if folder_id:
            projs = [p for p in projs if p.folder_id == folder_id]
        if media_type:
            projs = [p for p in projs if getattr(p, "media_type", "photo") == media_type]
        return sorted(projs, key=lambda p: p.last_opened_at, reverse=True)

    def get_project_by_id(self, project_id: str) -> Optional[Project]:
        return self.projects.get(project_id)

    def save_project(self, project: Project) -> None:
        self.projects[project.id] = project
        self.save()

    def delete_project(self, project_id: str) -> bool:
        if project_id in self.projects:
            del self.projects[project_id]
            self.save()
            return True
        return False

    def update_project_date(self, project_id: str, new_date: str) -> bool:
        project = self.projects.get(project_id)
        if project:
            project.shoot_date = new_date.strip()
            self.save()
            return True
        return False

    def update_project_folder(self, project_id: str, new_folder_id: str) -> bool:
        project = self.projects.get(project_id)
        if project:
            project.folder_id = new_folder_id
            self.save()
            return True
        return False

    def update_project_name(self, project_id: str, new_name: str) -> bool:
        project = self.projects.get(project_id)
        if project:
            project.name = new_name.strip()
            self.save()
            return True
        return False

    # ==========================================================================
    # GALLERY FOLDER OPERATIONS
    # ==========================================================================
    def log_gallery_activity(self, action_type: str, title: str, save_now: bool = True) -> GalleryActivity:
        act = GalleryActivity(action_type=action_type, title=title)
        self.gallery_activities.insert(0, act)
        self.gallery_activities = self.gallery_activities[:100]
        if save_now:
            self.save()
        return act

    def get_gallery_folders(self) -> List[GalleryFolder]:
        if not self.gallery_folders:
            self._seed_gallery_defaults(save_after=False)
        return sorted(list(self.gallery_folders.values()), key=lambda f: f.name.lower())

    def get_gallery_folder_by_id(self, folder_id: str) -> Optional[GalleryFolder]:
        if not folder_id:
            return None
        return self.gallery_folders.get(folder_id)

    def get_top_level_gallery_folders(self) -> List[GalleryFolder]:
        if not self.gallery_folders:
            self._seed_gallery_defaults(save_after=False)
        folders = [f for f in self.gallery_folders.values() if not f.parent_id or f.parent_id not in self.gallery_folders]
        return sorted(folders, key=lambda f: f.name.lower())

    def get_gallery_subfolders(self, parent_id: str) -> List[GalleryFolder]:
        folders = [f for f in self.gallery_folders.values() if f.parent_id == parent_id]
        return sorted(folders, key=lambda f: f.name.lower())

    def get_gallery_folder_descendant_ids(self, folder_id: str) -> List[str]:
        descendants = []
        for sub in self.get_gallery_subfolders(folder_id):
            descendants.append(sub.id)
            descendants.extend(self.get_gallery_folder_descendant_ids(sub.id))
        return descendants

    def get_gallery_folder_ancestry(self, folder_id: str) -> List[GalleryFolder]:
        chain = []
        visited = set()
        curr_id = folder_id
        while curr_id and curr_id in self.gallery_folders and curr_id not in visited:
            visited.add(curr_id)
            f = self.gallery_folders[curr_id]
            chain.append(f)
            curr_id = f.parent_id
        chain.reverse()
        return chain

    def get_gallery_folder_path(self, folder_id: str) -> str:
        chain = self.get_gallery_folder_ancestry(folder_id)
        return " / ".join(f.name.strip() for f in chain) if chain else ""

    def get_gallery_folders_with_depth(self) -> List[Tuple[GalleryFolder, int]]:
        result = []
        def _walk(parent_id: Optional[str], depth: int):
            subs = self.get_top_level_gallery_folders() if parent_id is None else self.get_gallery_subfolders(parent_id)
            for f in subs:
                result.append((f, depth))
                _walk(f.id, depth + 1)
        _walk(None, 0)
        return result

    def create_gallery_folder(self, name: str, parent_id: Optional[str] = None) -> GalleryFolder:
        gf = GalleryFolder(name=name.strip(), parent_id=parent_id)
        self.gallery_folders[gf.id] = gf
        self.log_gallery_activity("folder", f"Created folder '{gf.name}'", save_now=False)
        self.save()
        return gf

    def rename_gallery_folder(self, folder_id: str, new_name: str) -> Optional[GalleryFolder]:
        gf = self.gallery_folders.get(folder_id)
        if gf:
            old_name = gf.name
            gf.name = new_name.strip()
            self.log_gallery_activity("folder", f"Renamed folder '{old_name}' to '{gf.name}'", save_now=False)
            self.save()
        return gf

    def delete_gallery_folder(self, folder_id: str, reassign_to_folder_id: Optional[str] = None) -> bool:
        """Deletes a Gallery folder (and subfolders) WITHOUT deleting any photographs.
        If reassign_to_folder_id is given, moves contained photos into that folder;
        otherwise keeps them safely in All Photos (unassigned from the deleted folder)."""
        if folder_id not in self.gallery_folders:
            return False
        folder_name = self.gallery_folders[folder_id].name
        descendant_ids = set(self.get_gallery_folder_descendant_ids(folder_id))
        all_to_remove = descendant_ids | {folder_id}

        for photo in self.gallery_photos.values():
            if any(fid in all_to_remove for fid in photo.folder_ids):
                photo.folder_ids = [fid for fid in photo.folder_ids if fid not in all_to_remove]
                if reassign_to_folder_id and reassign_to_folder_id in self.gallery_folders:
                    if reassign_to_folder_id not in photo.folder_ids:
                        photo.folder_ids.append(reassign_to_folder_id)

        for fid in all_to_remove:
            if fid in self.gallery_folders:
                del self.gallery_folders[fid]

        self.log_gallery_activity("folder", f"Removed folder '{folder_name}' (photos preserved)", save_now=False)
        self.save()
        return True

    def count_photos_in_gallery_folder(self, folder_id: str, include_subfolders: bool = True) -> int:
        target_ids = {folder_id}
        if include_subfolders:
            target_ids |= set(self.get_gallery_folder_descendant_ids(folder_id))
        return sum(
            1 for p in self.gallery_photos.values()
            if not p.is_deleted and any(fid in target_ids for fid in p.folder_ids)
        )

    # ==========================================================================
    # GALLERY PHOTO & SMART ALBUM OPERATIONS
    # ==========================================================================
    def add_gallery_photo(self, photo: GalleryPhoto, save_now: bool = True) -> GalleryPhoto:
        self.gallery_photos[photo.id] = photo
        if save_now:
            self.save()
        return photo

    def get_gallery_photo_by_id(self, photo_id: str) -> Optional[GalleryPhoto]:
        return self.gallery_photos.get(photo_id)

    def get_active_gallery_photos(self) -> List[GalleryPhoto]:
        return [p for p in self.gallery_photos.values() if not p.is_deleted]

    def get_deleted_gallery_photos(self) -> List[GalleryPhoto]:
        return sorted(
            [p for p in self.gallery_photos.values() if p.is_deleted],
            key=lambda p: p.deleted_at or "",
            reverse=True
        )

    def get_missing_gallery_photos(self) -> List[GalleryPhoto]:
        self.refresh_missing_file_status(save_now=False)
        return [p for p in self.gallery_photos.values() if not p.is_deleted and p.is_missing]

    def refresh_missing_file_status(self, save_now: bool = True) -> int:
        missing_count = 0
        changed = False
        for p in self.gallery_photos.values():
            path = p.active_path
            exists = bool(path and os.path.exists(path))
            new_missing = not exists
            if p.is_missing != new_missing:
                p.is_missing = new_missing
                changed = True
            if new_missing and not p.is_deleted:
                missing_count += 1
        if changed and save_now:
            self.save()
        return missing_count

    def query_gallery_photos(
        self,
        section: str = "all",  # "all", "favorites", "raw", "jpeg", "other", "recent", "missing", "deleted", "folder:<id>", "smart:<id>"
        search_query: str = "",
        format_filter: str = "All",  # "All", "RAW", "JPEG", "Other", "Favorites", "Recent", "5★"
        min_rating: int = 0,
        color_label: str = "any",
        sort_by: str = "newest",  # "newest", "oldest", "name_asc", "name_desc", "size_desc", "size_asc", "rating_desc"
    ) -> List[GalleryPhoto]:
        if section == "deleted":
            items = [p for p in self.gallery_photos.values() if p.is_deleted]
        else:
            items = [p for p in self.gallery_photos.values() if not p.is_deleted]

        if section == "favorites":
            items = [p for p in items if p.is_favorite]
        elif section == "raw":
            items = [p for p in items if p.format_type == "RAW"]
        elif section == "jpeg":
            items = [p for p in items if p.format_type == "JPEG"]
        elif section == "other":
            items = [p for p in items if p.format_type == "OTHER"]
        elif section == "missing":
            items = [p for p in items if p.is_missing or not (p.active_path and os.path.exists(p.active_path))]
        elif section == "recent":
            items = sorted(items, key=lambda p: p.imported_at, reverse=True)[:100]
        elif section.startswith("folder:"):
            fid = section.split(":", 1)[1]
            target_ids = {fid} | set(self.get_gallery_folder_descendant_ids(fid))
            items = [p for p in items if any(f in target_ids for f in p.folder_ids)]
        elif section.startswith("smart:"):
            said = section.split(":", 1)[1]
            sa = self.smart_albums.get(said)
            if sa:
                items = [p for p in items if sa.matches(p)]

        # Additional pill filter
        if format_filter == "RAW":
            items = [p for p in items if p.format_type == "RAW"]
        elif format_filter == "JPEG":
            items = [p for p in items if p.format_type == "JPEG"]
        elif format_filter == "Other":
            items = [p for p in items if p.format_type == "OTHER"]
        elif format_filter == "Favorites":
            items = [p for p in items if p.is_favorite]
        elif format_filter == "5★":
            items = [p for p in items if p.rating >= 5]

        if min_rating > 0:
            items = [p for p in items if p.rating >= min_rating]

        if color_label and color_label not in ("any", "all"):
            items = [p for p in items if p.color_label == color_label]

        # Global Search (filename, folder names, camera model, format, location, notes)
        if search_query and search_query.strip():
            q = search_query.strip().lower()
            filtered = []
            for p in items:
                folder_names = " ".join(
                    self.gallery_folders[fid].name.lower()
                    for fid in p.folder_ids if fid in self.gallery_folders
                )
                searchable = " ".join([
                    p.filename.lower(),
                    p.camera.lower(),
                    p.camera_model.lower(),
                    p.lens.lower(),
                    p.format_type.lower(),
                    p.ext.lower(),
                    p.capture_date.lower(),
                    p.location_name.lower(),
                    p.notes.lower(),
                    folder_names,
                ])
                if q in searchable:
                    filtered.append(p)
            items = filtered

        # Sorting
        if sort_by == "newest":
            items.sort(key=lambda p: (p.capture_date, p.imported_at), reverse=True)
        elif sort_by == "oldest":
            items.sort(key=lambda p: (p.capture_date, p.imported_at), reverse=False)
        elif sort_by == "name_asc":
            items.sort(key=lambda p: p.filename.lower())
        elif sort_by == "name_desc":
            items.sort(key=lambda p: p.filename.lower(), reverse=True)
        elif sort_by == "size_desc":
            items.sort(key=lambda p: p.size_bytes, reverse=True)
        elif sort_by == "size_asc":
            items.sort(key=lambda p: p.size_bytes)
        elif sort_by == "rating_desc":
            items.sort(key=lambda p: (p.rating, p.is_favorite, p.capture_date), reverse=True)

        return items

    def move_photos_to_gallery_folder(self, photo_ids: List[str], target_folder_id: Optional[str], keep_existing_folders: bool = False) -> int:
        count = 0
        for pid in photo_ids:
            p = self.gallery_photos.get(pid)
            if p:
                if not keep_existing_folders:
                    p.folder_ids = [target_folder_id] if target_folder_id else []
                else:
                    if target_folder_id and target_folder_id not in p.folder_ids:
                        p.folder_ids.append(target_folder_id)
                count += 1
        if count > 0:
            fname = self.gallery_folders[target_folder_id].name if (target_folder_id and target_folder_id in self.gallery_folders) else "All Photos"
            self.log_gallery_activity("folder", f"Moved {count} photo(s) to '{fname}'", save_now=False)
            self.save()
        return count

    def toggle_photo_favorite(self, photo_id: str) -> bool:
        p = self.gallery_photos.get(photo_id)
        if p:
            p.is_favorite = not p.is_favorite
            if p.is_favorite:
                self.log_gallery_activity("favorite", f"Starred '{p.filename}' as Favorite", save_now=False)
            self.save()
            return p.is_favorite
        return False

    def bulk_set_favorite(self, photo_ids: List[str], is_fav: bool = True) -> int:
        count = 0
        for pid in photo_ids:
            p = self.gallery_photos.get(pid)
            if p and p.is_favorite != is_fav:
                p.is_favorite = is_fav
                count += 1
        if count > 0:
            action = "Added" if is_fav else "Removed"
            self.log_gallery_activity("favorite", f"{action} {count} favorite(s)", save_now=False)
            self.save()
        return count

    def set_photo_rating(self, photo_ids: List[str], rating: int, color_label: Optional[str] = None, notes: Optional[str] = None) -> int:
        count = 0
        rating = max(0, min(5, int(rating)))
        for pid in photo_ids:
            p = self.gallery_photos.get(pid)
            if p:
                p.rating = rating
                if color_label is not None:
                    p.color_label = color_label
                if notes is not None:
                    p.notes = notes
                count += 1
        if count > 0:
            self.save()
        return count

    def soft_delete_photos(self, photo_ids: List[str]) -> int:
        """Moves photos to Recently Deleted without deleting original files."""
        count = 0
        now_iso = datetime.now().isoformat()
        for pid in photo_ids:
            p = self.gallery_photos.get(pid)
            if p and not p.is_deleted:
                p.is_deleted = True
                p.deleted_at = now_iso
                p.previous_folder_ids = list(p.folder_ids)
                count += 1
        if count > 0:
            self.log_gallery_activity("delete", f"Moved {count} photo(s) to Recently Deleted", save_now=False)
            self.save()
        return count

    def restore_deleted_photos(self, photo_ids: List[str]) -> int:
        """Restores photos from Recently Deleted back to their previous folder associations."""
        count = 0
        for pid in photo_ids:
            p = self.gallery_photos.get(pid)
            if p and p.is_deleted:
                p.is_deleted = False
                p.deleted_at = None
                valid_folders = [fid for fid in p.previous_folder_ids if fid in self.gallery_folders]
                if valid_folders:
                    p.folder_ids = valid_folders
                count += 1
        if count > 0:
            self.log_gallery_activity("import", f"Restored {count} photo(s) from Recently Deleted", save_now=False)
            self.save()
        return count

    def permanently_remove_photos(self, photo_ids: List[str], delete_from_disk: bool = False) -> int:
        """Removes photo records from Gallery.
        Only deletes physical files if delete_from_disk=True was explicitly confirmed by the user."""
        count = 0
        for pid in list(photo_ids):
            p = self.gallery_photos.get(pid)
            if not p:
                continue
            # Always clean up cached thumbnail if present
            if p.thumbnail_path and os.path.exists(p.thumbnail_path):
                try:
                    os.remove(p.thumbnail_path)
                except Exception:
                    pass
            # If managed copy exists and we are removing from gallery, remove managed copy
            if p.is_managed and p.managed_path and os.path.exists(p.managed_path):
                try:
                    os.remove(p.managed_path)
                except Exception:
                    pass
            # NEVER delete original_path unless explicitly requested
            if delete_from_disk and p.original_path and os.path.exists(p.original_path):
                try:
                    os.remove(p.original_path)
                except Exception:
                    pass
            del self.gallery_photos[pid]
            count += 1
        if count > 0:
            self.save()
        return count

    # ==========================================================================
    # DEDUPLICATED STORAGE STATISTICS ENGINE
    # ==========================================================================
    def calculate_gallery_statistics(self) -> Dict[str, Any]:
        """Calculates accurate, deduplicated Gallery statistics.
        If the same physical file is referenced in multiple folders (or even multiple GalleryPhoto records),
        its byte size is counted only once."""
        active = [p for p in self.gallery_photos.values() if not p.is_deleted]
        deleted = [p for p in self.gallery_photos.values() if p.is_deleted]

        seen_physical_keys = set()
        raw_bytes = 0
        jpeg_bytes = 0
        other_bytes = 0
        managed_bytes = 0
        referenced_bytes = 0

        raw_count = 0
        jpeg_count = 0
        other_count = 0
        favorites_count = 0
        missing_count = 0

        for p in active:
            if p.is_favorite:
                favorites_count += 1
            if p.is_missing or not os.path.exists(p.active_path):
                missing_count += 1

            if p.format_type == "RAW":
                raw_count += 1
            elif p.format_type == "JPEG":
                jpeg_count += 1
            else:
                other_count += 1

            # Deduplicate physical storage counting by normalized path or hash
            phys_key = os.path.normcase(os.path.abspath(p.active_path)) if p.active_path else (p.file_hash or p.id)
            if phys_key not in seen_physical_keys:
                seen_physical_keys.add(phys_key)
                sz = max(0, int(p.size_bytes))
                if p.format_type == "RAW":
                    raw_bytes += sz
                elif p.format_type == "JPEG":
                    jpeg_bytes += sz
                else:
                    other_bytes += sz

                if p.is_managed:
                    managed_bytes += sz
                else:
                    referenced_bytes += sz

            # If a RAW photo also has a paired converted JPEG, count the paired JPEG if not already indexed separately
            if p.paired_jpeg_path and os.path.exists(p.paired_jpeg_path):
                pair_key = os.path.normcase(os.path.abspath(p.paired_jpeg_path))
                if pair_key not in seen_physical_keys:
                    seen_physical_keys.add(pair_key)
                    psz = os.path.getsize(p.paired_jpeg_path)
                    jpeg_bytes += psz
                    managed_bytes += psz

        total_bytes = raw_bytes + jpeg_bytes + other_bytes
        if total_bytes > 0:
            raw_pct = round((raw_bytes / total_bytes) * 100, 1)
            jpeg_pct = round((jpeg_bytes / total_bytes) * 100, 1)
            other_pct = round(max(0.0, 100.0 - raw_pct - jpeg_pct), 1)
        else:
            raw_pct = jpeg_pct = other_pct = 0.0

        folder_counts = {}
        for fid in self.gallery_folders:
            folder_counts[fid] = sum(1 for p in active if fid in p.folder_ids)

        return {
            "total_photos": len(active),
            "raw_count": raw_count,
            "jpeg_count": jpeg_count,
            "other_count": other_count,
            "favorites_count": favorites_count,
            "missing_count": missing_count,
            "deleted_count": len(deleted),
            "total_bytes": total_bytes,
            "raw_bytes": raw_bytes,
            "jpeg_bytes": jpeg_bytes,
            "other_bytes": other_bytes,
            "managed_bytes": managed_bytes,
            "referenced_bytes": referenced_bytes,
            "raw_pct": raw_pct,
            "jpeg_pct": jpeg_pct,
            "other_pct": other_pct,
            "raw_percent": raw_pct,
            "jpeg_percent": jpeg_pct,
            "other_percent": other_pct,
            "folder_counts": folder_counts,
        }

    # ==========================================================================
    # SMART ALBUMS CRUD
    # ==========================================================================
    def get_smart_albums(self) -> List[SmartAlbum]:
        if not self.smart_albums:
            self._seed_gallery_defaults(save_after=False)
        return list(self.smart_albums.values())

    def save_smart_album(self, album: SmartAlbum) -> SmartAlbum:
        self.smart_albums[album.id] = album
        self.save()
        return album

    def delete_smart_album(self, album_id: str) -> bool:
        if album_id in self.smart_albums:
            del self.smart_albums[album_id]
            self.save()
            return True
        return False


    @property
    def gallery_converted_dir(self) -> str:
        d = os.path.join(self.data_dir, "gallery_converted")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def sessions(self) -> List[Project]:
        return self.get_projects()

    @property
    def gallery_backups(self) -> List[BackupRecord]:
        return self.backup_records

    def get_gallery_folder(self, folder_id: str) -> Optional[GalleryFolder]:
        return self.get_gallery_folder_by_id(folder_id)

    def toggle_gallery_favorite(self, photo_id: str) -> bool:
        return self.toggle_photo_favorite(photo_id)

    def assign_photos_to_folder(self, photo_ids: List[str], folder_id: str) -> int:
        return self.move_photos_to_gallery_folder(photo_ids, folder_id, keep_existing_folders=True)

    def create_smart_album(self, name: str, rules: Dict[str, Any]) -> SmartAlbum:
        sa = SmartAlbum(name=name.strip(), rules=rules, is_builtin=False)
        return self.save_smart_album(sa)


# Global storage instance
storage = StorageManager()
