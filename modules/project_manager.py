import json
import os
import uuid
from datetime import datetime
from typing import Optional, List

PROJECTS_BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "projects")


def _user_dir(username: str) -> str:
    return os.path.join(PROJECTS_BASE, username)


def _ensure_dir(username: str):
    os.makedirs(_user_dir(username), exist_ok=True)


def _project_path(username: str, project_id: str) -> str:
    return os.path.join(_user_dir(username), f"{project_id}.json")


def save_project(username: str, data: dict, project_id: Optional[str] = None) -> str:
    """프로젝트 저장. project_id가 없으면 새로 생성."""
    _ensure_dir(username)
    now = datetime.now().isoformat()

    if project_id is None:
        project_id = uuid.uuid4().hex[:12]
        data["created_at"] = now

    data["project_id"] = project_id
    data["updated_at"] = now

    with open(_project_path(username, project_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return project_id


def load_project(username: str, project_id: str) -> Optional[dict]:
    """프로젝트 불러오기."""
    path = _project_path(username, project_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_projects(username: str) -> List[dict]:
    """해당 유저의 프로젝트 목록 (최신순)."""
    _ensure_dir(username)
    projects = []
    for fname in os.listdir(_user_dir(username)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(_user_dir(username), fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            projects.append({
                "project_id": d.get("project_id", fname.replace(".json", "")),
                "name": d.get("name", "제목 없음"),
                "input_type": d.get("input_type", ""),
                "created_at": d.get("created_at", ""),
                "updated_at": d.get("updated_at", ""),
                "video_type": d.get("video_type", ""),
            })
        except Exception:
            continue
    projects.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
    return projects


def delete_project(username: str, project_id: str) -> bool:
    """프로젝트 삭제."""
    path = _project_path(username, project_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
