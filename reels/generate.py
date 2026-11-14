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

from . import approval, chart, config, history, news, pending, render, script, stock, storage, telegram, tts
from .utils import git_push_state, load_state, save_state

KST = dt.timezone(dt.timedelta(hours=9))

SAMPLE = {
    "tag": "금리",
    "hook_title": "미국 금리 [0.25%p 인하], 내 대출은?",
    "segments": [
        {"text": "미국이 또 금리를 내렸어요. 이번엔 0.25%p예요.", "keywords": "federal reserve", "show_chart": False},
        {"text": "연준은 물가보다 일자리 둔화를 더 걱정하고 있다는 뜻이죠.", "keywords": "office workers city", "show_chart": False},
        {"text": "발표 직후 S&P 500 지수는 1.2% 올랐어요.", "keywords": "stock market screen", "show_chart": True},
        {"text": "금리가 내려가면 달러 가치가 약해지는 경우가 많아요.", "keywords": "us dollar money", "show_chart": False},
        {"text": "그러면 원/달러 환율이 내려가 수입 물가 부담이 줄 수 있죠.", "keywords": "shipping containers port", "show_chart": False},
        {"text": "한국은행도 금리 인하를 고민할 시간이 다가오고 있어요.", "keywords": "seoul skyline night", "show_chart": False},
        {"text": "여러분은 이번 인하, 내 대출에 도움이 될 거라 보시나요?", "keywords": "family home", "show_chart": False},
    ],
    "chart": {"ticker": "^GSPC", "label": "S&P 500 · 최근 1개월"},
    "key_facts": ["(샘플 데이터 - 실제 뉴스 아님)"],
    "caption": "테스트용 샘플 대본입니다.",
    "hashtags": ["#경제뉴스", "#테스트"],
}


SAMPLE_HISTORY = {
    "hook_title": "파산 직전 애플, [90일]의 기적",
    "segments": [
        {"text": "1997년, 애플은 파산까지 90일밖에 남지 않았어요.", "keywords": "empty office night", "show_chart": False},
        {"text": "쫓겨났던 창업자 스티브 잡스가 회사로 돌아옵니다.", "keywords": "man walking city 1990s", "show_chart": False},
        {"text": "그가 처음 한 일은 제품 수십 개를 4개로 줄이는 거였죠.", "keywords": "boardroom meeting", "show_chart": False},
        {"text": "그리고 경쟁자 마이크로소프트의 투자를 받아들였어요.", "keywords": "handshake business", "show_chart": False},
        {"text": "그 결정 이후 애플 주가는 수백 배가 됐습니다.", "keywords": "stock market screen", "show_chart": True},
        {"text": "위기 때 필요한 건 더하기가 아니라 빼기였던 거죠.", "keywords": "minimal desk", "show_chart": False},
        {"text": "여러분 회사라면, 무엇을 먼저 버리시겠어요?", "keywords": "office window view", "show_chart": False},
    ],
    "chart": {"ticker": "AAPL", "label": "애플 주가 · 1994년~현재"},
    "key_facts": ["(샘플 데이터 - 검수 전)"],
    "caption": "테스트용 샘플 대본입니다.",
    "hashtags": ["#그때그결정", "#테스트"],
    "tag": "그때 그 결정", "pill": "1997년", "brand": "EP.1 · 애플",
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
    return sc, sources, meta, {}


def _history_script():
    used = load_state("episodes", [])
    tried = []
    print("1) 에피소드 선정 + 위키백과 근거 수집")
    for _ in range(3):
        ep = history.pick_episode(used + tried)
        print(f"   → {ep.get('company_ko')} {ep.get('year')}년: {ep.get('episode_ko')}")
        material, links = history.gather(ep)
        if material:
            break
        tried.append(ep)
    else:
        raise RuntimeError("위키백과에서 충분한 근거 자료를 찾지 못했습니다.")
    print("2) 대본 작성")
    sc = script.normalize(history.write_script(ep, material, config.BRAND_NAME))
    n = load_state("history_ep", {"published": 0}).get("published", 0) + 1
    sc.update({"tag": history.SERIES_NAME, "pill": f"{ep['year']}년", "brand": f"EP.{n} · {ep.get('company_ko', '')}"})
    if sc.get("chart") is None and ep.get("ticker"):
        sc["chart"] = {"ticker": ep["ticker"], "label": f"{ep.get('company_ko', '')} 주가 · {ep['year']}년~현재"}
    meta = {"title_en": ep.get("company", ""), "topic": ep.get("episode_ko", ""), "links": links, "episode": ep}
    return sc, ["Wikipedia"], meta, {"start_year": ep["year"] - 3, "mark_year": ep["year"]}


def make_reel(series="news", offline=False):
    now = dt.datetime.now(KST)
    rid = ("h" if series == "history" else "n") + now.strftime("%Y%m%d-%H%M%S")
    work = config.WORK_DIR / rid
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if offline:
        if series == "history":
            sc, sources, meta, copt = SAMPLE_HISTORY, ["Wikipedia"], {"topic": "sample"}, {"start_year": 1994, "mark_year": 1997}
        else:
            sc, sources, meta, copt = SAMPLE, ["Sample News"], {"title_en": "sample", "link": "", "topic": "sample"}, {}
    else:
        sc, sources, meta, copt = _history_script() if series == "history" else _news_script()

    print("음성 생성")
    narration, durs = tts.synthesize([s["text"] for s in sc["segments"]], work)
    print("배경 영상·차트")
    clips = [None] * len(durs) if offline else stock.fetch_clips(sc["segments"], durs, work)
    chart_png = chart.make_chart(sc.get("chart"), work / "chart.png", offline=offline, **copt)
    print("렌더링")
    bgms = sorted((config.ASSETS_DIR / "bgm").glob("*.mp3")) if (config.ASSETS_DIR / "bgm").exists() else []
    bgm = bgms[now.toordinal() % len(bgms)] if bgms else None
    out = config.OUTPUT_DIR / f"reel_{rid}.mp4"
    render.render(sc, durs, clips, narration, chart_png, sources, work, out, bgm=bgm)

    return {"id": rid, "series": series, "created_at": now.isoformat(), "video": str(out), "script": sc,
            "sources": sources, "caption": build_caption(sc, sources, series),
            "duration": round(sum(durs), 1), **meta}


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

    if telegram.enabled():
        sc, rid, label = res["script"], res["id"], pending.LABEL[series]
        telegram.send_message(
            f"🎬 [{label}] 릴스 초안 ({res['duration']}초)\n\n"
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
    pending.save(series, {k: v for k, v in res.items() if k not in ("script", "episode")}
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
