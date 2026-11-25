"""'이슈 뒷담화' (예전 이름: 대담 특집): 진행자(서현)가 묻고 패널(필재)이 답하는 약 5분 가로 장편 (유튜브).
근거는 최근 뉴스 기사 본문(구글 뉴스·가디언 검색). 주제·검색어·구성은 jobs/talk_custom.json 에서 받음.
사실은 패널 발언만 팩트체크(진행자의 질문·맞장구는 사실 주장이 아니라서 제외)."""
import datetime as dt
import json
import re

from . import config, factcheck, llm, news, script
from .utils import load_state, save_state

SERIES_NAME = "이슈 뒷담화"
# name: 화면·대본 속 이름 (채널 캐릭터), voice: 타입캐스트 목소리 이름 (사용자 결정 11/22: 목소리는 그대로)
# 패널 이름은 정해지면 여기 name만 바꾸면 됨
SPEAKERS = {
    "host": {"name": "지수", "voice": "서현", "role": "진행", "color": [255, 196, 64]},
    "panel": {"name": "정환", "voice": "필재", "role": "패널", "color": [96, 170, 255]},
}


def load_job(path=None):
    f = config.ROOT / (path or "jobs/talk_custom.json")
    return json.loads(f.read_text(encoding="utf-8"))


def pick_topic():
    """자동 모드: 최근 2~3일 경제 뉴스에서 대담 주제를 AI가 고르고 검색어·챕터 구성까지 정함."""
    from .history import hot_headlines
    heads = hot_headlines(n=80, hours=72)
    done = "\n".join(f"- {t.get('date', '')} {t.get('topic', '')}" for t in load_state("talk_history", [])[-12:]) or "(없음)"
    prompt = f"""너는 경제 유튜브 채널 '경제 원픽'의 PD야. 진행자와 패널이 5분 동안 뉴스 뒷이야기를 문답하는 '{SERIES_NAME}'의 이번 주제를 하나 골라.

[고르는 기준 — 위에서부터 중요]
1. 최근 2~3일 동안 여러 매체가 크게 다룬 경제 이슈 (실적, 금리, 환율, 반도체·AI, 무역·관세, 빅테크, 에너지 등)
2. 한국 시청자와 바로 이어짐: 한국 기업·증시·환율·물가·일자리에 미치는 영향을 이야기할 거리가 있음
3. 5분 동안 문답할 만큼 배경·쟁점·숫자가 풍부함
피해야 할 것: 사건·사고만 있는 소식, 사람의 사생활·추문·범죄 의혹이 중심인 이야기, 최근 대담에서 다룬 주제와 같은 이야기.

[최근 대담 주제(중복 금지)]
{done}

[최근 뉴스 제목]
{chr(10).join(heads) or '(뉴스를 가져오지 못함)'}

JSON으로만 답해:
{{"topic": "대담 주제 한 문장(한국어)", "label_ko": "짧은 이름 12자 이내", "label_en": "short English label",
 "company": {{"name_ko": "중심 기업·기관 1~3개", "country_ko": "나라", "industry_ko": "분야"}},
 "photo_titles": ["썸네일 사진을 찾을 영어 위키백과 문서 제목 1~3개(기업·기관)"],
 "tickers": ["관련 yfinance 티커 1~3개 (예: NVDA, 005930.KS, ^KS11, KRW=X)"],
 "queries": ["같은 주제 기사를 찾을 검색어 6~8개. 영어 4~5개 + 한국어 2~3개, 구체적인 기업·사건 이름 포함"],
 "extra_rules": "챕터 5개 구성 지시(① 무슨 일 ② 왜 ③ 누가 영향을 받나 ④ 한국에는 ⑤ 지켜볼 점 세 가지 처럼 이 주제에 맞게) + 숫자는 날짜·기준과 함께 말하라는 지시"}}"""
    job = llm.ask_json(prompt, temperature=0.5)
    if not job.get("topic") or not job.get("queries"):
        raise ValueError("대담 주제 선정 실패: " + str(job)[:300])
    print(f"  [대담 주제] {job['topic']}")
    return job


WEEKLY_RULES = ("이번 편은 일요일 저녁 '한 주 결산 + 다음 주 전망' 편이야. 챕터 구성: "
                "① 이번 주 무슨 일(이번 주 가장 뜨거웠던 이슈 하나, 언제 무엇이 있었나) "
                "② 왜 이렇게 커졌나(배경과 쟁점 분석, 자료 속 매체·전문가 시각) "
                "③ 국내 증시에는(그 기간 코스피·코스닥·환율과 관련 업종·기업에 어떤 영향이 있었는지, [최근 시세] 숫자 활용) "
                "④ 다음 주 전망(자료에 나온 다음 주 예정 일정·발표와 시각. '~하면 ~할 수 있다' 같은 조건부로, "
                "자료에 없는 예측은 '아직 알 수 없다'고 말해) "
                "⑤ 정리: 다음 주 지켜볼 점 세 가지(진행자가 정리). "
                "투자 권유·목표 주가·'오른다/내린다' 단정은 금지. 숫자는 날짜·기준과 함께.")


def _edition():
    """수요일 편(최근 3일) / 일요일 편(한 주). 사용자 결정 11/22: 주 2회, 둘 다 '가장 핫한 이슈'."""
    wed = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).weekday() == 2
    return ({"name": "수요일 편", "days": 3, "sessions": 3, "span": "이번 주 초(일~수)",
             "outlook": "남은 이번 주와 다음 주 전망"} if wed else
            {"name": "일요일 편", "days": 7, "sessions": 5, "span": "이번 한 주",
             "outlook": "다음 주 전망"})


def pick_weekly():
    """수·일 정기 편: 그 기간 가장 핫한 이슈 하나 (원픽·브리핑에서 다룬 주제 + 최근 뉴스 제목 참고)."""
    from .history import hot_headlines
    ed = _edition()
    heads = hot_headlines(n=80, hours=96)
    week_ago = (dt.datetime.now(dt.timezone(dt.timedelta(hours=9))) - dt.timedelta(days=ed["days"])).strftime("%Y%m%d")
    picks = [f"- {h.get('date', '')[:8]} {h.get('title_ko', '')} / {h.get('topic', '')}"
             for h in load_state("history", []) if str(h.get("date", ""))[:8] >= week_ago]
    done = "\n".join(f"- {t.get('date', '')} {t.get('topic', '')}" for t in load_state("talk_history", [])[-8:]) or "(없음)"
    prompt = f"""너는 경제 유튜브 채널 '경제 원픽'의 PD야. '{SERIES_NAME}' {ed['name']}({ed['span']} 결산 + {ed['outlook']})에서 다룰
{ed['span']} 가장 뜨거웠던 경제 이슈 하나를 골라.

[고르는 기준 — 위에서부터 중요]
1. {ed['span']} 여러 매체가 크게 다룬 이슈 (아래 '최근 우리 채널이 다룬 주제'에 여러 번 나왔으면 유력)
2. 한국 증시(코스피·코스닥)·환율·한국 기업에 영향이 있고, 다음 주에도 이어질 일정이나 쟁점이 있음
3. 사건·사고만 있는 소식, 사람의 사생활·추문 중심 이야기는 제외. 최근 이슈 뒷담화와 같은 주제는 제외

[최근 우리 채널이 다룬 주제]
{chr(10).join(picks) or '(기록 없음)'}

[최근 뉴스 제목]
{chr(10).join(heads) or '(뉴스를 가져오지 못함)'}

[최근 이슈 뒷담화 주제(중복 금지)]
{done}

JSON으로만 답해:
{{"topic": "이슈와 국내 증시 영향·전망을 담은 주제 한 문장(한국어)", "label_ko": "짧은 이름 12자 이내",
 "label_en": "short English label",
 "company": {{"name_ko": "중심 기업·기관 1~3개", "country_ko": "나라", "industry_ko": "분야"}},
 "photo_titles": ["썸네일 사진을 찾을 영어 위키백과 문서 제목 1~3개"],
 "tickers": ["관련 yfinance 티커 1~3개 (예: ^KS11, 005930.KS, NVDA, KRW=X)"],
 "queries": ["기사 검색어 7~9개: 이번 주 이슈(영어 3 + 한국어 2), 국내 증시 영향(한국어 2), 다음 주 일정·전망(영어 1 + 한국어 1)"]}}"""
    job = llm.ask_json(prompt, temperature=0.4)
    if not job.get("topic") or not job.get("queries"):
        raise ValueError("이슈 뒷담화 주제 선정 실패: " + str(job)[:300])
    job["extra_rules"] = (WEEKLY_RULES.replace("일요일 저녁 '한 주 결산 + 다음 주 전망' 편", f"{ed['name']}({ed['span']} 결산 + {ed['outlook']})")
                          .replace("이번 주 무슨 일", f"{ed['span']} 무슨 일").replace("④ 다음 주 전망", f"④ {ed['outlook']}")
                          .replace("다음 주 지켜볼 점", "앞으로 지켜볼 점"))
    job["days"] = ed["days"]
    job["sessions"] = ed["sessions"]
    print(f"  [이슈 뒷담화 주제] {job['topic']}")
    return job


def _weekly_custom():
    """jobs/talk_custom.json 의 date(한국시간 YYYYMMDD)가 오늘이면 그 주제로 정기 편을 만듦 (다시 만들기용)."""
    try:
        job = load_job()
    except Exception:
        return None
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y%m%d")
    if str(job.get("date")) != today:
        return None
    ed = _edition()
    job.setdefault("extra_rules", WEEKLY_RULES)
    job.update({"days": ed["days"], "sessions": ed["sessions"]})
    print(f"  [이슈 뒷담화 주제] (지정) {job['topic']}")
    return job


def remember(job):
    hist = load_state("talk_history", [])
    hist.append({"date": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y%m%d"), "topic": job["topic"]})
    save_state("talk_history", hist[-50:])


def gather(job, want=10, limit_chars=16000):
    """검색어마다 같은 주제 기사를 찾아 본문을 확보 (본문 있는 자료만)."""
    mats, seen = [], set()
    for q in job.get("queries", []):
        got = 0
        for it in news.guardian_search(q, n=3) + news.gnews_search(q, n=6, days=job.get("days", 2)):
            key = re.sub(r"\W+", "", (it.get("title") or "").lower())[:60]
            if not key or key in seen or it.get("link") in seen:
                continue
            seen.update({key, it.get("link")})
            if not it.get("body"):
                it["body"] = news.fetch_article_text(it["link"])
            if it.get("body"):
                mats.append(it)
                got += 1
            if got >= 3:   # 검색어마다 최대 3개 (한 주제로 쏠리지 않게)
                break
        if len(mats) >= want:
            break
    total, out = 0, []
    for m in mats:
        if total > limit_chars:
            break
        out.append(m)
        total += len(m["body"][:2500])
    print(f"  [대담 근거] 본문 확보 기사 {len(out)}개: " + ", ".join(m["source"] for m in out))
    return out


def write(job, mats):
    blocks = []
    for i, m in enumerate(mats):
        pub = m.get("published")
        blocks.append(f"[자료 {i+1}] 매체: {m['source']}" + (f" ({pub:%Y-%m-%d})" if pub else "")
                      + f"\n제목: {m['title']}\n본문 일부: {m['body'][:2500]}")
    h, p = SPEAKERS["host"], SPEAKERS["panel"]
    prompt = f"""너는 경제 유튜브 채널 '경제 원픽'의 시리즈 '{SERIES_NAME}' 작가야.
진행자 {h['name']}(여성)가 묻고 패널 {p['name']}(남성)이 답하는 약 5분짜리 한국어 토크 대본을 써.
패널을 '경제 해설가', '전문가', '위원' 같은 직함으로 부르지 마. 이름에 '님'만 붙여 불러.
코너 성격: 뉴스 헤드라인 뒤에 숨은 사정과 맥락을 카페에서 편하게 수다 떨듯 풀어내는 '뒷이야기' 토크.
말투는 가볍고 친근하게("근데 진짜 궁금한 건요…", "여기서 재밌는 게 뭐냐면요…"), 하지만 내용은 자료에 근거한 사실만.
'뒷담화'라는 이름이어도 사람 험담·소문·추측은 절대 하지 마. 뒷이야기는 기업 전략, 숫자의 의미, 업계 사정 같은 맥락이야.
주제: {job['topic']}

{('[이번 편 지시 — 아래 규칙보다 우선]' + chr(10) + job['extra_rules'] + chr(10)) if job.get('extra_rules') else ''}
[대담 규칙]
1. 숫자·날짜·인명·기업명·발언은 아래 [자료]에 있는 것만. 자료에 없는 수치·사실은 절대 지어내지 마.
   숫자는 자료 문장에 적힌 그대로 옮겨(단위·기준일 포함). 주가 등락률·시가총액처럼 그럴듯한 숫자를 짐작해서 쓰면 그 문장은 팩트체크에서 통째로 삭제돼.
   자료에 숫자가 없으면 숫자 없이 "크게 올랐다", "아직 공개된 숫자는 없다"처럼 말해.
2. 앞으로의 전망은 단정하지 말고 "자료에서 누가 어떻게 봤는지" 또는 "앞으로 지켜볼 점"으로 말해. 투자 권유(사라/팔아라)는 금지.
3. 사람의 사생활·추문·의혹은 다루지 마. 인물 이야기는 경영·사업 결정만.
4. 진행자(host): 시청자 대신 궁금한 걸 짧게 묻고, 어려운 말을 쉬운 말로 되짚고, 가끔 반응("와, 그 정도예요?", "잠깐만요, 그러면…")을 해. 한 번에 1~2문장, 각 15~45자.
   패널(panel): 근거를 바탕으로 쉽게 설명해. 한 번에 2~4문장, 각 30~60자. 패널 문장 하나에는 사실 하나만.
   노트북 LM 팟캐스트처럼 자연스럽게 주고받되, 같은 말 반복이나 의미 없는 맞장구로 시간을 채우지 마.
5. 구성: intro + chapters 4~5개. intro는 정확히 이 순서로:
   ① 진행: "이슈 뒷담화, 진행 {h['name']}입니다." + 오늘 무슨 이야기를 하는지 한 문장
   ② 진행: "오늘 주제 함께 얘기해 주실 {p['name']}님 모셨습니다."
   ③ 패널: "안녕하세요, {p['name']}입니다." (이 인사만, 덧붙이지 마)
   챕터 제목 8자 이내, summary는 챕터 핵심 한 줄(20자 이내), year는 null.
   마지막 챕터는 진행자가 핵심을 세 줄로 정리하고, 시청자에게 댓글 질문 하나("여러분은 어떻게 보세요?")로 끝내.
6. 전체 글자 수 2,200~2,600자 (읽으면 약 5분).
7. 모든 segment에 speaker("host" 또는 "panel"). keywords: 배경 스톡 영상 검색어, 그 문장을 눈에 보이는 구체적 장면으로 바꾼 영어 2~3단어
   (좋은 예: "semiconductor factory cleanroom", "data center servers", "stock exchange screen", "seoul skyline night").
   감정·추상어, 인물 이름, 로고·브랜드명 금지. 담배·약물·약품·술 취함·선정·폭력·도박 장면도 금지.
8. 핵심 숫자가 나오는 패널 문장(전체 3~6개)에 number: {{"value": 자료의 숫자 그대로(가격·수치만), "change": 등락폭이 있으면 따로(예: "-7.95%", "+4.6원", 없으면 ""), "label": 10자 내외, "dir": "up|down|none"}}.
9. 주가 차트(중요): 기업이나 업종을 이야기하는 패널 문장에는 그 기업·업종의 주가 차트를 붙여: "chart": {{"ticker": "...", "label": "기업명 · 최근 1년"}}.
   대본에 여러 업종(예: 반도체, 자동차, 배터리, 조선)이 나오면 업종마다 대표 기업 차트를 하나씩, 한 편에 3~6개 폭넓게. 같은 차트는 한 번만.
   티커는 이 목록에서만 골라: {json.dumps(TICKERS, ensure_ascii=False)}
   (이 주제의 참고 티커: {json.dumps(job.get('tickers', []), ensure_ascii=False)}). 차트를 붙인 문장에는 number를 넣지 마.
   chart(맨 아래 항목)는 이 대담 전체를 대표하는 주가 하나.
10. topic_keyword(6자 이내), hook_title(18자 이내, topic_keyword 포함, 핵심 단어 하나를 [ ]로),
    thumb_line1·thumb_line2(썸네일 두 줄, 각 7자 이내, 한 줄에 topic_keyword), youtube_title(40자 이내, 질문형이나 결론형),
    description(3~5줄), tags(10개 이내).
   thumb_number·thumb_number_label·thumb_dir·thumb_question·thumb_person: 새 썸네일(숫자 충격형)용.
     thumb_number: 이 영상에서 가장 충격적인 숫자 하나를 대본에 쓴 그대로 짧게(예: "-6.16%", "30억 달러", "66억 개"). 대본에 없는 숫자 금지. 마땅한 숫자가 없으면 "".
     thumb_number_label: 그 숫자 위에 붙을 설명 10자 이내(예: "코스피 하루 만에", "인수 금액").
     thumb_dir: 숫자가 오름이면 "up", 내림이면 "down", 둘 다 아니면 "none".
     thumb_question: 숫자 아래 노란 띠에 들어갈 궁금증 한 줄, 9자 이내(예: "젠슨황 효과 끝?", "왜 샀을까?").
     thumb_person: 이 이야기의 핵심 인물(CEO·창업자 등)의 영어 위키백과 문서 제목(예: "Jensen Huang"). 없으면 "".

[자료]
{chr(10).join(blocks)}

JSON으로만 답해:
{{
 "topic_keyword": "...", "hook_title": "...", "thumb_line1": "...", "thumb_line2": "...", "thumb_number": "...", "thumb_number_label": "...", "thumb_dir": "down", "thumb_question": "...", "thumb_person": "...", "youtube_title": "...",
 "description": "...", "tags": ["..."],
 "intro": [{{"speaker": "host", "text": "...", "keywords": "...", "show_chart": false, "number": null}}],
 "chapters": [{{"title": "...", "year": null, "summary": "...", "segments": [{{"speaker": "host|panel", "text": "...", "keywords": "...", "chart": null, "number": null}}]}}],
 "chart": {{"ticker": "...", "label": "기업명 주가 · 최근 1년"}},
 "key_facts": ["대본에 쓴 숫자·사실 + 근거 매체"]
}}"""
    d = llm.ask_json(prompt, temperature=0.7)

    def segs(items):
        out = script.norm_segments(items)
        for s, raw in zip(out, [x for x in (items or []) if isinstance(x, dict) and str(x.get("text", "")).strip()]):
            s["speaker"] = "host" if str(raw.get("speaker", "")).lower().startswith("h") else "panel"
            c = raw.get("chart")
            if isinstance(c, dict) and c.get("ticker") in TICKERS.values():
                s["chart"] = {"ticker": c["ticker"], "label": str(c.get("label") or c["ticker"])[:30]}
                s["number"] = None
        return out

    chapters = []
    for c in d.get("chapters", []):
        ss = segs(c.get("segments"))
        if ss:
            chapters.append({"title": str(c.get("title", ""))[:12], "year": None,
                             "summary": str(c.get("summary") or "")[:30], "segments": ss})
    if len(chapters) < 3:
        raise ValueError("대담 대본 챕터가 부족합니다")
    chart = d.get("chart") if isinstance(d.get("chart"), dict) and d["chart"].get("ticker") else None
    kw = str(d.get("topic_keyword") or "").strip()[:10]
    from .history import with_keyword, _thumb_fields
    return {"hook_title": with_keyword(str(d.get("hook_title", ""))[:30], kw), "topic_keyword": kw,
            "thumb_line1": str(d.get("thumb_line1") or "")[:10], "thumb_line2": str(d.get("thumb_line2") or "")[:10],
            **_thumb_fields(d),
            "youtube_title": str(d.get("youtube_title", ""))[:90], "description": str(d.get("description", "")),
            "tags": [str(t).lstrip("#") for t in d.get("tags", [])][:15],
            "intro": segs(d.get("intro")), "chapters": chapters, "chart": chart,
            "key_facts": d.get("key_facts", [])}


# 주가 차트용 티커 (대본 AI에게 주는 목록 + 대본에 업종이 나왔는데 차트가 없을 때 자동 보완)
TICKERS = {
    "삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "현대차": "005380.KS", "기아": "000270.KS",
    "현대모비스": "012330.KS", "LG에너지솔루션": "373220.KS", "삼성SDI": "006400.KS", "POSCO홀딩스": "005490.KS",
    "HD현대중공업": "329180.KS", "한화오션": "042660.KS", "한화에어로스페이스": "012450.KS", "셀트리온": "068270.KS",
    "삼성바이오로직스": "207940.KS", "네이버": "035420.KS", "카카오": "035720.KS", "KB금융": "105560.KS",
    "신한지주": "055550.KS", "한국전력": "015760.KS", "S-Oil": "010950.KS", "대한항공": "003490.KS",
    "LG화학": "051910.KS", "삼성전기": "009150.KS", "한미반도체": "042700.KQ", "에코프로비엠": "247540.KQ",
    "코스피": "^KS11", "코스닥": "^KQ11", "원/달러 환율": "KRW=X", "엔비디아": "NVDA", "TSMC": "TSM",
    "AMD": "AMD", "애플": "AAPL", "마이크로소프트": "MSFT", "테슬라": "TSLA", "필라델피아 반도체지수": "^SOX",
    "나스닥": "^IXIC", "S&P 500": "^GSPC", "WTI 유가": "CL=F", "금": "GC=F", "비트코인": "BTC-USD",
}
SECTORS = [   # (대본 속 단어들, 대표 차트 이름)
    (("자동차", "완성차", "車"), "현대차"), (("배터리", "2차전지", "이차전지"), "LG에너지솔루션"),
    (("조선",), "HD현대중공업"), (("방산", "방위산업"), "한화에어로스페이스"), (("바이오", "제약"), "삼성바이오로직스"),
    (("은행", "금융지주"), "KB금융"), (("정유",), "S-Oil"), (("항공사", "항공업"), "대한항공"),
    (("철강",), "POSCO홀딩스"), (("반도체", "HBM", "메모리"), "SK하이닉스"), (("인터넷", "플랫폼"), "네이버"),
    (("전력", "한전"), "한국전력"), (("유가", "원유"), "WTI 유가"), (("환율",), "원/달러 환율"),
]
MAX_CHARTS = 6


def _chart(name):
    t = TICKERS.get(name)
    return {"ticker": t, "label": f"{name} · 최근 1년"} if t else None


def ensure_charts(lsc):
    """업종·기업 이야기를 폭넓게 시각화 (사용자 요청 11/22): 대본에 나온 업종인데 차트가 없으면
    그 업종을 처음 말하는 패널 문장에 대표 종목 차트를 붙임. 한 편에 최대 MAX_CHARTS개."""
    flat = lsc["intro"] + [x for c in lsc["chapters"] for x in c["segments"]]
    have = {s["chart"]["ticker"] for s in flat if isinstance(s.get("chart"), dict)}
    for words, name in SECTORS:
        if len(have) >= MAX_CHARTS:
            break
        ch = _chart(name)
        if ch and name not in words[0]:
            ch["label"] = f"{words[0]} 대표 · {name} · 최근 1년"
        if not ch or ch["ticker"] in have:
            continue
        for k, s in enumerate(flat):
            if s.get("speaker") == "panel" and not s.get("chart") and any(w in s["text"] for w in words):
                s["chart"] = ch
                have.add(ch["ticker"])
                print(f"  [차트 보완] '{name}' → {k + 1}번 문장")
                break
    print(f"  [차트] 이번 편 주가 차트 {len(have)}개: " + ", ".join(sorted(have)))
    return lsc


PRIVATE = ("스캔들", "추문", "불륜", "외도", "혼외", "성추행", "성희롱", "사생활", "염문")


def factcheck_panel(lsc, mats):
    """패널 발언만 팩트체크 (고치거나 뺌). 진행자 문장은 그대로."""
    flat = lsc["intro"] + [s for c in lsc["chapters"] for s in c["segments"]]
    panel = [s for s in flat if s.get("speaker") == "panel"]
    sc = {"segments": panel}
    sc, report = factcheck.run(sc, mats)
    for s in lsc["intro"] + [x for c in lsc["chapters"] for x in c["segments"]]:
        if any(w in s.get("text", "") for w in PRIVATE):   # 사생활 이야기는 다루지 않음 (팩트체크가 고치며 넣은 경우 포함)
            print(f"  [사생활 표현] 문장 뺌: {s['text']}")
            s["text"] = ""
    lsc["intro"] = [s for s in lsc["intro"] if s.get("text")]
    for c in lsc["chapters"]:
        c["segments"] = [s for s in c["segments"] if s.get("text")]
    lsc["chapters"] = [c for c in lsc["chapters"] if c["segments"]]
    lsc["factcheck"] = report
    return lsc


def repair_flow(lsc):
    """팩트체크로 패널 발언이 빠지거나 바뀐 뒤 대화 흐름 다듬기: 질문만 있고 답이 없는 곳, 앞뒤가 안 맞는 맞장구를 고침.
    문장 수·순서·말하는 사람은 그대로, 숫자는 글자 그대로 유지 (바뀌면 원래 문장을 둠)."""
    flat = lsc["intro"] + [s for c in lsc["chapters"] for s in c["segments"]]
    lines = [{"i": i, "who": SPEAKERS[s.get("speaker", "panel")]["name"], "text": s["text"]} for i, s in enumerate(flat)]
    prompt = f"""아래는 '{SERIES_NAME}' 토크 대본이야(진행 {SPEAKERS['host']['name']}, 패널 {SPEAKERS['panel']['name']}).
팩트체크로 일부 문장이 빠져서 대화가 어색하게 끊긴 곳이 있을 수 있어. 소리 내어 들었을 때 자연스럽게 다듬어.
- 문장 수·순서·말하는 사람은 그대로. 같은 길이의 배열로 돌려줘.
- 질문에 대한 답이 빠졌으면, 질문을 바로 다음 패널 답과 이어지게 바꾸거나 맞장구로 바꿔.
- 숫자·사실·인명·기업명은 절대 더하거나 바꾸지 마. 바꿀 수 있는 건 질문·맞장구·접속 표현뿐이야.
- 진행 문장 45자, 패널 문장 60자 이내. 사람 험담·추측 금지.
[대본]
{json.dumps(lines, ensure_ascii=False)}
JSON으로만: {{"lines": ["문장", ...]}}"""
    try:
        data = llm.ask_json(prompt, temperature=0.3)
        raw = data.get("lines", []) if isinstance(data, dict) else data   # 배열만 돌려줘도 처리
        out = [str(t.get("text", "") if isinstance(t, dict) else t).strip() for t in raw]
    except Exception as e:
        print(f"  [대화 흐름] 건너뜀: {e}")
        return lsc
    if len(out) != len(flat):
        print(f"  [대화 흐름] 문장 수가 달라 적용 안 함 ({len(flat)}→{len(out)})")
        return lsc
    digits = lambda t: re.findall(r"\d+", t)
    n = 0
    for s, t in zip(flat, out):
        if t and t != s["text"] and digits(t) == digits(s["text"]) and len(t) <= 70:
            s["text"] = t
            n += 1
    print(f"  [대화 흐름] 다듬은 문장 {n}개")
    return lsc


def build(job_path=None):
    """반환: (장편 대본, 에피소드 정보, 근거 링크, 근거 매체 목록).
    TALK_TOPIC=auto(자동 예약 실행)면 AI가 주제를 고르고, 아니면 jobs/talk_custom.json 을 씀."""
    mode = config.env("TALK_TOPIC", "file")
    if mode == "weekly":
        job = _weekly_custom() or pick_weekly()
    else:
        job = pick_topic() if mode == "auto" else load_job(job_path)
    print(f"1) 대담 주제: {job['topic']}")
    mats = gather(job)
    if job.get("sessions"):   # 수·일 정기 편: 최근 거래일 지수·환율 등락을 근거 맨 앞에
        from . import market
        wk = market.weekly_material(job["sessions"])
        if wk:
            mats.insert(0, wk)
    if len(mats) < 3:
        raise RuntimeError(f"대담 근거 기사 본문을 {len(mats)}개밖에 확보하지 못했어요 (최소 3개)")
    print("2) 대담 대본")
    lsc = write(job, mats)
    print("3) 팩트체크 (패널 발언)")
    lsc = factcheck_panel(lsc, mats)
    if (lsc.get("factcheck") or {}).get("fixed", 0) + (lsc.get("factcheck") or {}).get("dropped", 0):
        print("3-1) 대화 흐름 다듬기 (팩트체크로 고치거나 뺀 문장 주변)")
        lsc = repair_flow(lsc)
    print("4) 자막 맞춤법 검수")
    lsc = script.proofread(lsc)
    lsc = ensure_charts(lsc)
    lsc["headlines"] = script.headline_list([m for m in mats if m.get("source") != "Yahoo Finance"])
    lsc.update({"speakers": SPEAKERS, "series_name": SERIES_NAME, "ep": "", "year": None,
                "open_meta": f"{SERIES_NAME}  ·  진행 {SPEAKERS['host']['name']}  ·  패널 {SPEAKERS['panel']['name']}",
                "company": job.get("company") or {}, "wiki_titles": job.get("photo_titles", [])})
    ep = {"company": job.get("label_en", "talk"), "company_ko": job.get("label_ko", SERIES_NAME), "year": "",
          "episode_ko": job["topic"]}
    links = [news.decode_gnews(m["link"]) if "news.google.com" in m["link"] else m["link"] for m in mats]
    sources = list(dict.fromkeys(m["source"] for m in mats))
    remember(job)
    return lsc, ep, [l for l in links if l], sources
