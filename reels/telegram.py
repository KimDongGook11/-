"""텔레그램 봇: 미리보기 전송, 승인 버튼, 업데이트 읽기."""
import json
import time

import requests

from . import config


def _api(method):
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}"


def enabled():
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def _kb(buttons):
    if not buttons:
        return None
    return json.dumps({"inline_keyboard": [[{"text": t, "callback_data": d}] for t, d in buttons]})


def send_message(text, buttons=None):
    data = {"chat_id": config.TELEGRAM_CHAT_ID, "text": text[:4000], "disable_web_page_preview": True}
    if buttons:
        data["reply_markup"] = _kb(buttons)
    r = requests.post(_api("sendMessage"), data=data, timeout=30)
    r.raise_for_status()
    return r.json()["result"]["message_id"]


def _post_file(method, data, field, path, timeout, tries=4):
    """파일 전송: 연결 끊김·일시 오류 시 잠깐 쉬고 다시 시도."""
    last = None
    for i in range(tries):
        try:
            with open(path, "rb") as f:
                r = requests.post(_api(method), data=data, files={field: f}, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()["result"]["message_id"]
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            last = e
            if isinstance(e, requests.HTTPError) and e.response is not None and 400 <= e.response.status_code < 429:
                raise
            print(f"  [텔레그램] {method} 실패({type(e).__name__}) → {10 * (i + 1)}초 뒤 다시 시도")
            time.sleep(10 * (i + 1))
    raise last


def send_video(path, caption, buttons=None):
    data = {"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption[:1000], "supports_streaming": "true"}
    if buttons:
        data["reply_markup"] = _kb(buttons)
    return _post_file("sendVideo", data, "video", path, 300)


def send_photo(path, caption=""):
    return _post_file("sendPhoto", {"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption[:1000]},
                      "photo", path, 120)


def send_document(path, caption=""):
    return _post_file("sendDocument", {"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption[:1000]},
                      "document", path, 300)


def remove_buttons(message_id):
    try:
        requests.post(_api("editMessageReplyMarkup"), timeout=20, data={
            "chat_id": config.TELEGRAM_CHAT_ID, "message_id": message_id,
            "reply_markup": json.dumps({"inline_keyboard": []})})
    except Exception:
        pass


def answer_callback(cb_id, text):
    try:  # 오래된 버튼은 응답 기한이 지나 에러가 날 수 있으나 무시
        requests.post(_api("answerCallbackQuery"), data={"callback_query_id": cb_id, "text": text}, timeout=20)
    except Exception:
        pass


def get_updates(offset=None, timeout=0):
    """timeout>0 이면 새 메시지가 올 때까지 최대 timeout초 기다림(롱폴링)."""
    params = {"timeout": timeout, "allowed_updates": json.dumps(["message", "callback_query"])}
    if offset:
        params["offset"] = offset
    import time
    r = None
    # 502/5xx가 이어지면(텔레그램 쪽 일시 장애나 큰 업데이트 때문) 잠깐 쉬었다가, 그다음엔 한 건씩 받아 봄
    for attempt, limit in enumerate((None, None, 1, 1)):
        q = dict(params, **({"limit": limit} if limit else {}))
        r = requests.get(_api("getUpdates"), params=q, timeout=timeout + 20)
        if r.status_code < 500:
            break
        print(f"  [텔레그램] getUpdates {r.status_code} → 다시 시도({attempt + 1}/4)")
        time.sleep(3 + attempt * 3)
    r.raise_for_status()
    return r.json().get("result", [])
