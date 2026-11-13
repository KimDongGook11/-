"""텔레그램 봇: 미리보기 전송, 승인 버튼, 업데이트 읽기."""
import json

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


def send_video(path, caption, buttons=None):
    data = {"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption[:1000], "supports_streaming": "true"}
    if buttons:
        data["reply_markup"] = _kb(buttons)
    with open(path, "rb") as f:
        r = requests.post(_api("sendVideo"), data=data, files={"video": f}, timeout=300)
    r.raise_for_status()
    return r.json()["result"]["message_id"]


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
    r = requests.get(_api("getUpdates"), params=params, timeout=timeout + 20)
    r.raise_for_status()
    return r.json().get("result", [])
