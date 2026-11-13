"""오늘의 릴스 만들기: 뉴스 수집 → 선정 → 대본 → 음성 → 영상 → 텔레그램 미리보기.

사용법:
  python -m reels.generate            # 실제 실행
  python -m reels.generate --offline  # 인터넷/키 없이 샘플로 렌더링만 테스트
"""
import argparse
import datetime as dt
import shutil
import sys
import traceback

from . import chart, config, news, render, script, stock, storage, telegram, tts
from .utils import load_state, save_state

KST = dt.timezone(dt.timedelta(hours=9))

SAMPLE = {
    "hook_title": "미국 금리 0.25%p 인하, 내 대출은?",
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


def build_caption(sc, sources):
    tags = " ".join(sc["hashtags"])
    src = ", ".join(sources[:3])
    return (f"{sc['caption']}\n\n📰 출처: {src}\n🎞 영상: Pixabay\n"
            f"🤖 이 콘텐츠는 AI로 제작되었으며 투자 권유가 아닙니다.\n\n{tags}")


def make_reel(offline=False):
    now = dt.datetime.now(KST)
    rid = now.strftime("%Y%m%d-%H%M")
    work = config.WORK_DIR / rid
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    history = load_state("history", [])

    if offline:
        sc, sources, meta = SAMPLE, ["Sample News"], {"title_en": "sample", "link": "", "topic": "sample"}
    else:
        print("1) 뉴스 수집")
        items = news.fetch_all()
        cands, pool = news.rank(items, history)
        if not cands:
            raise RuntimeError("후보 뉴스를 찾지 못했습니다 (RSS 수집 실패).")
        print("2) 오늘의 뉴스 선정")
        idx, pick = script.pick_story(cands, history)
        main = cands[idx]
        print(f"   → {main['title']} ({main['source']}) / {pick.get('reason')}")
        mats = script.gather_materials(pool, main)
        print("3) 대본 작성")
        sc = script.write_script(mats, pick.get("topic") or main["title"], config.BRAND_NAME)
        sources = list(dict.fromkeys(m["source"] for m in mats))
        meta = {"title_en": main["title"], "link": main["link"], "topic": pick.get("topic", ""),
                "links": [m["link"] for m in mats]}

    print("4) 음성 생성")
    narration, durs = tts.synthesize([s["text"] for s in sc["segments"]], work)
    print("5) 배경 영상·차트")
    clips = [None] * len(durs) if offline else stock.fetch_clips(sc["segments"], durs, work)
    chart_png = chart.make_chart(sc.get("chart"), work / "chart.png", offline=offline)
    print("6) 렌더링")
    bgms = sorted((config.ASSETS_DIR / "bgm").glob("*.mp3")) if (config.ASSETS_DIR / "bgm").exists() else []
    bgm = bgms[now.toordinal() % len(bgms)] if bgms else None
    out = config.OUTPUT_DIR / f"reel_{rid}.mp4"
    render.render(sc, durs, clips, narration, chart_png, sources, work, out, bgm=bgm)

    return {"id": rid, "created_at": now.isoformat(), "video": str(out), "script": sc,
            "sources": sources, "caption": build_caption(sc, sources), "duration": round(sum(durs), 1), **meta}


def expire_pending():
    old = load_state("pending", None)
    if not old:
        return
    if old.get("release_tag") and storage.enabled():
        storage.delete(old["release_tag"])
    if telegram.enabled() and old.get("tg_message_id"):
        telegram.remove_buttons(old["tg_message_id"])
    save_state("pending", None)


def deliver(res, offline=False):
    """보관(GitHub Release) + 텔레그램 미리보기 + 대기 상태 저장."""
    expire_pending()
    if not offline and storage.enabled():
        res["release_tag"] = storage.upload(res["video"], f"reel-{res['id']}", res["script"]["hook_title"])
    history = load_state("history", [])
    history.append({"date": res["id"], "title_ko": res["script"]["hook_title"],
                    "title_en": res.get("title_en", ""), "topic": res.get("topic", ""), "link": res.get("link", "")})
    save_state("history", history[-60:])

    if telegram.enabled():
        sc = res["script"]
        rid = res["id"]
        telegram.send_message(
            f"🎬 오늘의 릴스 초안 ({res['duration']}초)\n\n"
            f"■ 제목: {sc['hook_title']}\n\n■ 대본\n" +
            "\n".join(f"{i+1}. {s['text']}" for i, s in enumerate(sc["segments"])) +
            "\n\n■ 숫자 검수용 (원문 대조)\n" + "\n".join(f"- {k}" for k in sc.get("key_facts", [])) +
            "\n\n■ 원문 링크\n" + "\n".join(res.get("links", [])[:4]) +
            "\n\n■ 캡션\n" + res["caption"])
        res["tg_message_id"] = telegram.send_video(
            res["video"], f"{sc['hook_title']}\n\n아래 버튼을 눌러 주세요. (반영까지 최대 30분)",
            buttons=[("✅ 승인 → 인스타 게시", f"approve:{rid}"),
                     ("🔁 다른 뉴스로 다시 만들기", f"redo:{rid}"),
                     ("❌ 폐기", f"reject:{rid}")])
    save_state("pending", {k: v for k, v in res.items() if k != "script"} | {"hook_title": res["script"]["hook_title"]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="샘플 데이터로 렌더링만 테스트")
    ap.add_argument("--no-deliver", action="store_true", help="텔레그램 전송·상태 저장 생략")
    a = ap.parse_args()
    if a.offline:
        config.TTS_ENGINE = "dummy" if config.TTS_ENGINE == "edge" and not _has("edge_tts") else config.TTS_ENGINE
    try:
        res = make_reel(offline=a.offline)
        if not a.no_deliver:
            deliver(res, offline=a.offline)
        print("완료:", res["video"])
    except Exception as e:
        traceback.print_exc()
        if telegram.enabled() and not a.offline:
            try:
                telegram.send_message(f"❌ 오늘 릴스 생성 실패\n{type(e).__name__}: {str(e)[:600]}\n\n"
                                      "GitHub Actions 로그를 확인하거나 텔레그램에 /new 를 보내 다시 시도하세요.")
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
