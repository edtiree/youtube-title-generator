import json
import os
import streamlit as st
from config import OPENAI_API_KEY, ANTHROPIC_API_KEY, YOUTUBE_API_KEY
from modules.audio_extractor import extract_audio, chunk_audio_if_needed, cleanup_temp_files, download_youtube_subtitle, is_youtube_url, extract_frames_from_youtube, extract_frames_from_upload
from modules.transcriber import transcribe_audio
from modules.youtube_analyzer import search_similar_videos
from modules.title_generator import generate_titles, analyze_transcript, analyze_thumbnails, evaluate_title
from modules.project_manager import save_project, load_project, list_projects, delete_project
from modules.google_auth import check_auth, get_login_url, logout, process_oauth_callback, save_last_project, get_last_project

# ── 페이지 설정 ──
st.set_page_config(page_title="유튜브 제목 생성기", page_icon="▶️", layout="wide")

# ── 인증 ──
process_oauth_callback()  # OAuth 콜백을 가장 먼저 처리
is_logged_in, google_user = check_auth()

if not is_logged_in:
    # 랜딩 페이지
    st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
    html, body, .stApp, p, span, div, h1, h2, h3, h4, h5, h6,
    label, input, textarea, select, button, a, li, td, th, code {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    .stApp { background-color: #FFFFFF; }
    .login-container {
        display: flex; flex-direction: column; align-items: center;
        justify-content: center; min-height: 60vh; text-align: center;
    }
    .login-logo {
        background: #18181B; border-radius: 16px; width: 64px; height: 64px;
        display: flex; align-items: center; justify-content: center; margin: 0 auto 24px;
    }
    .login-title {
        font-size: 32px; font-weight: 900; color: #18181B;
        letter-spacing: -1px; margin-bottom: 8px;
    }
    .login-sub {
        font-size: 16px; color: #71717A; margin-bottom: 40px; line-height: 1.6;
    }
    .google-btn {
        display: inline-flex; align-items: center; gap: 12px;
        background: #FFFFFF; border: 1px solid #E4E4E7; border-radius: 12px;
        padding: 14px 32px; font-size: 15px; font-weight: 600; color: #18181B;
        text-decoration: none; transition: all 0.15s; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .google-btn:hover {
        border-color: #DFFF32; box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        transform: translateY(-1px);
    }
    .login-footer { color: #A1A1AA; font-size: 12px; margin-top: 32px; }
    </style>
    """, unsafe_allow_html=True)

    login_url = get_login_url()

    st.markdown(f"""
    <div class="login-container">
        <div class="login-logo">
            <svg viewBox="0 0 28 20" width="28" height="20">
                <rect width="28" height="20" rx="4" fill="#DFFF32"/>
                <polygon points="11,4 11,16 20,10" fill="#18181B"/>
            </svg>
        </div>
        <div class="login-title">유튜브 제목 생성기</div>
        <div class="login-sub">
            대본을 입력하면 AI가 분석하고,<br>
            클릭을 부르는 최적의 제목을 만들어 드립니다.
        </div>
        <a href="{login_url or '#'}" class="google-btn">
            <svg width="20" height="20" viewBox="0 0 48 48">
                <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
            </svg>
            Google 계정으로 로그인
        </a>
        <div class="login-footer">허가된 계정만 사용할 수 있습니다</div>
    </div>
    """, unsafe_allow_html=True)

    if not login_url:
        st.warning("Google OAuth가 설정되지 않았습니다. .env 파일에 GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET을 추가하세요.")
    st.stop()

# 로그인 성공
_current_user = google_user["email"].split("@")[0]  # 이메일 앞부분을 유저ID로 사용
_current_user_name = google_user["name"]
_current_user_picture = google_user.get("picture", "")

# ── CSS (Lilys AI 스타일) ──
st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
html, body, .stApp, p, span, div, h1, h2, h3, h4, h5, h6,
label, input, textarea, select, button, a, li, td, th, code {
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* 전체 배경 */
.stApp { background-color: #FFFFFF; }
header[data-testid="stHeader"] { background: #FFFFFF !important; border-bottom: 1px solid #E4E4E7; }

/* 사이드바 */
section[data-testid="stSidebar"] {
    background-color: #F9FAFB !important;
    border-right: 1px solid #E4E4E7;
}
section[data-testid="stSidebar"] * { color: #27272A; }
section[data-testid="stSidebar"] .stCaption p { color: #52525B !important; }

/* 섹션 헤더 */
.section-header {
    color: #18181B; font-size: 20px; font-weight: 800;
    margin: 36px 0 16px; padding: 0; letter-spacing: -0.5px;
}
.section-sub { color: #52525B; font-size: 13px; margin-top: 2px; margin-bottom: 12px; }

/* 탭 (Lilys 칩 스타일) */
.stTabs [data-baseweb="tab-list"] { gap: 8px; background: transparent; border-bottom: none !important; }
.stTabs [data-baseweb="tab"] {
    background-color: #F4F4F5 !important; border-radius: 8px !important;
    border: 1px solid #E4E4E7 !important; color: #52525B !important;
    font-size: 13px !important; font-weight: 500 !important;
    padding: 8px 16px !important; height: auto !important;
    transition: all 0.15s ease-in-out;
}
.stTabs [data-baseweb="tab"]:hover {
    background-color: #E4E4E7 !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    background-color: #18181B !important; color: #FFFFFF !important;
    border-color: #18181B !important;
}
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }
.stTabs [data-baseweb="tab-border"] { display: none !important; }

/* 제목 카드 */
.title-card {
    background: #FFFFFF; border-radius: 12px; padding: 20px 24px;
    margin-bottom: 12px; border: 1px solid #E4E4E7;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    transition: all 0.2s ease-in-out;
}
.title-card:hover {
    border-color: #DFFF32; box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    transform: translateY(-1px);
}
.title-text { color: #18181B; font-size: 17px; font-weight: 700; line-height: 1.6; margin-bottom: 10px; letter-spacing: -0.3px; }
.title-meta { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }

/* YouTube 미리보기 카드 */
.yt-preview {
    width: 100%; max-width: 300px; border-radius: 12px; overflow: hidden;
    margin-bottom: 16px; background: #fff;
}
.yt-preview-thumb {
    width: 100%; aspect-ratio: 16/9; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    position: relative; display: flex; align-items: flex-end; justify-content: flex-start;
    border-radius: 12px; overflow: hidden;
}
.yt-preview-thumb-text {
    padding: 14px 16px; line-height: 1.2; letter-spacing: -1px; word-break: keep-all;
}
.yt-preview-thumb-line1 {
    color: #fff; font-size: 30px; font-weight: 900;
    -webkit-text-stroke: 2px #000;
    paint-order: stroke fill;
    display: block; margin-bottom: 4px;
}
.yt-preview-thumb-line2 {
    color: #FFE500; font-size: 32px; font-weight: 900;
    -webkit-text-stroke: 2px #000;
    paint-order: stroke fill;
    display: block;
}
.yt-preview-info {
    display: flex; gap: 10px; padding: 10px 2px 0;
}
.yt-preview-avatar {
    width: 36px; height: 36px; border-radius: 50%; background: #E4E4E7;
    flex-shrink: 0; display: flex; align-items: center; justify-content: center;
    font-size: 10px; font-weight: 700; color: #52525B; overflow: hidden;
}
.yt-preview-avatar img { width: 100%; height: 100%; object-fit: cover; }
.yt-preview-meta { flex: 1; min-width: 0; }
.yt-preview-title {
    color: #0f0f0f; font-size: 14px; font-weight: 600; line-height: 1.4;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden; margin-bottom: 4px;
}
.yt-preview-channel { color: #606060; font-size: 12px; line-height: 1.4; }
.yt-preview-stats { color: #606060; font-size: 12px; }
.chip {
    background: #F4F4F5; color: #52525B; font-size: 11px;
    padding: 3px 10px; border-radius: 6px; font-weight: 500;
    border: 1px solid #E4E4E7;
}
.chip-primary { background: rgba(223,255,50,0.15); color: #4a5500; border-color: rgba(223,255,50,0.4); }
.score-pill {
    background: #18181B; color: #DFFF32; font-size: 13px; font-weight: 700;
    padding: 4px 12px; border-radius: 6px; white-space: nowrap;
}
.reasoning-text { color: #71717A; font-size: 13px; line-height: 1.6; margin-top: 8px; }

/* 유사 영상 카드 */
.vid-card {
    display: flex; gap: 14px; align-items: flex-start; padding: 12px;
    border-radius: 12px; text-decoration: none; transition: all 0.15s ease-in-out;
    margin-bottom: 4px; border: 1px solid transparent;
}
.vid-card:hover { background: #F9FAFB; border-color: #E4E4E7; }
.vid-thumb {
    width: 168px; height: 94px; border-radius: 10px;
    object-fit: cover; flex-shrink: 0; background: #F4F4F5;
}
.vid-info { flex: 1; min-width: 0; padding-top: 2px; }
.vid-title {
    color: #18181B; font-size: 14px; font-weight: 600; line-height: 1.5;
    margin-bottom: 6px; display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; overflow: hidden;
}
.vid-channel { color: #71717A; font-size: 12px; }
.vid-views { color: #A1A1AA; font-size: 12px; }

/* 입력 요소 */
[data-testid="stFileUploader"] section {
    background: #F9FAFB !important; border: 2px dashed #E4E4E7 !important;
    border-radius: 12px !important; transition: border-color 0.15s;
}
[data-testid="stFileUploader"] section:hover { border-color: #DFFF32 !important; }
.stTextArea textarea {
    background: #F9FAFB !important; border: 1px solid #E4E4E7 !important;
    border-radius: 10px !important; color: #18181B !important;
    font-size: 14px !important; transition: border-color 0.15s;
}
.stTextArea textarea:focus { border-color: #DFFF32 !important; box-shadow: 0 0 0 3px rgba(223,255,50,0.2) !important; }
.stTextInput input {
    background: #F9FAFB !important; border: 1px solid #E4E4E7 !important;
    border-radius: 10px !important; color: #18181B !important;
    padding: 10px 16px !important; font-size: 14px !important;
    transition: border-color 0.15s;
}
.stTextInput input:focus { border-color: #DFFF32 !important; box-shadow: 0 0 0 3px rgba(223,255,50,0.2) !important; }
.stTextInput input::placeholder { color: #A1A1AA !important; }

/* 셀렉트박스 */
.stSelectbox > div > div {
    background: #F9FAFB !important; border: 1px solid #E4E4E7 !important;
    border-radius: 10px !important; color: #18181B !important;
}
.stSelectbox input { pointer-events: none !important; caret-color: transparent !important; }

/* 버튼 */
.stButton > button {
    border-radius: 10px !important; font-weight: 600 !important;
    font-size: 14px !important; padding: 10px 24px !important;
    transition: all 0.15s ease-in-out !important; border: none !important;
    height: 44px !important;
}
.stButton > button[kind="primary"] {
    background: #DFFF32 !important; color: #18181B !important;
    font-weight: 700 !important; box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
}
.stButton > button[kind="primary"]:hover {
    background: #C9E42E !important; box-shadow: 0 4px 12px rgba(223,255,50,0.3) !important;
    transform: translateY(-1px);
}
.stButton > button[kind="secondary"], .stButton > button:not([kind="primary"]) {
    background: #F4F4F5 !important; color: #27272A !important;
    border: 1px solid #E4E4E7 !important;
}
.stButton > button[kind="secondary"]:hover, .stButton > button:not([kind="primary"]):hover {
    background: #E4E4E7 !important;
}

/* 메트릭 */
[data-testid="stMetricValue"] { color: #18181B !important; font-size: 24px !important; font-weight: 800 !important; }
[data-testid="stMetricLabel"] { color: #71717A !important; }

/* 디바이더 */
hr { border-color: #E4E4E7 !important; }

/* 스크롤바 */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #D4D4D8; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #A1A1AA; }

/* 정보 박스 */
.info-box {
    background: #F9FAFB; border: 1px solid #E4E4E7; border-radius: 12px;
    padding: 16px 20px; display: flex; align-items: center;
    gap: 14px; margin-bottom: 12px;
}
.info-box-icon { font-size: 28px; flex-shrink: 0; }
.info-box-title { color: #18181B; font-size: 14px; font-weight: 600; }
.info-box-sub { color: #71717A; font-size: 12px; margin-top: 2px; }

/* API 상태 */
.api-ok { color: #16a34a; font-size: 13px; font-weight: 500; }
.api-fail { color: #dc2626; font-size: 13px; font-weight: 500; }

/* 분석 카드 */
.analysis-card {
    background: #FFFFFF; border: 1px solid #E4E4E7; border-radius: 14px;
    padding: 24px 28px; margin-bottom: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

/* 인용문 */
.quote-block {
    border-left: 3px solid #DFFF32; padding: 12px 18px; margin-bottom: 10px;
    background: #FAFAF5; border-radius: 0 10px 10px 0;
    color: #27272A; font-size: 14px; line-height: 1.6;
}

/* 키워드 칩 */
.kw-chip {
    display: inline-block; background: rgba(223,255,50,0.2);
    color: #3d4d00; font-size: 13px; padding: 5px 14px;
    border-radius: 20px; font-weight: 500; margin: 3px;
    border: 1px solid rgba(223,255,50,0.4);
}

/* expander */
.streamlit-expanderHeader {
    background: #F9FAFB !important; border-radius: 10px !important;
    font-weight: 600 !important; color: #27272A !important;
}

/* spinner */
.stSpinner > div { border-top-color: #DFFF32 !important; }

/* status */
[data-testid="stStatusWidget"] { background: #F9FAFB !important; border: 1px solid #E4E4E7 !important; border-radius: 12px !important; }

/* 히어로 타이틀 */
.hero-title {
    font-size: 28px; font-weight: 900; color: #18181B;
    letter-spacing: -1px; margin: 0; line-height: 1.3;
}
.hero-sub {
    font-size: 15px; color: #71717A; font-weight: 400;
    margin-top: 6px; margin-bottom: 32px;
}
.hero-badge {
    display: inline-block; background: #DFFF32; color: #18181B;
    font-size: 12px; font-weight: 700; padding: 4px 12px;
    border-radius: 6px; margin-bottom: 12px;
}

/* 채널 칩 */
.channel-chip {
    display: flex !important; align-items: center; justify-content: center; gap: 10px;
    background: #F4F4F5; border: 1px solid #E4E4E7;
    border-radius: 20px; padding: 6px 14px 6px 8px;
    font-size: 13px; color: #27272A; font-weight: 500;
    height: 36px; box-sizing: border-box;
    text-align: center; overflow: hidden; white-space: nowrap;
}
/* 칩 컬럼 내 모든 컨테이너 폭 100% 강제 (칩 자체는 제외) */
[data-testid="stColumn"]:has(.channel-chip) > div,
[data-testid="stColumn"]:has(.channel-chip) > div > div,
[data-testid="stColumn"]:has(.channel-chip) > div > div > *,
[data-testid="stColumn"]:has(.channel-chip) > div > div > * > div,
[data-testid="stColumn"]:has(.channel-chip) > div > div > * > div > div,
[data-testid="stColumn"]:has(.channel-chip) > div > div > * > div > div > div:not(.channel-chip),
[data-testid="stColumn"]:has(.channel-chip) .stButton {
    width: 100% !important; display: block !important;
}
/* X 버튼: 칩 위로 겹치기 */
[data-testid="stColumn"]:has(.channel-chip) .stButton {
    margin-top: -36px !important;
    position: relative !important;
    z-index: 10 !important;
}
[data-testid="stColumn"]:has(.channel-chip) .stButton > button {
    opacity: 0 !important; transition: opacity 0.15s !important;
    width: 100% !important; height: 36px !important; min-height: 0 !important;
    border-radius: 20px !important; padding: 0 !important;
    background: #dc2626 !important; color: #fff !important;
    border: none !important; font-size: 16px !important; font-weight: 700 !important;
}
[data-testid="stColumn"]:has(.channel-chip):hover .stButton > button {
    opacity: 1 !important;
}

/* 채널 검색 결과 */
.ch-result {
    display: flex; align-items: center; gap: 12px;
    padding: 12px 16px; border-radius: 12px;
    background: #FFFFFF; margin-bottom: 4px;
    border: 1px solid #E4E4E7;
    transition: all 0.15s;
}
.ch-result:hover { background: #F9FAFB; }

/* 코드 블록 (복사용) */
[data-testid="stCode"] {
    background: #F9FAFB !important; border: 1px solid #E4E4E7 !important;
    border-radius: 8px !important;
}
[data-testid="stCode"] code { color: #18181B !important; }
</style>
""", unsafe_allow_html=True)

# ── 세션 상태 ──
for key in ["transcript", "pattern_data", "titles", "analysis", "similar_videos"]:
    if key not in st.session_state:
        st.session_state[key] = None
if "video_type" not in st.session_state:
    st.session_state.video_type = None  # "롱폼" or "숏폼"
if "video_thumbnail" not in st.session_state:
    st.session_state.video_thumbnail = None
if "video_frames" not in st.session_state:
    st.session_state.video_frames = []  # 영상에서 추출한 프레임 (base64)
if "current_project_id" not in st.session_state:
    st.session_state.current_project_id = None
if "project_name" not in st.session_state:
    st.session_state.project_name = ""
if "page" not in st.session_state:
    st.session_state.page = "home"  # "home" 또는 "project"


def _auto_save_project():
    """현재 세션 데이터를 프로젝트로 자동 저장."""
    if not st.session_state.transcript:
        return
    data = {
        "name": st.session_state.get("project_name") or _make_project_name(),
        "transcript": st.session_state.transcript,
        "analysis": st.session_state.analysis,
        "similar_videos": st.session_state.similar_videos,
        "titles": st.session_state.titles,
        "video_type": st.session_state.video_type,
        "search_keywords": st.session_state.get("search_keywords"),
        "input_type": st.session_state.get("input_type", ""),
        "input_name": st.session_state.get("input_name", ""),
        "ref_channels": st.session_state.get("ref_channels", []),
    }
    pid = save_project(_current_user, data, st.session_state.current_project_id)
    st.session_state.current_project_id = pid
    st.session_state.project_name = data["name"]
    save_last_project(pid)


def _make_project_name():
    """프로젝트 이름 자동 생성 (분석 결과 우선, 없으면 입력 정보)."""
    a = st.session_state.get("analysis")
    if a and isinstance(a, dict):
        if a.get("guest"):
            return a["guest"][:30]
        if a.get("summary"):
            return a["summary"][:30] + "..."
    # 입력 정보로 대체
    input_name = st.session_state.get("input_name", "")
    if input_name and input_name != "직접 입력":
        return input_name[:30]
    from datetime import datetime
    return f"프로젝트 {datetime.now().strftime('%m/%d %H:%M')}"


def _load_project_to_session(project_id: str):
    """저장된 프로젝트를 세션에 불러오기."""
    data = load_project(_current_user, project_id)
    if not data:
        return
    st.session_state.page = "project"
    st.session_state.current_project_id = project_id
    st.session_state.project_name = data.get("name", "")
    st.session_state.transcript = data.get("transcript")
    st.session_state.analysis = data.get("analysis")
    st.session_state.similar_videos = data.get("similar_videos")
    st.session_state.titles = data.get("titles")
    st.session_state.video_type = data.get("video_type")
    st.session_state.search_keywords = data.get("search_keywords")
    st.session_state.input_type = data.get("input_type", "")
    st.session_state.input_name = data.get("input_name", "")
    st.session_state.ref_channels = data.get("ref_channels", [])
    st.session_state.video_frames = []
    st.session_state.video_thumbnail = None

# ── 사이드바 ──
with st.sidebar:
    # 로고 = 홈 버튼
    if st.button("▶️ 제목 생성기", key="home_btn", use_container_width=True):
        st.session_state.page = "home"
        st.session_state.current_project_id = None
        st.session_state.project_name = ""
        for key in ["transcript", "analysis", "similar_videos", "titles", "search_keywords", "video_type", "video_thumbnail", "video_frames", "selected_frame"]:
            st.session_state[key] = None
        st.rerun()

    _pic_html = f'<img src="{_current_user_picture}" style="width:24px;height:24px;border-radius:50%;object-fit:cover;">' if _current_user_picture else ""
    st.markdown(f'<div style="display:flex;align-items:center;gap:8px;color:#52525B;font-size:13px;margin-bottom:4px;">{_pic_html}<b>{_current_user_name}</b></div>', unsafe_allow_html=True)
    if st.button("로그아웃", key="logout_btn"):
        logout()
        st.rerun()

    st.divider()
    st.markdown("**연결 상태**")
    for name, ok in [("OpenAI (Whisper)", bool(OPENAI_API_KEY)), ("Claude AI", bool(ANTHROPIC_API_KEY)), ("YouTube API", bool(YOUTUBE_API_KEY))]:
        icon = "✓" if ok else "✗"
        cls = "api-ok" if ok else "api-fail"
        st.markdown(f'<span class="{cls}">{icon} {name}</span>', unsafe_allow_html=True)

    st.divider()
    st.markdown("**사용 방법**")
    steps = [
        "영상 파일/링크/대본 입력",
        "AI가 영상 내용 자동 분석",
        "유사한 인기 영상 표시",
        "제목 스타일 & 참고 채널 설정",
        "AI가 최적의 제목 생성",
    ]
    for i, s in enumerate(steps, 1):
        st.caption(f"{i}. {s}")

    st.divider()
    st.caption("파일 업로드: Whisper API (유료)")
    st.caption("YouTube 링크: 자막 추출 (무료)")
    st.caption("대본 직접 입력: 무료")

# ══════════════════════════════════════════
# 메인
# ══════════════════════════════════════════
# ══════════════════════════════════════════
# 홈 화면
# ══════════════════════════════════════════
if st.session_state.page == "home":
    st.markdown('<span class="hero-badge">AI Powered</span>', unsafe_allow_html=True)
    st.markdown('<div class="hero-title">유튜브 제목 생성기</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-sub">대본을 입력하면 AI가 분석하고, 클릭을 부르는 최적의 제목을 만들어 드립니다.</div>', unsafe_allow_html=True)

    # 내 프로젝트 목록
    _home_projects = list_projects(_current_user)
    if _home_projects:
        st.markdown('<div class="section-header">내 프로젝트</div>', unsafe_allow_html=True)
        for proj in _home_projects:
            name = proj["name"][:30] + ("..." if len(proj["name"]) > 30 else "")
            vtype = proj.get("video_type", "")
            badge = f'<span style="font-size:11px;color:#71717A;background:#F4F4F5;padding:2px 8px;border-radius:4px;margin-left:8px;">{vtype}</span>' if vtype else ""
            if st.button(f"{name}  {vtype}", key=f"home_load_{proj['project_id']}", use_container_width=True):
                _load_project_to_session(proj["project_id"])
                st.rerun()

    st.markdown('<div class="section-header" style="margin-top:32px;">새 프로젝트 시작</div>', unsafe_allow_html=True)

# ── 영상 입력 (홈에서만) ──
uploaded_file = None
youtube_url = ""
if st.session_state.page == "home":
    tab1, tab2, tab3 = st.tabs(["📁 파일 업로드", "🔗 YouTube 링크", "📝 대본 직접 입력"])
    direct_script = ""

    with tab1:
        uploaded_file = st.file_uploader("파일", type=["mp4", "mov", "avi", "mkv", "webm", "mpeg4"], label_visibility="collapsed")
        if uploaded_file:
            mb = uploaded_file.size / (1024 * 1024)
            st.markdown(f'<div class="info-box"><span class="info-box-icon">🎬</span><div><div class="info-box-title">{uploaded_file.name}</div><div class="info-box-sub">{mb:.1f} MB</div></div></div>', unsafe_allow_html=True)

    with tab2:
        youtube_url = st.text_input("URL", placeholder="https://youtube.com/watch?v=...", label_visibility="collapsed")
        if youtube_url and is_youtube_url(youtube_url):
            st.markdown(f'<div class="info-box"><span class="info-box-icon">▶️</span><div><div class="info-box-title">YouTube 영상</div><div class="info-box-sub">{youtube_url}</div></div></div>', unsafe_allow_html=True)
        elif youtube_url:
            st.warning("올바른 YouTube URL을 입력하세요.")

    with tab3:
        direct_script = st.text_area("대본", placeholder="대본을 붙여넣으세요...", height=200, label_visibility="collapsed")
        if direct_script:
            st.markdown(f'<div class="info-box"><span class="info-box-icon">📄</span><div><div class="info-box-title">직접 입력</div><div class="info-box-sub">{len(direct_script):,}자</div></div></div>', unsafe_allow_html=True)
            if st.button("이 대본으로 진행", type="primary"):
                st.session_state.transcript = direct_script
                st.session_state.analysis = None
                st.session_state.similar_videos = None
                st.session_state.titles = None
                st.session_state.search_keywords = None
                st.session_state.video_type = "숏폼" if len(direct_script) <= 500 else "롱폼"
                st.session_state.input_type = "direct"
                st.session_state.input_name = "직접 입력"
                st.session_state.current_project_id = None
                st.session_state.project_name = ""
                st.session_state.page = "project"
                _auto_save_project()
                st.rerun()

# 홈 화면: 스크립트 추출은 허용, 나머지는 멈춤
if st.session_state.page == "home":
    needs_extraction = uploaded_file or (youtube_url and is_youtube_url(youtube_url))
    if needs_extraction and not st.session_state.transcript:
        if st.button("🎙️ 스크립트 추출 & 프로젝트 생성", type="primary", use_container_width=True):
            # URL/파일 정보를 세션에 저장 후 프로젝트 페이지로 전환
            if youtube_url:
                st.session_state["_pending_youtube_url"] = youtube_url
            st.session_state.page = "project"
            st.rerun()
    st.stop()

# ══════════════════════════════════════════
# 프로젝트 화면
# ══════════════════════════════════════════

# ── 스크립트 추출 ──
# 홈에서 넘어온 대기 URL 복원
_pending_url = st.session_state.pop("_pending_youtube_url", None)
if _pending_url and not youtube_url:
    youtube_url = _pending_url

needs_extraction = uploaded_file or (youtube_url and is_youtube_url(youtube_url))
_auto_extract = _pending_url is not None  # 홈에서 버튼 눌러서 넘어온 경우 자동 추출

if needs_extraction and not st.session_state.transcript:
    if _auto_extract:
        _do_extract = True
    else:
        st.markdown('<div class="section-header">스크립트 추출</div>', unsafe_allow_html=True)
        if not OPENAI_API_KEY and not (youtube_url and is_youtube_url(youtube_url)):
            st.error("OpenAI API 키가 필요합니다.")
            _do_extract = False
        else:
            _do_extract = st.button("🎙️ 스크립트 추출", type="primary")
    if _do_extract:
        with st.status("추출 중...", expanded=True) as status:
            if youtube_url and is_youtube_url(youtube_url):
                st.write("YouTube 자막 추출 중...")
                try:
                    st.session_state.transcript = download_youtube_subtitle(youtube_url)
                    st.session_state.analysis = None
                    st.session_state.similar_videos = None
                    st.session_state.titles = None
                    st.session_state.search_keywords = None
                    # 영상에서 프레임 추출
                    st.write("영상에서 썸네일 후보 추출 중...")
                    st.session_state.video_frames = extract_frames_from_youtube(youtube_url, num_frames=6)
                    if st.session_state.video_frames:
                        st.session_state.video_thumbnail = st.session_state.video_frames[0]
                    # 숏폼 감지: URL에 /shorts/ 포함 여부
                    if "/shorts/" in youtube_url:
                        st.session_state.video_type = "숏폼"
                    else:
                        # YouTube API로 영상 길이 확인
                        import re as _re_yt
                        vid_match = _re_yt.search(r'(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})', youtube_url)
                        if vid_match and YOUTUBE_API_KEY:
                            try:
                                from googleapiclient.discovery import build as _yt_build
                                _yt = _yt_build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
                                _vr = _yt.videos().list(part="contentDetails", id=vid_match.group(1)).execute()
                                _dur = _vr.get("items", [{}])[0].get("contentDetails", {}).get("duration", "")
                                import re as _re2
                                _dm = _re2.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', _dur)
                                if _dm:
                                    _secs = sum(int(x or 0) * m for x, m in zip(_dm.groups(), [3600, 60, 1]))
                                    st.session_state.video_type = "숏폼" if _secs <= 60 else "롱폼"
                                else:
                                    st.session_state.video_type = "롱폼"
                            except Exception:
                                st.session_state.video_type = "롱폼"
                        else:
                            st.session_state.video_type = "롱폼"
                    st.write("✅ 자막 추출 완료")
                    st.session_state.input_type = "youtube"
                    st.session_state.input_name = youtube_url
                    st.session_state.current_project_id = None
                    st.session_state.project_name = ""
                    _auto_save_project()
                except Exception as e:
                    st.error(str(e)); st.stop()
            else:
                st.write("영상에서 오디오 추출 중...")
                video_bytes = uploaded_file.read()
                try:
                    audio_path = extract_audio(video_bytes, uploaded_file.name)
                except Exception as e:
                    st.error(str(e)); st.stop()
                audio_chunks = chunk_audio_if_needed(audio_path)
                st.write(f"{len(audio_chunks)}개 청크 준비 완료")
                prog = st.progress(0)
                def _tp(c, t): prog.progress(c / t if t else 0)
                try:
                    result = transcribe_audio(audio_chunks, progress_callback=_tp)
                    st.session_state.transcript = result["full_text"]
                    st.session_state.analysis = None
                    st.session_state.similar_videos = None
                    st.session_state.titles = None
                    st.session_state.search_keywords = None
                    st.session_state.video_type = "숏폼" if result['duration_seconds'] <= 60 else "롱폼"
                    st.write(f"완료 ({result['duration_seconds']/60:.1f}분)")
                    # 영상에서 프레임 추출
                    st.write("썸네일 후보 추출 중...")
                    st.session_state.video_frames = extract_frames_from_upload(video_bytes, uploaded_file.name, num_frames=6)
                    if st.session_state.video_frames:
                        st.session_state.video_thumbnail = st.session_state.video_frames[0]
                    st.session_state.input_type = "upload"
                    st.session_state.input_name = uploaded_file.name
                    st.session_state.current_project_id = None
                    st.session_state.project_name = ""
                    _auto_save_project()
                except Exception as e:
                    st.error(str(e)); st.stop()
                finally:
                    cleanup_temp_files(audio_chunks)
            status.update(label="추출 완료", state="complete")

# ══════════════════════════════════════════
# 스크립트 이후
# ══════════════════════════════════════════
if st.session_state.transcript:
    with st.expander("📄 스크립트 보기/수정", expanded=False):
        st.session_state.transcript = st.text_area("스크립트", value=st.session_state.transcript, height=200, label_visibility="collapsed")

    # ── 영상 분석 (수동) ──
    if st.session_state.analysis is None and ANTHROPIC_API_KEY:
        if st.button("🔍 AI 영상 분석하기", type="primary"):
            st.session_state["_do_analysis"] = True
            st.rerun()

    if st.session_state.get("_do_analysis"):
        st.session_state.pop("_do_analysis", None)
        _analysis_ok = False
        with st.spinner("AI가 영상 내용을 분석하는 중..."):
            try:
                result = analyze_transcript(st.session_state.transcript)
                if result and result.get("keywords"):
                    st.session_state.analysis = result
                    if result.get("guest"):
                        st.session_state.project_name = result["guest"][:30]
                    elif result.get("summary"):
                        st.session_state.project_name = result["summary"][:30]
                    _auto_save_project()
                    _analysis_ok = True
                else:
                    st.session_state.analysis = None
            except Exception as e:
                st.session_state.analysis = None
                st.error(f"AI 분석 실패: {e}")
        if _analysis_ok:
            st.rerun()
        else:
            st.error("분석에 실패했습니다. 크레딧을 확인하고 다시 시도해주세요.")

    if st.session_state.analysis:
        a = st.session_state.analysis
        st.markdown('<div class="section-header">영상 분석</div>', unsafe_allow_html=True)

        guest = a.get("guest", "")
        summary = a.get("summary", "")
        if guest or summary:
            guest_html = f'<div style="color:#18181B;font-size:16px;font-weight:700;margin-bottom:10px;">👤 {guest}</div>' if guest else ""
            summary_html = f'<div style="color:#52525B;font-size:14px;line-height:1.7;">{summary}</div>' if summary else ""
            st.markdown(f'<div class="analysis-card">{guest_html}{summary_html}</div>', unsafe_allow_html=True)

        keywords = a.get("keywords", [])
        if keywords:
            chips = "".join(f'<span class="kw-chip">{kw}</span>' for kw in keywords)
            st.markdown(f'<div style="margin-bottom:20px;"><div style="color:#71717A;font-size:13px;font-weight:500;margin-bottom:10px;">🏷️ 주요 키워드</div>{chips}</div>', unsafe_allow_html=True)

        key_points = a.get("key_points", [])
        if key_points:
            points_html = "".join(f'<li style="color:#27272A;font-size:14px;margin-bottom:8px;line-height:1.6;">{p}</li>' for p in key_points)
            st.markdown(f'<div style="margin-bottom:20px;"><div style="color:#71717A;font-size:13px;font-weight:500;margin-bottom:10px;">📌 핵심 포인트</div><ul style="margin:0;padding-left:20px;">{points_html}</ul></div>', unsafe_allow_html=True)

        quotes = a.get("notable_quotes", [])
        if quotes:
            quotes_html = "".join(f'<div class="quote-block">"{q}"</div>' for q in quotes)
            st.markdown(f'<div style="margin-bottom:20px;"><div style="color:#71717A;font-size:13px;font-weight:500;margin-bottom:10px;">💬 인상적인 발언</div>{quotes_html}</div>', unsafe_allow_html=True)

        if ANTHROPIC_API_KEY:
            if st.button("🔄 다시 분석하기", key="re_analyze"):
                st.session_state.analysis = None
                st.session_state.similar_videos = None
                st.session_state.search_keywords = None
                st.session_state["_do_analysis"] = True
                _auto_save_project()
                st.rerun()

    # ── 유사 영상 (YouTube 검색) ── (분석 완료 후에만 표시)
    if YOUTUBE_API_KEY and st.session_state.analysis:
        ai_kw = st.session_state.analysis.get("keywords", []) if st.session_state.analysis else []
        ai_summary = st.session_state.analysis.get("summary", "") if st.session_state.analysis else ""
        search_queries = st.session_state.analysis.get("search_queries", []) if st.session_state.analysis else []

        if not ai_kw:
            from modules.youtube_analyzer import extract_script_keywords
            # 1차: 브랜드/플랫폼 고유명사 추출
            ai_kw = extract_script_keywords(st.session_state.transcript)
            # 2차: 금액/직업 등 구체적 패턴 추출
            import re as _re
            specific = _re.findall(r'\d+[억만천원]|월\s?\d+만|연봉\s?\d+|[가-힣]{2,4}(?:부업|창업|사업|수익|투자|수출|편집)', st.session_state.transcript[:5000])
            for s in specific:
                if s not in ai_kw:
                    ai_kw.append(s)
            ai_kw = ai_kw[:5]

        # 출연자 이름 추출
        guest_name = st.session_state.analysis.get("guest_name", "") if st.session_state.analysis else ""

        # 검색 키워드 세션 초기화: AI 검색 쿼리 우선 + 출연자 이름 추가
        if "search_keywords" not in st.session_state:
            st.session_state.search_keywords = None
        if st.session_state.search_keywords is None:
            kw_parts = []
            if search_queries:
                kw_parts = search_queries[:4]
            elif ai_kw:
                kw_parts = ai_kw[:3]
            # 출연자 이름이 있으면 이름 검색 쿼리 추가
            if guest_name:
                kw_parts.append(guest_name)
            st.session_state.search_keywords = ", ".join(kw_parts)

        # 검색 키워드 표시 & 수정
        st.markdown('<div class="section-header">유사 영상 검색</div>', unsafe_allow_html=True)
        st.markdown('<div style="color:#71717A;font-size:13px;font-weight:500;margin-bottom:8px;">검색 키워드 (쉼표로 구분, 수정 가능)</div>', unsafe_allow_html=True)
        kw_col, btn_col = st.columns([4, 1])
        with kw_col:
            edited_kw = st.text_input(
                "검색 키워드",
                value=st.session_state.search_keywords or "",
                placeholder="예: 유튜브 수익화, 북한 콘텐츠, AI 영상",
                label_visibility="collapsed",
                key="kw_input",
            )
        with btn_col:
            search_clicked = st.button("🔍 검색", type="primary", key="search_similar_btn")

        # 키워드 파싱
        search_kw_list = [k.strip() for k in edited_kw.split(",") if k.strip()] if edited_kw else []

        # 검색 실행: 버튼 클릭 시에만
        if search_clicked and search_kw_list:
            st.session_state.search_keywords = edited_kw
            st.session_state.vid_page = 1
            st.session_state.selected_ref_videos = set()

        if search_clicked and search_kw_list:
            with st.spinner("비슷한 영상을 검색하는 중..."):
                try:
                    # 롱폼이면 긴 영상만, 숏폼이면 짧은 영상만 검색
                    _vtype = st.session_state.get("video_type", "롱폼")
                    _dur_filter = "short" if _vtype == "숏폼" else "any"
                    _results = search_similar_videos(
                        YOUTUBE_API_KEY, search_kw_list, ai_summary, max_results=50, duration_filter=_dur_filter
                    )
                    # 롱폼 분석 중이면 쇼츠(3분 이하) 제외
                    if _vtype == "롱폼":
                        _results = [v for v in _results if v.get("duration_sec", 0) > 180]
                    st.session_state.similar_videos = _results[:30]
                except Exception as e:
                    st.session_state.similar_videos = []
                    st.warning(f"유사 영상 검색 실패: {e}")

        if st.session_state.similar_videos is not None and len(st.session_state.similar_videos) == 0:
            st.caption("검색 결과가 없습니다. 키워드를 수정 후 다시 검색해보세요.")

        if st.session_state.similar_videos:
            st.markdown(f'<div style="color:#71717A;font-size:13px;margin:12px 0 8px;">검색 결과 {len(st.session_state.similar_videos)}개</div>', unsafe_allow_html=True)

            # 정렬 컨트롤
            fc1, fc2 = st.columns([1, 3])
            with fc1:
                vid_sort = st.selectbox("정렬", ["관련도순", "인기순", "최신순"], label_visibility="collapsed", key="vid_sort")

            filtered = st.session_state.similar_videos

            # 정렬 적용 (관련도순은 관련성 점수 순서 유지)
            if vid_sort == "최신순":
                filtered = sorted(filtered, key=lambda v: v.get("published_at", ""), reverse=True)
            elif vid_sort == "인기순":
                filtered = sorted(filtered, key=lambda v: v.get("view_count", 0), reverse=True)

            # 화면에 보이는 영상 목록 저장 (썸네일 분석용)
            st.session_state["_displayed_videos"] = filtered

            # 페이지네이션
            per_page = 5
            total_pages = max(1, (len(filtered) + per_page - 1) // per_page)
            if "vid_page" not in st.session_state:
                st.session_state.vid_page = 1
            if st.session_state.vid_page > total_pages:
                st.session_state.vid_page = 1
            start_idx = (st.session_state.vid_page - 1) * per_page
            page_items = filtered[start_idx:start_idx + per_page]

            # 선택된 영상 세션 초기화
            if "selected_ref_videos" not in st.session_state:
                st.session_state.selected_ref_videos = set()

            # 영상 표시 (체크박스 포함)
            for sv in page_items:
                vid = sv["video_id"]
                vd = f"조회수 {sv.get('view_display', '')}회" if sv.get('view_count', 0) > 0 else ""
                dur = sv.get("duration_display", "")
                vtype = sv.get("type", "")
                type_badge = ""
                dur_badge = f'<span style="position:absolute;bottom:6px;right:6px;background:rgba(0,0,0,0.75);color:#fff;font-size:11px;padding:2px 6px;border-radius:4px;font-weight:500;">{dur}</span>' if dur else ""
                thumb = sv.get("thumbnail", f"https://img.youtube.com/vi/{vid}/mqdefault.jpg")
                # 업로드 날짜
                pub = sv.get("published_at", "")
                pub_html = ""
                if pub:
                    from datetime import datetime, timezone
                    try:
                        pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                        diff = datetime.now(timezone.utc) - pub_dt
                        hours = int(diff.total_seconds() / 3600)
                        if hours < 1:
                            pub_html = " · 방금 전"
                        elif hours < 24:
                            pub_html = f" · {hours}시간 전"
                        elif hours < 24 * 30:
                            pub_html = f" · {hours // 24}일 전"
                        elif hours < 24 * 365:
                            pub_html = f" · {hours // (24 * 30)}개월 전"
                        else:
                            pub_html = f" · {hours // (24 * 365)}년 전"
                    except Exception:
                        pass

                chk_col, card_col = st.columns([0.05, 0.95])
                with chk_col:
                    is_selected = st.checkbox(
                        "선택", value=vid in st.session_state.selected_ref_videos,
                        key=f"ref_{vid}", label_visibility="collapsed"
                    )
                    if is_selected:
                        st.session_state.selected_ref_videos.add(vid)
                    else:
                        st.session_state.selected_ref_videos.discard(vid)
                with card_col:
                    st.markdown(f"""
                    <a href="https://www.youtube.com/watch?v={vid}" target="_blank" style="text-decoration:none;">
                        <div class="vid-card">
                            <div style="position:relative;flex-shrink:0;">
                                <img src="{thumb}" class="vid-thumb">
                                {dur_badge}
                            </div>
                            <div class="vid-info">
                                <div class="vid-title">{sv['title']}</div>
                                <div class="vid-channel">{sv['channel_name']}{type_badge}</div>
                                <div class="vid-views">{vd}{pub_html}</div>
                            </div>
                        </div>
                    </a>""", unsafe_allow_html=True)

            # 선택된 영상 수 표시
            sel_count = len(st.session_state.selected_ref_videos)
            if sel_count > 0:
                st.caption(f"✅ {sel_count}개 영상 선택됨 — 제목 생성 시 레퍼런스로 사용됩니다")

            if not filtered:
                st.caption("해당 조건의 영상이 없습니다.")

            # 페이지 네비게이션
            if total_pages > 1:
                nav_cols = st.columns([1, 2, 1])
                with nav_cols[0]:
                    if st.session_state.vid_page > 1:
                        if st.button("◀ 이전", key="vid_prev", use_container_width=True):
                            st.session_state.vid_page -= 1
                            st.rerun()
                with nav_cols[1]:
                    st.markdown(f'<div style="text-align:center;color:#71717A;font-size:13px;padding:8px 0;">{st.session_state.vid_page} / {total_pages}</div>', unsafe_allow_html=True)
                with nav_cols[2]:
                    if st.session_state.vid_page < total_pages:
                        if st.button("다음 ▶", key="vid_next", use_container_width=True):
                            st.session_state.vid_page += 1
                            st.rerun()

    # ══════════════════════════════════════════
    # 제목 생성 설정 (분석 완료 후에만 표시)
    # ══════════════════════════════════════════
    if st.session_state.analysis is None or not st.session_state.analysis:
        st.stop()

    st.markdown('<div class="section-header">제목 생성 설정</div>', unsafe_allow_html=True)

    # 제목 스타일 선택
    st.markdown('<div style="color:#71717A;font-size:13px;font-weight:500;margin-bottom:8px;">제목 스타일</div>', unsafe_allow_html=True)
    title_style = st.selectbox(
        "스타일",
        options=[
            "자동 (AI가 최적 스타일 선택)",
            "호기심 자극형 (궁금증 유발)",
            "숫자/금액 강조형 (월 1000만원, 3가지 방법)",
            "질문형 (왜? 어떻게? ~할까?)",
            "스토리형 (퇴사 후, ~했더니)",
            "권위/신뢰형 (전문가, 경력 N년)",
            "자극적/도발형 (충격, 레전드, 실화)",
            "정보/리스트형 (TOP 5, 총정리)",
        ],
        label_visibility="collapsed",
    )

    # 참고 채널 검색 & 선택
    st.markdown('<div style="color:#71717A;font-size:13px;font-weight:500;margin-bottom:8px;margin-top:20px;">참고할 채널 (선택사항)</div>', unsafe_allow_html=True)

    if "ref_channels" not in st.session_state:
        st.session_state.ref_channels = []
    if "ref_search_results" not in st.session_state:
        st.session_state.ref_search_results = []

    # 선택된 채널 표시 (호버 시 빨간색 X 오버레이)
    if st.session_state.ref_channels:
        to_remove = None
        n = len(st.session_state.ref_channels)
        cols_per_row = 5
        rows = [st.session_state.ref_channels[i:i+cols_per_row] for i in range(0, n, cols_per_row)]
        for row in rows:
            chip_cols = st.columns(cols_per_row, gap="small")
            for i, rc in enumerate(row):
                with chip_cols[i]:
                    thumb = rc.get("thumbnail", "")
                    thumb_el = f'<img src="{thumb}" style="width:20px;height:20px;border-radius:50%;object-fit:cover;flex-shrink:0;margin-right:6px;">' if thumb else ""
                    short_name = rc["name"].split(" - ")[0].split(" | ")[0][:8]
                    st.markdown(f'<div class="channel-chip">{thumb_el}<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{short_name}</span></div>', unsafe_allow_html=True)
                    if st.button("✕", key=f"ref_del_{rc['channel_id']}"):
                        to_remove = rc["channel_id"]
        if to_remove:
            st.session_state.ref_channels = [rc for rc in st.session_state.ref_channels if rc["channel_id"] != to_remove]
            st.rerun()

    # 채널 검색
    def _on_ref_search():
        q = st.session_state.get("ref_channel_search", "")
        if q and YOUTUBE_API_KEY:
            try:
                from modules.youtube_analyzer import search_channels
                st.session_state.ref_search_results = search_channels(YOUTUBE_API_KEY, q, max_results=5)
            except Exception:
                st.session_state.ref_search_results = []

    st.text_input("채널 검색", placeholder="채널명 입력 후 엔터", label_visibility="collapsed", key="ref_channel_search", on_change=_on_ref_search)

    # 검색 결과
    if st.session_state.ref_search_results:
        already_ids = [rc.get("channel_id", "") for rc in st.session_state.ref_channels]
        for ch in st.session_state.ref_search_results:
            is_added = ch["channel_id"] in already_ids
            thumb_url = ch.get("thumbnail", "")
            if is_added:
                st.markdown(f"""<div class="ch-result" style="opacity:0.4;">
                    <img src="{thumb_url}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;">
                    <div>
                        <div style="color:#18181B;font-size:13px;font-weight:600;">{ch['name']} <span style="color:#16a34a;font-size:10px;font-weight:700;">추가됨</span></div>
                        <div style="color:#71717A;font-size:11px;">구독자 {ch['subscriber_display']}명</div>
                    </div>
                </div>""", unsafe_allow_html=True)
            else:
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(f"""<div style="display:flex;align-items:center;gap:12px;padding:8px 0;">
                        <img src="{thumb_url}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;">
                        <div>
                            <div style="color:#18181B;font-size:13px;font-weight:600;">{ch['name']}</div>
                            <div style="color:#71717A;font-size:11px;">구독자 {ch['subscriber_display']}명</div>
                        </div>
                    </div>""", unsafe_allow_html=True)
                with col_btn:
                    if st.button("추가", key=f"ref_add_{ch['channel_id']}", type="primary"):
                        st.session_state.ref_channels.append({
                            "channel_id": ch["channel_id"],
                            "name": ch["name"],
                            "thumbnail": ch.get("thumbnail", ""),
                        })
                        st.session_state.ref_search_results = []
                        st.rerun()

    ref_channels = ", ".join(rc["name"] for rc in st.session_state.ref_channels)

    # 추가 요청사항
    st.markdown('<div style="color:#71717A;font-size:13px;font-weight:500;margin-bottom:8px;margin-top:20px;">추가 요청사항 (선택사항)</div>', unsafe_allow_html=True)
    extra_request = st.text_input(
        "요청",
        placeholder="예: 20대 타겟으로, 반말 사용, 이모지 넣어줘",
        label_visibility="collapsed",
    )

    # ── 제목 생성 ──
    if not ANTHROPIC_API_KEY:
        st.error("Anthropic API 키가 필요합니다.")
    elif st.button("✨ 제목 생성하기", type="primary", use_container_width=True):
        # 프롬프트에 설정 반영
        style_instruction = ""
        if title_style != "자동 (AI가 최적 스타일 선택)":
            style_instruction = f"\n\n## 제목 스타일 지정\n사용자가 '{title_style}' 스타일을 요청했습니다. 이 스타일을 우선적으로 적용하세요."

        channel_instruction = ""
        if st.session_state.ref_channels:
            from modules.youtube_analyzer import fetch_channel_videos
            channel_instruction = "\n\n## 참고 채널 제목 스타일 분석\n"
            for rc in st.session_state.ref_channels:
                ch_name = rc["name"]
                ch_id = rc["channel_id"]
                channel_instruction += f"\n### {ch_name}\n"
                try:
                    with st.spinner(f"'{ch_name}' 채널 영상 제목 가져오는 중..."):
                        ch_videos = fetch_channel_videos(YOUTUBE_API_KEY, ch_id, max_videos=30)
                    if ch_videos:
                        # 조회수 높은 순 상위 20개 제목
                        ch_videos.sort(key=lambda v: v.get("view_count", 0), reverse=True)
                        top_titles = ch_videos[:20]
                        channel_instruction += "이 채널의 인기 영상 제목:\n"
                        for v in top_titles:
                            vc = v.get("view_count", 0)
                            channel_instruction += f"- \"{v['title']}\" ({vc:,}회)\n"
                    else:
                        channel_instruction += f"(영상 정보를 가져오지 못했습니다. '{ch_name}' 스타일을 참고하세요.)\n"
                except Exception:
                    channel_instruction += f"(영상 정보를 가져오지 못했습니다. '{ch_name}' 스타일을 참고하세요.)\n"
            channel_instruction += "\n위 채널들의 제목 패턴(문장 구조, 숫자 사용법, 말투, 강조 방식)을 분석하고, 비슷한 스타일로 제목을 만들어주세요."

        extra_instruction = ""
        if extra_request.strip():
            extra_instruction = f"\n\n## 추가 요청사항\n{extra_request}"

        # 유사 영상 정보 (체크된 영상만 사용)
        similar_info = ""
        thumbnail_analysis = ""
        selected_ids = st.session_state.get("selected_ref_videos", set())
        if st.session_state.similar_videos and selected_ids:
            ref_videos = [sv for sv in st.session_state.similar_videos if sv["video_id"] in selected_ids]
            if ref_videos:
                similar_info = "\n\n## 비슷한 주제의 고조회수 영상 제목 (참고용)\n"
                for sv in ref_videos:
                    similar_info += f"- \"{sv['title']}\" ({sv['channel_name']}, {sv['view_count']:,}회)\n"

            # 썸네일 문구 분석 (선택된 영상 중 상위 5개)
            displayed = ref_videos[:5] if ref_videos else []
            thumb_urls = [f"https://img.youtube.com/vi/{sv['video_id']}/maxresdefault.jpg" for sv in displayed]
            if thumb_urls:
                with st.spinner("인기 영상 썸네일 문구 분석 중..."):
                    thumbnail_analysis = analyze_thumbnails(thumb_urls)
                if thumbnail_analysis:
                    similar_info += f"\n\n## 인기 영상 썸네일 문구 분석 (참고용)\n{thumbnail_analysis}\n위 인기 영상들의 썸네일 문구 패턴을 참고하여 썸네일 문구를 추천하세요."
                    st.session_state["_thumbnail_analysis"] = thumbnail_analysis

        # pattern_data 구성
        pattern_data = {
            "summary_for_prompt": (
                (st.session_state.analysis.get("summary", "") if st.session_state.analysis else "")
                + similar_info
                + style_instruction
                + channel_instruction
                + extra_instruction
            ),
            "top_titles": [],
            "avg_length": 35,
            "patterns": {},
            "total_videos_analyzed": 0,
            "top_videos_count": 0,
        }

        with st.spinner("AI가 최적의 제목을 생성하는 중..."):
            try:
                st.session_state.titles = generate_titles(
                    transcript=st.session_state.transcript,
                    pattern_analysis=pattern_data,
                )
                _auto_save_project()
            except Exception as e:
                st.error(f"생성 실패: {e}")

    # ── 내 제목 평가 ──
    if st.session_state.analysis:
        st.markdown('<div class="section-header">내 제목 평가받기</div>', unsafe_allow_html=True)
        eval_col, eval_btn_col = st.columns([4, 1])
        with eval_col:
            my_title = st.text_input(
                "내 제목",
                placeholder="직접 생각한 제목을 입력하세요",
                label_visibility="collapsed",
                key="my_title_input",
            )
        with eval_btn_col:
            eval_clicked = st.button("💬 평가", type="primary", key="eval_title_btn")

        if eval_clicked and my_title.strip():
            selected_ids = st.session_state.get("selected_ref_videos", set())
            ref_vids = []
            if st.session_state.get("similar_videos") and selected_ids:
                ref_vids = [sv for sv in st.session_state.similar_videos if sv["video_id"] in selected_ids]
            with st.spinner("제목을 평가하는 중..."):
                try:
                    result = evaluate_title(my_title.strip(), st.session_state.transcript, ref_vids)
                    st.session_state["title_eval_result"] = result
                except Exception as e:
                    st.error(f"평가 실패: {e}")

        if st.session_state.get("title_eval_result"):
            st.markdown(st.session_state["title_eval_result"])

    # ── 결과 ──
    if st.session_state.titles:
        st.markdown(f'<div class="section-header">추천 제목 <span style="color:#DFFF32;background:#18181B;padding:2px 10px;border-radius:6px;font-size:16px;">{len(st.session_state.titles)}개</span></div>', unsafe_allow_html=True)

        # 썸네일 이미지 업로드
        st.markdown('<div style="color:#71717A;font-size:13px;font-weight:500;margin-bottom:8px;">썸네일 배경 이미지</div>', unsafe_allow_html=True)

        # 직접 업로드
        thumb_upload = st.file_uploader("직접 업로드", type=["png", "jpg", "jpeg", "webp"], label_visibility="collapsed", key="thumb_img")
        thumb_bg_url = ""

        if thumb_upload:
            import base64
            b64 = base64.b64encode(thumb_upload.read()).decode()
            thumb_bg_url = f"data:{thumb_upload.type};base64,{b64}"
        else:
            # 프레임이 아직 없으면 추출 버튼 표시
            if not st.session_state.get("video_frames"):
                # YouTube URL에서 video_id 추출 시도
                _yt_url = youtube_url if youtube_url and is_youtube_url(youtube_url) else ""
                if _yt_url:
                    if st.button("🎬 영상에서 장면 추출", type="primary", key="extract_frames_btn"):
                        with st.spinner("영상에서 장면 추출 중... (최대 1분)"):
                            st.session_state.video_frames = extract_frames_from_youtube(_yt_url, num_frames=6)
                            if st.session_state.video_frames:
                                st.session_state.selected_frame = 0
                            st.rerun()
                else:
                    st.caption("YouTube 링크 또는 직접 업로드로 썸네일 배경을 추가하세요.")

        # 추출된 프레임이 있으면 선택 UI
        if not thumb_upload and st.session_state.get("video_frames"):
            st.markdown('<div style="color:#71717A;font-size:12px;margin-bottom:8px;">영상에서 추출한 장면 (클릭하여 선택)</div>', unsafe_allow_html=True)
            if "selected_frame" not in st.session_state:
                st.session_state.selected_frame = 0
            # HTML flexbox로 모바일에서도 가로 배치
            frames_html = '<div style="display:flex;gap:6px;overflow-x:auto;">'
            for i, frame in enumerate(st.session_state.video_frames):
                border = "3px solid #DFFF32" if i == st.session_state.selected_frame else "2px solid #E4E4E7"
                frames_html += f'<img src="{frame}" style="min-width:30%;max-width:30%;aspect-ratio:16/9;object-fit:cover;border-radius:8px;border:{border};flex-shrink:0;">'
            frames_html += '</div>'
            st.markdown(frames_html, unsafe_allow_html=True)
            # 선택 버튼은 st.columns로 (번호만)
            btn_cols = st.columns(len(st.session_state.video_frames))
            for i in range(len(st.session_state.video_frames)):
                with btn_cols[i]:
                    if st.button(f"{i+1}", key=f"frame_{i}", type="primary" if i == st.session_state.selected_frame else "secondary"):
                        st.session_state.selected_frame = i
                        st.rerun()
            thumb_bg_url = st.session_state.video_frames[st.session_state.selected_frame]

        # 채널 정보 (참고 채널 첫 번째 또는 기본값)
        _ch_name = "내 채널"
        _ch_thumb = ""
        if st.session_state.get("ref_channels"):
            _ch_name = st.session_state.ref_channels[0].get("name", "내 채널")
            _ch_thumb = st.session_state.ref_channels[0].get("thumbnail", "")
        _avatar_html = f'<img src="{_ch_thumb}">' if _ch_thumb else _ch_name[:2]

        for td in st.session_state.titles:
            score = td.get("score", 0)
            tags = "".join(f'<span class="chip chip-primary">{p}</span>' for p in td.get("patterns_used", []))
            ref = td.get("style_reference", "")
            if ref:
                tags += f'<span class="chip">{ref}</span>'
            reasoning = td.get("reasoning", "")
            thumb_text = td.get("thumbnail_text", "")
            # 썸네일 줄 분리 + 색상 파싱
            import re as _re_thumb
            raw_lines = thumb_text.split("\\n") if "\\n" in thumb_text else thumb_text.split("\n") if "\n" in thumb_text else [thumb_text]
            color_map = {"흰색": "#fff", "노란색": "#FFE500", "빨간색": "#FF3B30", "초록색": "#34C759", "녹색": "#34C759", "파란색": "#007AFF", "주황색": "#FF9500", "검은색": "#000"}
            parsed_lines = []
            for line in raw_lines:
                if not line.strip():
                    continue
                color = "#fff"
                color_match = _re_thumb.search(r'\[([가-힣]+색?)\]', line)
                if color_match:
                    color = color_map.get(color_match.group(1), "#fff")
                    line = line[:color_match.start()].strip()
                parsed_lines.append({"text": line, "color": color})

            # 줄 수에 따라 폰트 크기 결정 (레퍼런스처럼 크고 굵게)
            num_lines = len(parsed_lines)
            if num_lines <= 2:
                base_size = 26
            elif num_lines == 3:
                base_size = 21
            else:
                base_size = 18

            thumb_html_lines = ""
            for i, pl in enumerate(parsed_lines):
                color = pl["color"]
                line = pl["text"]
                # 첫 줄 기본 흰색 유지, 2줄 이후 기본 노란색
                if i > 0 and color == "#fff":
                    color = "#FFE500"
                # 글자수 길면 약간 축소
                size = base_size if len(line) <= 8 else max(base_size - 4, 14)
                thumb_html_lines += f'<span style="display:block;color:{color};font-size:{size}px;font-weight:900;-webkit-text-stroke:1.5px #000;paint-order:stroke fill;line-height:1.35;letter-spacing:-0.5px;">{line}</span>'

            # 레퍼런스 매칭
            references = td.get("references", [])
            ref_html = ""

            def _find_ref_video(ref_text):
                if not ref_text or not st.session_state.similar_videos:
                    return None
                for sv in st.session_state.similar_videos:
                    if ref_text in sv.get("title", "") or sv.get("title", "") in ref_text:
                        return sv
                ref_words = set(ref_text.replace('"', '').split())
                best, best_score = None, 0
                for sv in st.session_state.similar_videos:
                    title_words = set(sv.get("title", "").split())
                    overlap = len(ref_words & title_words)
                    if overlap > best_score:
                        best_score = overlap
                        best = sv
                return best if best_score >= 2 else None

            if references:
                ref_cards = ""
                for ref_text in references:
                    ref_vid = _find_ref_video(ref_text)
                    if ref_vid:
                        _rv_thumb = ref_vid.get("thumbnail", f"https://img.youtube.com/vi/{ref_vid['video_id']}/mqdefault.jpg")
                        _rv_views = ref_vid.get("view_display", "")
                        ref_cards += f'''<div style="display:flex;gap:10px;align-items:center;margin-bottom:6px;">
                            <img src="{_rv_thumb}" style="width:80px;height:45px;border-radius:4px;object-fit:cover;flex-shrink:0;">
                            <div><div style="font-size:12px;color:#18181B;font-weight:600;line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">{ref_vid["title"]}</div>
                            <div style="font-size:10px;color:#71717A;">{ref_vid["channel_name"]} · {_rv_views}회</div></div>
                        </div>'''
                    else:
                        ref_cards += f'<div style="font-size:11px;color:#52525B;margin-bottom:4px;">· {ref_text}</div>'
                ref_html = f'<div style="margin-top:12px;padding:10px 12px;background:#F9FAFB;border-radius:8px;border-left:3px solid #DFFF32;"><div style="font-size:10px;color:#71717A;font-weight:600;margin-bottom:6px;">레퍼런스</div>{ref_cards}</div>'

            bg_style = f'background-image:url({thumb_bg_url});background-size:cover;background-position:center;' if thumb_bg_url else ''

            st.markdown(f"""
            <style>
            .result-row {{ display: flex; gap: 20px; margin-bottom: 28px; align-items: flex-start; }}
            .result-preview {{ flex: 1; min-width: 280px; max-width: 380px; }}
            .result-detail {{ flex: 1.2; min-width: 280px; }}
            @media (max-width: 768px) {{
                .result-row {{ flex-direction: column; align-items: center; }}
                .result-preview {{ max-width: 100%; }}
                .result-detail {{ max-width: 100%; }}
            }}
            </style>
            <div class="result-row">
                <div class="result-preview">
                    <div class="yt-preview" style="max-width:100%;width:100%;">
                        <div class="yt-preview-thumb" style="{bg_style}width:100%;height:auto;aspect-ratio:16/9;">
                            <div style="position:absolute;bottom:0;left:0;right:0;height:70%;background:linear-gradient(transparent,rgba(0,0,0,0.7));z-index:1;border-radius:0 0 12px 12px;"></div>
                            <div style="position:relative;z-index:2;padding:14px 16px;display:flex;flex-direction:column;justify-content:flex-end;height:100%;">
                                {thumb_html_lines}
                            </div>
                        </div>
                        <div class="yt-preview-info">
                            <div class="yt-preview-avatar">{_avatar_html}</div>
                            <div class="yt-preview-meta">
                                <div class="yt-preview-title">{td['title']}</div>
                                <div class="yt-preview-channel">{_ch_name}</div>
                                <div class="yt-preview-stats">조회수 0회 · 방금 전</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="result-detail">
                    <div class="title-card" style="margin-top:0;">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
                            <div class="title-text" style="font-size:16px;">{td['title']}</div>
                            <div class="score-pill">{score}점</div>
                        </div>
                        <div class="title-meta">{tags}</div>
                        <div class="reasoning-text">{reasoning}</div>
                        {ref_html}
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)

    # ── 썸네일 분석 결과 ──
    if st.session_state.get("_thumbnail_analysis"):
        with st.expander("🖼️ 썸네일 문구 분석 결과", expanded=False):
            st.markdown(st.session_state["_thumbnail_analysis"])

    # ── 새 영상 분석 ──
    st.divider()
    if st.button("🔄 새 영상 분석하기", use_container_width=True):
        for key in ["transcript", "analysis", "similar_videos", "titles", "search_keywords", "video_type", "video_thumbnail", "video_frames", "selected_frame"]:
            st.session_state[key] = None
        st.session_state.current_project_id = None
        st.session_state.project_name = ""
        st.rerun()
