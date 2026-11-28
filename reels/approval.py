"""텔레그램 버튼/명령 처리.

1) 대기 모드: 영상을 보낸 작업이 그대로 일정 시간 텔레그램을 실시간 확인 → 버튼을 누르면 바로 처리
2) 점검 모드(python -m reels.approval): 대기 시간이 끝난 뒤 누른 버튼이나 명령을 30분마다 처리

- ✅ 승인: 인스타 게시   - 🔁 다시: 같은 시리즈로 새로 만들기   - ❌ 폐기
- 명령어: /new(오늘의 경제), /history(그때 그 결정), /status, /help
"""
import datetime as dt
import re
import os
import tempfile
import time

from . import config, instagram, pending, script, storage, telegram, youtube
from .utils import git_push_state, load_state, save_state

HELP = ("명령어\n/us - 미국 증시 마감 브리핑 새로 만들기\n/re - 주간 부동산 새로 만들기\n/term - 1분 경제 용어 새로 만들기\n/new - 오늘의 원픽 새로 만들기\n/kr - 국내 증시 마감 브리핑 새로 만들기\n/history - '그때 그 결정' 새 에피소드 만들기\n"
        "/status - 승인 대기 중인 영상 보기\n/approve - 대기 중인 오늘의 원픽 영상 게시 (버튼이 없을 때)\n"
        "/approve us - 대기 중인 미국 증시 마감 게시\n/approve re - 대기 중인 주간 부동산 게시\n/approve term - 대기 중인 1분 경제 용어 게시\n/approve kr - 대기 중인 국내 증시 마감 게시\n/approve history - 대기 중인 '그때 그 결정' 릴스 게시\n/approve youtube - 대기 중인 유튜브 장편 게시\n/help - 도움말\n\n"
        "버튼은 보통 1분 안에 처리돼요. (대기 영상이 남아 있는 동안 계속 확인해요)")


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
    key = {"news": "news_ep", "kr": "kr_ep", "us": "us_ep", "re": "re_ep", "term": "term_ep"}.get(series)   # 그때 그 결정은 회차 번호를 세지 않음
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


def _next_news_no(series="news"):
    key = {"kr": "kr_ep", "us": "us_ep", "re": "re_ep", "term": "term_ep"}.get(series, "news_ep")
    return load_state(key, {"published": 0}).get("published", 0) + 1


def _local_video(p):
    path = p.get("video")
    if not path or not os.path.exists(path):
        path = os.path.join(tempfile.gettempdir(), f"reel_{p['id']}.mp4")
        if not os.path.exists(path):
            storage.download(p["release_tag"], path)
    return path


def _publish_at(series="news", slot=None):
    """고정 공개 시각(한국시간)이 아직 안 지났으면 그 시각(UTC ISO), 지났으면 None(바로 공개).
    slot: 영상마다 정한 시각(주말 12:00 그때 그 결정 등). 없으면 시리즈 기본값(config.YT_SLOTS)."""
    hhmm = (slot or config.YT_SLOTS.get(series) or "").strip()
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


def _subscribe_line():
    h = (config.CHANNEL_HANDLE or "").strip()
    if not h:
        return ""
    return f"🔔 구독: https://www.youtube.com/{h if h.startswith('@') else '@' + h}\n"


def _history_meta(p):
    hook = p.get("hook_title", "").strip()
    brand = (p.get("brand") or "").strip()          # 예: "코닥"
    # 2026-11-21 채널 진단: 라벨형 제목 → 말하듯 쓴 제목 + 해시태그 3개. 시리즈 이름은 설명란으로
    title = script.youtube_title(p, f"{hook} {brand}".strip(), extra_tags=("#그때그결정",))
    long_id = load_state("history_links", {}).get(p["id"], {}).get("long")
    long_line = (f"▶ 5분 풀버전 보기: https://youtu.be/{long_id}\n\n" if long_id
                 else "▶ 5분 풀버전은 채널의 '그때 그 결정' 재생목록에서 볼 수 있어요.\n\n" if config.HISTORY_LONG
                 else "")
    refs = "\n".join(p.get("links", [])[:3])
    desc = (f"💬 {p.get('question', '')}\n댓글로 여러분 생각을 남겨 주세요!\n\n{long_line}"
            f"{p.get('caption', '')}\n\n" + (f"📚 참고 자료\n{refs}\n\n" if refs else "")
            + f"📅 기업의 운명을 바꾼 결정적 순간 — 그때 그 결정 {brand}\n{_subscribe_line()}#Shorts")
    tags = [t.lstrip("#") for t in p.get("hashtags", [])]
    return title, desc, list(dict.fromkeys(tags + ["Shorts", "그때그결정", "기업이야기"]))


def _shorts_meta(p):
    if p.get("series") == "history":
        return _history_meta(p)
    series = p.get("series", "news")
    no = _next_news_no(series)
    name = {"kr": "국내 증시 마감", "us": "미국 증시 마감", "re": "주간 부동산", "term": "1분 경제 용어"}.get(series, "오늘의 원픽")
    # 2026-11-21 채널 진단: [증시] 같은 분류 꼬리표·회차 번호로 시작하는 제목 → 말하듯 쓴 제목 + 해시태그 3개
    title = script.youtube_title(p, p.get("hook_title", ""), extra_tags={
        "kr": ("#국내주식", "#코스피"), "us": ("#미국주식", "#미국증시"), "re": ("#부동산", "#아파트"),
        "term": ("#경제용어", "#주식공부")}.get(series, ("#경제뉴스",)))
    tags = [t.lstrip("#") for t in p.get("hashtags", []) + p.get("title_tags", [])]
    links = "\n".join(p.get("links", [])[:3])
    slogan = {"kr": "매일 오후 5시 국내 증시 마감 정리", "us": "매일 아침 7시 미국 증시 마감 정리",
              "re": "매주 토요일 낮 12시 부동산 정책·시세 정리", "term": "매일 밤 9시 경제 용어 하나"}.get(
        series, "매일 낮 12시 오늘의 경제 이슈 딱 하나")
    desc = (f"💬 {p.get('question', '')}\n댓글로 여러분 생각을 남겨 주세요!\n\n"
            f"{p.get('caption', '')}\n\n"
            + (f"🔗 원문 기사\n{links}\n\n" if links else "")
            + f"📅 {slogan} — {name} #{no:03d}\n{_subscribe_line()}#Shorts")
    extra = {"kr": ["Shorts", "경제뉴스", "국내주식", "코스피", "증시마감"],
             "us": ["Shorts", "경제뉴스", "미국주식", "미국증시", "나스닥"],
             "re": ["Shorts", "부동산", "아파트", "재건축", "청약", "부동산뉴스"],
             "term": ["Shorts", "경제용어", "경제공부", "주식공부", "재테크기초"]}.get(series, ["Shorts", "경제뉴스", "오늘의원픽"])
    return title, desc, list(dict.fromkeys(tags + extra))


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


def _channel_caption(p, vid=None):
    """채널 게시글: 제목 + 요약 + 질문 + 유튜브 링크 + 투자 권유 아님 안내."""
    title = script.clean_yt_title(p.get("yt_title")) or script.clean_yt_title(p.get("hook_title", ""))
    body = re.split(r"\n\n(?:📰|📚|🎞|🤖)", p.get("caption", "") or "")[0].strip()
    lines = [f"📌 {title}", "", body] if body else [f"📌 {title}"]
    if p.get("question"):
        lines += ["", f"💬 {p['question']}"]
    if vid:
        lines += ["", f"▶ 유튜브로 보기: https://youtube.com/shorts/{vid}"]
    if config.CHANNEL_HANDLE:
        h = config.CHANNEL_HANDLE if config.CHANNEL_HANDLE.startswith("@") else "@" + config.CHANNEL_HANDLE
        lines.append(f"🔔 구독: https://www.youtube.com/{h}")
    lines += ["", "ℹ️ 투자 권유가 아닌 경제 뉴스 브리핑입니다."]
    return "\n".join(lines)


def _queue_channel(p, vid=None, at=None):
    """채널 게시 예약: 유튜브 공개 시각(at, UTC ISO)이 되면 flush_channel이 올림. 채널 미설정이면 건너뜀."""
    if not telegram.channel_id() or not p.get("tg_message_id"):
        return
    q = load_state("channel_queue", [])
    if any(x.get("id") == p["id"] for x in q):
        return
    q.append({"id": p["id"], "due": at or _now().isoformat(timespec="seconds"), "msg": p["tg_message_id"],
              "caption": _channel_caption(p, vid)})
    save_state("channel_queue", q[-20:])
    print(f"  [채널] 게시 예약: {at or '바로'}")


def flush_channel():
    """시각이 된 채널 게시를 올림. 텔레그램을 확인할 때마다 불려서, 공개 시각 뒤 최대 몇십 분 안에 올라감."""
    q = load_state("channel_queue", [])
    if not q or not telegram.channel_id():
        return
    now, left, posted = _now(), [], 0
    for x in q:
        try:
            due = dt.datetime.fromisoformat(x["due"].replace("Z", "+00:00"))
        except Exception:
            due = now
        if due > now:
            left.append(x)
            continue
        try:
            try:
                telegram.copy_to_channel(x["msg"], x["caption"])
            except Exception as e:   # 영상 메시지를 못 찾으면 글만이라도
                print(f"  [채널] 영상 복사 실패 → 글만 게시: {e}")
                telegram.send_channel_message(x["caption"])
            posted += 1
        except Exception as e:
            print(f"  [채널] 게시 실패(다음 확인 때 다시): {e}")
            if (now - due).total_seconds() < 12 * 3600:
                left.append(x)
    if posted or len(left) != len(q):
        save_state("channel_queue", left)
        print(f"  [채널] {posted}건 게시")


def _on_channel_admin(m):
    """봇이 채널 관리자로 추가되면(사장님이 추가한 경우만) 채널 주소를 기록."""
    chat, new = m.get("chat", {}), (m.get("new_chat_member") or {}).get("status")
    if chat.get("type") != "channel" or not _owner(m.get("from", {}).get("id")):
        return
    if new in ("administrator", "creator"):
        save_state("telegram_channel", {"id": chat["id"], "title": chat.get("title", ""),
                                        "username": chat.get("username", "")})
        telegram.send_message(f"📣 채널 연결 완료: {chat.get('title', '')}"
                              + (f" (@{chat['username']})" if chat.get("username") else "")
                              + "\n앞으로 승인한 영상은 유튜브 공개 시각에 이 채널에도 올라가요.")
    elif new in ("left", "kicked") and str(load_state("telegram_channel", {}).get("id")) == str(chat.get("id")):
        save_state("telegram_channel", {})
        telegram.send_message("📣 채널에서 봇이 빠져서 채널 자동 게시를 멈췄어요.")


def _upload_short(p):
    """릴스를 유튜브 쇼츠로도 게시. 성공 True."""
    series = p.get("series", "news")
    title, desc, tags = _shorts_meta(p)
    at = _publish_at(series, p.get("slot"))
    try:
        vid, st = youtube.upload(_local_video(p), title, desc, tags, category="27" if series == "history" else "25",
                                 publish_at=at, privacy=config.env("YT_PRIVACY", "public"), thumb=_cover(p))
    except Exception as e:
        print(f"  [유튜브 쇼츠] 실패: {e}")
        telegram.send_message(f"⚠️ 유튜브 쇼츠 게시 실패 (인스타는 끝났어요)\n{str(e)[:600]}\n\n"
                              "해결한 뒤 " + {"history": "/approve history", "kr": "/approve kr", "us": "/approve us", "re": "/approve re", "term": "/approve term"}.get(series, "/approve")
                              + " 를 보내면 유튜브만 다시 올려요.")
        return False
    p["yt_short_id"] = vid
    pending.save(series, p)
    if series == "history":
        meta = {k: p.get(k) for k in ("hook_title", "brand", "question", "caption", "links", "hashtags",
                                       "yt_title", "title_tags")}
        _link_history(p["id"], short=vid, short_title=title, short_tags=tags, short_meta=meta)
    when = (f"{p.get('slot') or config.YT_SLOTS.get(series)} 예약 공개" if at else f"상태: {st}")
    _queue_channel(p, vid, at)
    if series == "history" and config.HISTORY_LONG:
        tip = "💡 유튜브 앱에서 이 쇼츠의 '관련 동영상'에 이번 편 장편을 연결해 두면 장편 조회수에 도움이 돼요."
    else:
        tip = "💡 유튜브 앱에서 이 쇼츠를 시리즈 재생목록에 넣고, 고정 댓글로 '내일 다뤘으면 하는 종목'을 물어보세요."
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
        at = _publish_at("youtube", p["slot"]) if p.get("slot") else None   # 이슈 뒷담화: 일요일 20:00 예약 공개
        vid, st = youtube.upload(vid_path, p["yt_title"], p.get("yt_description", ""), p.get("yt_tags", []),
                                 privacy=config.env("YT_PRIVACY", "public"), thumb=th, publish_at=at)
        if at:
            st = f"{p['slot']} 예약 공개"
        pl_note = ""
        if p.get("playlist"):   # 이슈 뒷담화 등: 채널의 같은 이름 재생목록에 자동 추가
            pl_note = (f"\n📂 재생목록 '{p['playlist']}'에 추가했어요." if youtube.add_to_playlist(vid, p["playlist"])
                       else f"\n⚠️ 재생목록 '{p['playlist']}'에 넣지 못했어요. 앱에서 직접 넣어 주세요.")
        telegram.send_message(f"🎉 유튜브 게시 완료! (상태: {st})\nhttps://youtu.be/{vid}\n\n"
                              "썸네일·자막 처리는 몇 분 더 걸릴 수 있어요." + pl_note)
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
    if series in ("news", "kr", "us", "re", "term", "history") and not youtube.enabled():
        _queue_channel(p)   # 유튜브 연결이 없으면 채널에는 바로 (링크 없이)
    if series in ("news", "kr", "us", "re", "term", "history") and youtube.enabled() and not p.get("yt_short_id"):
        telegram.send_message("⏫ 유튜브 쇼츠로도 올리는 중이에요.")
        if not _upload_short(p):
            return False
    _published(p)
    _clear(p)
    return True


def _sent_before(msg, p):
    """텔레그램 메시지가 대기 영상이 텔레그램에 도착하기 전에 보낸 것인지."""
    try:
        sent = dt.datetime.fromisoformat(p.get("sent_at") or p.get("created_at") or "")
        if sent.tzinfo is None:
            sent = sent.replace(tzinfo=dt.timezone.utc)
        return dt.datetime.fromtimestamp(int(msg.get("date", 0)), dt.timezone.utc) < sent
    except Exception:
        return False


def handle(updates):
    """반환: (다시 만들 시리즈 또는 None, 처리가 끝난 영상 id 집합)"""
    redo, finished = None, set()
    for u in updates:
        if "my_chat_member" in u:
            _on_channel_admin(u["my_chat_member"])
            continue
        if "callback_query" in u:
            cq = u["callback_query"]
            if not _owner(cq["from"]["id"]):
                continue
            action, _, rid = cq.get("data", "").partition(":")
            if action == "topic":   # 제작 작업이 아닌 점검 작업이 받은 주제 버튼 → 기록해 두면 제작 작업이 읽어 감
                token, _, idx = rid.partition(":")
                save_state("topic_choice", {"token": token, "index": int(idx or 0)})
                git_push_state("state: topic choice")
                telegram.answer_callback(cq["id"], "선택했어요")
                continue
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
                                      "❌ 폐기했어요. 새로 만들려면 /us, /new, /kr 또는 /history 를 보내 주세요.")
                _clear(p)
                finished.add(rid)
            elif action == "redo":
                telegram.answer_callback(cq["id"], "다시 만들게요")
                telegram.send_message(f"🔁 [{pending.LABEL[p.get('series', 'news')]}] 다시 만드는 중이에요. "
                                      + ("20~40분 뒤 도착합니다." if p.get("series") in ("youtube", "history")
                                         else "5~15분 뒤 도착합니다."))
                _clear(p)
                finished.add(rid)
                redo = "history" if p.get("series") == "youtube" else p.get("series", "news")
        elif "message" in u:
            m = u["message"]
            if not _owner(m.get("chat", {}).get("id")):
                continue
            text = (m.get("text") or "").strip().lower()
            print(f"  [텔레그램] 메시지 {text[:20]}")
            series = ("history" if text.startswith(("/history", "/그때")) else "kr" if text.startswith(("/kr", "/국내"))
                      else "us" if text.startswith(("/us", "/미국")) else "re" if text.startswith(("/re", "/부동산"))
                      else "term" if text.startswith(("/term", "/용어"))
                      else "news" if text.startswith("/new") else None)
            if series:
                old = pending.load(series)
                if old and _sent_before(m, old):
                    # 11/21: 첫 제작 실패 뒤 보낸 /new가 늦게 처리돼, 그사이 도착한 새 영상을 버리고 다시 만들다 실패
                    print(f"  [텔레그램] {text[:10]}는 대기 영상보다 먼저 보낸 명령이라 무시")
                    telegram.send_message(f"ℹ️ 보내신 {text.split()[0]} 명령보다 새 [{pending.LABEL[series]}] 영상이 "
                                          "나중에 도착해서, 그 영상을 그대로 두었어요. 위 영상의 버튼을 눌러 주세요. "
                                          f"정말 새로 만들려면 {text.split()[0]} 를 한 번 더 보내 주세요.")
                    continue
                if old:
                    _clear(old)
                    finished.add(old["id"])
                telegram.send_message(f"🔁 [{pending.LABEL[series]}] 새로 만드는 중이에요. 5~15분 뒤 도착합니다.")
                redo = series
            elif text.startswith(("/approve", "/승인")):
                which = ("youtube" if ("youtube" in text or "유튜브" in text) else
                         "history" if ("history" in text or "그때" in text) else
                         "kr" if (" kr" in text or "국내" in text) else
                         "us" if (" us" in text or "미국" in text) else
                         "re" if (" re" in text or "부동산" in text) else
                         "term" if (" term" in text or "용어" in text) else "news")
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
    try:
        flush_channel()
    except Exception as e:
        print(f"  [채널] 확인 실패(무시): {e}")
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
    p = pending.find(rid) or pending.find(f"yt{rid}")
    if not p:
        return "done", None
    until = _now() + dt.timedelta(minutes=minutes)
    wait_ids = ({rid} if pending.find(rid) else set()) | ({f"yt{rid}"} if pending.find(f"yt{rid}") else set())   # 장편 유튜브 버튼도 함께 기다림
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


def direct_approve(which):
    """텔레그램 버튼을 못 받을 때(텔레그램 장애 등) 대기 중인 영상을 바로 게시. which: history,youtube,news 쉼표 구분.
    텔레그램 알림은 보내 보되 실패해도 게시는 계속."""
    for name in ("send_message", "send_photo", "send_video", "send_document"):
        f = getattr(telegram, name)
        def safe(*a, _f=f, _n=name, **k):
            try:
                return _f(*a, **k)
            except Exception as e:
                print(f"  [텔레그램] {_n} 실패(무시): {e}")
        setattr(telegram, name, safe)
    for w in [x.strip() for x in which.split(",") if x.strip()]:
        p = pending.load(w)
        if not p:
            print(f"  [직접 승인] {w}: 대기 중인 영상 없음")
            continue
        print(f"  [직접 승인] {w}: {p.get('hook_title')} ({p['id']})")
        ok = _approve(p)
        print(f"  [직접 승인] {w}: {'완료' if ok else '실패'}")


def _sync():
    """GitHub Actions 안에서만: 다른 작업이 올린 최신 상태(새 대기 영상 등)를 받아옴."""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    import subprocess
    git_push_state("state: approval watch")   # 바뀐 게 있으면 먼저 올림(작업 트리를 깨끗하게)
    if subprocess.run(["git", "pull", "-q", "--rebase"], cwd=config.ROOT).returncode != 0:
        subprocess.run(["git", "rebase", "--abort"], cwd=config.ROOT)


def _other_waiting():
    tw = load_state("topic_wait", {}).get("until")
    if tw and dt.datetime.fromisoformat(tw) > _now():   # 제작 작업이 주제 선택을 기다리는 중
        return True
    return any(p.get("waiting_until") and dt.datetime.fromisoformat(p["waiting_until"]) > _now()
               for p in pending.all_items())


NUM = ["1️⃣", "2️⃣", "3️⃣"]


def ask_topic(label, options, minutes):
    """제작 전 주제 고르기 (2026-11-28 사용자 결정). options: [{"title", "detail"}] 2~3개.
    텔레그램 버튼으로 고르면 그 번호, 시간 안에 안 고르면 0(1순위). 텔레그램이 없거나 후보가 1개면 바로 0."""
    if not telegram.enabled() or len(options) < 2 or minutes <= 0:
        return 0
    token = _now().strftime("%m%d%H%M%S")
    body = "\n\n".join(f"{NUM[i]} {o['title']}" + (f"\n   {o['detail']}" if o.get("detail") else "")
                         for i, o in enumerate(options[:3]))
    try:
        mid = telegram.send_message(f"🗳 [{label}] 오늘 주제를 골라 주세요\n\n{body}\n\n"
                                    f"⏱ {minutes}분 안에 안 고르시면 1번으로 만들어요.",
                                    buttons=[(f"{NUM[i]} 이걸로", f"topic:{token}:{i}") for i in range(len(options[:3]))])
    except Exception as e:
        print(f"  [주제 고르기] 전송 실패 → 1순위로 진행: {e}")
        return 0
    until = _now() + dt.timedelta(minutes=minutes)
    save_state("topic_wait", {"until": until.isoformat(), "token": token})
    git_push_state("state: topic wait")      # 30분 점검 작업이 버튼을 가로채지 않게
    choice, how = None, "시간 초과"
    try:
        while _now() < until and choice is None:
            left = (until - _now()).total_seconds()
            ups = _fetch(timeout=int(max(1, min(30, left))))
            rest = []
            for u in ups:
                d = (u.get("callback_query") or {}).get("data", "")
                if d.startswith(f"topic:{token}:") and _owner(u["callback_query"]["from"]["id"]):
                    choice, how = int(d.rsplit(":", 1)[1]), "선택"
                    telegram.answer_callback(u["callback_query"]["id"], f"{choice + 1}번으로 만들게요")
                elif not d.startswith("topic:"):
                    rest.append(u)
            if rest:   # 기다리는 동안 들어온 다른 버튼·명령(승인 등)도 처리
                handle(rest)
            if choice is None:
                _sync()
                saved = load_state("topic_choice", {})
                if saved.get("token") == token:
                    choice, how = int(saved["index"]), "선택"
    finally:
        save_state("topic_wait", {})
    choice = choice if choice is not None and 0 <= choice < len(options) else 0
    telegram.remove_buttons(mid)
    telegram.send_message(f"✅ [{label}] {NUM[choice]} {options[choice]['title']}\n"
                          + ("이 주제로 만들어요. 10~15분 뒤 초안이 와요." if how == "선택"
                             else "시간 안에 고르지 않아서 1순위 주제로 만들어요. 10~15분 뒤 초안이 와요."))
    print(f"  [주제 고르기] {how}: {choice + 1}번 {options[choice]['title']}")
    return choice


def _open_items(hours=48):
    """아직 버튼을 안 누른 대기 영상 (너무 오래된 건 제외)."""
    out = []
    for p in pending.all_items():
        try:
            t = dt.datetime.fromisoformat(p.get("created_at", ""))
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
        except Exception:
            t = _now()
        if _now() - t < dt.timedelta(hours=hours):
            out.append(p)
    return out


def watch(minutes):
    """대기 영상이 남아 있는 동안 텔레그램을 실시간 확인 (예약 점검이 몇 시간씩 빠져도 버튼이 바로 처리되게).
    다른 작업이 실시간 대기를 시작하면 버튼을 가로채지 않도록 바로 물러남. 반환: 다시 만들 시리즈 또는 None"""
    until = _now() + dt.timedelta(minutes=minutes)
    print(f"  [감시] 대기 영상 {len(_open_items())}개 → 최대 {minutes}분 동안 버튼 확인")
    while _now() < until:
        _sync()
        if _other_waiting():
            print("  [감시] 다른 작업이 실시간 대기를 시작해서 넘겨줌")
            return None
        if not _open_items():
            print("  [감시] 대기 영상이 모두 처리됨")
            return None
        redo, _ = handle(_fetch(timeout=50))
        if redo:
            return redo
    print("  [감시] 시간 끝 (남은 영상은 다음 점검이 이어서 확인)")
    return None


def need_watch():
    """워크플로 마지막 단계용: 버튼을 기다리는 영상이 남았고 실시간 대기 중인 작업이 없으면 0(이어서 감시 필요)."""
    return 0 if (_open_items() and not _other_waiting()) else 1


def main():
    direct = os.environ.get("APPROVE_DIRECT", "").strip()
    if direct:
        direct_approve(direct)
        return
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
        mins = int(os.environ.get("APPROVAL_WATCH_MIN", "0") or 0)
        if not redo and mins > 0 and _open_items():
            redo = watch(mins)
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"redo={'true' if redo else 'false'}\nseries={redo or 'news'}\n")
    print("redo =", redo)


if __name__ == "__main__":
    import sys
    if "--need-watch" in sys.argv:
        sys.exit(need_watch())
    main()
