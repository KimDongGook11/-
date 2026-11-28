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
    "GEMINI_MODELS", "gemini-flash-latest,gemini-flash-lite-latest").split(",") if m.strip()]
BRAND_NAME = env("BRAND_NAME", "경제원픽")
if BRAND_NAME == "오늘의 글로벌 경제":   # 2026-11-21 채널명 변경(경제원픽). 예전 기본값이 Variables에 남아 있어도 새 이름으로
    BRAND_NAME = "경제원픽"
TTS_VOICE = env("TTS_VOICE", "ko-KR-SunHiNeural")   # 남성: ko-KR-InJoonNeural
TTS_RATE = env("TTS_RATE", "+12%")
TTS_ENGINE = env("TTS_ENGINE", "typecast" if env("TYPECAST_API_KEY") else "edge")   # edge | typecast | gemini | gtts | dummy
FONT_NAME = env("FONT_NAME", "Noto Sans CJK KR")
# 비워 두면 토큰 종류로 자동 선택: EAA… → graph.facebook.com(통합 로그인), IG… → graph.instagram.com
IG_GRAPH_HOST = env("IG_GRAPH_HOST")
IG_API_VERSION = env("IG_API_VERSION", "v23.0")

# 오늘의 경제 마지막에 매일 붙는 마무리 멘트 (비워 두려면 Variables에 OUTRO_TEXT를 공백 한 칸으로)
OUTRO_TEXT = env("OUTRO_TEXT", "매일 아침 경제 뉴스 딱 하나, 구독하고 내일 또 만나요!")
# 유튜브 쇼츠 공개 시각(한국시간). 승인이 이 시각 전이면 이 시각에 예약 공개, 지나면 바로 공개. 비우면 항상 바로 공개
YT_SHORTS_TIME = env("YT_SHORTS_TIME", "07:30")
# 그때 그 결정 1분 세로 요약(인스타 릴스·유튜브 쇼츠)도 만들지. 2026-11-17 22:32 사용자 최종 결정: 만듦
# (5분 장편 = 유튜브, 1분 요약 = 인스타 릴스 + 유튜브 쇼츠). 끄려면 Variables에 HISTORY_SHORT=false
HISTORY_SHORT = env("HISTORY_SHORT", "true").lower() == "true"

# --- 채널 성장 운영 설정 (2026-11-21 채널 진단 반영) ---
# 그때 그 결정 5분 장편을 만들어 유튜브에 올릴지. 진단 결과 3~5분 장편의 중앙 조회수가 7회라 기본은 끔(쇼츠 집중).
# 쇼츠 반응이 좋았던 주제(조회수 500회 이상)로 심층 장편을 만들 때만 Variables에 HISTORY_LONG=true
HISTORY_LONG = env("HISTORY_LONG", "false").lower() == "true"
# 하루 운영 (2026-11-21 사용자 결정): 07:00 미국 증시 마감 / 12:00 오늘의 원픽(그날 이슈 하나) / 17:00 국내 마감 브리핑·뉴스 정리 (11/25 사용자 결정: 18:00→17:00, 제작 16:00. 주말은 그대로)
# 주말: 토 07:00 미국 마감(금요일장), 12:00 원픽, 18:00 그때 그 결정
# 시리즈별 유튜브 쇼츠 공개 시각(한국시간). 승인이 이 시각 전이면 예약 공개, 지나면 바로 공개. 비우면 바로 공개
# (예전 YT_SHORTS_TIME 변수는 쓰지 않음: 원픽 시간이 아침→낮으로 바뀌어 예전 값이 남아 있으면 어긋나기 때문)
YT_SLOTS = {
    "us": env("YT_US_TIME", "07:00"),            # 미국 증시 마감 브리핑
    "news": env("YT_NEWS_TIME", "12:00"),        # 오늘의 원픽
    "kr": env("YT_KR_TIME", "17:00"),            # 국내 증시 마감 브리핑 + 뉴스 정리
    "history": env("YT_HISTORY_TIME", "18:00"),  # 그때 그 결정 (주말)
    "re": env("YT_RE_TIME", "12:00"),            # 주간 부동산 (토요일)
}
# 시리즈별 마무리 멘트 (예전 OUTRO_TEXT 변수는 '매일 아침' 문구라 쓰지 않음)
OUTROS = {
    "us": env("US_OUTRO_TEXT", "매일 아침 7시 미국 증시 정리, 구독하고 내일 또 만나요!"),
    "news": env("NEWS_OUTRO_TEXT", "매일 낮 12시 경제 이슈 딱 하나, 구독하고 내일 또 만나요!"),
    "kr": env("KR_OUTRO_TEXT", "매일 오후 5시 국내 증시 정리, 구독하고 내일 또 만나요!"),
    "re": env("RE_OUTRO_TEXT", "매주 토요일 낮 12시 부동산 정리, 구독하고 다음 주에 또 만나요!"),
}
OUTRO_TEXT = OUTROS["news"]
# 주말(토·일)에는 그때 그 결정을 하루 2편: 12:00(원픽 자리, daily.yml) + 18:00(history.yml). 끄려면 WEEKEND_HISTORY=false
WEEKEND_HISTORY = env("WEEKEND_HISTORY", "true").lower() == "true"
# 제작 전 주제 고르기 (2026-11-28 사용자 결정): 후보 2~3개를 텔레그램으로 보내고 고르면 제작.
# 정해진 시간(분) 안에 안 고르면 1순위로 자동 진행. 끄려면 Variables에 TOPIC_PICK=false
TOPIC_PICK = env("TOPIC_PICK", "true").lower() == "true"
TOPIC_WAIT = {"us": 15, "kr": 15, "news": 40, "global": 40, "re": 40, "history": 40}
# 채널 핸들 (설명란 구독 링크용). 2026-11-21 핸들 변경 완료 → 기본값. 다르게 쓰려면 Variables에 CHANNEL_HANDLE
CHANNEL_HANDLE = env("CHANNEL_HANDLE", "@econonepick")

# --- 영상 규격 ---
W, H, FPS = 1080, 1920, 30

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
