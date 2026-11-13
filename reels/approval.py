"""텔레그램 버튼/명령 처리.

두 가지 방식으로 쓰입니다.
1) 대기 모드: 영상을 보낸 작업이 그대로 2시간 동안 텔레그램을 실시간으로 확인 → 버튼을 누르면 바로 처리
2) 점검 모드(python -m reels.approval): 대기 시간이 끝난 뒤 누른 버튼이나 /new 를 30분마다 처리

- ✅ 승인: 인스타 게시 (인스타 미연결이면 안내만)
- 🔁 다시: 다른 뉴스로 새로 만들기
- ❌ 폐기
- 명령어: /new(새로 만들기), /status(상태), /help
"""
import datetime as dt
import os
import tempfile
import time

from . import config, instagram, storage, telegram
from .utils import git_push_state, load_state, save_state

HELP = ("명령어\n/new - 다른 뉴스로 새로 만들기\n/status - 승인 대기 상태 보기\n/help - 도움말\n\n"
        "영상이 온 뒤 2시간 안에 누른 버튼은 바로 처리되고, 그 뒤에는 최대 30분 안에 처리돼요.")


def _owner(uid):
    return str(uid) == str(config.TELEGRAM_CHAT_ID)


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _clear(pending, keep_file=False):
    if pending.get("tg_message_id"):
        telegram.remove_buttons(pending["tg_message_id"])
    if not keep_file and pending.get("release_tag") and storage.enabled():
        storage.delete(pending["release_tag"])
    save_state("pending", None)


def _approve(pending):
    """게시에 성공하거나 인스타 미연결이면 True(처리 끝), 실패하면 False(영상 보관, 다시 시도 가능)."""
    if not instagram.enabled():
        telegram.send_message("✅ 승인 확인!\n아직 인스타그램이 연결되지 않아 자동 게시는 건너뛰었어요.\n"
                              "GitHub Secrets에 IG_USER_ID와 IG_ACCESS_TOKEN을 등록하면 다음부터 자동으로 게시됩니다.")
        _clear(pending)
        return True
    telegram.send_message("⏫ 인스타에 올리는 중이에요. 1~3분 걸려요.")
    path = pending.get("video")
    if not path or not os.path.exists(path):
        path = os.path.join(tempfile.gettempdir(), "reel.mp4")
        storage.download(pending["release_tag"], path)
    try:
        mid, link = instagram.publish_reel(path, pending["caption"])
        telegram.send_message(f"🎉 인스타 게시 완료!\n{link or mid}")
        _clear(pending)
        return True
    except Exception as e:
        print(f"  [인스타] 실패: {e}")
        telegram.send_message(f"⚠️ 인스타 게시 실패\n{str(e)[:700]}\n\n영상은 그대로 보관 중이에요. "
                              "이 메시지를 Claude에게 보여주고, 해결한 뒤 승인 버튼을 다시 눌러 주세요.")
        return False


def handle(updates):
    """업데이트 목록 처리. 반환: (redo 필요 여부, 대기 중 영상 처리가 끝났는지)"""
    redo, finished = False, False
    for u in updates:
        pending = load_state("pending", None)
        if "callback_query" in u:
            cq = u["callback_query"]
            if not _owner(cq["from"]["id"]):
                continue
            action, _, rid = cq.get("data", "").partition(":")
            print(f"  [텔레그램] 버튼 {action} ({rid}), 대기 영상: {pending.get('id') if pending else '없음'}")
            if not pending or pending.get("id") != rid:
                telegram.answer_callback(cq["id"], "만료된 영상이에요")
                telegram.send_message("ℹ️ 이 버튼은 이전 영상의 버튼이라 처리하지 않았어요. "
                                      "가장 최근에 온 영상의 버튼을 눌러 주세요. (/status 로 확인)")
                continue
            if action == "approve":
                telegram.answer_callback(cq["id"], "게시를 시작합니다")
                finished = _approve(pending) or finished
            elif action == "reject":
                telegram.answer_callback(cq["id"], "폐기했어요")
                telegram.send_message("❌ 폐기했어요. 새로 만들려면 /new 를 보내 주세요.")
                _clear(pending)
                finished = True
            elif action == "redo":
                telegram.answer_callback(cq["id"], "다른 뉴스로 다시 만들게요")
                telegram.send_message("🔁 다른 뉴스로 다시 만드는 중이에요. 5~15분 뒤 도착합니다.")
                _clear(pending)
                redo = True
        elif "message" in u:
            m = u["message"]
            if not _owner(m.get("chat", {}).get("id")):
                continue
            text = (m.get("text") or "").strip().lower()
            print(f"  [텔레그램] 메시지 {text[:20]}")
            if text.startswith("/new"):
                if pending:
                    _clear(pending)
                telegram.send_message("🔁 새 릴스를 만드는 중이에요. 5~15분 뒤 도착합니다.")
                redo = True
            elif text.startswith("/status"):
                telegram.send_message(f"⏳ 승인 대기: {pending['hook_title']} ({pending['id']})" if pending
                                      else "대기 중인 영상이 없어요.")
            elif text.startswith("/help") or text.startswith("/start"):
                telegram.send_message(HELP)
        if redo:
            break   # 다시 만들기는 바로 시작
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


def wait_for_decision(minutes):
    """영상 전송 직후 실시간 대기. 반환: 'redo' | 'done' | 'timeout'"""
    pending = load_state("pending", None)
    if not pending:
        return "done"
    until = _now() + dt.timedelta(minutes=minutes)
    pending["waiting_until"] = until.isoformat()
    save_state("pending", pending)
    git_push_state("state: waiting")      # 30분 점검 작업이 끼어들지 않게 표시
    print(f"  [대기] {minutes}분 동안 버튼 대기")
    result = "timeout"
    while _now() < until:
        left = (until - _now()).total_seconds()
        redo, finished = handle(_fetch(timeout=int(max(1, min(50, left)))))
        if redo:
            result = "redo"
            break
        if finished:
            result = "done"
            break
    p = load_state("pending", None)
    if p and "waiting_until" in p:
        p.pop("waiting_until")
        save_state("pending", p)
    print(f"  [대기] 끝: {result}")
    return result


def main():
    if not telegram.enabled():
        print("텔레그램 설정 없음")
        return
    pending = load_state("pending", None)
    redo = False
    if pending and pending.get("waiting_until") and \
            dt.datetime.fromisoformat(pending["waiting_until"]) > _now():
        print("영상 작업이 실시간 대기 중이라 이번 점검은 건너뜁니다.")
    else:
        redo, _ = handle(_fetch(timeout=0))
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"redo={'true' if redo else 'false'}\n")
    print("redo =", redo)


if __name__ == "__main__":
    main()
