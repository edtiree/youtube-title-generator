import os
import re
import shutil
import subprocess
import json as json_module
from googleapiclient.discovery import build
from config import YOUTUBE_API_KEY, TARGET_CHANNELS
from modules.cache_manager import load_cache, save_cache


def _get_ytdlp_path():
    path = shutil.which("yt-dlp")
    if path:
        return path
    local = os.path.expanduser("~/Library/Python/3.9/bin/yt-dlp")
    if os.path.exists(local):
        return local
    return "yt-dlp"


def extract_script_keywords(transcript: str) -> list[str]:
    """대본에서 구체적인 브랜드/플랫폼 키워드를 직접 추출한다."""
    text = transcript[:5000]
    keywords = []
    seen = set()

    # 브랜드/플랫폼/회사명/도구명 (구체적 고유명사만)
    brand_patterns = [
        r'(?:쿠팡|네이버|유튜브|틱톡|인스타그램?|인스타|올리브영|다이소|코스트코|아마존|당근마켓?|배민|배달의민족|토스|카카오|삼성|애플|테슬라|무신사|오늘의집|마켓컬리|스마트스토어|크몽|탈잉|클래스101|에어비앤비|쏘카|타다|야놀자|직방|번개장터|중고나라|알리바바|알리익스프레스|아마존|이베이|쇼피|테무)',
        r'(?:GPT|ChatGPT|챗GPT|클로바|제미나이|미드저니|노션|슬랙|피그마)',
        r'(?:캡컷|CapCut|캡쳇|프리미어|다빈치|어도비|캔바|Canva)',
        r'(?:쇼츠|Shorts|릴스|Reels)',
    ]
    for pattern in brand_patterns:
        for m in re.finditer(pattern, text):
            kw = m.group()
            if kw not in seen:
                seen.add(kw)
                keywords.append(kw)

    return keywords


def search_channels(api_key: str, query: str, max_results: int = 5) -> list[dict]:
    """YouTube에서 채널을 검색한다."""
    youtube = build("youtube", "v3", developerKey=api_key)

    search_response = youtube.search().list(
        part="snippet",
        q=query,
        type="channel",
        maxResults=max_results,
    ).execute()

    channels = []
    channel_ids = [item["snippet"]["channelId"] for item in search_response.get("items", [])]

    if not channel_ids:
        return channels

    # 구독자 수 등 상세 정보 가져오기
    ch_response = youtube.channels().list(
        part="snippet,statistics",
        id=",".join(channel_ids),
    ).execute()

    for item in ch_response.get("items", []):
        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})
        sub_count = int(stats.get("subscriberCount", 0))
        channels.append({
            "channel_id": item["id"],
            "name": snippet.get("title", ""),
            "description": snippet.get("description", "")[:100],
            "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
            "subscriber_count": sub_count,
            "subscriber_display": _format_count(sub_count),
        })

    # 검색어와 채널명 일치도 순으로 정렬
    q_lower = query.lower().replace(" ", "")
    def _match_score(ch):
        name = ch["name"].lower().replace(" ", "")
        if name == q_lower:
            return 0  # 완전 일치
        if name.startswith(q_lower):
            return 1  # 앞부분 일치
        if q_lower in name:
            return 2  # 포함
        return 3  # 나머지
    channels.sort(key=lambda ch: (_match_score(ch), -ch["subscriber_count"]))

    return channels


def search_similar_videos(api_key: str, keywords: list, summary: str = "", max_results: int = 10, order: str = "relevance", duration_filter: str = "any", custom_query: str = "") -> list[dict]:
    """YouTube에서 비슷한 영상을 검색한다. 키워드별로 따로 검색 후 합친다."""
    youtube = build("youtube", "v3", developerKey=api_key)

    if custom_query:
        queries = [custom_query]
    else:
        kw_list = [kw for kw in keywords if kw.strip()]
        # 문장형 쿼리 여부 판단 (띄어쓰기 포함 = AI가 생성한 검색 쿼리)
        has_phrase = any(" " in kw for kw in kw_list)
        if has_phrase:
            # 문장형 쿼리는 그대로 각각 검색
            queries = kw_list
        elif len(kw_list) >= 2:
            from itertools import combinations
            pairs = [" ".join(pair) for pair in combinations(kw_list, 2)]
            queries = [" ".join(kw_list)] + pairs[:4]
            seen_q = set()
            unique_queries = []
            for q in queries:
                if q not in seen_q:
                    seen_q.add(q)
                    unique_queries.append(q)
            queries = unique_queries
        elif kw_list:
            queries = kw_list
        else:
            queries = [summary[:50]] if summary else []
    if not queries:
        return []

    # 키워드별로 검색 후 합치기 (중복 제거, 다중 쿼리 등장 추적)
    all_video_ids = []
    seen_ids = set()
    multi_query_hits = {}  # video_id -> 등장한 쿼리 수
    per_query = max(max_results // len(queries), 5) if queries else max_results

    for query in queries:
        search_params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": per_query,
            "order": order,
            "regionCode": "KR",
            "relevanceLanguage": "ko",
        }
        if duration_filter != "any":
            search_params["videoDuration"] = duration_filter

        search_response = youtube.search().list(**search_params).execute()
        for item in search_response.get("items", []):
            vid = item["id"]["videoId"]
            multi_query_hits[vid] = multi_query_hits.get(vid, 0) + 1
            if vid not in seen_ids:
                seen_ids.add(vid)
                all_video_ids.append(vid)

    if not all_video_ids:
        return []

    # 영상 상세 정보 (50개씩 배치)
    videos = []
    for i in range(0, len(all_video_ids), 50):
        batch = all_video_ids[i:i+50]
        v_response = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(batch),
        ).execute()

        for item in v_response.get("items", []):
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            view_count = int(stats.get("viewCount", 0))
            duration_str = item.get("contentDetails", {}).get("duration", "")
            duration_sec = _parse_duration(duration_str)
            duration_display = _format_duration(duration_sec)
            vid_type = "숏폼" if duration_sec <= 180 else "롱폼"
            videos.append({
                "video_id": item["id"],
                "title": snippet.get("title", ""),
                "channel_name": snippet.get("channelTitle", ""),
                "view_count": view_count,
                "view_display": _format_count(view_count),
                "thumbnail": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
                "published_at": snippet.get("publishedAt", ""),
                "duration_sec": duration_sec,
                "duration_display": duration_display,
                "type": vid_type,
            })

    # 관련성 점수 계산 (개선: 일반 단어 제외 + 구문 매칭 + 다중쿼리 보너스)
    generic_words = {
        "유튜브", "영상", "방법", "추천", "정리", "공개", "진짜", "최신", "직접",
        "전부", "완벽", "이렇게", "하는", "되는", "만드는", "하면", "시작",
        "어떻게", "소개", "알려", "해보", "한번", "지금", "올해", "요즘",
    }
    core_keywords = set()
    for kw in keywords:
        for word in kw.strip().split():
            if len(word) >= 2 and word not in generic_words:
                core_keywords.add(word)

    # 원본 구문 키워드 (2단어 이상 조합 매칭용)
    phrase_keywords = []
    for kw in keywords:
        words = [w for w in kw.strip().split() if len(w) >= 2 and w not in generic_words]
        if len(words) >= 2:
            phrase_keywords.append(" ".join(words))

    for v in videos:
        title = v["title"]
        score = 0
        # 개별 키워드 매칭 (1점씩)
        score += sum(1 for kw in core_keywords if kw in title)
        # 구문 매칭 보너스 (구문 내 2개 이상 단어가 제목에 포함되면 +3)
        for phrase in phrase_keywords:
            phrase_words = phrase.split()
            matched = sum(1 for pw in phrase_words if pw in title)
            if matched >= 2:
                score += 3
        # 다중 쿼리 등장 보너스 (2개 이상 쿼리에서 등장 시 +5씩)
        query_hits = multi_query_hits.get(v["video_id"], 1)
        if query_hits >= 2:
            score += (query_hits - 1) * 5
        v["_relevance"] = score

    # 관련도 높은 순 → 같으면 조회수 높은 순
    videos.sort(key=lambda v: (v.get("_relevance", 0), v["view_count"]), reverse=True)
    return videos[:max_results]


def _parse_duration(iso: str) -> int:
    """ISO 8601 duration (PT1H2M3S)을 초로 변환."""
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso)
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def _format_duration(sec: int) -> str:
    """초를 mm:ss 또는 h:mm:ss로 변환."""
    if sec < 3600:
        return f"{sec // 60}:{sec % 60:02d}"
    return f"{sec // 3600}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"


def _format_count(n: int) -> str:
    """숫자를 한국식 축약 표기로 변환한다."""
    if n >= 10000:
        return f"{n / 10000:.1f}만"
    if n >= 1000:
        return f"{n / 1000:.1f}천"
    return str(n)


def fetch_channel_videos_ytdlp(channel_id: str, max_videos: int = 100) -> list[dict]:
    """yt-dlp로 채널 영상 제목과 조회수를 직접 가져온다."""
    url = f"https://www.youtube.com/channel/{channel_id}/videos"
    cmd = [
        _get_ytdlp_path(),
        "--flat-playlist",
        "--no-download",
        "--print", "%(title)s\t%(view_count)s\t%(id)s",
        "--playlist-end", str(max_videos),
        "--no-warnings",
        "--extractor-args", "youtube:lang=ko",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        return []

    videos = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            title = parts[0]
            try:
                view_count = int(parts[1]) if parts[1] and parts[1] not in ("NA", "None", "") else 0
            except ValueError:
                view_count = 0
            videos.append({
                "video_id": parts[2],
                "title": title,
                "view_count": view_count,
                "like_count": 0,
                "published_at": "",
            })
    return videos


def fetch_channel_videos(api_key: str, channel_id: str, max_videos: int = 200) -> list[dict]:
    """채널의 영상 목록과 통계를 가져온다."""
    youtube = build("youtube", "v3", developerKey=api_key)

    # 1. 채널의 uploads 플레이리스트 ID 가져오기
    ch_response = youtube.channels().list(
        part="contentDetails,snippet,statistics",
        id=channel_id,
    ).execute()

    if not ch_response.get("items"):
        return []

    channel_info = ch_response["items"][0]
    uploads_id = channel_info["contentDetails"]["relatedPlaylists"]["uploads"]

    # 2. 플레이리스트에서 영상 ID 수집
    video_ids = []
    next_page = None
    while len(video_ids) < max_videos:
        pl_response = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_id,
            maxResults=50,
            pageToken=next_page,
        ).execute()

        for item in pl_response.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])

        next_page = pl_response.get("nextPageToken")
        if not next_page:
            break

    video_ids = video_ids[:max_videos]

    # 3. 영상 상세 정보 가져오기 (50개씩 배치)
    videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        v_response = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(batch),
        ).execute()

        for item in v_response.get("items", []):
            stats = item.get("statistics", {})
            videos.append({
                "video_id": item["id"],
                "title": item["snippet"]["title"],
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "published_at": item["snippet"]["publishedAt"],
            })

    return videos


def find_similar_videos(transcript: str, cache_data: dict, selected_ids: list = None, top_n: int = 10, ai_keywords: list = None) -> list[dict]:
    """스크립트 내용과 유사한 영상을 찾는다."""
    keywords = set()

    # AI가 분석한 키워드 우선 사용 (가중치 높음)
    priority_keywords = set()
    if ai_keywords:
        priority_keywords.update(ai_keywords)
        keywords.update(ai_keywords)

    # 스크립트에서 추가 키워드 추출
    keyword_patterns = [
        r'\d+[억만천원살대]',
        r'월\s?\d+',
        r'연봉\s?\d+',
        r'[가-힣]{2,4}(?:사업|장사|부업|창업|투자|직업|직장|회사|알바)',
        r'(?:쿠팡|네이버|유튜브|틱톡|인스타|올리브영|다이소|코스트코|아마존)',
        r'AI|부동산|주식|코인|쇼핑몰|온라인|오프라인|프리랜서|자영업',
        r'(?:퇴사|퇴직|이직|취업|자퇴)',
    ]
    for pattern in keyword_patterns:
        found = re.findall(pattern, transcript)
        keywords.update(found)

    words = re.findall(r'[가-힣]{2,4}', transcript)
    stopwords = {"그래서", "그런데", "하지만", "그리고", "이런", "저런", "이거", "저거",
                 "그거", "진짜", "정말", "되게", "너무", "약간", "사실", "근데", "아니",
                 "네네", "그냥", "어떻게", "뭔가", "거의", "조금", "많이", "하는", "되는"}
    word_freq = {}
    for w in words:
        if w not in stopwords:
            word_freq[w] = word_freq.get(w, 0) + 1
    top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:30]
    keywords.update(w for w, _ in top_words)

    if not keywords:
        return []

    # 모든 영상에서 유사도 계산
    scored_videos = []
    for ch_id, ch_data in cache_data.get("channels", {}).items():
        if selected_ids and ch_id not in selected_ids:
            continue
        ch_name = ch_data.get("name", "")
        for video in ch_data.get("videos", []):
            title = video.get("title", "")
            # AI 키워드 매칭은 가중치 3, 일반 키워드는 1
            score = sum(3 for kw in priority_keywords if kw in title)
            score += sum(1 for kw in (keywords - priority_keywords) if kw in title)
            if score > 0:
                scored_videos.append({
                    "video_id": video["video_id"],
                    "title": title,
                    "view_count": video.get("view_count", 0),
                    "channel_name": ch_name,
                    "similarity_score": score,
                    "thumbnail": f"https://img.youtube.com/vi/{video['video_id']}/mqdefault.jpg",
                })

    # 유사도 높은 것 중 조회수 높은 순 정렬
    scored_videos.sort(key=lambda v: (v["similarity_score"], v["view_count"]), reverse=True)
    return scored_videos[:top_n]


def load_or_refresh_cache(force_refresh: bool = False, progress_callback=None, channels_override=None) -> dict:
    """캐시를 로드하거나 yt-dlp로 채널 데이터를 가져온다."""
    if not force_refresh:
        cache = load_cache()
        if cache and "channels" in cache:
            return cache

    channels = channels_override if channels_override else TARGET_CHANNELS

    cache_data = {"channels": {}}
    channel_items = list(channels.items())

    for i, (channel_id, channel_name) in enumerate(channel_items):
        if progress_callback:
            progress_callback(i, len(channel_items), channel_name)

        try:
            # yt-dlp로 직접 가져오기 (더 정확함)
            videos = fetch_channel_videos_ytdlp(channel_id, max_videos=100)
            if not videos and YOUTUBE_API_KEY:
                # 실패 시 API 폴백
                videos = fetch_channel_videos(YOUTUBE_API_KEY, channel_id)
            cache_data["channels"][channel_id] = {
                "name": channel_name,
                "videos": videos,
            }
        except Exception as e:
            cache_data["channels"][channel_id] = {
                "name": channel_name,
                "videos": [],
                "error": str(e),
            }

    if progress_callback:
        progress_callback(len(channel_items), len(channel_items), "완료")

    save_cache(cache_data)
    return cache_data


def analyze_title_patterns(cache_data: dict) -> dict:
    """캐시 데이터에서 고성과 제목 패턴을 분석한다."""
    all_videos = []
    for ch_data in cache_data.get("channels", {}).values():
        all_videos.extend(ch_data.get("videos", []))

    if not all_videos:
        return _empty_analysis()

    # 조회수 기준 정렬
    all_videos.sort(key=lambda v: v["view_count"], reverse=True)

    # 상위 20% 고성과 영상
    top_count = max(1, len(all_videos) // 5)
    top_videos = all_videos[:top_count]

    # 패턴 분석
    patterns = {
        "질문형": _analyze_pattern(top_videos, _is_question),
        "숫자 활용": _analyze_pattern(top_videos, _has_numbers),
        "감정 자극": _analyze_pattern(top_videos, _has_emotional_hook),
        "대비/반전": _analyze_pattern(top_videos, _has_contrast),
        "괄호 강조": _analyze_pattern(top_videos, _has_brackets),
        "인용/명언": _analyze_pattern(top_videos, _has_quotes),
    }

    # 제목 길이 분포
    lengths = [len(v["title"]) for v in top_videos]
    avg_length = sum(lengths) / len(lengths) if lengths else 0

    # 상위 50개 제목 (프롬프트용)
    top_titles = [
        {"title": v["title"], "view_count": v["view_count"]}
        for v in top_videos[:50]
    ]

    # Claude 프롬프트용 한국어 요약 (채널별 제목 포함)
    summary = _build_summary(patterns, avg_length, top_titles, cache_data)

    return {
        "top_titles": top_titles,
        "avg_length": avg_length,
        "patterns": patterns,
        "total_videos_analyzed": len(all_videos),
        "top_videos_count": top_count,
        "summary_for_prompt": summary,
    }


def _empty_analysis() -> dict:
    return {
        "top_titles": [],
        "avg_length": 0,
        "patterns": {},
        "total_videos_analyzed": 0,
        "top_videos_count": 0,
        "summary_for_prompt": "분석 데이터가 없습니다.",
    }


def _analyze_pattern(videos: list[dict], detector) -> dict:
    matches = [v for v in videos if detector(v["title"])]
    return {
        "count": len(matches),
        "ratio": len(matches) / len(videos) if videos else 0,
        "avg_views": sum(v["view_count"] for v in matches) / len(matches) if matches else 0,
        "examples": [v["title"] for v in matches[:5]],
    }


def _is_question(title: str) -> bool:
    return bool(re.search(r"[?？]|왜\s|어떻게|무엇|뭐가|할까|일까|인가|인걸까|걸까|는가|나요|까요", title))


def _has_numbers(title: str) -> bool:
    return bool(re.search(r"\d+[억만천원살개가지위년월]|\d+%", title))


def _has_emotional_hook(title: str) -> bool:
    hooks = ["충격", "경악", "눈물", "소름", "미쳤", "역대급", "레전드", "대박", "실화", "ㄷㄷ", "놀라운", "충격적", "결국", "드디어"]
    return any(h in title for h in hooks)


def _has_contrast(title: str) -> bool:
    markers = ["했더니", "알고보니", "근데", "반전", "하지만", "그런데", "vs", "VS", "였는데", "더니"]
    return any(m in title for m in markers)


def _has_brackets(title: str) -> bool:
    return bool(re.search(r"[【】\[\]()（）《》]", title))


def _has_quotes(title: str) -> bool:
    return bool(re.search(r'["""\u2018\u2019]', title))


def _build_summary(patterns: dict, avg_length: float, top_titles: list[dict], cache_data: dict = None) -> str:
    lines = ["## 한국 비즈니스/자기계발 인터뷰 채널 제목 패턴 분석 결과\n"]
    lines.append(f"- 고성과 제목 평균 길이: {avg_length:.0f}자")

    for name, data in patterns.items():
        ratio_pct = data["ratio"] * 100
        avg_views = data["avg_views"]
        lines.append(f"- {name}: 사용 비율 {ratio_pct:.1f}%, 평균 조회수 {avg_views:,.0f}회")
        if data["examples"]:
            for ex in data["examples"][:3]:
                lines.append(f"  예시: \"{ex}\"")

    # 채널별 고조회수 제목 예시 (채널 스타일을 학습시키기 위함)
    if cache_data and "channels" in cache_data:
        lines.append("\n## 채널별 고조회수 제목 (이 스타일을 반드시 따라하세요)")
        for ch_id, ch_data in cache_data.get("channels", {}).items():
            ch_name = ch_data.get("name", "")
            videos = ch_data.get("videos", [])
            if not videos:
                continue
            sorted_videos = sorted(videos, key=lambda v: v["view_count"], reverse=True)
            top_10 = sorted_videos[:10]
            lines.append(f"\n### {ch_name} 채널 (조회수 TOP 10)")
            for i, v in enumerate(top_10, 1):
                lines.append(f"  {i}. \"{v['title']}\" ({v['view_count']:,}회)")
    else:
        lines.append("\n## 조회수 상위 30개 제목 예시")
        for i, t in enumerate(top_titles[:30], 1):
            lines.append(f"{i}. \"{t['title']}\" (조회수: {t['view_count']:,})")

    return "\n".join(lines)
