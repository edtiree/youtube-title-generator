import time
import openai
from config import OPENAI_API_KEY, WHISPER_MODEL, WHISPER_LANGUAGE


def transcribe_audio(audio_paths: list[str], language: str = WHISPER_LANGUAGE, progress_callback=None) -> dict:
    """오디오 파일들을 Whisper API로 트랜스크립션한다."""
    client = openai.OpenAI(api_key=OPENAI_API_KEY)

    all_text = []
    all_segments = []
    total_duration = 0.0

    for i, path in enumerate(audio_paths):
        if progress_callback:
            progress_callback(i, len(audio_paths))

        text, segments, duration = _transcribe_single(client, path, language)
        all_text.append(text)
        all_segments.extend(segments)
        total_duration += duration

    if progress_callback:
        progress_callback(len(audio_paths), len(audio_paths))

    # 오버랩 구간 중복 제거 (간단한 방식: 텍스트 합치기)
    full_text = " ".join(all_text)

    return {
        "full_text": full_text,
        "segments": all_segments,
        "duration_seconds": total_duration,
    }


def _transcribe_single(client: openai.OpenAI, audio_path: str, language: str, max_retries: int = 3) -> tuple:
    """단일 오디오 파일을 트랜스크립션한다. 실패 시 재시도."""
    for attempt in range(max_retries):
        try:
            with open(audio_path, "rb") as f:
                response = client.audio.transcriptions.create(
                    model=WHISPER_MODEL,
                    file=f,
                    language=language,
                    response_format="verbose_json",
                )

            text = response.text
            segments = []
            if hasattr(response, "segments") and response.segments:
                segments = [
                    {
                        "start": s.start if hasattr(s, 'start') else s.get("start", 0),
                        "end": s.end if hasattr(s, 'end') else s.get("end", 0),
                        "text": s.text if hasattr(s, 'text') else s.get("text", ""),
                    }
                    for s in response.segments
                ]
            duration = response.duration if hasattr(response, "duration") else 0.0

            return text, segments, duration

        except openai.RateLimitError:
            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                raise
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise
