"""RSS로 지난 24~30시간의 세계 경제 뉴스를 모으고, 여러 매체가 동시에 다룬 순으로 점수를 매깁니다."""
import datetime as dt
import email.utils
import html
import json
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
    ("Google News", "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en"),
    ("Google News", GN + "site:reuters.com+(economy+OR+markets)+when:1d"),
    ("Google News", GN + "site:bloomberg.com+(economy+OR+markets)+when:1d"),
    ("Google News", GN + "site:ft.com+economy+when:1d"),
    ("Google News KR", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"),
    # 본문을 받을 수 있는 매체 (2026-11-17 추가: 팩트체크 근거 확보용)
    ("Guardian", "https://www.theguardian.com/business/economics/rss"),
    ("Guardian", "https://www.theguardian.com/business/rss"),
    ("NPR", "https://feeds.npr.org/1017/rss.xml"),
    ("Google News", GN + "site:apnews.com+(economy+OR+markets+OR+stocks)+when:1d"),
    ("연합뉴스", "https://www.yna.co.kr/rss/economy.xml"),
    ("매일경제", "https://www.mk.co.kr/rss/30100041/"),
]

GN_KR = "https://news.google.com/rss/search?hl=ko&gl=KR&ceid=KR:ko&q="
# 국내 증시 원픽용 (2026-11-21 채널 진단: 고성장 채널 인기 쇼츠는 삼전·하이닉스·코스피 같은 국내 투자 주제)
KR_FEEDS = [
    ("연합뉴스", "https://www.yna.co.kr/rss/economy.xml"),
    ("연합뉴스", "https://www.yna.co.kr/rss/market.xml"),
    ("매일경제", "https://www.mk.co.kr/rss/30100041/"),
    ("매일경제", "https://www.mk.co.kr/rss/50200011/"),
    ("한국경제", "https://www.hankyung.com/feed/finance"),
    ("한국경제", "https://www.hankyung.com/feed/economy"),
    ("Google News KR", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"),
    ("Google News KR", GN_KR + "(코스피+OR+코스닥)+마감+when:1d"),
    ("Google News KR", GN_KR + "(삼성전자+OR+SK하이닉스)+주가+when:1d"),
    ("Google News KR", GN_KR + "(환율+OR+원달러)+when:1d"),
    ("Google News KR", GN_KR + "(배당+OR+공모주+OR+외국인+순매도)+when:1d"),
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


_GN_CACHE = {}


def decode_gnews(url):
    """구글 뉴스 중계 주소(news.google.com/rss/articles/…)를 원래 기사 주소로 풀기. 실패하면 ""."""
    if url in _GN_CACHE:
        return _GN_CACHE[url]
    real = ""
    try:
        m = re.search(r"/articles/([^?/]+)", url)
        if m:
            aid = m.group(1)
            r = requests.get(f"https://news.google.com/rss/articles/{aid}", headers=config.UA, timeout=12)
            sg = re.search(r'data-n-a-sg="([^"]+)"', r.text)
            ts = re.search(r'data-n-a-ts="([^"]+)"', r.text)
            if sg and ts:
                inner = json.dumps(["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None,
                                                    None, None, None, None, 0, 1], "X", "X", 1, [1, 1, 1], 1, 1,
                                                   None, 0, 0, None, 0], aid, int(ts.group(1)), sg.group(1)])
                body = "f.req=" + requests.utils.quote(json.dumps([[["Fbv4je", inner, None, "generic"]]]))
                p = requests.post("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=body, timeout=12,
                                  headers={**config.UA, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
                arr = json.loads(p.text.split("\n\n", 1)[1])
                real = json.loads(arr[0][2])[1]
    except Exception:
        real = ""
    _GN_CACHE[url] = real
    return real


def _extract(html_text, url=""):
    """기사 HTML → 본문 텍스트. trafilatura가 있으면 그것, 없으면 JSON-LD articleBody, 그다음 <p> 태그."""
    try:
        import trafilatura
        t = trafilatura.extract(html_text, url=url or None, include_comments=False, include_tables=False,
                                favor_recall=True)
        if t and len(t) > 300:
            return re.sub(r"\s+", " ", t).strip()
    except Exception:
        pass
    for m in re.finditer(r'"articleBody"\s*:\s*"((?:[^"\\]|\\.)*)"', html_text):
        try:
            t = json.loads('"' + m.group(1) + '"')
            if len(t) > 300:
                return _clean(t, 20000)
        except Exception:
            pass
    paras = re.findall(r"<p[^>]*>(.*?)</p>", html_text, flags=re.S | re.I)
    return " ".join(_clean(p, 2000) for p in paras)


def fetch_article_text(url, limit=3500):
    """기사 본문 일부를 가져옵니다 (실패하면 빈 문자열). 팩트체크 근거로 씁니다."""
    if not url:
        return ""
    if "news.google.com" in url:
        url = decode_gnews(url)
        if not url:
            return ""
    try:
        r = requests.get(url, headers=config.UA, timeout=12)
        if r.status_code != 200:
            return ""
        r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
        text = _extract(r.text, url)
        return text[:limit] if len(text) >= 300 else ""
    except Exception:
        return ""


def guardian_search(query, n=3, limit=3500):
    """가디언 무료 API로 같은 주제의 기사 본문 찾기 (키: GUARDIAN_API_KEY, 없으면 개발용 'test')."""
    try:
        r = requests.get("https://content.guardianapis.com/search", timeout=15, params={
            "q": query, "from-date": (dt.date.today() - dt.timedelta(days=3)).isoformat(),
            "order-by": "relevance", "page-size": n, "show-fields": "bodyText,trailText",
            "api-key": config.env("GUARDIAN_API_KEY", "test")})
        out = []
        for x in r.json().get("response", {}).get("results", []):
            body = (x.get("fields") or {}).get("bodyText", "")
            if len(body) > 300:
                out.append({"title": x.get("webTitle", ""), "link": x.get("webUrl", ""), "source": "Guardian",
                            "summary": _clean((x.get("fields") or {}).get("trailText", "")), "body": body[:limit],
                            "published": _date(x.get("webPublicationDate"))})
        return out
    except Exception:
        return []


def gnews_search(query, n=6):
    """구글 뉴스 검색(최근 2일)으로 같은 주제의 다른 매체 기사 찾기."""
    try:
        base, name = (GN_KR, "Google News KR") if re.search(r"[가-힣]", query) else (GN, "Google News")
        r = requests.get(base + requests.utils.quote(query + " when:2d"), headers=config.UA, timeout=15)
        return parse_feed(r.content, name)[:n]
    except Exception:
        return []
