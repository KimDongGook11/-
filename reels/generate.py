"""오늘의 릴스 만들기: 뉴스 수집 → 선정 → 대본 → 음성 → 영상 → 텔레그램 미리보기.

사용법:
  python -m reels.generate                      # 오늘의 경제
  python -m reels.generate --series history     # 그때 그 결정
  python -m reels.generate --offline            # 인터넷/키 없이 샘플로 렌더링만 테스트
"""
import argparse
import datetime as dt
import shutil
import signal
import sys
import time
import traceback

from . import talk
from . import approval, config, factcheck, history, instagram, market, news, pending, produce, qc, render, script, storage, telegram, tts, youtube
from .utils import git_push_state, load_state, save_state

KST = dt.timezone(dt.timedelta(hours=9))

def _seg(text, kw="stock market", **k):
    return {"text": text, "keywords": kw, "show_chart": k.get("show_chart", False), "number": k.get("number")}


SAMPLE = {
    "tag": "금리",
    "hook_title": "미국 금리 [0.25%p 인하], 내 대출은?",
    "segments": [
        _seg("미국이 또 금리를 내렸어요. 이번엔 0.25%p예요.", "federal reserve",
             number={"value": "0.25%p", "label": "미국 기준금리 인하", "dir": "down"}),
        _seg("연준은 물가보다 일자리 둔화를 더 걱정하고 있다는 뜻이죠.", "office workers city"),
        _seg("발표 직후 S&P 500 지수는 1.2% 올랐어요.", "stock market screen", show_chart=True),
        _seg("금리가 내려가면 달러 가치가 약해지는 경우가 많아요.", "us dollar money"),
        _seg("그러면 원/달러 환율이 내려가 수입 물가 부담이 줄 수 있죠.", "shipping containers port"),
        _seg("이번 인하, 내 대출에 도움이 될까요? 여러분은 어떻게 생각하세요?", "family home"),
    ],
    "chart": {"ticker": "^GSPC", "label": "S&P 500 · 최근 1개월"},
    "key_facts": ["(샘플 데이터 - 실제 뉴스 아님)"],
    "caption": "테스트용 샘플 대본입니다.",
    "hashtags": ["#경제뉴스", "#테스트"],
}

SAMPLE_LONG = {
    "hook_title": "파산 직전 애플, [90일]의 기적", "thumb_title": "[90일] 남은 애플",
    "thumb_line1": "파산 90일 전", "thumb_line2": "돌아온 창업자",
    "youtube_title": "(샘플) 파산 90일 전 애플은 무엇을 버렸나", "description": "테스트용 샘플입니다.",
    "tags": ["애플", "스티브잡스"],
    "intro": [_seg("1997년 여름, 애플에는 90일을 버틸 돈밖에 없었습니다.", "empty office night"),
              _seg("이 회사는 어떻게 세계에서 가장 비싼 기업이 됐을까요?", "city skyline")],
    "chapters": [
        {"title": "무너지는 애플", "year": 1996, "summary": "제품만 늘고 손실은 커졌다", "segments": [
            _seg("1990년대 중반, 애플은 매년 큰 손실을 냈어요.", "old computer"),
            _seg("제품은 수십 종류로 늘었지만 팔리는 건 없었죠.", "warehouse boxes",
                 number={"value": "10억 달러", "label": "누적 손실(샘플)", "dir": "down"})]},
        {"title": "돌아온 창업자", "year": 1997, "summary": "제품 라인을 4개로 줄이다", "segments": [
            _seg("그리고 쫓겨났던 창업자가 회사로 돌아옵니다.", "man walking city"),
            _seg("첫 결정은 제품을 4개로 줄이는 것이었어요.", "minimal desk",
                 number={"value": "4개", "label": "남긴 제품 라인", "dir": "none"})]},
        {"title": "그 후", "year": 2001, "summary": "빼기가 만든 반전", "segments": [
            _seg("그 결정 이후 주가는 어떻게 됐을까요?", "stock market screen", show_chart=True),
            _seg("위기에서 필요한 건 더하기가 아니라 빼기였던 거죠.", "sunrise city")]},
    ],
    "chart": {"ticker": "AAPL", "label": "애플 주가 · 1994년~현재"},
    "key_facts": ["(샘플 데이터 - 검수 전)"],
    "company": {"name_ko": "애플", "country_ko": "미국", "industry_ko": "IT·전자"},
}


def build_caption(sc, sources, series="news"):
    tags = " ".join(sc["hashtags"])
    if series == "history":
        return (f"{sc['caption']}\n\n📚 참고: {', '.join(sources[:3])}\n🎞 영상: Pixabay\n"
                f"🤖 이 콘텐츠는 AI로 제작되었습니다.\n\n{tags}")
    return (f"{sc['caption']}\n\n📰 출처: {', '.join(sources[:3])}\n🎞 영상: Pixabay\n"
            f"🤖 이 콘텐츠는 AI로 제작되었으며 투자 권유가 아닙니다.\n\n{tags}")


def _custom_news():
    """jobs/news_custom.json 의 date(한국시간 YYYYMMDD)가 오늘이면 자동 선정 대신 그 주제·확정 사실로 원픽을 만듦.
    (예: 장중 기사로 만든 원고를 폐기하고 종가 확정 기사로 다시 만들 때)"""
    import json
    f = config.ROOT / "jobs" / "news_custom.json"
    if not f.exists():
        return None
    try:
        c = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [지정 주제] 읽기 실패: {e}")
        return None
    if str(c.get("date")) != _today():
        return None
    return c


def _news_script(focus="global"):
    """focus: global = 12:00 오늘의 원픽, us = 07:00 미국 증시 마감, kr = 18:00 국내 마감 브리핑·뉴스 정리.
    세 시리즈는 '이미 다룬 주제' 기록을 함께 써서 하루 안에 같은 이슈가 겹치지 않음."""
    mk = market.material(focus) if focus in ("us", "kr") else None
    history_log = load_state("history", [])
    custom = _custom_news() if focus == "global" else None
    if custom:
        print(f"1~2) 지정 주제(jobs/news_custom.json): {custom['topic']}")
        main = {"title": custom["title"], "source": custom["source"], "link": custom["link"],
                "summary": custom.get("summary", ""), "related": []}
        pick = {"topic": custom["topic"]}
        mats = script.gather_materials([], main)
        mats.insert(0, {"title": custom["title"], "source": custom["source"], "link": custom["link"],
                        "summary": custom.get("summary", ""), "body": custom["facts"]})
        drop = set(custom.get("drop_history", []))   # 폐기한 영상은 '이미 다룬 영상'에서 뺌
        history_log = [h for h in history_log if h.get("date") not in drop]
    else:
        print("1) 뉴스 수집" + (" (국내 증시)" if focus == "kr" else ""))
        items = news.fetch_all(news.KR_FEEDS if focus == "kr" else news.FEEDS)
        cands, pool = news.rank(items, history_log)
        if not cands:
            raise RuntimeError("후보 뉴스를 찾지 못했습니다 (RSS 수집 실패).")
        print("2) 오늘의 뉴스 선정")
        idx, pick = script.pick_story(cands, history_log, focus=focus, market=mk["body"] if mk else "")
        main = cands[idx]
        print(f"   → {main['title']} ({main['source']}) / {pick.get('reason')}")
        mats = script.gather_materials(pool, main)
        if focus == "kr":   # 뉴스 정리용: 주 이슈와 다른 화제 뉴스 2개 (제목·요약만, 그 안의 사실만 쓰게 함)
            others = [c for j, c in enumerate(cands) if j != idx and j not in main.get("related", [])][:2]
            for c in others:
                mats.append({"title": "[그밖의 뉴스] " + c["title"], "source": c["source"], "link": c["link"],
                             "summary": c.get("summary", ""), "body": c.get("summary", "")})
    if mk:
        mats.insert(0, {**mk, "title": "[시세 데이터] " + mk["title"]})
    print("3) 대본 작성")
    sc = script.write_script(mats, pick.get("topic") or main["title"], config.BRAND_NAME, recent=history_log, focus=focus)
    print("4) 팩트체크 (숫자 대조 + AI 검증)")
    try:
        sc, sc["factcheck"] = factcheck.run(sc, mats, skip_last=1)   # 마지막 질문은 사실 확인 대상이 아님
    except Exception as e:
        print(f"  [팩트체크] 건너뜀: {e}")
        sc["factcheck"] = None
    print("5) 원고 검수 (흐름·마지막 질문 연결)")
    outro = config.OUTROS.get(focus, config.OUTROS["news"])
    sc = script.polish_flow(sc, outro)
    sc = script.add_outro(sc, outro)
    print("6) 자막 맞춤법 검수")
    sc = script.proofread(sc)
    sources = list(dict.fromkeys(m["source"] for m in mats))
    meta = {"title_en": main["title"], "link": main["link"], "topic": pick.get("topic", ""),
            "links": [m["link"] for m in mats],
            "kr": bool(pick.get("kr")) or focus == "kr" or script.is_kr(sc.get("hook_title"))}
    return sc, sources, meta


def _custom_episode():
    """jobs/history_custom.json 의 date(한국시간 YYYYMMDD)가 오늘이면 자동 선정 대신 그 에피소드·자료를 씀.
    이미 같은 날 그 에피소드를 만들었으면(episodes 기록) 다시 쓰지 않음."""
    import json
    f = config.ROOT / "jobs" / "history_custom.json"
    if not f.exists():
        return None
    try:
        c = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [지정 에피소드] 읽기 실패: {e}")
        return None
    if str(c.get("date")) != _today():
        return None
    ep = c["ep"]
    replaces = set(c.get("replaces", []))   # 지우고 다시 만드는 회차 id (그 회차는 '이미 만듦'으로 치지 않음)
    if any(e.get("date", "").startswith(f"h{c['date']}") and e.get("company") == ep.get("company")
           and e.get("date") not in replaces for e in load_state("episodes", [])):
        print("  [지정 에피소드] 오늘 이미 만들었어요 → 자동 선정으로")
        return None
    if c.get("material"):
        return ep, c["material"], c.get("links", [])
    material, links = history.gather(ep, limit=12000)   # 자료를 안 적었으면 위키백과에서 모음
    if not material:
        print("  [지정 에피소드] 위키백과 근거가 부족해요 → 자동 선정으로")
        return None
    return ep, material, links


def _history_scripts():
    """반환: (장편 대본, 60초 대본, 에피소드, 근거 링크)"""
    used = load_state("episodes", [])
    custom = _custom_episode()
    if custom:
        ep, material, links = custom
        print(f"1) 지정 에피소드(jobs/history_custom.json): {ep.get('company_ko')} {ep.get('year')}년 — {ep.get('episode_ko')}")
        print("2) 장편 대본(약 5분)")
        lsc = history.write_long(ep, material, config.BRAND_NAME)
        if lsc.get("chart") is None and ep.get("ticker"):
            lsc["chart"] = {"ticker": ep["ticker"], "label": f"{ep.get('company_ko', '')} 주가 · {ep['year']}년~현재"}
        ssc = None
        if _need_short():
            print("3) 60초 요약 대본")
            ssc = history.condense_short(lsc, ep, has_long=config.HISTORY_LONG)
        print("4) 자막 맞춤법 검수")
        if config.HISTORY_LONG:
            lsc = script.proofread(lsc)
        if ssc:
            ssc = script.proofread(ssc)
        return lsc, ssc, ep, links
    tried = []
    print("1) 에피소드 선정(지금 화제인 기업 우선) + 위키백과 근거 수집")
    heads = history.hot_headlines()
    print(f"  [화제] 최근 뉴스 제목 {len(heads)}개 참고")
    for _ in range(3):
        ep = history.pick_episode(used + tried, heads)
        print(f"   → {ep.get('company_ko')} {ep.get('year')}년: {ep.get('episode_ko')}"
              + (f"  (요즘 화제: {ep['hot_reason']})" if ep.get("hot_reason") else ""))
        material, links = history.gather(ep, limit=12000)
        if material:
            break
        tried.append(ep)
    else:
        raise RuntimeError("위키백과에서 충분한 근거 자료를 찾지 못했습니다.")
    print("2) 장편 대본(약 5분)" + ("" if config.HISTORY_LONG else " — 쇼츠 압축용 원고로만 사용"))
    lsc = history.write_long(ep, material, config.BRAND_NAME)
    if lsc.get("chart") is None and ep.get("ticker"):
        lsc["chart"] = {"ticker": ep["ticker"], "label": f"{ep.get('company_ko', '')} 주가 · {ep['year']}년~현재"}
    ssc = None
    if _need_short():
        print("3) 60초 요약 대본")
        ssc = history.condense_short(lsc, ep, has_long=config.HISTORY_LONG)
    print("4) 자막 맞춤법 검수")
    if config.HISTORY_LONG:
        lsc = script.proofread(lsc)
    if ssc:
        ssc = script.proofread(ssc)
    return lsc, ssc, ep, links


def _need_short():
    """장편을 안 만들면 쇼츠는 꼭 만듦 (둘 다 꺼져 있어도 쇼츠는 만듦)."""
    return config.HISTORY_SHORT or not config.HISTORY_LONG


def make_reel(series="news", offline=False):
    """반환: 결과 dict. history면 res["long"]에 장편 정보가 들어감."""
    now = dt.datetime.now(KST)
    rid = {"history": "h", "kr": "k", "us": "u", "talk": "t"}.get(series, "n") + now.strftime("%Y%m%d-%H%M%S")
    tts.set_series(series)   # 목소리: 원픽 서현, 그때 그 결정 필재
    work = config.WORK_DIR / rid
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = config.OUTPUT_DIR / f"reel_{rid}.mp4"

    if series in ("news", "kr", "us"):
        if offline:
            sc, sources, meta = SAMPLE, ["Sample News"], {"title_en": "sample", "link": "", "topic": "sample"}
        else:
            sc, sources, meta = _news_script(focus=series if series in ("kr", "us") else "global")
        print("영상 제작 (세로 릴스)")
        dur, info = produce.short(sc, work / "short", out, sources, offline=offline)
        info["range"] = (70, 110)   # 오늘의 원픽 = 약 1분 30초 (2026-11-17 사용자 결정)
        return {"id": rid, "series": series, "created_at": now.isoformat(), "video": str(out), "script": sc,
                "sources": sources, "caption": build_caption(sc, sources, series), "duration": round(dur, 1),
                "qc": qc.check(out, info, sc, offline=offline), **meta}

    if series == "talk":   # ---- 대담 특집: 진행 서현 + 패널 필재, 가로 약 5분 (유튜브 장편만) ----
        lsc, ep, links, sources = talk.build()
        print("영상 제작: 대담 장편 (가로 약 5분)")
        long_out = config.OUTPUT_DIR / f"long_{rid}.mp4"
        ldur, chapters, thumb, linfo = produce.long(lsc, work / "long", long_out, sources, offline=offline,
                                                    chart_opts={"start_year": now.year - 1})
        return {"id": rid, "series": series, "created_at": now.isoformat(), "sources": sources,
                "title_en": ep["company"], "topic": ep["episode_ko"], "links": links, "episode": ep,
                "video": None, "script": lsc, "long_only": True, "talk": True,
                "long": {"video": str(long_out), "thumb": str(thumb), "duration": round(ldur, 1),
                         "chapters": chapters, "script": lsc, "qc": qc.check(long_out, linfo, lsc, offline=offline)}}

    # ---- 그때 그 결정: 장편(가로 5분) + 60초 릴스 ----
    if offline:
        lsc = dict(SAMPLE_LONG)
        ssc = script.normalize({"hook_title": lsc["hook_title"], "segments": lsc["intro"] + lsc["chapters"][1]["segments"]
                                + lsc["chapters"][2]["segments"], "caption": "테스트용 샘플입니다.",
                                "hashtags": ["#그때그결정"], "chart": lsc["chart"]})
        ep = {"company": "Apple", "company_ko": "애플", "year": 1997, "episode_ko": "샘플"}
        links = []
    else:
        lsc, ssc, ep, links = _history_scripts()
    lsc.update({"ep": "", "year": ep["year"],   # 회차 번호(EP.n)는 쓰지 않음
                "wiki_titles": [ep.get("company", "")] + list(ep.get("wiki_titles") or [])})
    if ssc:
        ssc.update({"tag": history.SERIES_NAME, "pill": f"{ep['year']}년", "brand": ep.get('company_ko', '')})
    copt = {"start_year": ep["year"] - 3, "mark_year": ep["year"]}
    sources = ["Wikipedia"]

    long_res = None
    if config.HISTORY_LONG:
        print("영상 제작 ① 장편 (가로 약 5분)")
        long_out = config.OUTPUT_DIR / f"long_{rid}.mp4"
        ldur, chapters, thumb, linfo = produce.long(lsc, work / "long", long_out, sources, offline=offline, chart_opts=copt)
        long_res = {"video": str(long_out), "thumb": str(thumb), "duration": round(ldur, 1), "chapters": chapters,
                    "script": lsc, "qc": qc.check(long_out, linfo, lsc, offline=offline)}
    else:
        print("영상 제작 ① 장편: 건너뜀 (HISTORY_LONG=false, 쇼츠 집중)")
    base = {"id": rid, "series": series, "created_at": now.isoformat(), "sources": sources,
            "title_en": ep.get("company", ""), "topic": ep.get("episode_ko", ""), "links": links, "episode": ep,
            "long": long_res}
    if not ssc:   # 장편만 (유튜브 전용)
        return {**base, "video": None, "script": lsc, "long_only": True}
    print("영상 제작 ② 60초 릴스 (세로)")
    sdur, sinfo = produce.short(ssc, work / "short", out, sources, offline=offline, chart_opts=copt)
    return {**base, "video": str(out), "script": ssc, "caption": build_caption(ssc, sources, series),
            "duration": round(sdur, 1), "qc": qc.check(out, sinfo, ssc, offline=offline)}


def _mmss(t):
    t = int(round(t))
    return f"{t // 60:02d}:{t % 60:02d}"


def deliver_long(res, offline=False):
    """장편: GitHub Release에 원본·썸네일 보관 → 텔레그램에 썸네일, 미리보기, 유튜브 업로드용 문구."""
    lg, ep = res["long"], res.get("episode", {})
    lsc = lg["script"]
    is_talk = bool(res.get("talk"))
    label = talk.SERIES_NAME if is_talk else "그때 그 결정"
    url = None
    if not offline and storage.enabled():
        tag = f"long-{res['id']}"
        storage.upload(lg["video"], tag, lsc.get("youtube_title") or lsc["hook_title"])
        storage.add_asset(tag, lg["thumb"], "thumbnail.jpg")
        url = storage.public_url(tag, f"{tag}.mp4")
        storage.prune("long-", keep=6)
    if not telegram.enabled():
        return
    chap = "\n".join(f"{_mmss(t)} {name}" for t, name in lg["chapters"])
    desc = (f"{lsc.get('description', '')}\n\n⏱ 챕터\n{chap}\n\n📚 참고: "
            + (", ".join(res.get("sources", [])[:6]) if is_talk else "Wikipedia") + "\n"
            + "\n".join(res.get("links", [])[:3]) + "\n🎞 영상: Pixabay"
            + (f"\n🖼 썸네일 사진: {lsc['thumb_credit']}" if lsc.get("thumb_credit") else "")
            + "\n🤖 이 콘텐츠는 AI로 제작되었습니다.")
    telegram.send_photo(lg["thumb"], f"🖼 [{label}] 유튜브 썸네일 · {ep.get('company_ko', '')}"
                        + (f" {ep['year']}년" if ep.get("year") else ""))
    pv = str(lg["video"]).replace(".mp4", "_preview.mp4")
    render.preview(lg["video"], pv)
    telegram.send_video(pv, f"🎬 [유튜브 장편 미리보기 · 저화질] {_mmss(lg['duration'])}\n{qc.summary(lg.get('qc'))}")
    yt_on = youtube.enabled() and not offline and url
    yt_title = (lsc.get('youtube_title') or lsc['hook_title'].replace('[', '').replace(']', ''))[:100]
    yrid = f"yt{res['id']}"
    msg_id = telegram.send_message(
        ("📺 유튜브 장편 — 아래 버튼을 누르면 경제원픽 채널에 바로 공개 게시돼요 (제목·설명·태그·썸네일 포함)\n\n"
         if yt_on else "📺 유튜브 업로드용 (직접 올리기)\n\n")
        + (f"■ 원본 영상 다운로드 (1080p)\n{url}\n\n" if url else "")
        + f"■ 제목\n{yt_title}\n\n"
        + f"■ 설명\n{desc}\n\n■ 태그\n{', '.join(lsc.get('tags', []))}\n\n"
        + (factcheck.summary(lsc["factcheck"]) + "\n\n" if lsc.get("factcheck") else "")
        + "■ 사실 검수용\n" + "\n".join(f"- {k}" for k in lsc.get("key_facts", [])[:8])
        + (f"\n\n{script.proofread_summary(lsc)}" if script.proofread_summary(lsc) else ""),
        buttons=([("✅ 유튜브 게시 (공개)", f"approve:{yrid}")]
                 + ([("🔁 다른 에피소드로 다시 만들기", f"redo:{yrid}")] if res.get("long_only") and not is_talk else [])
                 + [("❌ 유튜브에는 안 올림", f"reject:{yrid}")])
        if yt_on else None)
    if yt_on:
        expire_pending("youtube")
        pending.save("youtube", {"id": yrid, "series": "youtube", "created_at": res.get("created_at"),
                                 "release_tag": f"long-{res['id']}", "keep_release": True,
                                 "video_name": f"long-{res['id']}.mp4", "thumb_name": "thumbnail.jpg",
                                 "hook_title": yt_title, "yt_title": yt_title, "yt_description": desc,
                                 "yt_tags": lsc.get("tags", []), "tg_message_id": msg_id})


def expire_pending(series):
    old = pending.load(series)
    if not old:
        return
    if old.get("release_tag") and storage.enabled() and not old.get("keep_release"):
        storage.delete(old["release_tag"])
    if telegram.enabled() and old.get("tg_message_id"):
        telegram.remove_buttons(old["tg_message_id"])
    pending.save(series, None)


def deliver(res, offline=False):
    """보관(GitHub Release) + 텔레그램 미리보기 + 대기 상태 저장."""
    series = res["series"]
    if res.get("talk"):   # 대담 특집: 유튜브 장편 승인만 (다른 시리즈의 대기 영상은 건드리지 않음)
        deliver_long(res, offline=offline)
        return
    expire_pending(series)
    if res.get("long_only"):
        eps = load_state("episodes", [])
        ep = res.get("episode", {})
        eps.append({"date": res["id"], "company": ep.get("company", ""), "year": ep.get("year"),
                    "episode_ko": ep.get("episode_ko", res.get("topic", ""))})
        save_state("episodes", eps[-200:])
        deliver_long(res, offline=offline)
        return
    if not offline and storage.enabled():
        res["release_tag"] = storage.upload(res["video"], f"reel-{res['id']}", res["script"]["hook_title"])
        cov = instagram.cover_frame(res["video"], str(res["video"]).replace(".mp4", "_cover.jpg"))
        if cov:   # 유튜브 쇼츠 썸네일 = 인스타 커버 (승인 처리 쪽엔 ffmpeg가 없을 수 있어 미리 보관)
            storage.add_asset(res["release_tag"], cov, "cover.jpg")
            res["cover_name"] = "cover.jpg"
    if series == "history":
        eps = load_state("episodes", [])
        ep = res.get("episode", {})
        eps.append({"date": res["id"], "company": ep.get("company", ""), "year": ep.get("year"),
                    "country_ko": ep.get("country_ko", ""), "episode_ko": ep.get("episode_ko", res.get("topic", ""))})
        save_state("episodes", eps[-200:])
    else:
        log = load_state("history", [])
        log.append({"date": res["id"], "series": series, "kr": bool(res.get("kr")), "title_ko": res["script"]["hook_title"],
                    "title_en": res.get("title_en", ""), "topic": res.get("topic", ""), "link": res.get("link", "")})
        save_state("history", log[-60:])

    if res.get("long"):
        deliver_long(res, offline=offline)
    if telegram.enabled():
        sc, rid, label = res["script"], res["id"], pending.LABEL[series]
        telegram.send_message(
            f"🎬 [{label}] 릴스(세로) 초안 ({res['duration']}초)\n{qc.summary(res.get('qc'))}\n"
            + (factcheck.summary(sc.get("factcheck")) + "\n" if sc.get("factcheck") else "")
            + (script.proofread_summary(sc) + "\n" if script.proofread_summary(sc) else "") + "\n"
            f"■ 화면 제목: [{sc.get('tag', '')}] {sc['hook_title']}\n"
            f"■ 유튜브 제목: {script.youtube_title(sc, sc['hook_title'])}\n\n■ 대본\n" +
            "\n".join(f"{i+1}. {s['text']}" for i, s in enumerate(sc["segments"])) +
            "\n\n■ 사실 검수용 (근거와 대조)\n" + "\n".join(f"- {k}" for k in sc.get("key_facts", [])) +
            "\n\n■ 근거 링크\n" + "\n".join(res.get("links", [])[:4]) +
            "\n\n■ 캡션\n" + res["caption"])
        yt_note = " + 유튜브 쇼츠" if youtube.enabled() else ""
        buttons = [(f"✅ 승인 → 인스타{yt_note} 게시", f"approve:{rid}"),
                     ("🔁 다른 " + ("에피소드로" if series == "history" else "뉴스로") + " 다시 만들기", f"redo:{rid}"),
                     ("❌ 폐기", f"reject:{rid}")]
        cap = f"[{label}] {sc['hook_title']}\n\n아래 버튼을 눌러 주세요. 2시간 안에 누르면 바로 처리돼요."
        try:
            res["tg_message_id"] = telegram.send_video(res["video"], cap, buttons=buttons)
        except Exception as e:   # 영상 전송이 끝내 안 되면 다운로드 링크 + 버튼으로 대신 보냄
            print("  [텔레그램] 릴스 영상 전송 실패 → 링크로 대체:", e)
            link = storage.public_url(res["release_tag"], f"{res['release_tag']}.mp4") if res.get("release_tag") else ""
            res["tg_message_id"] = telegram.send_message(
                f"⚠️ 영상 파일 전송이 실패해서 링크로 보내요.\n{link}\n\n" + cap, buttons=buttons)
    pending.save(series, {k: v for k, v in res.items() if k not in ("script", "episode", "long")}
                 | {"sent_at": dt.datetime.now(dt.timezone.utc).isoformat(), "hook_title": res["script"]["hook_title"], "tag": res["script"].get("tag", ""),
                    "hashtags": res["script"].get("hashtags", []), "brand": res["script"].get("brand", ""),
                    "yt_title": res["script"].get("yt_title", ""), "title_tags": res["script"].get("title_tags", []),
                    "question": res["script"].get("question") or res["script"]["segments"][-1]["text"]})


def _wait_us_close(max_min=40):   # 작업 시간 제한(180분) 안에 버튼 대기까지 끝나도록
    """미국 증시 마감 브리핑은 미국 장 마감(뉴욕 16:00) + 10분 뒤에만 제작. 장중이면 마감까지 기다림.
    너무 오래 기다려야 하면 False (이번 실행은 건너뜀)."""
    from zoneinfo import ZoneInfo
    ny = dt.datetime.now(ZoneInfo("America/New_York"))
    open_t = ny.replace(hour=9, minute=30, second=0, microsecond=0)
    ready = ny.replace(hour=16, minute=10, second=0, microsecond=0)
    if ny.weekday() >= 5 or not (open_t <= ny < ready):
        return True
    mins = (ready - ny).total_seconds() / 60
    if mins > max_min:
        print(f"미국 장이 열려 있어요(마감까지 {mins:.0f}분). 장 마감 뒤에 다시 실행해 주세요. 건너뜁니다.")
        return False
    print(f"미국 장 마감 전이에요. 종가 확정까지 {mins:.0f}분 기다린 뒤 만들어요.")
    time.sleep(mins * 60)
    return True


def _kr_ready():
    """국내 마감 브리핑은 평일 코스피 마감(15:30) 뒤에만, 오늘 장이 열렸을 때만 제작."""
    now = dt.datetime.now(KST)
    if now.weekday() >= 5:
        print("주말이라 국내 마감 브리핑은 쉬어요. 건너뜁니다.")
        return False
    if now.hour * 60 + now.minute < 15 * 60 + 40:
        print("코스피 마감(15:30) 전이에요. 15:40 이후에 다시 실행해 주세요. 건너뜁니다.")
        return False
    last = market.last_session("^KS11")
    if last and last != now.date():
        print(f"오늘은 국내 증시 휴장이에요(마지막 거래일 {last}). 건너뜁니다.")
        return False
    return True


def _us_session_today():
    """미국 증시 마감 브리핑: 방금 끝난 뉴욕 거래일이 있을 때만 (주말·미국 휴장이면 건너뜀). 시세를 못 받으면 그대로 진행."""
    from zoneinfo import ZoneInfo
    ny = dt.datetime.now(ZoneInfo("America/New_York"))
    if ny.weekday() >= 5:
        print("미국 증시가 쉬는 날이에요(주말). 건너뜁니다.")
        return False
    last = market.last_session("^GSPC")
    if last and last != ny.date():
        print(f"오늘(뉴욕 {ny.date()}) 미국 증시는 휴장이에요(마지막 거래일 {last}). 건너뜁니다.")
        return False
    return True


def _today():
    return dt.datetime.now(KST).strftime("%Y%m%d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", choices=["news", "us", "kr", "history", "talk"], default="news",
                    help="us=07:00 미국 증시 마감, news=12:00 오늘의 원픽, kr=18:00 국내 마감 브리핑, history=그때 그 결정")
    ap.add_argument("--offline", action="store_true", help="샘플 데이터로 렌더링만 테스트")
    ap.add_argument("--no-deliver", action="store_true", help="텔레그램 전송·상태 저장 생략")
    ap.add_argument("--wait", type=int, default=0, help="영상 전송 후 버튼을 실시간으로 기다릴 시간(분)")
    ap.add_argument("--once-per-day", action="store_true", help="오늘 자동 제작을 이미 했으면 건너뜀")
    a = ap.parse_args()
    if a.offline:
        config.TTS_ENGINE = "dummy" if config.TTS_ENGINE == "edge" and not _has("edge_tts") else config.TTS_ENGINE
    series = a.series
    slot = None
    if (series == "news" and a.once_per_day and not a.offline and config.WEEKEND_HISTORY
            and dt.datetime.now(KST).weekday() >= 5):   # 예약 자동 실행만 (주말에 /new로 직접 부르면 원픽)
        # 주말 12:00 자리는 원픽 대신 그때 그 결정 (주말엔 하루 2편: 12:00 + 18:00)
        print("주말이라 12:00 자리는 '그때 그 결정'으로 만들어요.")
        series, slot = "history", config.YT_SLOTS["news"]
    if series == "us" and not a.offline and (not _wait_us_close() or not _us_session_today()):
        return
    if series == "kr" and not a.offline and not _kr_ready():
        return
    def _on_cancel(signum, frame):   # Actions 취소·시간 초과 때도 아래 except로 가서 '오늘 했음' 표시를 되돌림
        raise RuntimeError(f"작업이 중단됨(신호 {signum}: 취소 또는 시간 초과)")
    signal.signal(signal.SIGTERM, _on_cancel)
    signal.signal(signal.SIGINT, _on_cancel)
    if a.once_per_day:
        key = ("last_daily" if series == "news" else "last_daily_history_noon" if slot
               else f"last_daily_{series}")
        prev_mark = load_state(key, {})
        if prev_mark.get("date") == _today():
            print("오늘 자동 제작은 이미 했어요. 건너뜁니다.")
            return
        save_state(key, {"date": _today()})
        git_push_state("state: daily start")   # 다른 예약 실행과 중복 방지
    deadline = dt.datetime.now(KST) + dt.timedelta(minutes=a.wait)   # 다시 만들기가 있어도 전체 대기는 a.wait 안에서
    delivered = False
    try:
        while True:
            res = make_reel(series, offline=a.offline)
            if slot:
                res["slot"] = slot      # 유튜브 공개 시각을 시리즈 기본값 대신 이 시각으로
            if a.no_deliver:
                break
            deliver(res, offline=a.offline)
            delivered = True
            print("완료:", res.get("video") or res.get("long", {}).get("video"))
            left = int((deadline - dt.datetime.now(KST)).total_seconds() // 60)
            if not a.wait or not telegram.enabled() or left < 5:
                break
            kind, nxt = approval.wait_for_decision(res["id"], left)
            if kind != "redo":
                break
            series = nxt
            slot = slot if nxt == "history" else None
    except Exception as e:
        traceback.print_exc()
        if a.once_per_day and not delivered:   # 전송 전에 실패하면 '오늘 했음' 표시를 되돌려 다시 시도할 수 있게
            try:
                save_state(key, prev_mark)
                git_push_state("state: daily reset (실패)")
            except Exception as e2:
                print("  [상태] 되돌리기 실패:", e2)
        if telegram.enabled() and not a.offline:
            try:
                telegram.send_message(f"❌ [{pending.LABEL[series]}] 릴스 생성 실패\n{type(e).__name__}: {str(e)[:600]}\n\n"
                                      "/new 또는 /history 로 다시 시도하거나, 이 메시지를 Claude에게 보여주세요.")
            except Exception:
                pass
        sys.exit(1)


def _has(mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    main()
