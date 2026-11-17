"""오늘의 뉴스 고르기 + 릴스 대본 작성."""
import datetime as dt
import re

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
한국의 20~40대 인스타그램·유튜브 쇼츠 시청자에게 오늘 가장 '핫한' 글로벌 경제 뉴스 1개를 골라.

[선정 기준 — 위에서부터 중요]
1. 내 지갑 연결: 한국 시청자의 주식·환율·기름값·대출 금리·물가·월급 중 하나와 바로 이어지는가. 한 문장으로 "그래서 내 돈이 어떻게 되는데?"에 답할 수 있어야 해.
2. 누구나 아는 큰 이름: 유가, 환율, 금리(연준), 엔비디아·애플·테슬라·삼성·AI 빅테크, 비트코인처럼 시청자가 이미 아는 주제가 유리해.
3. 눈에 띄는 숫자: 급등·급락률, 사상 최고·최저, 금액 등 화면에 크게 띄울 숫자가 있는 뉴스가 유리해.
4. 여러 매체가 동시에 보도한 정도(score).
피해야 할 것: 시장 영향이 불분명한 해외 사건·사고(장애, 파업, 사고 소식만 있는 기사), 개별 기업 홍보성 기사, 칼럼·전망만 있는 기사.
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


def _query(title):
    """기사 제목 → 같은 주제 기사를 찾을 검색어 (핵심 단어 5~6개)."""
    words = [w for w in re.findall(r"[A-Za-z0-9$%.\-]+|[가-힣]{2,}", title)
             if w.lower() not in news.STOP and len(w) > 1]
    return " ".join(words[:6])


def gather_materials(pool, main_item, limit=8, want=3):
    """선택된 뉴스와 같은 주제의 기사를 모으고 본문을 확보합니다 (팩트체크 근거).
    본문이 want개보다 적으면 가디언 API·구글 뉴스 검색으로 같은 주제 기사를 더 찾아 보강."""
    group = [main_item] + [pool[j] for j in main_item.get("related", [])]
    seen, mats = set(), []
    for it in group:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        mats.append(it)
        if len(mats) >= 6:
            break
    for m in mats:
        m["body"] = news.fetch_article_text(m["link"])
    have = sum(1 for m in mats if m.get("body"))
    q = _query(main_item["title"])
    if have < want and q:
        extra = news.guardian_search(q) + news.gnews_search(q)
        for it in extra:
            if have >= want or len(mats) >= limit:
                break
            key = re.sub(r"\W+", "", it["title"].lower())[:60]
            if it["link"] in seen or key in {re.sub(r"\W+", "", m["title"].lower())[:60] for m in mats}:
                continue
            seen.add(it["link"])
            if not it.get("body"):
                it["body"] = news.fetch_article_text(it["link"])
            if it.get("body"):
                mats.append(it)
                have += 1
    mats.sort(key=lambda m: (m is not main_item, not m.get("body")))   # 주 기사 먼저, 본문 있는 자료 앞으로
    print(f"  [근거] 자료 {len(mats)}개 중 본문 확보 {have}개: "
          + ", ".join(f"{m['source']}{'✓' if m.get('body') else '✗'}" for m in mats))
    return mats


def write_script(mats, topic, brand):
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y년 %m월 %d일")
    blocks = []
    for i, m in enumerate(mats):
        b = f"[자료 {i+1}] 매체: {m['source']}\n제목: {m['title']}\n요약: {m['summary'] or '-'}"
        if m.get("body"):
            b += f"\n본문 일부: {m['body'][:3500]}"
        blocks.append(b)
    prompt = f"""너는 '{brand}'라는 인스타그램 경제 릴스 채널의 작가야. 오늘은 {today}이야.
주제: {topic}

아래 자료만 근거로 약 1분 20초(80초 안팎)짜리 한국어 릴스 대본을 써.

[규칙]
1. 숫자·날짜·인명·기관명은 자료에 나온 것만 써. 자료에 없는 수치는 절대 지어내지 마.
2. 자료 문장을 번역해서 그대로 옮기지 말고, 쉬운 말로 새로 풀어서 써.
3. 말투는 친근한 존댓말(~요, ~죠). 경제 용어는 한 번 쉽게 풀어줘.
4. 구성: 1번 문장은 3초 안에 멈추게 하는 후킹 → 무슨 일이 있었나 → 왜 이런 일이 생겼나(배경) → 한국/내 지갑에 미치는 영향 → 앞으로 볼 것 → 마지막은 시청자에게 던지는 질문.
   - 길어진 만큼 중간에 지루하지 않게, 3~4문장마다 새 정보(숫자·비교·반전)를 하나씩 넣어.
   - 1번 문장에는 자료에 있는 가장 강한 숫자(등락률·금액·최고/최저 기록)를 꼭 넣어. 숫자가 자료에 없을 때만 숫자 없이 써.
   - 1번 문장에는 1번 segment의 number 카드도 함께 넣어서, 영상 첫 화면부터 큰 숫자가 보이게 해.
   - 마지막 질문은 댓글로 답하기 쉬운 양자택일이나 한 단어 답 질문으로 (예: "여러분은 지금 달러, 사시겠어요 기다리시겠어요?").
5. segments는 12~15개, 각 문장은 25~45자. 전체 합계 500~580자. 같은 내용 반복으로 길이를 채우지 마.
6. 투자 권유(사라/팔아라)는 하지 마.
7. 각 segment의 keywords는 배경 스톡 영상 검색어야. 그 문장 내용을 **눈으로 보이는 구체적인 장면**으로 바꾼 영어 2~3단어.
   좋은 예: "stock exchange screen", "oil refinery", "shipping containers port", "semiconductor factory", "tokyo street night", "bank building", "gas station price", "supermarket shopping".
   나쁜 예(금지): 감정·추상어("tension", "shock", "betrayal", "crisis drama", "success"), 특정 인물 이름, 로고·브랜드명.
8. chart는 이 뉴스와 가장 관련 있는 시세 1개. 아래 목록 중에서 고르고, 맞는 게 없으면 null:
{TICKERS}
9. show_chart는 차트를 보여주기 좋은 segment 1개에만 true.
10. 핵심 숫자가 나오는 segment 2~3개에는 number를 넣어 화면에 큰 숫자 카드로 띄워. value는 자료에 있는 숫자 그대로(예: "4.34%", "1,200억 달러"), label은 10자 내외 설명, dir은 up/down/none. 차트를 보여주는 segment에는 넣지 마.

[자료]
{chr(10).join(blocks)}

JSON으로만 답해:
{{
 "tag": "제목 위 빨간 꼬리표 2~4자 (예: 금리, 환율, 증시, 유가, 반도체, 코인). '속보'라는 말은 절대 쓰지 마",
 "hook_title": "화면 위에 고정할 제목, 18자 이내. 가장 중요한 단어 하나를 [ ]로 감싸 강조. 자료에 숫자가 있으면 숫자를 넣고, 내 돈과의 연결이 보이게 (좋은 예: 유가 [8% 급락], 기름값 내려가나 / 엔비디아 [4% 급락]). '??', '먹통', '마비'처럼 자료보다 과장된 표현은 금지",
 "segments": [{{"text": "내레이션 문장", "keywords": "english keywords", "show_chart": false,
               "number": null 또는 {{"value": "4.34%", "label": "엔비디아 주가 하락", "dir": "down"}}}}],
 "chart": {{"ticker": "^GSPC", "label": "S&P 500 · 최근 1개월"}},
 "key_facts": ["대본에 쓴 숫자와 그 출처 매체 (검수용)"],
 "caption": "인스타 캡션 본문 3~5줄 (이모지 약간)",
 "hashtags": ["#경제뉴스", "#글로벌경제"]
}}"""
    data = llm.ask_json(prompt, temperature=0.7)
    return normalize(data, max_segs=16)


def polish_flow(sc, outro=""):
    """팩트체크 뒤 원고 흐름 검수: 고치거나 뺀 문장 때문에 끊긴 연결, 특히 마지막 질문과 마무리 멘트로
    넘어가는 부분을 자연스럽게 다듬음. 사실·숫자는 바꾸지 않고, 바뀌면 원래 문장을 그대로 둠."""
    from .factcheck import ko_numbers
    segs = sc["segments"]
    if len(segs) < 3:
        return sc
    lines = "\n".join(f"{i}. {x['text']}" for i, x in enumerate(segs))
    prompt = f"""너는 경제 릴스 원고 편집자야. 아래 [원고]는 내레이션 문장 목록이고, 끝에 마무리 멘트 "{outro}"가 붙어.
일부 문장은 팩트체크로 고쳐지거나 빠져서 흐름이 끊겼을 수 있어. 소리 내어 읽었을 때 자연스럽게 이어지도록 다듬어.

[규칙]
- 문장 수와 순서는 그대로. 각 번호의 문장을 같은 번호로 돌려줘.
- 사실·숫자·인명·기관명은 절대 바꾸거나 더하거나 빼지 마. 바꿀 수 있는 건 접속어, 문장 끝맺음, 앞뒤 연결 표현, 어순뿐이야.
- 같은 말 반복이나 앞 문장과 어색하게 부딪치는 부분을 고쳐.
- 마지막 문장은 시청자에게 던지는 질문이어야 해. 바로 앞 문장 내용에서 자연스럽게 이어지고, 이 뉴스와 직접 관련 있고,
  댓글로 답하기 쉬운 양자택일이나 한 단어 답 질문으로, 물음표로 끝내. 질문 뒤에 마무리 멘트가 바로 이어져도 어색하지 않게.
- 투자 권유(사라/팔아라)는 하지 마. 말투는 친근한 존댓말(~요, ~죠). 각 문장 45자 이내.
- 고칠 게 없으면 그대로 돌려줘.

[원고]
{lines}

JSON으로만: {{"segments": ["0번 문장", "1번 문장", ...], "changed": [바꾼 번호들]}}"""
    try:
        data = llm.ask_json(prompt, temperature=0.3)
        out = [str(t).strip() for t in data.get("segments", [])]
    except Exception as e:
        print(f"  [원고 검수] 건너뜀: {e}")
        return sc
    if len(out) != len(segs):
        print(f"  [원고 검수] 문장 수가 달라 적용 안 함 ({len(segs)}→{len(out)})")
        return sc
    nums = lambda t: sorted(round(v, 2) for v, _, _ in ko_numbers(t))
    changed = []
    for i, t in enumerate(out):
        if not t or t == segs[i]["text"]:
            continue
        if nums(t) != nums(segs[i]["text"]) or len(t) > 60:
            print(f"  [원고 검수] {i}번 문장은 숫자·길이가 달라져 원래대로 둠")
            continue
        segs[i]["text"] = t
        changed.append(i)
    if not segs[-1]["text"].rstrip().endswith("?"):
        print("  [원고 검수] ⚠️ 마지막 문장이 질문이 아니에요")
    print(f"  [원고 검수] 다듬은 문장 {len(changed)}개: {changed}")
    return sc


def add_outro(sc, text):
    """매일 같은 마무리 멘트를 붙여 '내일도 오는 채널'이라는 인상을 만듭니다."""
    text = (text or "").strip()
    if text and not any(s["text"] == text for s in sc["segments"]):
        sc["question"] = sc["segments"][-1]["text"]
        sc["segments"].append({"text": text, "keywords": "city sunrise skyline", "show_chart": False, "number": None})
    return sc


def _number(n):
    if not isinstance(n, dict) or not str(n.get("value", "")).strip():
        return None
    d = str(n.get("dir", "none")).lower()
    return {"value": str(n["value"]).strip()[:14], "label": str(n.get("label", "")).strip()[:18],
            "dir": d if d in ("up", "down") else "none"}


def norm_segments(items):
    segs = []
    for s in items or []:
        text = str(s.get("text", "")).strip()
        if text:
            segs.append({"text": text,
                         "keywords": str(s.get("keywords") or "stock market").strip()[:60],
                         "show_chart": bool(s.get("show_chart")),
                         "number": _number(s.get("number"))})
    return segs


def _no_sokbo(text):
    """제목·꼬리표에서 '속보' 문구를 뺀다 (사용자 요청)."""
    t = re.sub(r"[\[\(【]?\s*속보\s*[\]\)】]?\s*[:：·|]?", "", str(text or ""))
    return re.sub(r"\s{2,}", " ", t).strip()


def normalize(data, max_segs=9):
    segs = norm_segments(data.get("segments", []))
    if len(segs) < 3:
        raise ValueError("대본 문장이 너무 적습니다: " + str(data)[:300])
    chart = data.get("chart") or {}
    if not isinstance(chart, dict) or not chart.get("ticker"):
        chart = None
    tags = [t if str(t).startswith("#") else "#" + str(t) for t in data.get("hashtags", [])][:10]
    return {
        "tag": _no_sokbo(data.get("tag"))[:6],
        "hook_title": (_no_sokbo(data.get("hook_title")) or segs[0]["text"])[:30],
        "segments": segs[:max_segs],
        "chart": chart,
        "key_facts": data.get("key_facts", []),
        "caption": str(data.get("caption", "")).strip(),
        "hashtags": tags or ["#경제뉴스", "#글로벌경제"],
    }
