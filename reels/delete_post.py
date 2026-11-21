"""게시물 삭제 도구: 유튜브 영상 ID와 인스타 캡션 검색어를 받아 지움 (사용자 요청 시에만 수동 실행).
사용: python -m reels.delete_post --yt VIDEO_ID --ig "캡션에 들어간 단어"
인스타 API가 삭제를 허용하지 않으면 실패 이유를 남기고, 앱에서 직접 지우도록 링크를 알려 줌."""
import argparse

import requests

from . import config, instagram, telegram, youtube


def delete_youtube(vid):
    code = youtube.delete(vid)
    ok = code in (200, 204)
    print(f"  [유튜브] {vid} 삭제 {'완료' if ok else f'실패(HTTP {code})'}")
    return ok, f"유튜브 {vid}: " + ("삭제 완료" if ok else f"삭제 실패 (HTTP {code})")


def find_ig(word, limit=25):
    tok, uid = config.IG_ACCESS_TOKEN, config.IG_USER_ID
    base = f"https://{instagram.graph_host(tok)}/{config.IG_API_VERSION}"
    r = requests.get(f"{base}/{uid}/media", timeout=30, params={
        "fields": "id,caption,timestamp,permalink,media_type", "limit": limit, "access_token": tok})
    r.raise_for_status()
    return base, tok, [m for m in r.json().get("data", []) if word in (m.get("caption") or "")]


def delete_instagram(word):
    base, tok, found = find_ig(word)
    if not found:
        print(f"  [인스타] 캡션에 '{word}'가 들어간 최근 게시물이 없어요")
        return False, f"인스타: '{word}' 게시물을 찾지 못함"
    m = found[0]   # 가장 최근 것 하나만
    print(f"  [인스타] 대상: {m['id']} {m.get('timestamp')} {m.get('permalink')}")
    r = requests.delete(f"{base}/{m['id']}", params={"access_token": tok}, timeout=30)
    ok = r.status_code == 200 and "error" not in r.text
    print(f"  [인스타] 삭제 {'완료' if ok else '실패'}: HTTP {r.status_code} {r.text[:300]}")
    return ok, ("인스타: 삭제 완료 " if ok else
                f"인스타: API로 삭제 안 됨 (HTTP {r.status_code}). 앱에서 직접 지워 주세요 → ") + (m.get("permalink") or m["id"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yt", default="")
    ap.add_argument("--ig", default="")
    a = ap.parse_args()
    lines = []
    if a.yt:
        lines.append(delete_youtube(a.yt.strip())[1])
    if a.ig:
        try:
            lines.append(delete_instagram(a.ig.strip())[1])
        except Exception as e:
            lines.append(f"인스타: 오류 {str(e)[:300]}")
    print("\n".join(lines))
    if telegram.enabled() and lines:
        telegram.send_message("🗑 게시물 삭제 결과\n" + "\n".join(f"- {l}" for l in lines))


if __name__ == "__main__":
    main()
