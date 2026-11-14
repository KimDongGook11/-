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


def pick_episode(used):
    done = "\n".join(f"- {u.get('company')} {u.get('year')} {u.get('episode_ko')}" for u in used[-40:]) or "(없음)"
    prompt = f"""너는 경제 다큐멘터리 PD야. 인스타 릴스 시리즈 '{SERIES_NAME}'의 다음 에피소드를 하나 골라.
세계 유명 기업의 역사에서 회사의 운명을 바꾼 '결정적 순간' 하나(성공이든 실패든).
조건:
- 한국 20~40대가 아는 기업이거나, 이야기 자체가 놀라운 것
- 미국·유럽·일본·한국·중국 등 지역과 업종을 골고루. 성공담과 실패담을 섞어서
- 영어 위키백과에 그 사건이 자세히 나와 있을 법한 유명한 사건만
- 이미 다룬 에피소드와 같은 기업은 피해:
{done}

JSON으로만 답해:
{{"company": "영어 기업명", "company_ko": "한국어 기업명", "year": 사건 연도(숫자),
 "episode_ko": "에피소드 한 줄 요약(한국어)", "wiki_titles": ["이 사건이 나올 영어 위키백과 문서 제목 1~3개 (예: History of Apple Inc., Apple Inc.)"],
 "keywords": ["본문에서 이 사건을 찾을 영어 키워드 3~5개"],
 "ticker": "yfinance 티커 또는 null (예: AAPL, 7203.T, 005930.KS)", "listed_since": 상장 연도 또는 null}}"""
    ep = llm.ask_json(prompt, temperature=0.9)
    ep["year"] = int(re.sub(r"\D", "", str(ep.get("year", "0"))) or 0)
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


def write_script(ep, material, brand):
    prompt = f"""너는 인스타 경제 릴스 채널 '{brand}'의 시리즈 '{SERIES_NAME}' 작가야.
에피소드: {ep['company_ko']} ({ep['company']}), {ep['year']}년 — {ep['episode_ko']}

아래 [자료]에 있는 사실만 근거로 40~55초짜리 한국어 릴스 대본을 써.

[규칙]
1. 연도·금액·숫자·인물·인용은 자료에 있는 것만. 자료에 없으면 쓰지 말고, 확신 없는 디테일은 빼.
2. 자료 문장을 그대로 번역하지 말고 이야기처럼 새로 풀어 써.
3. 말투는 친근한 존댓말. 다큐 내레이션처럼 긴장감 있게.
4. 구성: ① 후킹(결과를 살짝 암시) ② {ep['year']}년 그때 상황 ③ 위기·갈림길 ④ 그 결정 ⑤ 결과(그 뒤 어떻게 됐나) ⑥ 오늘 우리에게 주는 의미 또는 질문.
5. segments 7~9개, 각 25~45자, 전체 260~360자.
6. keywords는 배경 스톡 영상 검색용 영어 1~3단어. 회사 로고·제품명·인물 이름은 피하고 분위기 위주(예: "old office 1990s", "factory assembly line", "boardroom meeting", "city at night").
7. 상장 기업이고 티커가 있으면 chart에 넣어. 없으면 null.
8. hook_title은 18자 이내, 가장 중요한 단어 하나를 [ ]로 감싸 강조(예: 파산 직전 애플, [90일]의 기적).

[자료]
{material}

JSON으로만 답해:
{{
 "hook_title": "...",
 "segments": [{{"text": "...", "keywords": "...", "show_chart": false}}],
 "chart": {{"ticker": "{ep.get('ticker') or ''}", "label": "기업명 주가 · {ep['year']}년~현재"}},
 "key_facts": ["대본에 쓴 연도·숫자 + 자료의 근거 문장 일부(영어 원문 짧게)"],
 "caption": "인스타 캡션 3~5줄",
 "hashtags": ["#그때그결정", "#기업역사"]
}}"""
    return llm.ask_json(prompt, temperature=0.7)
