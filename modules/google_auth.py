"""Google OAuth 2.0 인증 모듈 (Streamlit용) - 쿠키 기반 세션 유지"""
import os
import json
import urllib.parse
from datetime import datetime, timedelta
import requests
import streamlit as st
import extra_streamlit_components as stx

ALLOWED_EMAILS = os.environ.get("ALLOWED_EMAILS", "").split(",")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

SCOPES = "openid email profile"
COOKIE_NAME = "ytitle_auth"
COOKIE_PROJECT = "ytitle_project"
COOKIE_EXPIRY_DAYS = 30


def _client_id():
    return os.environ.get("GOOGLE_CLIENT_ID", "")


def _client_secret():
    return os.environ.get("GOOGLE_CLIENT_SECRET", "")


def _redirect_uri():
    return os.environ.get("REDIRECT_URI", "http://localhost:8501")


def get_login_url():
    """Google 로그인 URL 생성."""
    client_id = _client_id()
    if not client_id:
        return None

    params = {
        "client_id": client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


def _exchange_code(auth_code):
    """인증 코드를 액세스 토큰으로 교환."""
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        "code": auth_code,
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "redirect_uri": _redirect_uri(),
        "grant_type": "authorization_code",
    })
    if resp.status_code != 200:
        error_detail = resp.json().get("error_description", resp.json().get("error", resp.text))
        raise Exception(f"토큰 교환 실패: {error_detail}")
    return resp.json()


def _get_user_info(access_token):
    """액세스 토큰으로 사용자 정보 조회."""
    resp = requests.get(GOOGLE_USERINFO_URL, headers={
        "Authorization": f"Bearer {access_token}",
    })
    if resp.status_code != 200:
        raise Exception("사용자 정보 조회 실패")
    return resp.json()


def is_email_allowed(email):
    """이메일이 허용 목록에 있는지 확인."""
    if not ALLOWED_EMAILS or ALLOWED_EMAILS == [""]:
        return True
    return email in ALLOWED_EMAILS


def process_oauth_callback():
    """
    OAuth 콜백을 가장 먼저 처리 (CookieManager보다 앞서 실행).
    코드가 있으면 즉시 교환하고 세션에 저장한 뒤 URL을 정리.
    """
    if st.session_state.get("google_user"):
        return

    if st.session_state.get("_oauth_processing"):
        return

    auth_code = st.query_params.get("code")
    if not auth_code:
        return

    st.session_state["_oauth_processing"] = True
    try:
        tokens = _exchange_code(auth_code)
        user_info = _get_user_info(tokens["access_token"])

        user = {
            "email": user_info.get("email", ""),
            "name": user_info.get("name", ""),
            "picture": user_info.get("picture", ""),
        }

        if not is_email_allowed(user["email"]):
            st.error(f"'{user['email']}'은 접근 권한이 없습니다.")
            st.query_params.clear()
            st.session_state.pop("_oauth_processing", None)
            return

        st.session_state["google_user"] = user
        st.session_state["_save_cookie"] = True  # 다음 렌더에서 쿠키 저장
        st.query_params.clear()
        st.session_state.pop("_oauth_processing", None)
        st.rerun()
    except Exception as e:
        st.error(f"로그인 실패: {e}")
        st.query_params.clear()
        st.session_state.pop("_oauth_processing", None)


def check_auth():
    """
    인증 상태 확인.
    Returns: (is_logged_in, user_info)
    """
    # 1) 세션에 이미 있으면 반환
    if st.session_state.get("google_user"):
        # 쿠키에 저장 필요한 경우
        if st.session_state.pop("_save_cookie", False):
            try:
                cm = stx.CookieManager(key="auth_cookies")
                cm.set(
                    COOKIE_NAME,
                    json.dumps(st.session_state["google_user"], ensure_ascii=False),
                    expires_at=datetime.now() + timedelta(days=COOKIE_EXPIRY_DAYS),
                )
            except Exception:
                pass
        return True, st.session_state["google_user"]

    # 2) 쿠키에서 복원 시도
    try:
        cm = stx.CookieManager(key="auth_cookies")
        saved = cm.get(COOKIE_NAME)
        if saved:
            user = json.loads(saved) if isinstance(saved, str) else saved
            if user.get("email"):
                st.session_state["google_user"] = user
                return True, user
    except Exception:
        pass

    return False, None


def save_last_project(project_id):
    """마지막 프로젝트 ID를 쿠키에 저장."""
    try:
        cm = stx.CookieManager(key="auth_cookies")
        cm.set(COOKIE_PROJECT, project_id, expires_at=datetime.now() + timedelta(days=COOKIE_EXPIRY_DAYS))
    except Exception:
        pass


def get_last_project():
    """마지막 프로젝트 ID를 쿠키에서 가져오기."""
    try:
        cm = stx.CookieManager(key="auth_cookies")
        return cm.get(COOKIE_PROJECT)
    except Exception:
        return None


def logout():
    """로그아웃 (세션 + 쿠키 삭제)."""
    if "google_user" in st.session_state:
        del st.session_state["google_user"]
    try:
        cm = stx.CookieManager(key="auth_cookies")
        cm.delete(COOKIE_NAME)
        cm.delete(COOKIE_PROJECT)
    except Exception:
        pass
