"""'그때 그 결정' 시리즈: 세계 기업 역사 속 결정적 순간을 에피소드로.
사실 정확도를 위해 영어 위키백과 본문을 근거 자료로 가져오고, 그 안에 있는 사실만 쓰게 합니다."""
import re

import requests

from . import llm

WIKI = "https://en.wikipedia.org/w/api.php"
UA = {"User-Agent": "EconOnePickBot/1.0 (personal Instagram reels project; contact via GitHub)"}
SERIES_NAME = "그때 그 결정"


def _wiki(params):
    params = {"format": "json", "formatversion": 2, **params}
    r = requests.get(WIKI, params=params, headers=UA, timeout=20)
    r.raise_for_status()
    return r.json()


def wiki_text(title):
    d = _wiki({"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1, "titles": title})
    pages = d.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None, None
    p = pages[0]
    return p["title"], p.get("extract", "")


def wiki_search(q, n=3):
    d = _wiki({"action": "query", "list": "search", "srsearch": q, "srlimit": n})
    return [x["title"] for x in d.get("query", {}).get("search", [])]


def hot_headlines(n=60, hours=72):
    """지금 화제인 기업을 고르기 위한 최근 경제 뉴스 제목들 (최신순)."""
    import datetime as dt
    from . import news
    try:
        items = news.fetch_all()
    except Exception as e:
        print(f"  [화제] 뉴스 수집 실패: {e}")
        return []
    now = dt.datetime.now(dt.timezone.utc)
    fresh = [it for it in items if not it.get("published") or (now - it["published"]).total_seconds() < hours * 3600]
    fresh.sort(key=lambda x: x.get("published") or now, reverse=True)
    seen, out = set(), []
    for it in fresh:
        k = it["title"][:60].lower()
        if k not in seen:
            seen.add(k)
            out.append(f"- {it['title']} ({it['source']})")
    return out[:n]


def pick_episode(used, headlines=None):
    done = "\n".join(f"- {u.get('company')} {u.get('year')} {u.get('episode_ko')}" for u in used[-40:]) or "(없음)"
    hot = "\n".join(headlines or []) or "(뉴스를 가져오지 못함)"
    prompt = f"""너는 경제 다큐멘터리 PD야. 시리즈 '{SERIES_NAME}'의 다음 에피소드를 하나 골라.
세계 유명 기업의 역사에서 회사의 운명을 바꾼 '결정적 순간' 하나(성공이든 실패든).

[가장 중요: 지금 화제인 기업 우선]
아래는 최근 2~3일 세계·한국 경제 뉴스 제목이야. 여기에 등장하는 기업 중 지금 가장 화제인 기업을 우선으로 골라
(여러 뉴스에 나올수록, 실적·주가·신제품·인수합병·소송·위기 등 큰 뉴스일수록 우선).
그 기업의 과거에서, 지금 뉴스와 이어지는 결정적 순간을 골라 (예: 지금 AI 반도체로 화제 → 그 회사가 과거에 내린 큰 베팅).
뉴스에 적당한 기업이 없거나 이미 다룬 기업뿐이면 그때만 일반적으로 유명한 기업을 골라.

[최근 뉴스 제목]
{hot}

조건:
- 영어 위키백과에 그 사건이 자세히 나와 있을 법한 유명한 사건만
- 이미 다룬 에피소드와 같은 기업은 피해:
{done}

JSON으로만 답해:
{{"company": "영어 기업명", "company_ko": "한국어 기업명", "year": 사건 연도(숫자),
 "episode_ko": "에피소드 한 줄 요약(한국어)",
 "hot_reason": "지금 화제인 이유 한 줄(위 뉴스 제목에 있는 사실만, 한국어). 뉴스와 무관하게 골랐으면 빈 문자열",
 "wiki_titles": ["이 사건이 나올 영어 위키백과 문서 제목 1~3개 (예: History of Apple Inc., Apple Inc.)"],
 "keywords": ["본문에서 이 사건을 찾을 영어 키워드 3~5개"],
 "ticker": "yfinance 티커 또는 null (예: AAPL, 7203.T, 005930.KS)", "listed_since": 상장 연도 또는 null}}"""
    ep = llm.ask_json(prompt, temperature=0.7)
    ep["year"] = int(re.sub(r"\D", "", str(ep.get("year", "0"))) or 0)
    ep["hot_reason"] = str(ep.get("hot_reason") or "").strip()
    return ep


def gather(ep, limit=7000):
    """위키백과에서 사건 연도와 키워드가 들어간 문단을 모읍니다. 근거가 부족하면 None."""
    titles = list(dict.fromkeys((ep.get("wiki_titles") or []) + [f"History of {ep['company']}", ep["company"]]))
    y = ep["year"]
    years = {str(y - 1), str(y), str(y + 1)}
    kws = [k.lower() for k in ep.get("keywords", []) if k]
    picked, links, seen = [], [], set()
    for t in titles[:4]:
        try:
            real, text = wiki_text(t)
            if not real:
                found = wiki_search(t, 1)
                if not found:
                    continue
                real, text = wiki_text(found[0])
        except Exception as e:
            print(f"  [위키] {t} 실패: {e}")
            continue
        if not text or real in seen:
            continue
        seen.add(real)
        paras = [p.strip() for p in text.split("\n") if len(p.strip()) > 80]
        hits = [p for p in paras if any(yy in p for yy in years) or sum(k in p.lower() for k in kws) >= 2]
        if hits:
            links.append("https://en.wikipedia.org/wiki/" + real.replace(" ", "_"))
            picked.append(f"[위키백과: {real}]\n" + (paras[0][:600] + "\n" if paras else "") + "\n".join(hits))
        if sum(len(x) for x in picked) > limit:
            break
    material = "\n\n".join(picked)[:limit]
    print(f"  [위키] 근거 자료 {len(material)}자, 문서 {len(links)}개")
    if len(material) < 900:
        return None, []
    return material, links


def write_long(ep, material, brand):
    """약 5분 가로형 유튜브 대본 (챕터 구성)."""
    prompt = f"""너는 경제 다큐 유튜브 채널 '{brand}'의 시리즈 '{SERIES_NAME}' 작가야.
에피소드: {ep['company_ko']} ({ep['company']}), {ep['year']}년 — {ep['episode_ko']}

아래 [자료]에 있는 사실만 근거로 약 5분 분량의 한국어 내레이션 대본을 써.

[규칙]
1. 연도·금액·숫자·인물·인용은 자료에 있는 것만. 확신 없는 디테일은 빼.
2. 자료 문장을 그대로 번역하지 말고 이야기처럼 새로 풀어 써. 말투는 친근한 존댓말, 다큐 내레이션처럼.
3. 구성: intro(2~3문장, 결과를 살짝 보여주는 후킹) + chapters 5개
   {('요즘 화제: ' + ep['hot_reason'] + ' → intro 첫 문장은 이 요즘 소식으로 시작해서 과거 이야기로 넘어가. 이 소식은 이 문장에 적힌 내용만 쓰고 덧붙이지 마.') if ep.get('hot_reason') else ''}
   (① 그때 상황 ② 위기·갈림길 ③ 그 결정 ④ 그 후 어떻게 됐나 ⑤ 오늘 우리에게 주는 교훈).
   챕터 제목은 8자 이내, year는 그 챕터의 대표 연도(모르면 null), summary는 그 챕터 핵심을 담은 한 줄(20자 이내).
4. 각 segment는 한 문장 30~60자. 챕터마다 7~10문장. 전체 글자 수 2,000~2,400자 (읽으면 약 5분). 짧게 끝내지 말고 배경·인물·숫자·결과를 충분히 풀어 써.
5. keywords: 배경 스톡 영상 검색어. 그 문장을 **눈으로 보이는 구체적인 장면**으로 바꾼 영어 2~3단어.
   좋은 예: "video game console", "1990s office computer", "business handshake", "tokyo skyline", "factory assembly line", "newspaper printing", "boardroom meeting", "stock exchange screen".
   나쁜 예(금지): 감정·추상어("betrayal", "tension", "shock", "drama", "secret plan"), 인물 이름, 로고·브랜드명.
6. 핵심 숫자가 나오는 문장(전체 3~6개)에 number: {{"value": 자료의 숫자 그대로, "label": 10자 내외, "dir": "up|down|none"}}.
7. 주가 흐름을 보여주기 좋은 문장 1~2개에 show_chart: true (상장사일 때만).
8. hook_title: 18자 이내, 핵심 단어 하나를 [ ]로.
   thumb_line1, thumb_line2: 유튜브 썸네일 두 줄 문구. 각 줄 띄어쓰기 포함 7자 이내, 강하고 궁금하게 (예: "소니를 버린" / "닌텐도의 결정", "파산 90일 전" / "돌아온 창업자").
   company: 회사 이름·나라·업종을 한국어로 짧게.
9. youtube_title: 40자 이내, 호기심을 끄는 제목. description: 3~5줄 소개. tags: 10개 이내.

[자료]
{material}

JSON으로만 답해:
{{
 "hook_title": "...", "thumb_line1": "...", "thumb_line2": "...", "youtube_title": "...", "description": "...", "tags": ["..."],
 "intro": [{{"text": "...", "keywords": "...", "show_chart": false, "number": null}}],
 "company": {{"name_ko": "닌텐도", "country_ko": "일본", "industry_ko": "게임"}},
 "chapters": [{{"title": "...", "year": 1997, "summary": "핵심 한 줄", "segments": [{{"text": "...", "keywords": "...", "show_chart": false, "number": null}}]}}],
 "chart": {{"ticker": "{ep.get('ticker') or ''}", "label": "기업명 주가 · 연도~현재"}},
 "key_facts": ["대본에 쓴 연도·숫자 + 자료의 근거 문장 일부(영어 원문 짧게)"]
}}"""
    from .script import norm_segments
    d = llm.ask_json(prompt, temperature=0.7)
    chapters = []
    for c in d.get("chapters", []):
        segs = norm_segments(c.get("segments"))
        if segs:
            y = re.sub(r"\D", "", str(c.get("year") or ""))
            chapters.append({"title": str(c.get("title", ""))[:12], "year": int(y) if y else None,
                             "summary": str(c.get("summary") or "")[:30], "segments": segs})
    if len(chapters) < 3:
        raise ValueError("장편 대본 챕터가 부족합니다")
    chart = d.get("chart") if isinstance(d.get("chart"), dict) and d["chart"].get("ticker") else None
    return {"hook_title": str(d.get("hook_title", ""))[:30], "thumb_title": str(d.get("thumb_title", ""))[:34],
            "thumb_line1": str(d.get("thumb_line1") or "")[:10], "thumb_line2": str(d.get("thumb_line2") or "")[:10],
            "youtube_title": str(d.get("youtube_title", ""))[:90], "description": str(d.get("description", "")),
            "tags": [str(t).lstrip("#") for t in d.get("tags", [])][:15],
            "intro": norm_segments(d.get("intro")), "chapters": chapters, "chart": chart,
            "company": d.get("company") if isinstance(d.get("company"), dict) else {},
            "key_facts": d.get("key_facts", [])}


def condense_short(long_sc, ep):
    """장편 대본을 60초 이내 세로 릴스로 압축 (이미 근거 확인된 장편 대본만 사용)."""
    lines = [s["text"] for s in long_sc["intro"]]
    for c in long_sc["chapters"]:
        lines.append(f"[{c['title']}]")
        lines += [s["text"] for s in c["segments"]]
    prompt = f"""아래는 '{SERIES_NAME}' 장편(약 5분) 대본이야. 이걸 인스타 릴스용 40~55초 세로 영상 대본으로 압축해.
규칙:
- 아래 대본에 있는 사실만 사용. 새로운 숫자·사실 추가 금지.
- segments 7~9개, 각 25~45자, 전체 260~340자. 첫 문장은 강한 후킹.
- 마지막 문장은 반드시 "전체 이야기는 유튜브 '경제 원픽'에서 볼 수 있어요." 같은 안내.
- keywords는 문장을 눈으로 보이는 구체적 장면으로 바꾼 영어 2~3단어(감정·추상어 금지). 핵심 숫자 1~2문장에 number, 주가 흐름 1문장에 show_chart.
- hook_title 18자 이내, 핵심 단어 하나를 [ ]로.

[장편 대본]
{chr(10).join(lines)}

JSON으로만 답해:
{{"hook_title": "...", "segments": [{{"text": "...", "keywords": "...", "show_chart": false, "number": null}}],
 "caption": "인스타 캡션 3~5줄 (마지막 줄: 풀버전은 유튜브 경제 원픽에서)", "hashtags": ["#그때그결정", "#기업역사"]}}"""
    from .script import normalize
    d = llm.ask_json(prompt, temperature=0.6)
    d["chart"] = long_sc.get("chart")
    d["key_facts"] = long_sc.get("key_facts", [])
    return normalize(d)
