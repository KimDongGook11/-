"""1분 경제 용어 (매일 21:00, 2026-11-28 사용자 결정).
그날 올린 영상(미국 마감·원픽·국내 마감·부동산)에 나온 어려운 경제 용어를 하나 골라 30~40초로 풀어 줌.
- 뜻풀이 근거: 한국어 위키백과 요약 (근거가 없는 용어는 후보에서 뺌)
- 오늘 뉴스와 연결: 그날 영상 제목·주제 (state/history.json)
- 다룬 용어는 state/terms.json에 기록해 반복하지 않음"""
import datetime as dt
import re

import requests

from . import config, llm, script
from .utils import load_state

KST = dt.timezone(dt.timedelta(hours=9))
SERIES_NAME = "1분 경제 용어"
WIKI = "https://ko.wikipedia.org/w/api.php"
UA = {"User-Agent": "EconOnePickBot/1.0 (personal YouTube shorts project; contact via GitHub)"}


def _today_topics(days=1):
    """오늘(없으면 최근 days일) 만든 영상 제목·주제."""
    log = load_state("history", [])
    today = dt.datetime.now(KST).strftime("%Y%m%d")
    rows = [h for h in log if today in str(h.get("date", ""))]
    if not rows:
        rows = log[-4:]
    return [f"{h.get('title_ko', '')} / {h.get('topic', '')}" for h in rows]


def wiki_summary(term):
    """한국어 위키백과 도입부 (없으면 검색 1순위 문서). 반환: (문서 제목, 요약, 주소) 또는 None."""
    def extract(title):
        d = requests.get(WIKI, headers=UA, timeout=15, params={
            "action": "query", "format": "json", "formatversion": 2, "prop": "extracts", "exintro": 1,
            "explaintext": 1, "redirects": 1, "titles": title}).json()
        pages = d.get("query", {}).get("pages", [])
        if pages and not pages[0].get("missing") and len(pages[0].get("extract", "")) >= 120:
            p = pages[0]
            return p["title"], p["extract"][:2500], "https://ko.wikipedia.org/wiki/" + p["title"].replace(" ", "_")
        return None
    try:
        got = extract(term)
        if got:
            return got
        s = requests.get(WIKI, headers=UA, timeout=15, params={
            "action": "query", "format": "json", "list": "search", "srsearch": term, "srlimit": 1}).json()
        hits = s.get("query", {}).get("search", [])
        return extract(hits[0]["title"]) if hits else None
    except Exception as e:
        print(f"  [용어] 위키백과 실패({term}): {e}")
        return None


def candidates(n=3):
    """오늘 영상에서 나온 용어 후보 (위키백과 근거가 있는 것만). 반환: [{term, why, context, wiki}]"""
    topics = _today_topics()
    used = [t.get("term", "") for t in load_state("terms", [])[-120:]]
    prompt = f"""너는 경제 쇼츠 채널의 '1분 경제 용어' 담당이야.
아래는 오늘 채널에 올라간 경제 영상들의 제목/주제야.
{chr(10).join('- ' + t for t in topics) or '(없음)'}

이 영상들에 나왔거나 이해하는 데 꼭 필요한 경제·금융 용어 6개를 골라.
- 20~40대 직장인이 들어 봤지만 정확히 설명하긴 어려운 용어 (예: 사이드카, 기준금리, 공매도, 환율 우대, 서킷브레이커, 배당락, 리쇼어링, 공모가)
- 너무 쉬운 말(주식, 은행)이나 특정 회사 이름은 빼.
- 최근에 이미 다룬 용어는 빼: {', '.join(used[-40:]) or '(없음)'}

JSON으로만: {{"terms": [{{"term": "용어(한국어 표준 표기)", "why": "오늘 영상과의 연결 한 줄", "context": "연결된 영상 제목 그대로"}}]}}"""
    try:
        raw = llm.ask_json(prompt, temperature=0.4).get("terms", [])
    except Exception as e:
        print(f"  [용어] 후보 뽑기 실패: {e}")
        raw = []
    out = []
    for t in raw:
        term = str(t.get("term", "")).strip()
        if not term or term in used or any(o["term"] == term for o in out):
            continue
        w = wiki_summary(term)
        if not w:
            print(f"  [용어] '{term}' 위키백과 근거 없음 → 제외")
            continue
        out.append({"term": term, "why": str(t.get("why", "")), "context": str(t.get("context", "")), "wiki": w})
        if len(out) >= n:
            break
    return out


def write(c, brand):
    """용어 하나 → 30~40초 쇼츠 대본."""
    title, extract, url = c["wiki"]
    prompt = f"""너는 '{brand}' 채널의 '{SERIES_NAME}' 작가야. 오늘 용어: {c['term']}
오늘 영상과의 연결: {c['why']} (영상: {c['context']})

아래 [자료]의 뜻풀이만 근거로 30~40초짜리 한국어 쇼츠 대본을 써.
[구성]
1. 첫 문장: 오늘 뉴스에서 이 용어가 나온 장면으로 궁금증을 만들어 (예: "오늘 코스피에 사이드카가 떴다는데, 이게 뭘까요?"). 오늘 영상 제목에 있는 사실만 써.
2. 한 문장 정의: 아주 쉬운 말로.
3. 쉬운 비유 한 문장 (일상 생활 비유).
4. 왜 중요한지 / 내 돈과 어떻게 이어지는지 1~2문장.
5. 마지막: 시청자에게 던지는 짧은 질문 (예: "오늘 처음 아셨던 분?" 같은 가벼운 질문, 물음표로 끝내).
[규칙]
- segments 6~8개, 각 20~40자, 전체 220~280자. 친근한 존댓말.
- 숫자·연도·제도 내용은 자료에 있는 것만. 자료에 없는 수치·기준(예: 몇 % 오르면 발동)은 지어내지 마.
- 투자 권유 금지. keywords는 문장을 눈으로 보이는 구체적 장면으로 바꾼 영어 2~3단어(금융 장면 위주).
- number는 자료에 있는 핵심 숫자가 있을 때만 1개.
- yt_title: 25~40자, "○○가 뭐길래" / "○○, 1분이면 이해돼요"처럼 말하듯. [ ] 금지.
- title_tags: 해시태그 정확히 3개 (용어 1개 + #경제용어 + 분야 1개).
- hook_title: 14자 이내, 용어를 [ ]로 강조 (예: "[사이드카]가 뭐길래").

[자료: 위키백과 '{title}']
{extract}

JSON으로만:
{{"yt_title": "...", "title_tags": ["#..."], "tag": "경제용어", "hook_title": "...",
 "segments": [{{"text": "...", "keywords": "...", "show_chart": false, "number": null}}],
 "chart": null, "key_facts": ["대본에 쓴 정의·숫자와 근거 문장(자료에서 짧게)"],
 "caption": "인스타 캡션 3~4줄 (용어 뜻 한 줄 요약 포함)", "hashtags": ["#경제용어", "#{c['term'].replace(' ', '')}"]}}"""
    d = llm.ask_json(prompt, temperature=0.5)
    d["tag"] = "경제용어"
    return script.normalize(d, max_segs=9)
