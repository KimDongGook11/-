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
    # 2026-11-21 채널 진단: 미국 빅테크 비중이 높고 국내 투자자 관심사가 약함 → 최근 4편에 한국 기업이 없으면 이번엔 한국 기업
    kr_recent = sum(1 for u in used[-4:] if u.get("country_ko") == "한국")
    kr_rule = ("\n[이번 편은 한국 기업]\n최근 에피소드가 해외 기업뿐이었어. 이번에는 한국 시청자에게 친숙한 한국 기업"
               "(예: 삼성전자, SK하이닉스, 현대차, LG, 포스코, 네이버, 카카오, 셀트리온, 쿠팡)의 결정적 순간을 골라. "
               "영어 위키백과에 그 사건이 자세히 나오는 것만.\n") if used and kr_recent == 0 else \
              "\n해외 기업을 고를 때는 한국 기업·한국 시장과 얽힌 이야기(경쟁·협력·납품·투자)가 있으면 더 좋아.\n"
    prompt = f"""너는 경제 다큐멘터리 PD야. 시리즈 '{SERIES_NAME}'의 다음 에피소드를 하나 골라.
세계 유명 기업의 역사에서 회사의 운명을 바꾼 '결정적 순간' 하나(성공이든 실패든).

[가장 중요: 지금 화제인 기업 우선]
아래는 최근 2~3일 세계·한국 경제 뉴스 제목이야. 여기에 등장하는 기업 중 지금 가장 화제인 기업을 우선으로 골라
(여러 뉴스에 나올수록, 실적·주가·신제품·인수합병·소송·위기 등 큰 뉴스일수록 우선).
그 기업의 과거에서, 지금 뉴스와 이어지는 결정적 순간을 골라 (예: 지금 AI 반도체로 화제 → 그 회사가 과거에 내린 큰 베팅).
뉴스에 적당한 기업이 없거나 이미 다룬 기업뿐이면 그때만 일반적으로 유명한 기업을 골라.

[최근 뉴스 제목]
{hot}

{kr_rule}
조건:
- 영어 위키백과에 그 사건이 자세히 나와 있을 법한 유명한 사건만
- 이미 다룬 에피소드와 같은 기업은 피해:
{done}

JSON으로만 답해:
{{"company": "영어 기업명", "company_ko": "한국어 기업명", "country_ko": "기업 나라(한국어, 예: 한국, 미국, 일본)", "year": 사건 연도(숫자),
 "episode_ko": "에피소드 한 줄 요약(한국어)",
 "hot_reason": "지금 화제인 이유 한 줄(위 뉴스 제목 하나에 분명히 적힌 사실 하나만, 한국어, 25자 안팎의 자연스러운 문장. 실적·주가·신제품·인수합병·규제 같은 사업 소식만. 개인 추문·사퇴설·루머·범죄 의혹 등 사람에 대한 부정적 주장은 절대 쓰지 마. 뉴스 여러 개를 '~등 관련 이슈'로 뭉뚱그리지 마. 확실하지 않으면 빈 문자열). 뉴스와 무관하게 골랐으면 빈 문자열",
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
{('[이번 편 특별 지시 — 아래 규칙보다 우선]' + chr(10) + ep['extra_rules'] + chr(10)) if ep.get('extra_rules') else ''}
[규칙]
1. 연도·금액·숫자·인물·인용은 자료에 있는 것만. 확신 없는 디테일은 빼.
2. 자료 문장을 그대로 번역하지 말고 이야기처럼 새로 풀어 써. 말투는 친근한 존댓말, 다큐 내레이션처럼.
3. 구성: intro(2~3문장, 결과를 살짝 보여주는 후킹) + chapters 5개
   {('요즘 화제: ' + ep['hot_reason'] + ' → intro 첫 문장은 이 요즘 소식으로 시작해서 과거 이야기로 넘어가. 이 소식은 이 문장에 적힌 내용만 쓰고 덧붙이지 마.') if ep.get('hot_reason') else ''}
   intro에서 '대본', '스크립트', '오늘 영상에서는 ~를 다룹니다' 같은 제작 과정·예고 말투는 쓰지 마. 바로 이야기로 시작해.
   (① 그때 상황 ② 위기·갈림길 ③ 그 결정 ④ 그 후 어떻게 됐나 ⑤ 오늘 우리에게 주는 교훈).
   챕터 제목은 8자 이내, year는 그 챕터의 대표 연도(모르면 null), summary는 그 챕터 핵심을 담은 한 줄(20자 이내).
4. 각 segment는 한 문장 30~60자. 챕터마다 7~10문장. 전체 글자 수 2,000~2,400자 (읽으면 약 5분). 짧게 끝내지 말고 배경·인물·숫자·결과를 충분히 풀어 써.
5. keywords: 배경 스톡 영상 검색어. 그 문장을 **눈으로 보이는 구체적인 장면**으로 바꾼 영어 2~3단어.
   좋은 예: "video game console", "1990s office computer", "business handshake", "tokyo skyline", "factory assembly line", "newspaper printing", "boardroom meeting", "stock exchange screen".
   나쁜 예(금지): 감정·추상어("betrayal", "tension", "shock", "drama", "secret plan"), 인물 이름, 로고·브랜드명. 담배·흡연, 약물·알약·주사기 등 약품, 술 취한 모습, 선정적·폭력적 장면, 도박처럼 사회 통념에서 벗어나는 장면도 금지(이야기가 담배·제약 회사여도 공장·건물·사무실 같은 장면으로).
6. 핵심 숫자가 나오는 문장(전체 3~6개)에 number: {{"value": 자료의 숫자 그대로, "label": 10자 내외, "dir": "up|down|none"}}.
7. 주가 흐름을 보여주기 좋은 문장 1~2개에 show_chart: true (상장사일 때만).
8. topic_keyword: 시청자가 한눈에 알아보는 오늘 주제 키워드 하나. 기업 이야기면 기업명, 게임·제품 이야기면 그 이름 (예: "엔비디아", "스페이스X", "GTA"). 6자 이내.
   hook_title: 18자 이내, topic_keyword를 반드시 넣고, 핵심 단어 하나를 [ ]로.
   thumb_line1, thumb_line2: 유튜브 썸네일 두 줄 문구. 각 줄 띄어쓰기 포함 7자 이내, 강하고 궁금하게. 두 줄 중 한 줄에는 topic_keyword를 반드시 그대로 넣어 (예: "소니를 버린" / "닌텐도의 결정", "파산 직전" / "스페이스X", "GTA를 산" / "1998년 결단").
   company: 회사 이름·나라·업종을 한국어로 짧게.
   thumb_person: 썸네일용. 이 이야기의 핵심 인물(CEO·창업자 등)의 영어 위키백과 문서 제목(예: "Jensen Huang"). 없으면 "".
9. youtube_title: 40자 이내, 호기심을 끄는 제목. description: 3~5줄 소개. tags: 10개 이내.

[자료]
{material}

JSON으로만 답해:
{{
 "topic_keyword": "...", "hook_title": "...", "thumb_line1": "...", "thumb_line2": "...", "thumb_person": "...", "youtube_title": "...", "description": "...", "tags": ["..."],
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
    kw = str(d.get("topic_keyword") or ep.get("company_ko") or "").strip()[:10]
    hook = with_keyword(str(d.get("hook_title", ""))[:30], kw)
    l1, l2 = str(d.get("thumb_line1") or "")[:10], str(d.get("thumb_line2") or "")[:10]
    if kw and l1 and l2 and not _has_kw(l1 + l2, kw):
        print(f"  [썸네일] 주제 키워드 '{kw}' 없음 → 첫 줄을 키워드로: {l1}/{l2}")
        l1 = kw
    return {"hook_title": hook, "thumb_title": str(d.get("thumb_title", ""))[:34], "topic_keyword": kw,
            "thumb_line1": l1, "thumb_line2": l2, **_thumb_fields(d),
            "youtube_title": str(d.get("youtube_title", ""))[:90], "description": str(d.get("description", "")),
            "tags": [str(t).lstrip("#") for t in d.get("tags", [])][:15],
            "intro": norm_segments(d.get("intro")), "chapters": chapters, "chart": chart,
            "company": d.get("company") if isinstance(d.get("company"), dict) else {},
            "key_facts": d.get("key_facts", [])}


def _has_kw(text, kw):
    norm = lambda t: re.sub(r"[\s\[\]]", "", t).lower()
    return norm(kw) in norm(text)


def _thumb_fields(d):
    """숫자 충격형 썸네일 필드 (AI 응답 → 정리)."""
    dr = str(d.get("thumb_dir") or "none").lower()
    return {"thumb_number": str(d.get("thumb_number") or "").strip()[:12],
            "thumb_number_label": str(d.get("thumb_number_label") or "").strip()[:14],
            "thumb_dir": dr if dr in ("up", "down", "none") else "none",
            "thumb_question": str(d.get("thumb_question") or "").strip()[:12],
            "thumb_person": str(d.get("thumb_person") or "").strip()[:60]}


def with_keyword(hook, kw):
    """제목·썸네일 문구에 그날 주제 키워드(기업·게임·제품명)가 빠졌으면 앞에 붙임 (사용자 요청)."""
    hook = (hook or "").strip()
    if not kw or _has_kw(hook, kw):
        return hook
    print(f"  [제목] 주제 키워드 '{kw}' 없음 → 앞에 붙임: {hook}")
    return f"{kw}, {hook}"[:30]


def condense_short(long_sc, ep, has_long=True):
    """장편 대본을 60초 이내 세로 릴스로 압축 (이미 근거 확인된 장편 대본만 사용)."""
    last_rule = ("- 마지막 문장은 반드시 \"전체 이야기는 유튜브 '경제 원픽'에서 볼 수 있어요.\" 같은 안내." if has_long else
                 "- 마지막 문장은 이 결정에 대해 시청자에게 던지는 질문. 댓글로 답하기 쉬운 양자택일로, 물음표로 끝내 "
                 "(예: \"여러분이 사장이었다면, 팔았을까요 버텼을까요?\"). 장편·풀버전 안내는 하지 마.")
    cap_rule = " (마지막 줄: 풀버전은 유튜브 경제 원픽에서)" if has_long else " (마지막 줄: 댓글로 생각을 남겨 달라는 한 줄)"
    lines = [s["text"] for s in long_sc["intro"]]
    for c in long_sc["chapters"]:
        lines.append(f"[{c['title']}]")
        lines += [s["text"] for s in c["segments"]]
    prompt = f"""아래는 '{SERIES_NAME}' 장편(약 5분) 대본이야. 이걸 인스타 릴스용 40~55초 세로 영상 대본으로 압축해.
규칙:
- 아래 대본에 있는 사실만 사용. 새로운 숫자·사실 추가 금지.
- segments 7~9개, 각 25~45자, 전체 260~340자. 첫 문장은 강한 후킹.
{last_rule}
- keywords는 문장을 눈으로 보이는 구체적 장면으로 바꾼 영어 2~3단어(감정·추상어 금지). 담배·흡연, 약물·알약·주사기 등 약품, 술 취한 모습, 선정적·폭력적 장면, 도박처럼 사회 통념에서 벗어나는 장면도 금지(이야기가 담배·제약 회사여도 공장·건물·사무실 같은 장면으로). 핵심 숫자 1~2문장에 number, 주가 흐름 1문장에 show_chart.
- yt_title: 유튜브 쇼츠 제목 25~40자, 말하듯 쓴 결론형·질문형 (좋은 예: 삼성도 거절한 안드로이드, 구글은 왜 샀을까? / 파산 직전 애플을 살린 1억 5천만 달러). [ ] 기호와 분류 꼬리표는 쓰지 마. 주제 키워드를 꼭 넣어.
- title_tags: 제목 끝에 붙일 해시태그 정확히 3개 (기업명 1개 + 관련 종목·분야 2개, 예: #구글 #안드로이드 #기업이야기).
- hook_title 18자 이내, 주제 키워드 "{long_sc.get('topic_keyword') or ep.get('company_ko', '')}"를 반드시 넣고, 핵심 단어 하나를 [ ]로.

[장편 대본]
{chr(10).join(lines)}

JSON으로만 답해:
{{"yt_title": "...", "title_tags": ["#..."], "hook_title": "...", "segments": [{{"text": "...", "keywords": "...", "show_chart": false, "number": null}}],
 "caption": "인스타 캡션 3~5줄{cap_rule}", "hashtags": ["#그때그결정", "#기업역사"]}}"""
    from .script import normalize
    d = llm.ask_json(prompt, temperature=0.6)
    d["chart"] = long_sc.get("chart")
    d["key_facts"] = long_sc.get("key_facts", [])
    out = normalize(d)
    out["hook_title"] = with_keyword(out["hook_title"], long_sc.get("topic_keyword") or ep.get("company_ko", ""))
    return out
