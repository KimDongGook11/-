"""텔레그램 버튼/명령 처리.

1) 대기 모드: 영상을 보낸 작업이 그대로 일정 시간 텔레그램을 실시간 확인 → 버튼을 누르면 바로 처리
2) 점검 모드(python -m reels.approval): 대기 시간이 끝난 뒤 누른 버튼이나 명령을 30분마다 처리

- ✅ 승인: 인스타 게시   - 🔁 다시: 같은 시리즈로 새로 만들기   - ❌ 폐기
- 명령어: /new(오늘의 경제), /history(그때 그 결정), /status, /help
"""
import datetime as dt
import os
import tempfile
import time

from . import config, instagram, pending, storage, telegram, youtube
from .utils import git_push_state, load_state, save_state

HELP = ("명령어\n/new - 오늘의 경제 새로 만들기\n/history - '그때 그 결정' 새 에피소드 만들기\n"
        "/status - 승인 대기 중인 영상 보기\n/approve - 대기 중인 오늘의 경제 영상 게시 (버튼이 없을 때)\n"
        "/approve history - 대기 중인 '그때 그 결정' 릴스 게시\n/approve youtube - 대기 중인 유튜브 장편 게시\n/help - 도움말\n\n"
        "영상이 온 뒤 2시간 안에 누른 버튼은 바로 처리되고, 그 뒤에는 최대 30분 안에 처리돼요.")


def _owner(uid):
    return str(uid) == str(config.TELEGRAM_CHAT_ID)


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _clear(p, keep_file=False):
    if p.get("tg_message_id"):
        telegram.remove_buttons(p["tg_message_id"])
    if not keep_file and not p.get("keep_release") and p.get("release_tag") and storage.enabled():
        storage.delete(p["release_tag"])
    pending.save(p.get("series", "news"), None)


def _published(p):
    """회차 번호 올리기. 같은 에피소드의 릴스·유튜브 장편은 한 회차로 셈 (어느 쪽이 먼저 게시돼도 1번만)."""
    series = "history" if p.get("series") == "youtube" else p.get("series")
    key = {"history": "history_ep", "news": "news_ep"}.get(series)
    if not key:
        return
    rid = str(p.get("id", ""))
    rid = rid[2:] if rid.startswith("yt") else rid
    c = load_state(key, {"published": 0})
    ids = c.get("ids", [])
    if rid and rid in ids:
        return
    c["published"] = c.get("published", 0) + 1
    c["ids"] = (ids + [rid])[-100:] if rid else ids
    save_state(key, c)


def _next_news_no():
    return load_state("news_ep", {"published": 0}).get("published", 0) + 1


def _local_video(p):
    path = p.get("video")
    if not path or not os.path.exists(path):
        path = os.path.join(tempfile.gettempdir(), f"reel_{p['id']}.mp4")
        if not os.path.exists(path):
            storage.download(p["release_tag"], path)
    return path


def _publish_at():
    """설정한 공개 시각(한국시간)이 아직 안 지났으면 그 시각(UTC ISO), 지났으면 None(바로 공개)."""
    hhmm = (config.YT_SHORTS_TIME or "").strip()
    try:
        h, m = (int(x) for x in hhmm.split(":"))
    except ValueError:
        return None
    kst = dt.timezone(dt.timedelta(hours=9))
    now = dt.datetime.now(kst)
    at = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if at - now < dt.timedelta(minutes=10):
        return None
    return at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _history_meta(p):
    hook = p.get("hook_title", "").strip()
    brand = (p.get("brand") or "").strip()          # 예: "EP.3 · 코닥"
    title = f"{hook} | 그때 그 결정 {brand}".strip()[:100]
    long_id = load_state("history_links", {}).get(p["id"], {}).get("long")
    long_line = (f"▶ 5분 풀버전 보기: https://youtu.be/{long_id}\n\n" if long_id
                 else "▶ 5분 풀버전은 채널의 '그때 그 결정' 재생목록에서 볼 수 있어요.\n\n")
    refs = "\n".join(p.get("links", [])[:3])
    desc = (f"💬 {p.get('question', '')}\n댓글로 여러분 생각을 남겨 주세요!\n\n{long_line}"
            f"{p.get('caption', '')}\n\n" + (f"📚 참고 자료\n{refs}\n\n" if refs else "")
            + "📅 기업의 운명을 바꾼 결정적 순간 — 그때 그 결정\n#Shorts")
    tags = [t.lstrip("#") for t in p.get("hashtags", [])]
    return title, desc, list(dict.fromkeys(tags + ["Shorts", "그때그결정", "기업이야기"]))


def _shorts_meta(p):
    if p.get("series") == "history":
        return _history_meta(p)
    no = _next_news_no()
    hook = p.get("hook_title", "").strip()
    tag = (p.get("tag") or "").strip()
    title = f"[{tag}] {hook}" if tag and not hook.startswith("[") else hook
    title = f"{title} | 오늘의 원픽 #{no:03d}"
    if len(title) > 100:
        title = title[:100]
    tags = [t.lstrip("#") for t in p.get("hashtags", [])]
    links = "\n".join(p.get("links", [])[:3])
    desc = (f"💬 {p.get('question', '')}\n댓글로 여러분 생각을 남겨 주세요!\n\n"
            f"{p.get('caption', '')}\n\n"
            + (f"🔗 원문 기사\n{links}\n\n" if links else "")
            + f"📅 매일 아침 세계 경제 뉴스 딱 하나 — 오늘의 원픽 #{no:03d}\n#Shorts")
    return title, desc, list(dict.fromkeys(tags + ["Shorts", "경제뉴스", "오늘의원픽"]))


def _link_history(rid, **ids):
    """그때 그 결정: 같은 에피소드의 쇼츠·장편 영상 id를 기록 (서로 링크 걸기용)."""
    links = load_state("history_links", {})
    links.setdefault(rid, {}).update(ids)
    save_state("history_links", dict(list(links.items())[-30:]))
    return links[rid]


def _cover(p):
    """유튜브 쇼츠 썸네일 = 인스타 커버와 같은 화면. 못 구하면 None(유튜브 자동 선택)."""
    dest = os.path.join(tempfile.gettempdir(), f"cover_{p['id']}.jpg")
    try:
        got = instagram.cover_frame(_local_video(p), dest)
        if not got and p.get("cover_name") and p.get("release_tag"):
            got = storage.download(p["release_tag"], dest, name=p["cover_name"])
        return got
    except Exception as e:
        print(f"  [유튜브 쇼츠] 썸네일 준비 실패(자동 선택으로 진행): {e}")
        return None


def _upload_short(p):
    """릴스를 유튜브 쇼츠로도 게시. 성공 True."""
    series = p.get("series", "news")
    title, desc, tags = _shorts_meta(p)
    at = _publish_at() if series == "news" else None
    try:
        vid, st = youtube.upload(_local_video(p), title, desc, tags, category="25" if series == "news" else "27",
                                 publish_at=at, privacy=config.env("YT_PRIVACY", "public"), thumb=_cover(p))
    except Exception as e:
        print(f"  [유튜브 쇼츠] 실패: {e}")
        telegram.send_message(f"⚠️ 유튜브 쇼츠 게시 실패 (인스타는 끝났어요)\n{str(e)[:600]}\n\n"
                              "해결한 뒤 " + ("/approve history" if series == "history" else "/approve")
                              + " 를 보내면 유튜브만 다시 올려요.")
        return False
    p["yt_short_id"] = vid
    pending.save(series, p)
    if series == "history":
        meta = {k: p.get(k) for k in ("hook_title", "brand", "question", "caption", "links", "hashtags")}
        _link_history(p["id"], short=vid, short_title=title, short_tags=tags, short_meta=meta)
    when = (f"{config.YT_SHORTS_TIME} 예약 공개" if at else f"상태: {st}")
    tip = ("💡 유튜브 앱에서 이 쇼츠의 '관련 동영상'에 이번 편 장편을 연결해 두면 장편 조회수에 도움이 돼요."
           if series == "history" else
           "💡 유튜브 앱에서 이 쇼츠의 '관련 동영상'에 '그때 그 결정' 영상을 연결해 두면 장편 조회수에 도움이 돼요.")
    telegram.send_message(f"🎉 유튜브 쇼츠 게시 완료! ({when})\nhttps://youtube.com/shorts/{vid}\n\n{tip}")
    return True


def _link_long(p, long_id):
    """장편이 올라가면, 이미 올라간 같은 편 쇼츠 설명에 장편 링크를 넣어 줍니다."""
    rid = p["id"][2:] if p["id"].startswith("yt") else p["id"]
    rec = _link_history(rid, long=long_id)
    if not rec.get("short"):
        return
    try:
        _, desc, _ = _history_meta({"id": rid, "series": "history", **rec.get("short_meta", {})})
        youtube.update_snippet(rec["short"], rec.get("short_title", ""), desc, rec.get("short_tags", []), category="27")
        print("  [유튜브] 쇼츠 설명에 장편 링크 추가")
    except Exception as e:
        print(f"  [유튜브] 쇼츠 설명 수정 실패(무시): {e}")


def _approve_youtube(p):
    """장편을 유튜브에 공개 게시. 성공 True, 실패 False(다시 /approve youtube 가능)."""
    if not youtube.enabled():
        telegram.send_message("ℹ️ 유튜브 연결 정보(YT_…)가 없어서 올리지 못했어요. 직접 올려 주세요.")
        return False
    telegram.send_message("⏫ 유튜브에 올리는 중이에요. 5분 영상이라 3~10분 걸려요.")
    d = tempfile.mkdtemp()
    try:
        vid_path = storage.download(p["release_tag"], os.path.join(d, "long.mp4"), name=p.get("video_name"))
        try:
            th = storage.download(p["release_tag"], os.path.join(d, "thumb.jpg"), name=p.get("thumb_name", "thumbnail.jpg"))
        except Exception:
            th = None
        vid, st = youtube.upload(vid_path, p["yt_title"], p.get("yt_description", ""), p.get("yt_tags", []),
                                 privacy=config.env("YT_PRIVACY", "public"), thumb=th)
        telegram.send_message(f"🎉 유튜브 게시 완료! (상태: {st})\nhttps://youtu.be/{vid}\n\n"
                              "썸네일·자막 처리는 몇 분 더 걸릴 수 있어요.")
        _link_long(p, vid)
        _published(p)
        _clear(p)
        return True
    except Exception as e:
        print(f"  [유튜브] 실패: {e}")
        telegram.send_message(f"⚠️ 유튜브 게시 실패\n{str(e)[:700]}\n\n영상은 보관 중이에요. "
                              "이 메시지를 Claude에게 보여 주거나, 해결 뒤 /approve youtube 를 보내 주세요.")
        return False


def _approve(p):
    """게시 성공(또는 인스타 미연결)이면 True, 실패하면 False(영상 보관, 다시 누를 수 있음)."""
    if p.get("series") == "youtube":
        return _approve_youtube(p)
    series = p.get("series", "news")
    if not p.get("ig_done"):
        if not instagram.enabled():
            telegram.send_message("✅ 승인 확인!\n위 영상을 저장해서 인스타에 직접 올려 주세요. "
                                  "캡션은 초안 메시지의 '■ 캡션' 부분을 복사하면 돼요.")
        else:
            telegram.send_message("⏫ 인스타에 올리는 중이에요. 1~3분 걸려요.")
            try:
                mid, link = instagram.publish_reel(_local_video(p), p["caption"])
                telegram.send_message(f"🎉 인스타 게시 완료!\n{link or mid}")
            except Exception as e:
                print(f"  [인스타] 실패: {e}")
                telegram.send_message(f"⚠️ 인스타 게시 실패\n{str(e)[:700]}\n\n영상은 그대로 보관 중이에요. "
                                      "이 메시지를 Claude에게 보여주고, 해결한 뒤 승인 버튼을 다시 눌러 주세요.")
                return False
        p["ig_done"] = True
        pending.save(series, p)
    if series in ("news", "history") and youtube.enabled() and not p.get("yt_short_id"):
        telegram.send_message("⏫ 유튜브 쇼츠로도 올리는 중이에요.")
        if not _upload_short(p):
            return False
    _published(p)
    _clear(p)
    return True


def handle(updates):
    """반환: (다시 만들 시리즈 또는 None, 처리가 끝난 영상 id 집합)"""
    redo, finished = None, set()
    for u in updates:
        if "callback_query" in u:
            cq = u["callback_query"]
            if not _owner(cq["from"]["id"]):
                continue
            action, _, rid = cq.get("data", "").partition(":")
            p = pending.find(rid)
            print(f"  [텔레그램] 버튼 {action} ({rid}) → {'대기 영상' if p else '만료'}")
            if not p:
                telegram.answer_callback(cq["id"], "만료된 영상이에요")
                telegram.send_message("ℹ️ 이미 처리됐거나 이전 영상의 버튼이라 처리하지 않았어요. "
                                      "/status 로 대기 중인 영상을 확인하세요.")
                continue
            if action == "approve":
                telegram.answer_callback(cq["id"], "게시를 시작합니다")
                if _approve(p):
                    finished.add(rid)
            elif action == "reject":
                telegram.answer_callback(cq["id"], "폐기했어요")
                telegram.send_message("❌ 유튜브에는 올리지 않을게요. 영상 원본은 다운로드 링크로 계속 받을 수 있어요."
                                      if p.get("series") == "youtube" else
                                      "❌ 폐기했어요. 새로 만들려면 /new 또는 /history 를 보내 주세요.")
                _clear(p)
                finished.add(rid)
            elif action == "redo":
                telegram.answer_callback(cq["id"], "다시 만들게요")
                telegram.send_message(f"🔁 [{pending.LABEL[p.get('series', 'news')]}] 다시 만드는 중이에요. "
                                      "5~15분 뒤 도착합니다.")
                _clear(p)
                finished.add(rid)
                redo = p.get("series", "news")
        elif "message" in u:
            m = u["message"]
            if not _owner(m.get("chat", {}).get("id")):
                continue
            text = (m.get("text") or "").strip().lower()
            print(f"  [텔레그램] 메시지 {text[:20]}")
            series = "history" if text.startswith(("/history", "/그때")) else "news" if text.startswith("/new") else None
            if series:
                old = pending.load(series)
                if old:
                    _clear(old)
                    finished.add(old["id"])
                telegram.send_message(f"🔁 [{pending.LABEL[series]}] 새로 만드는 중이에요. 5~15분 뒤 도착합니다.")
                redo = series
            elif text.startswith(("/approve", "/승인")):
                which = ("youtube" if ("youtube" in text or "유튜브" in text) else
                         "history" if ("history" in text or "그때" in text) else "news")
                p = pending.load(which)
                if not p:
                    telegram.send_message(f"ℹ️ 승인 대기 중인 [{pending.LABEL[which]}] 영상이 없어요.")
                elif _approve(p):
                    finished.add(p["id"])
            elif text.startswith("/status"):
                items = pending.all_items()
                telegram.send_message("\n".join(f"⏳ [{pending.LABEL[p.get('series', 'news')]}] {p['hook_title']}"
                                                for p in items) if items else "대기 중인 영상이 없어요.")
            elif text.startswith("/help") or text.startswith("/start"):
                telegram.send_message(HELP)
        if redo:
            break
    return redo, finished


def _fetch(timeout=0):
    off = load_state("telegram_offset", {}).get("offset")
    try:
        ups = telegram.get_updates(off, timeout=timeout)
    except Exception as e:   # 다른 작업이 동시에 확인 중이면 409 등 → 이번 차례는 건너뜀
        print(f"  [텔레그램] 업데이트 확인 실패(무시): {e}")
        time.sleep(5)
        return []
    if ups:
        save_state("telegram_offset", {"offset": ups[-1]["update_id"] + 1})
    return ups


def wait_for_decision(rid, minutes):
    """영상 전송 직후 실시간 대기. 반환: ('redo', 시리즈) | ('done', None) | ('timeout', None)"""
    p = pending.find(rid)
    if not p:
        return "done", None
    until = _now() + dt.timedelta(minutes=minutes)
    wait_ids = {rid} | ({f"yt{rid}"} if pending.find(f"yt{rid}") else set())   # 장편 유튜브 버튼도 함께 기다림
    for q in (pending.find(i) for i in wait_ids):
        q["waiting_until"] = until.isoformat()
        pending.save(q["series"], q)
    git_push_state("state: waiting")      # 30분 점검 작업이 끼어들지 않게 표시
    print(f"  [대기] {minutes}분 동안 버튼 대기")
    result = ("timeout", None)
    while _now() < until:
        left = (until - _now()).total_seconds()
        redo, finished = handle(_fetch(timeout=int(max(1, min(50, left)))))
        if redo:
            result = ("redo", redo)
            break
        wait_ids -= finished
        if not wait_ids:
            result = ("done", None)
            break
    for q in pending.all_items():
        if q.pop("waiting_until", None):
            pending.save(q["series"], q)
    print(f"  [대기] 끝: {result}")
    return result


def main():
    if not telegram.enabled():
        print("텔레그램 설정 없음")
        return
    redo = None
    waiting = [p for p in pending.all_items() if p.get("waiting_until")
               and dt.datetime.fromisoformat(p["waiting_until"]) > _now()]
    if waiting:
        print("영상 작업이 실시간 대기 중이라 이번 점검은 건너뜁니다.")
    else:
        redo, _ = handle(_fetch(timeout=0))
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"redo={'true' if redo else 'false'}\nseries={redo or 'news'}\n")
    print("redo =", redo)


if __name__ == "__main__":
    main()
