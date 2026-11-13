"""RSS로 지난 24~30시간의 세계 경제 뉴스를 모으고, 여러 매체가 동시에 다룬 순으로 점수를 매깁니다."""
import datetime as dt
import email.utils
import html
import re
import xml.etree.ElementTree as ET

import requests

from . import config

GN = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="
FEEDS = [
    ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
    ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"),
    ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("BBC", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("Google News", "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en"),
    ("Google News", GN + "site:reuters.com+(economy+OR+markets)+when:1d"),
    ("Google News", GN + "site:bloomberg.com+(economy+OR+markets)+when:1d"),
    ("Google News", GN + "site:ft.com+economy+when:1d"),
    ("Google News KR", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"),
]

STOP = set("""the a an and or of to in on for with at by from as is are was were be been this that
these those it its into over after before about amid says said say new more than will would could
can may might up down out not but has have had how why what who when where which their they them
his her he she you your our we us all any some just also year years week day today report reports
news live update updates""".split())


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _child(el, *names):
    for c in el:
        if _local(c.tag) in names:
            return c
    return None


def _clean(s, limit=500):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def _date(s):
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except Exception:
        try:
            d = dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d


def parse_feed(xml_text, default_source):
    items = []
    root = ET.fromstring(xml_text)
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        t = _child(el, "title")
        title = _clean(t.text if t is not None else "", 300)
        if not title:
            continue
        l = _child(el, "link")
        link = ""
        if l is not None:
            link = (l.text or "").strip() or l.attrib.get("href", "")
        d = _child(el, "description", "summary", "content")
        p = _child(el, "pubdate", "published", "updated")
        s = _child(el, "source")
        source = _clean(s.text) if s is not None and s.text else default_source
        # 구글 뉴스 제목은 "제목 - 매체명" 형식
        if default_source.startswith("Google News") and " - " in title:
            title, src = title.rsplit(" - ", 1)
            source = source if source != default_source else src
        summary = _clean(d.text if d is not None else "")
        if summary.startswith(title[:40]):  # 구글 뉴스는 요약에 제목만 반복됨
            summary = ""
        items.append({"title": title, "link": link, "summary": summary, "source": source,
                      "published": (_date(p.text) if p is not None else None)})
    return items


def fetch_all(feeds=FEEDS):
    out = []
    for name, url in feeds:
        try:
            r = requests.get(url, headers=config.UA, timeout=15)
            r.raise_for_status()
            got = parse_feed(r.content, name)
            out.extend(got)
            print(f"  [뉴스] {name}: {len(got)}건")
        except Exception as e:
            print(f"  [뉴스] {name} 실패: {e}")
    return out


def tokens(text):
    words = re.findall(r"[a-z][a-z0-9'\-]+|[가-힣]{2,}", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in STOP}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def rank(items, history, max_age_hours=30, top=25):
    """여러 매체가 비슷한 뉴스를 동시에 보도할수록 높은 점수."""
    now = dt.datetime.now(dt.timezone.utc)
    seen, pool = set(), []
    for it in items:
        if it["published"] and (now - it["published"]).total_seconds() > max_age_hours * 3600:
            continue
        key = re.sub(r"\W+", "", it["title"].lower())[:80]
        if key in seen:
            continue
        seen.add(key)
        it["_tok"] = tokens(it["title"] + " " + it["summary"][:200])
        pool.append(it)

    hist_tok = [tokens(h.get("title_en", "") + " " + h.get("topic", "")) for h in history]

    for i, it in enumerate(pool):
        related = [j for j, o in enumerate(pool) if j != i and jaccard(it["_tok"], o["_tok"]) >= 0.18]
        sources = {pool[j]["source"] for j in related} - {it["source"]}
        age_h = (now - it["published"]).total_seconds() / 3600 if it["published"] else 24
        it["score"] = round(len(sources) * 1.0 + len(related) * 0.3 + max(0, 24 - age_h) / 24, 2)
        it["related"] = related
        it["_dup_history"] = any(jaccard(it["_tok"], h) >= 0.35 for h in hist_tok if h)

    fresh = [it for it in pool if not it["_dup_history"]]
    fresh.sort(key=lambda x: x["score"], reverse=True)
    return fresh[:top], pool


def fetch_article_text(url, limit=3500):
    """기사 본문 일부를 가져옵니다 (실패하면 빈 문자열). 수치 확인용 참고 자료로만 씁니다."""
    if not url or "news.google.com" in url:
        return ""
    try:
        r = requests.get(url, headers=config.UA, timeout=12)
        if r.status_code != 200:
            return ""
        paras = re.findall(r"<p[^>]*>(.*?)</p>", r.text, flags=re.S | re.I)
        text = " ".join(_clean(p, 2000) for p in paras)
        return text[:limit]
    except Exception:
        return ""
