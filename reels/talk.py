"""'이슈 뒷담화' (예전 이름: 대담 특집): 진행자(서현)가 묻고 패널(필재)이 답하는 약 5분 가로 장편 (유튜브).
근거는 최근 뉴스 기사 본문(구글 뉴스·가디언 검색). 주제·검색어·구성은 jobs/talk_custom.json 에서 받음.
사실은 패널 발언만 팩트체크(진행자의 질문·맞장구는 사실 주장이 아니라서 제외)."""
import datetime as dt
import json
import re

from . import config, factcheck, llm, news, script
from .utils import load_state, save_state

SERIES_NAME = "이슈 뒷담화"
SPEAKERS = {
    "host": {"name": "서현", "role": "진행", "color": [255, 196, 64]},
    "panel": {"name": "필재", "role": "패널", "color": [96, 170, 255]},
}


def load_job(path=None):
    f = config.ROOT / (path or "jobs/talk_custom.json")
    return json.loads(f.read_text(encoding="utf-8"))


def pick_topic():
    """자동 모드: 최근 2~3일 경제 뉴스에서 대담 주제를 AI가 고르고 검색어·챕터 구성까지 정함."""
    from .history import hot_headlines
    heads = hot_headlines(n=80, hours=72)
    done = "\n".join(f"- {t.get('date', '')} {t.get('topic', '')}" for t in load_state("talk_history", [])[-12:]) or "(없음)"
    prompt = f"""너는 경제 유튜브 채널 '경제 원픽'의 PD야. 진행자와 경제 해설가가 5분 동안 뉴스 뒷이야기를 문답하는 '{SERIES_NAME}'의 이번 주제를 하나 골라.

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


def remember(job):
    hist = load_state("talk_history", [])
    hist.append({"date": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y%m%d"), "topic": job["topic"]})
    save_state("talk_history", hist[-50:])


def gather(job, want=10, limit_chars=16000):
    """검색어마다 같은 주제 기사를 찾아 본문을 확보 (본문 있는 자료만)."""
    mats, seen = [], set()
    for q in job.get("queries", []):
        got = 0
        for it in news.guardian_search(q, n=3) + news.gnews_search(q, n=6):
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
진행자 {h['name']}(여성)가 묻고 패널 {p['name']}(남성, 경제 해설가)이 답하는 약 5분짜리 한국어 토크 대본을 써.
코너 성격: 뉴스 헤드라인 뒤에 숨은 사정과 맥락을 카페에서 편하게 수다 떨듯 풀어내는 '뒷이야기' 토크.
말투는 가볍고 친근하게("근데 진짜 궁금한 건요…", "여기서 재밌는 게 뭐냐면요…"), 하지만 내용은 자료에 근거한 사실만.
'뒷담화'라는 이름이어도 사람 험담·소문·추측은 절대 하지 마. 뒷이야기는 기업 전략, 숫자의 의미, 업계 사정 같은 맥락이야.
주제: {job['topic']}

{('[이번 편 지시 — 아래 규칙보다 우선]' + chr(10) + job['extra_rules'] + chr(10)) if job.get('extra_rules') else ''}
[대담 규칙]
1. 숫자·날짜·인명·기업명·발언은 아래 [자료]에 있는 것만. 자료에 없는 수치·사실은 절대 지어내지 마.
2. 앞으로의 전망은 단정하지 말고 "자료에서 누가 어떻게 봤는지" 또는 "앞으로 지켜볼 점"으로 말해. 투자 권유(사라/팔아라)는 금지.
3. 사람의 사생활·추문·의혹은 다루지 마. 인물 이야기는 경영·사업 결정만.
4. 진행자(host): 시청자 대신 궁금한 걸 짧게 묻고, 어려운 말을 쉬운 말로 되짚고, 가끔 반응("와, 그 정도예요?", "잠깐만요, 그러면…")을 해. 한 번에 1~2문장, 각 15~45자.
   패널(panel): 근거를 바탕으로 쉽게 설명해. 한 번에 2~4문장, 각 30~60자. 패널 문장 하나에는 사실 하나만.
   노트북 LM 팟캐스트처럼 자연스럽게 주고받되, 같은 말 반복이나 의미 없는 맞장구로 시간을 채우지 마.
5. 구성: intro(진행자의 짧은 오프닝 2~3문장: "이슈 뒷담화, 진행 서현입니다"처럼 코너 이름으로 시작해서 오늘 무슨 이야기를 하는지 + 패널 소개) + chapters 4~5개.
   챕터 제목 8자 이내, summary는 챕터 핵심 한 줄(20자 이내), year는 null.
   마지막 챕터는 진행자가 핵심을 세 줄로 정리하고, 시청자에게 댓글 질문 하나("여러분은 어떻게 보세요?")로 끝내.
6. 전체 글자 수 2,200~2,600자 (읽으면 약 5분).
7. 모든 segment에 speaker("host" 또는 "panel"). keywords: 배경 스톡 영상 검색어, 그 문장을 눈에 보이는 구체적 장면으로 바꾼 영어 2~3단어
   (좋은 예: "semiconductor factory cleanroom", "data center servers", "stock exchange screen", "seoul skyline night").
   감정·추상어, 인물 이름, 로고·브랜드명 금지. 담배·약물·약품·술 취함·선정·폭력·도박 장면도 금지.
8. 핵심 숫자가 나오는 패널 문장(전체 3~6개)에 number: {{"value": 자료의 숫자 그대로, "label": 10자 내외, "dir": "up|down|none"}}.
9. chart: 아래 중 이 대담에 가장 맞는 주가 하나 {json.dumps(job.get('tickers', []), ensure_ascii=False)}. 주가 흐름을 말하는 패널 문장 1~2개에 show_chart: true.
10. topic_keyword(6자 이내), hook_title(18자 이내, topic_keyword 포함, 핵심 단어 하나를 [ ]로),
    thumb_line1·thumb_line2(썸네일 두 줄, 각 7자 이내, 한 줄에 topic_keyword), youtube_title(40자 이내, 질문형이나 결론형),
    description(3~5줄), tags(10개 이내).

[자료]
{chr(10).join(blocks)}

JSON으로만 답해:
{{
 "topic_keyword": "...", "hook_title": "...", "thumb_line1": "...", "thumb_line2": "...", "youtube_title": "...",
 "description": "...", "tags": ["..."],
 "intro": [{{"speaker": "host", "text": "...", "keywords": "...", "show_chart": false, "number": null}}],
 "chapters": [{{"title": "...", "year": null, "summary": "...", "segments": [{{"speaker": "host|panel", "text": "...", "keywords": "...", "show_chart": false, "number": null}}]}}],
 "chart": {{"ticker": "...", "label": "기업명 주가 · 최근 1년"}},
 "key_facts": ["대본에 쓴 숫자·사실 + 근거 매체"]
}}"""
    d = llm.ask_json(prompt, temperature=0.7)

    def segs(items):
        out = script.norm_segments(items)
        for s, raw in zip(out, [x for x in (items or []) if isinstance(x, dict) and str(x.get("text", "")).strip()]):
            s["speaker"] = "host" if str(raw.get("speaker", "")).lower().startswith("h") else "panel"
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
    from .history import with_keyword
    return {"hook_title": with_keyword(str(d.get("hook_title", ""))[:30], kw), "topic_keyword": kw,
            "thumb_line1": str(d.get("thumb_line1") or "")[:10], "thumb_line2": str(d.get("thumb_line2") or "")[:10],
            "youtube_title": str(d.get("youtube_title", ""))[:90], "description": str(d.get("description", "")),
            "tags": [str(t).lstrip("#") for t in d.get("tags", [])][:15],
            "intro": segs(d.get("intro")), "chapters": chapters, "chart": chart,
            "key_facts": d.get("key_facts", [])}


def factcheck_panel(lsc, mats):
    """패널 발언만 팩트체크 (고치거나 뺌). 진행자 문장은 그대로."""
    flat = lsc["intro"] + [s for c in lsc["chapters"] for s in c["segments"]]
    panel = [s for s in flat if s.get("speaker") == "panel"]
    sc = {"segments": panel}
    sc, report = factcheck.run(sc, mats)
    lsc["intro"] = [s for s in lsc["intro"] if s.get("text")]
    for c in lsc["chapters"]:
        c["segments"] = [s for s in c["segments"] if s.get("text")]
    lsc["chapters"] = [c for c in lsc["chapters"] if c["segments"]]
    lsc["factcheck"] = report
    return lsc


def build(job_path=None):
    """반환: (장편 대본, 에피소드 정보, 근거 링크, 근거 매체 목록).
    TALK_TOPIC=auto(자동 예약 실행)면 AI가 주제를 고르고, 아니면 jobs/talk_custom.json 을 씀."""
    job = pick_topic() if config.env("TALK_TOPIC", "file") == "auto" else load_job(job_path)
    print(f"1) 대담 주제: {job['topic']}")
    mats = gather(job)
    if len(mats) < 3:
        raise RuntimeError(f"대담 근거 기사 본문을 {len(mats)}개밖에 확보하지 못했어요 (최소 3개)")
    print("2) 대담 대본")
    lsc = write(job, mats)
    print("3) 팩트체크 (패널 발언)")
    lsc = factcheck_panel(lsc, mats)
    print("4) 자막 맞춤법 검수")
    lsc = script.proofread(lsc)
    lsc["headlines"] = script.headline_list(mats)
    lsc.update({"speakers": SPEAKERS, "series_name": SERIES_NAME, "ep": "", "year": None,
                "open_meta": f"{SERIES_NAME}  ·  진행 {SPEAKERS['host']['name']}  ·  패널 {SPEAKERS['panel']['name']}",
                "company": job.get("company") or {}, "wiki_titles": job.get("photo_titles", [])})
    ep = {"company": job.get("label_en", "talk"), "company_ko": job.get("label_ko", SERIES_NAME), "year": "",
          "episode_ko": job["topic"]}
    links = [news.decode_gnews(m["link"]) if "news.google.com" in m["link"] else m["link"] for m in mats]
    sources = list(dict.fromkeys(m["source"] for m in mats))
    remember(job)
    return lsc, ep, [l for l in links if l], sources
