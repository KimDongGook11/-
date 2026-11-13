"""텔레그램 버튼/명령 확인 (30분마다 실행).
- ✅ 승인: 인스타 게시 (5단계 연결 전이면 안내만)
- 🔁 다시: 다른 뉴스로 재생성 → GitHub Actions의 다음 단계에서 실행 (redo=true 출력)
- ❌ 폐기
- 명령어: /new(새로 만들기), /status(상태), /help
"""
import os
import tempfile

from . import config, instagram, storage, telegram
from .utils import load_state, save_state

HELP = ("명령어\n/new - 다른 뉴스로 새로 만들기\n/status - 승인 대기 상태 보기\n"
        "/help - 도움말\n\n버튼과 명령은 최대 30분 안에 처리돼요.")


def _owner(uid):
    return str(uid) == str(config.TELEGRAM_CHAT_ID)


def _clear(pending, keep_file=False):
    if pending.get("tg_message_id"):
        telegram.remove_buttons(pending["tg_message_id"])
    if not keep_file and pending.get("release_tag") and storage.enabled():
        storage.delete(pending["release_tag"])
    save_state("pending", None)


def _approve(pending):
    if not instagram.enabled():
        telegram.send_message("✅ 승인 확인!\n아직 인스타그램이 연결되지 않아 자동 게시는 건너뛰었어요.\n"
                              "위 영상을 저장해서 직접 올리거나, 5단계(인스타 연결) 후에는 자동으로 게시됩니다.")
        _clear(pending)
        return
    path = pending.get("video")
    if not path or not os.path.exists(path):
        path = os.path.join(tempfile.gettempdir(), "reel.mp4")
        storage.download(pending["release_tag"], path)
    try:
        mid, link = instagram.publish_reel(path, pending["caption"])
        telegram.send_message(f"🎉 인스타 게시 완료!\n{link or mid}")
        _clear(pending)
    except Exception as e:
        telegram.send_message(f"⚠️ 인스타 게시 실패: {str(e)[:700]}\n영상은 그대로 보관 중이에요. "
                              "문제를 해결한 뒤 승인 버튼을 다시 눌러 주세요.")


def main():
    if not telegram.enabled():
        print("텔레그램 설정 없음")
        return
    off = load_state("telegram_offset", {}).get("offset")
    updates = telegram.get_updates(off)
    pending = load_state("pending", None)
    redo = False

    for u in updates:
        off = u["update_id"] + 1
        if "callback_query" in u:
            cq = u["callback_query"]
            if not _owner(cq["from"]["id"]):
                continue
            action, _, rid = cq.get("data", "").partition(":")
            if not pending or pending.get("id") != rid:
                telegram.answer_callback(cq["id"], "이미 처리됐거나 만료된 영상이에요.")
                continue
            if action == "approve":
                telegram.answer_callback(cq["id"], "게시를 시작합니다")
                _approve(pending)
            elif action == "reject":
                telegram.answer_callback(cq["id"], "폐기했어요")
                telegram.send_message("❌ 폐기했어요. 새로 만들려면 /new 를 보내 주세요.")
                _clear(pending)
            elif action == "redo":
                telegram.answer_callback(cq["id"], "다른 뉴스로 다시 만들게요")
                telegram.send_message("🔁 다른 뉴스로 다시 만드는 중이에요. 5~10분 뒤 도착합니다.")
                _clear(pending)
                redo = True
            pending = load_state("pending", None)
        elif "message" in u:
            m = u["message"]
            if not _owner(m.get("chat", {}).get("id")):
                continue
            text = (m.get("text") or "").strip().lower()
            if text.startswith("/new"):
                if pending:
                    _clear(pending)
                    pending = None
                telegram.send_message("🔁 새 릴스를 만드는 중이에요. 5~10분 뒤 도착합니다.")
                redo = True
            elif text.startswith("/status"):
                telegram.send_message(f"⏳ 승인 대기: {pending['hook_title']} ({pending['id']})" if pending
                                      else "대기 중인 영상이 없어요.")
            elif text.startswith("/help") or text.startswith("/start"):
                telegram.send_message(HELP)

    save_state("telegram_offset", {"offset": off})
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"redo={'true' if redo else 'false'}\n")
    print("redo =", redo)


if __name__ == "__main__":
    main()
