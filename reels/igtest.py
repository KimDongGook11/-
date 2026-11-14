"""인스타 업로드 진단 (게시는 하지 않음).
최근 릴스 영상으로 여러 업로드 방식을 시험해서, Meta가 처리 완료(FINISHED)까지 가는 방식을 찾습니다.
컨테이너만 만들고 media_publish는 부르지 않으니 계정에 아무것도 올라가지 않아요."""
import os
import tempfile
import time

import requests

from . import config, instagram, storage

TOK = config.IG_ACCESS_TOKEN.strip()
UID = config.IG_USER_ID.strip()
BASE = f"https://{instagram.graph_host(TOK)}/{config.IG_API_VERSION}"


def status(cid, wait=300):
    end = time.time() + wait
    s = {}
    while time.time() < end:
        s = requests.get(f"{BASE}/{cid}", params={"fields": "status_code,status", "access_token": TOK},
                         timeout=30).json()
        if s.get("status_code") in ("FINISHED", "ERROR", "EXPIRED"):
            return s
        time.sleep(10)
    return s


def resumable(path, extra_headers=None):
    r = requests.post(f"{BASE}/{UID}/media", timeout=60, data={
        "media_type": "REELS", "upload_type": "resumable", "caption": "test", "access_token": TOK})
    print("   컨테이너:", r.status_code, r.text[:300])
    r.raise_for_status()
    cid, uri = r.json()["id"], r.json().get("uri")
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        data = f.read()
    h = {"Authorization": f"OAuth {TOK}", "offset": "0", "file_size": str(size)}
    h.update(extra_headers or {})
    up = requests.post(uri, data=data, headers=h, timeout=600)
    print("   업로드:", up.status_code, up.text[:300])
    return status(cid) if up.status_code == 200 else {"upload_error": up.text[:300]}


def by_url(url):
    r = requests.post(f"{BASE}/{UID}/media", timeout=60, data={
        "media_type": "REELS", "video_url": url, "caption": "test", "access_token": TOK})
    print("   컨테이너:", r.status_code, r.text[:300])
    r.raise_for_status()
    return status(r.json()["id"])


def main():
    me = requests.get(f"{BASE}/{UID}", params={"fields": "username,id", "access_token": TOK}, timeout=30)
    print("계정 확인:", me.status_code, me.text[:300])
    if me.status_code != 200:
        print("→ 토큰이나 IG_USER_ID 문제예요. 업로드 시험을 멈춥니다.")
        return
    lim = requests.get(f"{BASE}/{UID}/content_publishing_limit", params={"fields": "quota_usage,config",
                       "access_token": TOK}, timeout=30)
    print("게시 한도:", lim.status_code, lim.text[:300])

    tag = os.environ.get("IG_TEST_TAG", "reel-h20261114-202226")
    print("시험 영상:", tag)
    src = os.path.join(tempfile.gettempdir(), "igtest.mp4")
    storage.download(tag, src)
    safe = instagram._ig_safe(src, src.replace(".mp4", "_ig.mp4"))
    print("파일 크기:", os.path.getsize(src), "→ 규격 변환", os.path.getsize(safe))

    results = {}
    trials = [
        ("A 직접 업로드(원본)", lambda: resumable(src)),
        ("B 직접 업로드(규격 변환)", lambda: resumable(safe)),
        ("C 직접 업로드(규격 변환 + Content-Type)", lambda: resumable(safe, {"Content-Type": "application/octet-stream"})),
    ]
    url, cleanup = None, lambda: None
    try:
        url, cleanup = instagram._public_url(safe)
        final = requests.head(url, allow_redirects=True, timeout=30).url
        trials += [("D 공개 주소(GitHub 링크)", lambda: by_url(url)),
                   ("E 공개 주소(리다이렉트 최종 주소)", lambda: by_url(final))]
    except Exception as e:
        print("공개 주소 준비 실패:", e)
    for name, fn in trials:
        print(f"\n== {name}")
        try:
            results[name] = fn()
        except Exception as e:
            results[name] = {"error": str(e)[:300]}
        print("   결과:", results[name])
    cleanup()
    print("\n===== 요약 =====")
    for k, v in results.items():
        ok = v.get("status_code") == "FINISHED"
        print(("✅ " if ok else "❌ ") + k + " :", v)


if __name__ == "__main__":
    main()
