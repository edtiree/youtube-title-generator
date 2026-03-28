import json
import uuid
from datetime import datetime
from typing import Optional, List

import firebase_admin
from firebase_admin import credentials, firestore


def _get_db():
    """Firestore 클라이언트를 반환한다. 앱 초기화는 한 번만."""
    if not firebase_admin._apps:
        try:
            import streamlit as st
            config = dict(st.secrets["FIREBASE"])
        except Exception:
            import os
            config = json.loads(os.getenv("FIREBASE_CONFIG", "{}"))
        cred = credentials.Certificate(config)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def _projects_ref(username: str):
    """유저의 프로젝트 컬렉션 참조."""
    db = _get_db()
    return db.collection("users").document(username).collection("projects")


def save_project(username: str, data: dict, project_id: Optional[str] = None) -> str:
    """프로젝트 저장. project_id가 없으면 새로 생성."""
    now = datetime.now().isoformat()

    if project_id is None:
        project_id = uuid.uuid4().hex[:12]
        data["created_at"] = now

    data["project_id"] = project_id
    data["updated_at"] = now

    _projects_ref(username).document(project_id).set(data)
    return project_id


def load_project(username: str, project_id: str) -> Optional[dict]:
    """프로젝트 불러오기."""
    doc = _projects_ref(username).document(project_id).get()
    if doc.exists:
        return doc.to_dict()
    return None


def list_projects(username: str) -> List[dict]:
    """해당 유저의 프로젝트 목록 (최신순)."""
    projects = []
    docs = _projects_ref(username).order_by("updated_at", direction=firestore.Query.DESCENDING).stream()
    for doc in docs:
        d = doc.to_dict()
        projects.append({
            "project_id": d.get("project_id", doc.id),
            "name": d.get("name", "제목 없음"),
            "input_type": d.get("input_type", ""),
            "created_at": d.get("created_at", ""),
            "updated_at": d.get("updated_at", ""),
            "video_type": d.get("video_type", ""),
        })
    return projects


def delete_project(username: str, project_id: str) -> bool:
    """프로젝트 삭제."""
    doc_ref = _projects_ref(username).document(project_id)
    if doc_ref.get().exists:
        doc_ref.delete()
        return True
    return False
