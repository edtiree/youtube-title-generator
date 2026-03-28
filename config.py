import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# Target YouTube Channels (비즈니스/자기계발 인터뷰 채널)
TARGET_CHANNELS = {
    # 기존 채널
    "UC31-nUU7jhm3I5DCYh6uLBA": "휴먼스토리",
    "UCgArjx0NL02Ulo69__m8k_A": "돈벌쥐",
    "UCfXp9zjXf49v3mqS6gi1G0Q": "현장속으로",
    "UCc666E6MZ5NEzWnRs_JFifA": "일터뷰",
    "UCucFucgJnJKJRTEaO-_Fqsw": "머니로드",
    "UCcudWSylWbpKj4FgT0xVX1w": "직업의온도",
    "UCDAmWzKQzoqmiSeFcAujgrg": "머니멘터리",
    # 추가 인터뷰 채널
    "UCIueALBHAyPPU7e7C2zVYRQ": "직업의모든것",
    "UClSUMM1_Ptww_Xe8AJJ9aPA": "30대 자영업자 이야기",
    "UC-EGSdvtv-2DU0379QyjamQ": "갈때까지간 남자",
    "UCfY7XL2ON1YhPJdAA-OGaZQ": "까레라이스TV",
    "UCLE8p8wtDGSNEPv2w0OG8yg": "잼뱅TV",
    "UCPR3eX5oGzNi_tPjd4MolvQ": "고수감별사",
}

# Audio Processing
AUDIO_BITRATE = "64k"
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
MAX_CHUNK_SIZE_MB = 24.0
CHUNK_OVERLAP_SECONDS = 30

# Whisper
WHISPER_MODEL = "whisper-1"
WHISPER_LANGUAGE = "ko"

# Claude
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 4096
NUM_TITLE_SUGGESTIONS = 3

# Cache
CACHE_FILE = os.path.join(os.path.dirname(__file__), "data", "channel_cache.json")
CACHE_MAX_AGE_DAYS = 7
