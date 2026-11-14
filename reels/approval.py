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

from . import config, instagram, pending, storage, telegram
from .utils import git_push_state, load_state, save_state

HELP = ("명령어\n/new - 오늘의 경제 새로 만들기\n/history - '그때 그 결정' 새 에피소드 만들기\n"
        "/status - 승인 대기 중인 영상 보기\n/approve - 대기 중인 오늘의 경제 영상 게시 (버튼이 없을 때)\n"
        "/approve history - 대기 중인 '그때 그 결정' 릴스 게시\n/help - 도움말\n\n"
        "영상이 온 뒤 2시간 안에 누른 버튼은 바로 처리되고, 그 뒤에는 최대 30분 안에 처리돼요.")


def _owner(uid):
    return str(uid) == str(config.TELEGRAM_CHAT_ID)


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _clear(p, keep_file=False):
    if p.get("tg_message_id"):
        telegram.remove_buttons(p["tg_message_id"])
    if not keep_file and p.get("release_tag") and storage.enabled():
        storage.delete(p["release_tag"])
    pending.save(p.get("series", "news"), None)


def _published(p):
    if p.get("series") == "history":
        c = load_state("history_ep", {"published": 0})
        c["published"] = c.get("published", 0) + 1
        save_state("history_ep", c)


def _approve(p):
    """게시 성공(또는 인스타 미연결)이면 True, 실패하면 False(영상 보관, 다시 누를 수 있음)."""
    if not instagram.enabled():
        telegram.send_message("✅ 승인 확인!\n위 영상을 저장해서 인스타에 직접 올려 주세요. "
                              "캡션은 초안 메시지의 '■ 캡션' 부분을 복사하면 돼요.")
        _published(p)
        _clear(p)
        return True
    telegram.send_message("⏫ 인스타에 올리는 중이에요. 1~3분 걸려요.")
    path = p.get("video")
    if not path or not os.path.exists(path):
        path = os.path.join(tempfile.gettempdir(), f"reel_{p['id']}.mp4")
        storage.download(p["release_tag"], path)
    try:
        mid, link = instagram.publish_reel(path, p["caption"])
        telegram.send_message(f"🎉 인스타 게시 완료!\n{link or mid}")
        _published(p)
        _clear(p)
        return True
    except Exception as e:
        print(f"  [인스타] 실패: {e}")
        telegram.send_message(f"⚠️ 인스타 게시 실패\n{str(e)[:700]}\n\n영상은 그대로 보관 중이에요. "
                              "이 메시지를 Claude에게 보여주고, 해결한 뒤 승인 버튼을 다시 눌러 주세요.")
        return False


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
                telegram.send_message("❌ 폐기했어요. 새로 만들려면 /new 또는 /history 를 보내 주세요.")
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
                which = "history" if ("history" in text or "그때" in text) else "news"
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
    p["waiting_until"] = until.isoformat()
    pending.save(p["series"], p)
    git_push_state("state: waiting")      # 30분 점검 작업이 끼어들지 않게 표시
    print(f"  [대기] {minutes}분 동안 버튼 대기")
    result = ("timeout", None)
    while _now() < until:
        left = (until - _now()).total_seconds()
        redo, finished = handle(_fetch(timeout=int(max(1, min(50, left)))))
        if redo:
            result = ("redo", redo)
            break
        if rid in finished:
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
