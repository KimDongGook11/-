"""보관된 장편의 유튜브 썸네일(thumbnail.jpg)을 다른 이미지로 바꾸기 (승인 버튼을 누르기 전에).
사용: python -m reels.thumb_replace <릴리스 태그> <새 썸네일 파일>"""
import sys

import requests

from . import storage, telegram


def main(tag, path, name="thumbnail.jpg"):
    r = requests.get(f"{storage.API}/repos/{storage._repo()}/releases/tags/{tag}", headers=storage._h(), timeout=30)
    r.raise_for_status()
    for a in r.json().get("assets", []):
        if a["name"] == name:
            requests.delete(f"{storage.API}/repos/{storage._repo()}/releases/assets/{a['id']}",
                            headers=storage._h(), timeout=30).raise_for_status()
            print("기존 썸네일 삭제:", a["id"])
    up = r.json()["upload_url"].split("{")[0]
    with open(path, "rb") as f:
        requests.post(f"{up}?name={name}", data=f, timeout=120,
                      headers=storage._h({"Content-Type": "image/jpeg"})).raise_for_status()
    print("새 썸네일 올림:", path)
    if telegram.enabled():
        try:
            telegram.send_photo(path, "🖼 [그때 그 결정] 장편 썸네일을 바꿨어요. 유튜브 게시 버튼을 누르면 이 썸네일로 올라가요.")
        except Exception as e:
            print("텔레그램 전송 실패(무시):", e)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
