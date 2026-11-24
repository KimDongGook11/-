"""승인 대기 영상: 시리즈마다 하나씩 (state/pending_news.json, state/pending_history.json)."""
from .utils import load_state, save_state

SERIES = ("us", "news", "kr", "re", "history", "youtube")
LABEL = {"us": "미국 증시 마감", "news": "오늘의 원픽", "kr": "국내 증시 마감", "re": "주간 부동산", "history": "그때 그 결정",
         "youtube": "유튜브 장편", "talk": "이슈 뒷담화"}


def load(series):
    p = load_state(f"pending_{series}", None)
    if p is None and series == "news":          # 예전 파일(state/pending.json) 호환
        p = load_state("pending", None)
        if p is not None:
            p.setdefault("series", "news")
    return p


def save(series, data):
    save_state(f"pending_{series}", data)
    if series == "news":
        save_state("pending", None)


def all_items():
    return [p for s in SERIES if (p := load(s))]


def find(rid):
    return next((p for p in all_items() if p.get("id") == rid), None)
