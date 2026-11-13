"""설정값 모음. 비밀값은 모두 환경변수(GitHub Secrets)로 받습니다."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
WORK_DIR = ROOT / "work"
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"


def env(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


# --- API 키 (GitHub Secrets) ---
GEMINI_API_KEY = env("GEMINI_API_KEY")
PIXABAY_API_KEY = env("PIXABAY_API_KEY")
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")
IG_USER_ID = env("IG_USER_ID")
IG_ACCESS_TOKEN = env("IG_ACCESS_TOKEN")

# --- 선택 설정 (GitHub Variables) ---
# 앞에서부터 차례로 시도하고, 실패하면 다음 모델로 넘어갑니다.
GEMINI_MODELS = [m.strip() for m in env(
    "GEMINI_MODELS", "gemini-flash-latest,gemini-2.5-flash,gemini-2.0-flash").split(",") if m.strip()]
BRAND_NAME = env("BRAND_NAME", "오늘의 글로벌 경제")
TTS_VOICE = env("TTS_VOICE", "ko-KR-SunHiNeural")   # 남성: ko-KR-InJoonNeural
TTS_RATE = env("TTS_RATE", "+12%")
TTS_ENGINE = env("TTS_ENGINE", "edge")               # edge | gtts | dummy
FONT_NAME = env("FONT_NAME", "Noto Sans CJK KR")
# 비워 두면 토큰 종류로 자동 선택: EAA… → graph.facebook.com(통합 로그인), IG… → graph.instagram.com
IG_GRAPH_HOST = env("IG_GRAPH_HOST")
IG_API_VERSION = env("IG_API_VERSION", "v23.0")

# --- 영상 규격 ---
W, H, FPS = 1080, 1920, 30

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
