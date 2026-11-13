"""오늘의 뉴스 고르기 + 릴스 대본 작성."""
import datetime as dt

from . import llm, news

TICKERS = """^GSPC(S&P500), ^IXIC(나스닥), ^DJI(다우), ^KS11(코스피), ^N225(닛케이), 000001.SS(상하이종합),
KRW=X(원/달러 환율), JPY=X(엔/달러), DX-Y.NYB(달러인덱스), ^TNX(미국 10년물 금리),
CL=F(WTI 유가), BZ=F(브렌트유), GC=F(금), SI=F(은), HG=F(구리), BTC-USD(비트코인),
개별 종목(예: NVDA, AAPL, TSLA, MSFT, 005930.KS 삼성전자, 000660.KS SK하이닉스)"""


def pick_story(candidates, history):
    lines = []
    for i, c in enumerate(candidates):
        lines.append(f"[{i}] (score {c['score']}) {c['title']} — {c['source']}"
                     + (f"\n     {c['summary'][:180]}" if c["summary"] else ""))
    recent = "\n".join(f"- {h.get('title_ko', '')} / {h.get('topic', '')}" for h in history[-14:]) or "(없음)"
    prompt = f"""너는 글로벌 경제 뉴스 에디터야.
아래는 지난 24시간 동안의 세계 경제 뉴스 후보야. score는 여러 매체가 동시에 보도한 정도야.
한국의 20~40대 인스타그램 시청자에게 오늘 가장 '핫한' 글로벌 경제 뉴스 1개를 골라.
기준: 시장·환율·금리·물가·일자리에 미치는 파급력, 화제성, 한국 생활과의 연관성. 단순 개별 기업 홍보성 기사나 칼럼은 피해.
최근에 이미 다룬 주제(중복 금지):
{recent}

후보:
{chr(10).join(lines)}

JSON으로만 답해: {{"pick": 번호, "topic": "영어로 한 줄 주제 요약", "reason": "선정 이유 한 문장(한국어)"}}"""
    res = llm.ask_json(prompt, temperature=0.3)
    idx = int(res.get("pick", 0))
    if not 0 <= idx < len(candidates):
        idx = 0
    return idx, res


def gather_materials(pool, main_item, limit=6):
    """선택된 뉴스와 같은 주제를 다룬 다른 매체 기사까지 모아 사실 확인 자료로 씁니다."""
    group = [main_item] + [pool[j] for j in main_item.get("related", [])]
    seen, mats = set(), []
    for it in group:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        mats.append(it)
        if len(mats) >= limit:
            break
    for m in mats[:3]:
        m["body"] = news.fetch_article_text(m["link"])
    return mats


def write_script(mats, topic, brand):
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y년 %m월 %d일")
    blocks = []
    for i, m in enumerate(mats):
        b = f"[자료 {i+1}] 매체: {m['source']}\n제목: {m['title']}\n요약: {m['summary'] or '-'}"
        if m.get("body"):
            b += f"\n본문 일부: {m['body'][:2500]}"
        blocks.append(b)
    prompt = f"""너는 '{brand}'라는 인스타그램 경제 릴스 채널의 작가야. 오늘은 {today}이야.
주제: {topic}

아래 자료만 근거로 30~50초짜리 한국어 릴스 대본을 써.

[규칙]
1. 숫자·날짜·인명·기관명은 자료에 나온 것만 써. 자료에 없는 수치는 절대 지어내지 마.
2. 자료 문장을 번역해서 그대로 옮기지 말고, 쉬운 말로 새로 풀어서 써.
3. 말투는 친근한 존댓말(~요, ~죠). 경제 용어는 한 번 쉽게 풀어줘.
4. 구성: 1번 문장은 3초 안에 멈추게 하는 후킹 → 무슨 일이 있었나 → 왜 중요한가 → 한국/내 지갑에 미치는 영향 → 마지막은 시청자에게 던지는 질문.
5. segments는 6~8개, 각 문장은 25~45자. 전체 합계 220~320자.
6. 투자 권유(사라/팔아라)는 하지 마.
7. 각 segment의 keywords는 배경 스톡 영상 검색어로, 영어 1~3단어(예: "stock market", "oil refinery", "federal reserve building", "shipping containers"). 사람 얼굴 클로즈업이나 특정 인물 이름은 피해.
8. chart는 이 뉴스와 가장 관련 있는 시세 1개. 아래 목록 중에서 고르고, 맞는 게 없으면 null:
{TICKERS}
9. show_chart는 차트를 보여주기 좋은 segment 1~2개에만 true.

[자료]
{chr(10).join(blocks)}

JSON으로만 답해:
{{
 "hook_title": "화면 위에 고정할 제목, 16자 이내, 숫자나 강한 단어 포함",
 "segments": [{{"text": "내레이션 문장", "keywords": "english keywords", "show_chart": false}}],
 "chart": {{"ticker": "^GSPC", "label": "S&P 500 · 최근 1개월"}},
 "key_facts": ["대본에 쓴 숫자와 그 출처 매체 (검수용)"],
 "caption": "인스타 캡션 본문 3~5줄 (이모지 약간)",
 "hashtags": ["#경제뉴스", "#글로벌경제"]
}}"""
    data = llm.ask_json(prompt, temperature=0.7)
    return normalize(data)


def normalize(data):
    segs = []
    for s in data.get("segments", []):
        text = str(s.get("text", "")).strip()
        if text:
            segs.append({"text": text,
                         "keywords": str(s.get("keywords") or "stock market").strip()[:60],
                         "show_chart": bool(s.get("show_chart"))})
    if len(segs) < 3:
        raise ValueError("대본 문장이 너무 적습니다: " + str(data)[:300])
    chart = data.get("chart") or {}
    if not isinstance(chart, dict) or not chart.get("ticker"):
        chart = None
    tags = [t if str(t).startswith("#") else "#" + str(t) for t in data.get("hashtags", [])][:10]
    return {
        "hook_title": str(data.get("hook_title") or segs[0]["text"])[:24],
        "segments": segs[:9],
        "chart": chart,
        "key_facts": data.get("key_facts", []),
        "caption": str(data.get("caption", "")).strip(),
        "hashtags": tags or ["#경제뉴스", "#글로벌경제"],
    }
