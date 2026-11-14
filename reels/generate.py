"""오늘의 릴스 만들기: 뉴스 수집 → 선정 → 대본 → 음성 → 영상 → 텔레그램 미리보기.

사용법:
  python -m reels.generate                      # 오늘의 경제
  python -m reels.generate --series history     # 그때 그 결정
  python -m reels.generate --offline            # 인터넷/키 없이 샘플로 렌더링만 테스트
"""
import argparse
import datetime as dt
import shutil
import sys
import traceback

from . import approval, config, history, news, pending, produce, qc, render, script, storage, telegram
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
        _seg("여러분은 이번 인하, 내 대출에 도움이 될 거라 보시나요?", "family home"),
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


def _news_script():
    history_log = load_state("history", [])
    print("1) 뉴스 수집")
    items = news.fetch_all()
    cands, pool = news.rank(items, history_log)
    if not cands:
        raise RuntimeError("후보 뉴스를 찾지 못했습니다 (RSS 수집 실패).")
    print("2) 오늘의 뉴스 선정")
    idx, pick = script.pick_story(cands, history_log)
    main = cands[idx]
    print(f"   → {main['title']} ({main['source']}) / {pick.get('reason')}")
    mats = script.gather_materials(pool, main)
    print("3) 대본 작성")
    sc = script.write_script(mats, pick.get("topic") or main["title"], config.BRAND_NAME)
    sources = list(dict.fromkeys(m["source"] for m in mats))
    meta = {"title_en": main["title"], "link": main["link"], "topic": pick.get("topic", ""),
            "links": [m["link"] for m in mats]}
    return sc, sources, meta


def _history_scripts():
    """반환: (장편 대본, 60초 대본, 에피소드, 근거 링크)"""
    used = load_state("episodes", [])
    tried = []
    print("1) 에피소드 선정 + 위키백과 근거 수집")
    for _ in range(3):
        ep = history.pick_episode(used + tried)
        print(f"   → {ep.get('company_ko')} {ep.get('year')}년: {ep.get('episode_ko')}")
        material, links = history.gather(ep, limit=12000)
        if material:
            break
        tried.append(ep)
    else:
        raise RuntimeError("위키백과에서 충분한 근거 자료를 찾지 못했습니다.")
    print("2) 장편 대본(약 5분)")
    lsc = history.write_long(ep, material, config.BRAND_NAME)
    if lsc.get("chart") is None and ep.get("ticker"):
        lsc["chart"] = {"ticker": ep["ticker"], "label": f"{ep.get('company_ko', '')} 주가 · {ep['year']}년~현재"}
    print("3) 60초 요약 대본")
    ssc = history.condense_short(lsc, ep)
    return lsc, ssc, ep, links


def make_reel(series="news", offline=False):
    """반환: 결과 dict. history면 res["long"]에 장편 정보가 들어감."""
    now = dt.datetime.now(KST)
    rid = ("h" if series == "history" else "n") + now.strftime("%Y%m%d-%H%M%S")
    work = config.WORK_DIR / rid
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = config.OUTPUT_DIR / f"reel_{rid}.mp4"

    if series == "news":
        if offline:
            sc, sources, meta = SAMPLE, ["Sample News"], {"title_en": "sample", "link": "", "topic": "sample"}
        else:
            sc, sources, meta = _news_script()
        print("영상 제작 (세로 릴스)")
        dur, info = produce.short(sc, work / "short", out, sources, offline=offline)
        return {"id": rid, "series": series, "created_at": now.isoformat(), "video": str(out), "script": sc,
                "sources": sources, "caption": build_caption(sc, sources, series), "duration": round(dur, 1),
                "qc": qc.check(out, info, sc, offline=offline), **meta}

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
    n = load_state("history_ep", {"published": 0}).get("published", 0) + 1
    ep_label = f"EP.{n}"
    lsc.update({"ep": ep_label, "year": ep["year"]})
    ssc.update({"tag": history.SERIES_NAME, "pill": f"{ep['year']}년", "brand": f"{ep_label} · {ep.get('company_ko', '')}"})
    copt = {"start_year": ep["year"] - 3, "mark_year": ep["year"]}
    sources = ["Wikipedia"]

    print("영상 제작 ① 장편 (가로 약 5분)")
    long_out = config.OUTPUT_DIR / f"long_{rid}.mp4"
    ldur, chapters, thumb, linfo = produce.long(lsc, work / "long", long_out, sources, offline=offline, chart_opts=copt)
    print("영상 제작 ② 60초 릴스 (세로)")
    sdur, sinfo = produce.short(ssc, work / "short", out, sources, offline=offline, chart_opts=copt)
    return {"id": rid, "series": series, "created_at": now.isoformat(), "video": str(out), "script": ssc,
            "sources": sources, "caption": build_caption(ssc, sources, series), "duration": round(sdur, 1),
            "title_en": ep.get("company", ""), "topic": ep.get("episode_ko", ""), "links": links, "episode": ep,
            "qc": qc.check(out, sinfo, ssc, offline=offline),
            "long": {"video": str(long_out), "thumb": str(thumb), "duration": round(ldur, 1), "chapters": chapters,
                     "script": lsc, "qc": qc.check(long_out, linfo, lsc, offline=offline)}}


def _mmss(t):
    t = int(round(t))
    return f"{t // 60:02d}:{t % 60:02d}"


def deliver_long(res, offline=False):
    """장편: GitHub Release에 원본·썸네일 보관 → 텔레그램에 썸네일, 미리보기, 유튜브 업로드용 문구."""
    lg, ep = res["long"], res.get("episode", {})
    lsc = lg["script"]
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
    desc = (f"{lsc.get('description', '')}\n\n⏱ 챕터\n{chap}\n\n📚 참고: Wikipedia\n"
            + "\n".join(res.get("links", [])[:3]) + "\n🎞 영상: Pixabay\n🤖 이 콘텐츠는 AI로 제작되었습니다.")
    telegram.send_photo(lg["thumb"], f"🖼 [그때 그 결정] 유튜브 썸네일 · {ep.get('company_ko', '')} {ep.get('year', '')}년")
    pv = str(lg["video"]).replace(".mp4", "_preview.mp4")
    render.preview(lg["video"], pv)
    telegram.send_video(pv, f"🎬 [유튜브 장편 미리보기 · 저화질] {_mmss(lg['duration'])}\n{qc.summary(lg.get('qc'))}")
    telegram.send_message(
        "📺 유튜브 업로드용 (직접 올리기)\n\n"
        + (f"■ 원본 영상 다운로드 (1080p)\n{url}\n\n" if url else "")
        + f"■ 제목\n{lsc.get('youtube_title') or lsc['hook_title'].replace('[', '').replace(']', '')}\n\n"
        + f"■ 설명\n{desc}\n\n■ 태그\n{', '.join(lsc.get('tags', []))}\n\n"
        + "■ 사실 검수용\n" + "\n".join(f"- {k}" for k in lsc.get("key_facts", [])[:8]))


def expire_pending(series):
    old = pending.load(series)
    if not old:
        return
    if old.get("release_tag") and storage.enabled():
        storage.delete(old["release_tag"])
    if telegram.enabled() and old.get("tg_message_id"):
        telegram.remove_buttons(old["tg_message_id"])
    pending.save(series, None)


def deliver(res, offline=False):
    """보관(GitHub Release) + 텔레그램 미리보기 + 대기 상태 저장."""
    series = res["series"]
    expire_pending(series)
    if not offline and storage.enabled():
        res["release_tag"] = storage.upload(res["video"], f"reel-{res['id']}", res["script"]["hook_title"])
    if series == "history":
        eps = load_state("episodes", [])
        ep = res.get("episode", {})
        eps.append({"date": res["id"], "company": ep.get("company", ""), "year": ep.get("year"),
                    "episode_ko": ep.get("episode_ko", res.get("topic", ""))})
        save_state("episodes", eps[-200:])
    else:
        log = load_state("history", [])
        log.append({"date": res["id"], "title_ko": res["script"]["hook_title"],
                    "title_en": res.get("title_en", ""), "topic": res.get("topic", ""), "link": res.get("link", "")})
        save_state("history", log[-60:])

    if res.get("long"):
        deliver_long(res, offline=offline)
    if telegram.enabled():
        sc, rid, label = res["script"], res["id"], pending.LABEL[series]
        telegram.send_message(
            f"🎬 [{label}] 릴스(세로) 초안 ({res['duration']}초)\n{qc.summary(res.get('qc'))}\n\n"
            f"■ 제목: [{sc.get('tag', '')}] {sc['hook_title']}\n\n■ 대본\n" +
            "\n".join(f"{i+1}. {s['text']}" for i, s in enumerate(sc["segments"])) +
            "\n\n■ 사실 검수용 (근거와 대조)\n" + "\n".join(f"- {k}" for k in sc.get("key_facts", [])) +
            "\n\n■ 근거 링크\n" + "\n".join(res.get("links", [])[:4]) +
            "\n\n■ 캡션\n" + res["caption"])
        res["tg_message_id"] = telegram.send_video(
            res["video"], f"[{label}] {sc['hook_title']}\n\n아래 버튼을 눌러 주세요. 2시간 안에 누르면 바로 처리돼요.",
            buttons=[("✅ 승인 → 인스타 게시", f"approve:{rid}"),
                     ("🔁 다른 " + ("에피소드로" if series == "history" else "뉴스로") + " 다시 만들기", f"redo:{rid}"),
                     ("❌ 폐기", f"reject:{rid}")])
    pending.save(series, {k: v for k, v in res.items() if k not in ("script", "episode", "long")}
                 | {"hook_title": res["script"]["hook_title"]})


def _today():
    return dt.datetime.now(KST).strftime("%Y%m%d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", choices=["news", "history"], default="news", help="news=오늘의 경제, history=그때 그 결정")
    ap.add_argument("--offline", action="store_true", help="샘플 데이터로 렌더링만 테스트")
    ap.add_argument("--no-deliver", action="store_true", help="텔레그램 전송·상태 저장 생략")
    ap.add_argument("--wait", type=int, default=0, help="영상 전송 후 버튼을 실시간으로 기다릴 시간(분)")
    ap.add_argument("--once-per-day", action="store_true", help="오늘 자동 제작을 이미 했으면 건너뜀")
    a = ap.parse_args()
    if a.offline:
        config.TTS_ENGINE = "dummy" if config.TTS_ENGINE == "edge" and not _has("edge_tts") else config.TTS_ENGINE
    series = a.series
    if a.once_per_day:
        key = "last_daily" if series == "news" else f"last_daily_{series}"
        if load_state(key, {}).get("date") == _today():
            print("오늘 자동 제작은 이미 했어요. 건너뜁니다.")
            return
        save_state(key, {"date": _today()})
        git_push_state("state: daily start")   # 다른 예약 실행과 중복 방지
    try:
        while True:
            res = make_reel(series, offline=a.offline)
            if a.no_deliver:
                break
            deliver(res, offline=a.offline)
            print("완료:", res["video"])
            if not a.wait or not telegram.enabled():
                break
            kind, nxt = approval.wait_for_decision(res["id"], a.wait)
            if kind != "redo":
                break
            series = nxt
    except Exception as e:
        traceback.print_exc()
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
