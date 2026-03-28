from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from config import CACHE_FILE, CACHE_MAX_AGE_DAYS


def load_cache() -> dict | None:
    """캐시 파일을 로드한다. 없거나 손상되면 None 반환."""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_cache(data: dict) -> None:
    """캐시 데이터를 파일에 저장한다."""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_cache_stale(max_age_days: int = CACHE_MAX_AGE_DAYS) -> bool:
    """캐시가 오래되었는지 확인한다."""
    cache = load_cache()
    if cache is None:
        return True
    last_updated = cache.get("last_updated")
    if not last_updated:
        return True
    try:
        updated_at = datetime.fromisoformat(last_updated)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - updated_at
        return age.days >= max_age_days
    except (ValueError, TypeError):
        return True
