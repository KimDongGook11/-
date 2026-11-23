"""텔레그램에 보냈던 초안 메시지 글을 되찾기 (대본 보관이 없던 영상용).
봇은 지난 메시지를 읽을 수 없어서, 같은 방으로 '전달(forward)'해 내용을 받은 뒤 전달본은 바로 지웁니다.
사용: python -m reels.tgrecover <마지막 메시지 번호> [몇 개 앞까지, 기본 8]"""
import sys

import requests

from . import config, telegram


def main():
    last = int(sys.argv[1])
    back = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    chat = config.TELEGRAM_CHAT_ID
    for mid in range(last - back, last + 1):
        r = requests.post(telegram._api("forwardMessage"), timeout=30,
                          data={"chat_id": chat, "from_chat_id": chat, "message_id": mid, "disable_notification": True})
        if r.status_code != 200 or not r.json().get("ok"):
            continue
        m = r.json()["result"]
        text = m.get("text") or m.get("caption") or ""
        requests.post(telegram._api("deleteMessage"), timeout=30, data={"chat_id": chat, "message_id": m["message_id"]})
        if text:
            print(f"\n===== 메시지 {mid} =====\n{text}")


if __name__ == "__main__":
    main()
