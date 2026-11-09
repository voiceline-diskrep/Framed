"""Persistent storage engine for Loupe folders and projects."""

import json
import os
from typing import List, Optional, Dict, Any
from loupe.config import get_app_dir
from loupe.models import Folder, Project

class StorageManager:
    def __init__(self):
        self.db_path = os.path.join(get_app_dir(), "database.json")
        self.folders: Dict[str, Folder] = {}
        self.projects: Dict[str, Project] = {}
        self.load()

    def load(self) -> None:
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
                return
            except Exception as e:
                print(f"Error loading database from {self.db_path}: {e}")

        # Seed with initial folders if completely fresh
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        school = Folder(id="folder_school", name="School")
        personal = Folder(id="folder_personal", name="Personal")
        commercial = Folder(id="folder_commercial", name="Commercial")
        for f in (school, personal, commercial):
            self.folders[f.id] = f
        self.save()

    def save(self) -> None:
        data = {
            "folders": [f.to_dict() for f in self.folders.values()],
            "projects": [p.to_dict() for p in self.projects.values()],
        }
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving database to {self.db_path}: {e}")

    # Folder operations
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
        # Prevent circular parenting
        if new_parent_id and new_parent_id in self.get_folder_descendant_ids(folder_id):
            return False
        folder.parent_id = new_parent_id
        self.save()
        return True

    def delete_folder(self, folder_id: str) -> bool:
        if folder_id in self.folders:
            descendant_ids = set(self.get_folder_descendant_ids(folder_id))
            all_to_remove = descendant_ids | {folder_id}
            
            # Reassign projects to personal or first available outside the deleted tree
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

    # Project operations
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

# Global storage instance
storage = StorageManager()
