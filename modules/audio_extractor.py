import os
import re
import shutil
import subprocess
import tempfile
from config import AUDIO_BITRATE, AUDIO_SAMPLE_RATE, AUDIO_CHANNELS, MAX_CHUNK_SIZE_MB, CHUNK_OVERLAP_SECONDS


def _get_ytdlp_path():
    """yt-dlp 실행 경로를 자동 탐지한다."""
    path = shutil.which("yt-dlp")
    if path:
        return path
    # 로컬 fallback
    local = os.path.expanduser("~/Library/Python/3.9/bin/yt-dlp")
    if os.path.exists(local):
        return local
    return "yt-dlp"


def download_youtube_subtitle(url: str) -> str:
    """YouTube URL에서 자막을 텍스트로 추출한다. 다운로드 불필요, 빠르고 무료."""
    from youtube_transcript_api import YouTubeTranscriptApi

    # URL에서 video ID 추출
    video_id = _extract_video_id(url)
    if not video_id:
        raise RuntimeError("올바른 YouTube URL이 아닙니다.")

    ytt_api = YouTubeTranscriptApi()

    # 한국어 → 영어 순서로 시도
    for langs in [["ko"], ["en"], ["ko", "en", "ja"]]:
        try:
            transcript = ytt_api.fetch(video_id, languages=langs)
            texts = [s.text for s in transcript.snippets]
            return " ".join(texts)
        except Exception:
            continue

    raise RuntimeError("자막을 찾을 수 없습니다. '파일 업로드' 또는 '대본 직접 입력'을 이용해주세요.")


def _extract_video_id(url: str) -> str:
    """YouTube URL에서 video ID를 추출한다."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'(?:shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return ""


def download_youtube_audio(url: str) -> str:
    """YouTube URL에서 오디오를 MP3로 다운로드한다 (폴백용)."""
    tmp_dir = tempfile.mkdtemp()
    output_template = os.path.join(tmp_dir, "audio.%(ext)s")

    cmd = [
        _get_ytdlp_path(),
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "64K",
        "--no-playlist",
        "--no-warnings",
        "--force-overwrites",
        "-o", output_template,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    for f in os.listdir(tmp_dir):
        filepath = os.path.join(tmp_dir, f)
        if os.path.isfile(filepath) and os.path.getsize(filepath) > 0:
            return filepath

    stderr = result.stderr or ""
    errors = [l for l in stderr.split("\n") if "ERROR" in l]
    raise RuntimeError(f"다운로드 실패: {errors[0] if errors else '파일을 생성하지 못했습니다.'}")


def get_youtube_title(url: str) -> str:
    """YouTube URL에서 영상 제목을 가져온다."""
    cmd = [_get_ytdlp_path(), "--get-title", "--no-playlist", "--no-warnings", url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        return result.stdout.strip()
    return ""


def is_youtube_url(url: str) -> bool:
    """YouTube URL인지 확인한다."""
    return bool(re.match(r'https?://(www\.)?(youtube\.com|youtu\.be)/', url))


def extract_audio(video_bytes: bytes, filename: str) -> str:
    """영상 파일에서 오디오를 MP3로 추출한다."""
    suffix = os.path.splitext(filename)[1] or ".mp4"
    tmp_video = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp_video.close()
    tmp_audio.close()

    try:
        with open(tmp_video.name, "wb") as f:
            f.write(video_bytes)

        cmd = [
            "ffmpeg", "-y",
            "-i", tmp_video.name,
            "-vn",
            "-ac", str(AUDIO_CHANNELS),
            "-ar", str(AUDIO_SAMPLE_RATE),
            "-b:a", AUDIO_BITRATE,
            "-f", "mp3",
            tmp_audio.name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 오류: {result.stderr[:500]}")
    finally:
        os.unlink(tmp_video.name)

    return tmp_audio.name


def chunk_audio_if_needed(audio_path: str, max_size_mb: float = MAX_CHUNK_SIZE_MB) -> list[str]:
    """오디오 파일이 max_size_mb를 초과하면 청크로 분할한다."""
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)

    if file_size_mb <= max_size_mb:
        return [audio_path]

    from pydub import AudioSegment
    audio = AudioSegment.from_mp3(audio_path)
    total_ms = len(audio)

    # 청크당 시간 계산 (파일 크기 비례)
    chunk_duration_ms = int(total_ms * (max_size_mb / file_size_mb) * 0.9)
    overlap_ms = CHUNK_OVERLAP_SECONDS * 1000

    chunks = []
    start = 0
    while start < total_ms:
        end = min(start + chunk_duration_ms, total_ms)
        chunk = audio[start:end]

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp.close()
        chunk.export(tmp.name, format="mp3", bitrate=AUDIO_BITRATE)
        chunks.append(tmp.name)

        if end >= total_ms:
            break
        start = end - overlap_ms

    # 원본 파일 삭제
    os.unlink(audio_path)
    return chunks


def extract_frames_from_youtube(url: str, num_frames: int = 6) -> list[str]:
    """YouTube 영상의 여러 시점 썸네일을 가져온다. base64 이미지 리스트 반환."""
    import base64
    import urllib.request

    video_id = _extract_video_id(url)
    if not video_id:
        return []

    # 영상 프레임만 (채널 썸네일 제외) - 25%, 50%, 75% 지점
    # sd = 640x480, hq = 480x360 (폴백)
    thumb_urls = [
        f"https://i.ytimg.com/vi/{video_id}/sd1.jpg",
        f"https://i.ytimg.com/vi/{video_id}/sd2.jpg",
        f"https://i.ytimg.com/vi/{video_id}/sd3.jpg",
    ]

    frames = []
    seen_sizes = set()
    for thumb_url in thumb_urls:
        try:
            req = urllib.request.Request(thumb_url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = resp.read()
            # 유효한 이미지인지 확인 (120x90 기본 플레이스홀더 제외)
            if len(data) > 2000 and len(data) not in seen_sizes:
                seen_sizes.add(len(data))
                # 로고(상단 12%)와 자막(하단 18%) 크롭
                data = _crop_clean(data)
                b64 = base64.b64encode(data).decode()
                frames.append(f"data:image/jpeg;base64,{b64}")
                if len(frames) >= num_frames:
                    break
        except Exception:
            continue

    return frames


def _crop_clean(image_bytes: bytes) -> bytes:
    """이미지에서 상단 로고(12%)와 하단 자막(18%) 영역을 잘라낸다."""
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    top = int(h * 0.12)
    bottom = int(h * 0.82)
    cropped = img.crop((0, top, w, bottom))

    # 16:9 비율로 리사이즈
    target_w = cropped.width
    target_h = int(target_w * 9 / 16)
    if target_h > cropped.height:
        target_h = cropped.height
        target_w = int(target_h * 16 / 9)
        left = (cropped.width - target_w) // 2
        cropped = cropped.crop((left, 0, left + target_w, target_h))
    else:
        top_offset = (cropped.height - target_h) // 2
        cropped = cropped.crop((0, top_offset, target_w, top_offset + target_h))

    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def extract_frames_from_upload(video_bytes: bytes, filename: str, num_frames: int = 6) -> list[str]:
    """업로드된 영상 파일에서 프레임을 추출한다. base64 이미지 리스트 반환."""
    tmp_dir = tempfile.mkdtemp()
    suffix = os.path.splitext(filename)[1] or ".mp4"
    tmp_video = os.path.join(tmp_dir, f"video{suffix}")

    try:
        with open(tmp_video, "wb") as f:
            f.write(video_bytes)
        return _extract_frames_from_file(tmp_video, tmp_dir, num_frames)
    except Exception:
        return []
    finally:
        if os.path.exists(tmp_video):
            os.unlink(tmp_video)


def _extract_frames_from_file(video_path: str, tmp_dir: str, num_frames: int = 6) -> list[str]:
    """영상 파일에서 균등 간격으로 프레임을 추출한다."""
    import base64

    # 영상 길이 확인
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    try:
        duration = float(result.stdout.strip())
    except (ValueError, AttributeError):
        return []

    if duration <= 0:
        return []

    # 균등 간격 타임스탬프 (시작/끝 10% 제외)
    start = duration * 0.1
    end = duration * 0.9
    timestamps = [start + (end - start) * i / (num_frames - 1) for i in range(num_frames)]

    frames = []
    for i, ts in enumerate(timestamps):
        frame_path = os.path.join(tmp_dir, f"frame_{i}.jpg")
        cmd = [
            "ffmpeg", "-y", "-ss", str(ts),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "3",
            frame_path,
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
            with open(frame_path, "rb") as f:
                raw = f.read()
            cleaned = _crop_clean(raw)
            b64 = base64.b64encode(cleaned).decode()
            frames.append(f"data:image/jpeg;base64,{b64}")
            os.unlink(frame_path)

    return frames


def cleanup_temp_files(file_paths: list[str]) -> None:
    """임시 파일들을 삭제한다."""
    for path in file_paths:
        try:
            if os.path.exists(path):
                os.unlink(path)
        except OSError:
            pass
