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

    def create_folder(self, name: str) -> Folder:
        folder = Folder(name=name.strip())
        self.folders[folder.id] = folder
        self.save()
        return folder

    def rename_folder(self, folder_id: str, new_name: str) -> Optional[Folder]:
        folder = self.folders.get(folder_id)
        if folder:
            folder.name = new_name.strip()
            self.save()
        return folder

    def delete_folder(self, folder_id: str) -> bool:
        if folder_id in self.folders:
            # Reassign projects to personal or first available
            other_folders = [fid for fid in self.folders if fid != folder_id]
            fallback_id = other_folders[0] if other_folders else "folder_personal"
            for project in self.projects.values():
                if project.folder_id == folder_id:
                    project.folder_id = fallback_id
            del self.folders[folder_id]
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
