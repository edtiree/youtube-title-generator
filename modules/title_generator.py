import json
import time
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_MAX_TOKENS, NUM_TITLE_SUGGESTIONS
from prompts.title_generation import SYSTEM_PROMPT_TEMPLATE, USER_PROMPT_TEMPLATE, SUMMARY_PROMPT

ANALYSIS_PROMPT = """아래 유튜브 영상 스크립트를 분석해주세요.

반드시 아래 JSON 형식으로만 응답하세요. JSON 외의 텍스트는 절대 포함하지 마세요.
문자열 값 안에 큰따옴표를 사용하지 마세요. 작은따옴표나 괄호로 대체하세요.

{{"summary": "영상 내용을 2-3문장으로 요약", "guest": "출연자/인터뷰 대상자 정보 (없으면 빈 문자열)", "guest_name": "출연자 실명 (대본에서 언급된 이름만, 없으면 빈 문자열)", "keywords": ["핵심키워드1", "핵심키워드2", "핵심키워드3", "핵심키워드4", "핵심키워드5"], "search_queries": ["유튜브 검색 쿼리1", "유튜브 검색 쿼리2", "유튜브 검색 쿼리3", "유튜브 검색 쿼리4", "유튜브 검색 쿼리5"], "key_points": ["핵심 포인트1", "핵심 포인트2", "핵심 포인트3"], "notable_quotes": ["인상적인 발언1", "인상적인 발언2"]}}

keywords 작성 규칙:
- 영상의 핵심 주제를 나타내는 명사/명사구 위주로 추출
- 절대 조사, 어미, 일반적인 동사(하다, 있다, 되다 등)는 포함하지 말 것
- 구체적인 소재: 직업명, 사업 분야, 금액, 브랜드명, 플랫폼명, 도구명 등
- 예시: '일본 쇼츠 부업', '유튜브 수익화', '무역업', '캡컷 편집', '월 700만원'

search_queries 작성 규칙 (매우 중요!):
- 이 영상과 정확히 같은 주제의 유튜브 영상을 찾기 위한 검색 쿼리 5개
- 반드시 2~3단어 키워드 조합으로 짧게 작성
- 금액, 수익, 돈, 월수입 등 숫자/금전 표현은 절대 넣지 마세요. 주제 키워드만!
- 플랫폼명 + 핵심소재 조합으로 작성
- 좋은 예시: '구글 블로그 애드센스', '티스토리 블로그 부업', 'AI 블로그 글쓰기'
- 좋은 예시: '유튜브 쇼츠 부업', '일본 쇼츠 수출', '캡컷 쇼츠 편집'
- 좋은 예시: '쿠팡 파트너스', '스마트스토어 창업', '네이버 블로그 수익화'
- 나쁜 예시: '블로그 부업 월 3억' (금액 포함), '구글 블로그 애드센스 수익' (수익 불필요)
- 나쁜 예시: '월 3억 수익 방법' (주제 특정 안됨), '부업으로 돈 많이 버는 법' (너무 일반적)

스크립트:
{transcript}
"""

MAX_RETRIES = 3


def _call_with_retry(client, **kwargs):
    """API 호출 시 overloaded/rate limit 에러에 대해 자동 재시도."""
    for attempt in range(MAX_RETRIES):
        try:
            return client.messages.create(**kwargs)
        except (anthropic.APIStatusError, anthropic.RateLimitError) as e:
            if attempt < MAX_RETRIES - 1:
                wait = 5 * (attempt + 1)
                time.sleep(wait)
            else:
                raise


def generate_titles(
    transcript: str,
    pattern_analysis: dict,
    num_titles: int = NUM_TITLE_SUGGESTIONS,
) -> list[dict]:
    """스크립트와 패턴 분석을 기반으로 제목을 생성한다."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # 긴 스크립트는 요약 후 사용
    if len(transcript) > 10000:
        transcript = _summarize_transcript(client, transcript)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        pattern_summary=pattern_analysis.get("summary_for_prompt", "데이터 없음")
    )
    user_prompt = USER_PROMPT_TEMPLATE.format(
        transcript=transcript,
        num_titles=num_titles,
    )

    response = _call_with_retry(
        client,
        model=CLAUDE_MODEL,
        max_tokens=CLAUDE_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    response_text = response.content[0].text
    return _parse_titles(response_text)


def analyze_transcript(transcript: str) -> dict:
    """스크립트를 분석하여 내용 요약, 키워드, 핵심 포인트를 반환한다."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    # 긴 대본은 앞/중간/뒤를 골고루 샘플링
    if len(transcript) > 8000:
        chunk = 2600
        mid = len(transcript) // 2
        text = transcript[:chunk] + "\n\n[...중략...]\n\n" + transcript[mid - chunk // 2:mid + chunk // 2] + "\n\n[...중략...]\n\n" + transcript[-chunk:]
    else:
        text = transcript

    prompt = ANALYSIS_PROMPT.format(transcript=text)
    response = _call_with_retry(
        client,
        model=CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return _safe_parse_json(response.content[0].text)


def _safe_parse_json(text: str) -> dict:
    """Claude 응답에서 JSON을 안전하게 파싱한다."""
    empty = {"summary": "", "guest": "", "keywords": [], "search_queries": [], "key_points": [], "notable_quotes": []}
    text = text.strip()

    # 코드블록 제거
    if "```json" in text:
        text = text[text.index("```json") + 7:]
        if "```" in text:
            text = text[:text.index("```")]
    elif "```" in text:
        text = text[text.index("```") + 3:]
        if "```" in text:
            text = text[:text.index("```")]

    # { } 추출
    text = text.strip()
    if "{" in text:
        start = text.index("{")
        end = text.rfind("}")
        if end > start:
            text = text[start:end + 1]

    # 1차 시도
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2차: 줄바꿈/제어문자 정리
    import re as _re
    # JSON 문자열 값 내부의 줄바꿈을 공백으로
    cleaned = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    # 연속 공백 제거
    cleaned = _re.sub(r" {2,}", " ", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3차: 이스케이프 안 된 따옴표 처리
    try:
        # 문자열 값 내의 이스케이프 안 된 따옴표를 작은따옴표로
        fixed = _re.sub(r'(?<=: ")(.*?)(?="[,\s\n\r]*[}\]])', lambda m: m.group(1).replace('"', "'"), cleaned)
        return json.loads(fixed)
    except (json.JSONDecodeError, Exception):
        pass

    return empty


def analyze_thumbnails(thumbnail_urls: list[str]) -> str:
    """유사 영상 썸네일 이미지들의 텍스트를 분석한다."""
    import base64
    import urllib.request

    if not thumbnail_urls or not ANTHROPIC_API_KEY:
        return ""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # 썸네일 이미지를 다운로드 → base64 변환
    image_blocks = []
    for url in thumbnail_urls[:5]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = resp.read()
            if len(data) > 1000:
                b64 = base64.b64encode(data).decode()
                image_blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                })
        except Exception:
            continue

    if not image_blocks:
        return ""

    image_blocks.append({
        "type": "text",
        "text": """위 유튜브 인기 영상 썸네일 이미지들을 분석해주세요.
이 이미지들은 유튜브 썸네일입니다. 썸네일 위에 큰 글씨로 적혀있는 한국어 텍스트를 정확히 읽어야 합니다.

각 썸네일(1번부터 순서대로)에서:
1. 썸네일 위에 적혀있는 텍스트/문구를 한 글자도 빠짐없이 정확하게 읽어주세요 (한국어 텍스트에 집중)
2. 텍스트가 몇 줄인지
3. 글자 색상 (흰색, 노란색, 빨간색 등)
4. 강조 방식 (테두리, 그림자, 크기 차이 등)

마지막에 '공통 패턴 요약'으로 이 썸네일들의 문구 스타일 특징을 정리해주세요.
(숫자/금액 사용법, 자극적 단어, 줄 구성 패턴 등)"""
    })

    try:
        response = _call_with_retry(
            client,
            model=CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": image_blocks}],
        )
        return response.content[0].text
    except Exception as e:
        print(f"[썸네일 분석 에러] {e}")
        return ""


def _summarize_transcript(client: anthropic.Anthropic, transcript: str) -> str:
    """긴 스크립트를 요약한다."""
    response = _call_with_retry(
        client,
        model=CLAUDE_MODEL,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": SUMMARY_PROMPT.format(transcript=transcript),
        }],
    )
    return response.content[0].text


def _parse_titles(response_text: str) -> list[dict]:
    """Claude 응답에서 제목 목록을 파싱한다."""
    # JSON 블록 추출 시도
    text = response_text.strip()

    # ```json ... ``` 블록 찾기
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()

    try:
        data = json.loads(text)
        titles = data.get("titles", [])
    except json.JSONDecodeError:
        # JSON 파싱 실패 시 텍스트에서 제목 추출 시도
        titles = _fallback_parse(response_text)

    # 점수 기준 정렬
    titles.sort(key=lambda t: t.get("score", 0), reverse=True)
    return titles


def evaluate_title(title: str, transcript: str, ref_videos: list = None) -> str:
    """사용자가 직접 작성한 제목을 평가한다."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if len(transcript) > 8000:
        chunk = 2600
        mid = len(transcript) // 2
        transcript = transcript[:chunk] + "\n[...중략...]\n" + transcript[mid - chunk // 2:mid + chunk // 2] + "\n[...중략...]\n" + transcript[-chunk:]

    ref_info = ""
    if ref_videos:
        ref_info = "\n\n## 비슷한 주제의 고조회수 레퍼런스 영상\n"
        for sv in ref_videos:
            ref_info += f"- \"{sv['title']}\" ({sv.get('channel_name', '')}, {sv.get('view_count', 0):,}회)\n"

    prompt = f"""아래 유튜브 영상 스크립트에 대해, 사용자가 직접 작성한 제목을 평가해주세요.
{ref_info}

## 사용자 제목
"{title}"

## 영상 스크립트
{transcript}

아래 항목별로 평가해주세요:

1. **점수**: 100점 만점 (숫자만)
2. **잘한 점**: 이 제목의 장점 (1~2줄)
3. **아쉬운 점**: 개선할 부분 (1~2줄)
4. **개선 제안**: 이 제목을 살짝 다듬은 버전 2~3개 (원래 의도를 유지하면서)

간결하게 답변해주세요. 마크다운 형식으로."""

    response = _call_with_retry(
        client,
        model=CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _fallback_parse(text: str) -> list[dict]:
    """JSON 파싱 실패 시 텍스트에서 제목을 추출한다."""
    titles = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if line and (line.startswith('"') or line.startswith("「")):
            title = line.strip('"「」"\'')
            if title and len(title) > 5:
                titles.append({
                    "title": title,
                    "score": 0,
                    "reasoning": "자동 파싱됨",
                    "patterns_used": [],
                    "style_reference": "",
                })
    return titles
