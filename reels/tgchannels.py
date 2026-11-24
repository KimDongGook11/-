"""텔레그램 공개 채널을 뉴스 자료로 (2026-11-24 사용자 결정, 9개 채널).
웹 미리보기(t.me/s/채널)로 최근 글을 읽어 쓰는 방식은 채널 성격마다 다름:
- source : 링크된 원문(DART 공시·기사)을 근거로 → 뉴스 후보에 원문 링크로 넣음 (공시는 요약 글이 곧 공시 내용)
- broker : 증권사 리서치 → '[증권사 의견]' 자료로, 대본에선 "○○증권은 ~로 봤어요"처럼 출처를 밝힌 의견으로만
- signal : 속보 번역 채널 → 사실 근거로 쓰지 않고, 같은 이슈를 다룬 채널 수만큼 뉴스 선정 점수를 올림
- idea   : 해설 채널 → 원픽 주제 후보로만 (출처가 없어 숫자는 쓰지 않음)
채널 글을 대본에 그대로 옮기지 않고, 출처에 텔레그램 채널 이름을 쓰지 않음."""
import datetime as dt
import html
import re

import requests

from . import config, news

CHANNELS = {
    "darthacking": {"label": "DART 공시", "mode": "source", "series": {"kr"}},
    "davidstocknew": {"label": "주식소리통", "mode": "source", "series": {"kr", "global"}},
    "kwusa": {"label": "키움증권 리서치", "mode": "broker", "series": {"us", "global"}},
    "hana_us_stock": {"label": "하나증권 리서치", "mode": "broker", "series": {"us", "global"}},
    "globaletfi": {"label": "하나증권 리서치", "mode": "broker", "series": {"us", "global"}},
    "insidertracking": {"label": "미국 주식 인사이더", "mode": "signal", "series": {"us", "global"}},
    "FastStockNewsUSA": {"label": "급등일보", "mode": "signal", "series": {"us", "global"}},
    "sharpha": {"label": "주식클라쓰", "mode": "signal", "series": {"kr", "global"}},
    "harveyspecterMike": {"label": "매크로 해설", "mode": "idea", "series": {"global"}},
}
SKIP_HOSTS = ("t.me", "telegram.me", "youtube.com", "youtu.be", "buly.kr", "da.gd", "iii.ad", "naver.me")
# 국내 공시는 큰 건만: 시가총액 1조 이상, 또는 계약·자사주 규모가 매출·시총의 10% 이상
BIG_CAP = 1e12


def _clean(fragment):
    t = re.sub(r"<br\s*/?>", "\n", fragment)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"[ \t]+", " ", t).strip()


def fetch(channel):
    """최근 글 [{text, links, published, url}] (최신이 뒤). 실패하면 []."""
    try:
        r = requests.get(f"https://t.me/s/{channel}", headers=config.UA, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"  [텔레그램 채널] {channel} 읽기 실패: {e}")
        return []
    posts = []
    for block in re.split(r'<div class="tgme_widget_message_wrap', r.text)[1:]:
        m = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
        if not m:
            continue
        when = re.search(r'<time datetime="([^"]+)"', block)
        post = re.search(r'data-post="([^"]+)"', block)
        links = [html.unescape(h) for h in re.findall(r'href="(https?://[^"]+)"', m.group(1))]
        posts.append({"text": _clean(m.group(1)), "url": f"https://t.me/{post.group(1)}" if post else "",
                      "links": [h for h in links if not any(s in h for s in SKIP_HOSTS)],
                      "published": dt.datetime.fromisoformat(when.group(1)) if when else None})
    return posts


def _recent(posts, hours):
    now = dt.datetime.now(dt.timezone.utc)
    return [p for p in posts if p["published"] and (now - p["published"]).total_seconds() < hours * 3600
            and len(p["text"]) >= 20]


HEADER = re.compile(r"^\s*(\[[^\]]{2,40}\]\s*$|◈.*◈|▶️?\s*(RA|텔레그램)|.*T\.\s?0?2-|\d{4}\.\d\d\.\d\d\s+[\d:]+$|https?://)")


def _title(text):
    """글의 첫 '내용' 줄 (작성자 꼬리표·전화번호·시각만 있는 줄은 건너뜀)."""
    for l in re.split(r"[\r\n\u2028\u2029]+", text):
        l = re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", l)).strip(" -•■▶*#")
        if len(l) >= 8 and not HEADER.match(l):
            return l.strip("[] ")[:120]
    return re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", text)).strip()[:80]


def _is_article(url):
    path = re.sub(r"^https?://[^/]+", "", url).strip("/")
    return len(path) >= 6   # 사이트 첫 화면 링크(finviz.com/ 등)는 기사가 아님


def _filing_title(text):
    name = re.search(r"기업명:\s*([^(\n]+)", text)
    rep = re.search(r"보고서명:\s*([^\n]+)", text)
    return f"{name.group(1).strip()} — {rep.group(1).strip()}" if name and rep else _title(text)


def _money(s):
    """'2조 1,527억' → 원 단위."""
    v = 0.0
    for num, unit in re.findall(r"([\d,.]+)\s*(조|억)", s or ""):
        v += float(num.replace(",", "")) * (1e12 if unit == "조" else 1e8)
    return v


def _big_filing(text):
    cap = _money((re.search(r"시가총액:\s*([^)]+)\)", text) or re.search("()", "")).group(1))
    ratio = re.search(r"(매출대비|시총대비)\s*:\s*([\d.]+)%", text)
    if "보유목적 : 경영권" in text or "보유목적: 경영권" in text:
        return True
    return cap >= BIG_CAP or (ratio and float(ratio.group(2)) >= 10)


def collect(focus, hours=24):
    """반환: (뉴스 후보 items, 화제 신호 토큰 목록, 화제·주제 제목 목록(선정 참고용), 큰 공시 자료 목록)"""
    items, signals, ideas, filings = [], [], [], []
    for ch, info in CHANNELS.items():
        if focus not in info["series"]:
            continue
        posts = _recent(fetch(ch), hours)
        mode = info["mode"]
        for p in posts:
            title = _title(p["text"])
            if len(title) < 8:
                continue
            if mode == "signal":
                signals.append(news.tokens(title + " " + p["text"][:200]))
                ideas.append(title)   # 원픽·브리핑 선정 때 '오늘 화제' 참고 목록으로도
            elif mode == "idea":
                ideas.append(title)
            elif mode == "broker":
                items.append({"title": "[증권사 의견] " + title, "link": (p["links"] or [p["url"]])[0],
                              "summary": p["text"][:300], "body": p["text"][:3000], "source": info["label"],
                              "published": p["published"], "opinion": True})
            elif ch == "darthacking":
                if _big_filing(p["text"]):
                    filings.append({"title": "[공시] " + _filing_title(p["text"]),
                                    "link": (p["links"] or [p["url"]])[0], "summary": p["text"][:300],
                                    "body": p["text"][:1500], "source": "DART 공시", "published": p["published"]})
            elif any(_is_article(h) for h in p["links"]):   # 기사 링크 채널: 원문 기사로
                link = next(h for h in p["links"] if _is_article(h))
                items.append({"title": title, "link": link, "summary": "", "source": _host(link),
                              "published": p["published"]})
        print(f"  [텔레그램 채널] {info['label']}({ch}): 최근 {len(posts)}건 ({mode})")
    return items, signals, ideas, filings[:4]


def _host(url):
    h = re.sub(r"^https?://(www\.|m\.|n\.)?", "", url).split("/")[0]
    names = {"yna.co.kr": "연합뉴스", "news.naver.com": "네이버 뉴스", "donga.com": "동아일보", "edaily.co.kr": "이데일리",
             "hankyung.com": "한국경제", "mk.co.kr": "매일경제", "thelec.kr": "디일렉", "chosun.com": "조선일보",
             "sedaily.com": "서울경제", "mt.co.kr": "머니투데이", "reuters.com": "Reuters", "sec.gov": "SEC"}
    return next((v for k, v in names.items() if h.endswith(k)), h)


def boost(cands, signals, per=0.5, cap=2.0):
    """속보 채널 여러 곳이 같은 이슈를 다루면 화제성 점수를 올림 (채널당 +0.5, 최대 +2)."""
    if not signals:
        return cands
    for c in cands:
        tok = c.get("_tok") or news.tokens(c["title"] + " " + c.get("summary", "")[:200])
        hit = sum(1 for s in signals if news.jaccard(tok, s) >= 0.15)
        if hit:
            c["score"] = round(c["score"] + min(cap, hit * per), 2)
            c["tg_signal"] = hit
    cands.sort(key=lambda x: x["score"], reverse=True)
    return cands
