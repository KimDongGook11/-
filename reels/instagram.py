"""Instagram Graph API로 릴스 게시 (공개 주소 video_url 방식, 직접 업로드는 예비).
5단계(인스타 연결)에서 IG_USER_ID, IG_ACCESS_TOKEN을 등록하면 동작합니다.
통합 로그인(EAA… 토큰)과 인스타 로그인(IG… 토큰)을 모두 지원합니다."""
import os
import time

import requests

from . import config


def enabled():
    """자동 게시는 IG_AUTO_PUBLISH=true 일 때만 (지금은 직접 올리는 방식이 기본)."""
    return bool(config.IG_USER_ID and config.IG_ACCESS_TOKEN) and \
        config.env("IG_AUTO_PUBLISH", "false").lower() == "true"


def graph_host(token):
    """통합 로그인(EAA… 토큰)은 graph.facebook.com, 인스타 로그인(IG… 토큰)은 graph.instagram.com."""
    forced = os.environ.get("IG_GRAPH_HOST")
    if forced:
        return forced
    return "graph.facebook.com" if token.startswith("EAA") else "graph.instagram.com"


def publish_reel(video_path, caption):
    """공개 주소 방식: 인스타 규격으로 다시 인코딩 → GitHub 공개 주소에 올리고 Meta가 가져가게(video_url).
    (2026-11-14 진단: 파일 직접 업로드(rupload)는 이 계정에서 항상 ProcessingFailedError, 공개 주소 방식은 정상 처리)
    공개 주소 방식이 실패하면 직접 업로드를 한 번 더 시도합니다."""
    import shutil
    src = str(video_path)
    if shutil.which("ffmpeg"):
        src = _ig_safe(video_path, str(video_path).replace(".mp4", "_ig.mp4"))
    try:
        url, cleanup = _public_url(src)
    except Exception as e:
        print(f"  [인스타] 공개 주소 준비 실패 → 직접 업로드 시도 ({e})")
        return _publish(src, caption)
    try:
        return _publish_url(url, caption)
    finally:
        cleanup()


def _gh():
    repo, tok = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not (repo and tok):
        raise RuntimeError("공개 주소 방식은 GitHub Actions 안에서만 동작해요.")
    return repo, {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}


def _public_url(path):
    """영상을 임시 GitHub Release에 올리고 누구나 받을 수 있는 주소를 돌려줍니다 (공개 저장소 필요)."""
    repo, h = _gh()
    tag = f"ig-upload-{int(time.time())}"
    r = requests.post(f"https://api.github.com/repos/{repo}/releases", headers=h, timeout=30,
                      json={"tag_name": tag, "name": tag, "prerelease": True, "body": "인스타 업로드용 임시 파일"})
    r.raise_for_status()
    rel = r.json()
    with open(path, "rb") as f:
        a = requests.post(rel["upload_url"].split("{")[0] + "?name=reel.mp4", data=f, timeout=300,
                          headers={**h, "Content-Type": "video/mp4"})
    a.raise_for_status()
    url = a.json()["browser_download_url"]
    chk = requests.head(url, allow_redirects=True, timeout=30)
    if chk.status_code != 200:
        raise RuntimeError(f"공개 주소에서 영상을 받을 수 없어요(HTTP {chk.status_code}). 저장소가 Public인지 확인하세요.")
    print(f"  [인스타] 공개 주소 준비: {url}")

    def cleanup():
        try:
            requests.delete(f"https://api.github.com/repos/{repo}/releases/{rel['id']}", headers=h, timeout=30)
            requests.delete(f"https://api.github.com/repos/{repo}/git/refs/tags/{tag}", headers=h, timeout=30)
        except Exception:
            pass
    return url, cleanup


def _wait_and_publish(base, uid, tok, cid):
    for _ in range(60):  # 최대 10분 처리 대기
        s = requests.get(f"{base}/{cid}", params={"fields": "status_code,status", "access_token": tok},
                         timeout=30).json()
        code = s.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"인스타 처리 실패: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("인스타 처리 시간 초과")
    p = requests.post(f"{base}/{uid}/media_publish", data={"creation_id": cid, "access_token": tok}, timeout=60)
    if p.status_code != 200:
        raise RuntimeError(f"게시 실패: {p.text[:400]}")
    mid = p.json()["id"]
    try:
        link = requests.get(f"{base}/{mid}", params={"fields": "permalink", "access_token": tok},
                            timeout=30).json().get("permalink")
    except Exception:
        link = None
    return mid, link


def _publish_url(url, caption):
    tok, uid = config.IG_ACCESS_TOKEN.strip(), config.IG_USER_ID.strip()
    base = f"https://{graph_host(tok)}/{config.IG_API_VERSION}"
    r = requests.post(f"{base}/{uid}/media", timeout=60, data={
        "media_type": "REELS", "video_url": url, "caption": caption[:2200],
        "share_to_feed": "true", "access_token": tok})
    if r.status_code != 200:
        raise RuntimeError(f"컨테이너 생성 실패(공개 주소 방식): {r.text[:400]}")
    return _wait_and_publish(base, uid, tok, r.json()["id"])


def _ig_safe(src, dst):
    """인스타 릴스 규격: H.264 main 4.0, 30fps, 2초 키프레임, AAC 48kHz 128kbps 스테레오."""
    import subprocess
    cmd = ["ffmpeg", "-y", "-i", str(src), "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "main",
           "-level:v", "4.0", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60", "-keyint_min", "60",
           "-sc_threshold", "0", "-crf", "21", "-maxrate", "6M", "-bufsize", "12M",
           "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(dst)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("다시 인코딩 실패: " + p.stderr[-300:])
    return dst


class UploadRejected(RuntimeError):
    pass


def _publish(video_path, caption):
    tok, uid = config.IG_ACCESS_TOKEN.strip(), config.IG_USER_ID.strip()
    base = f"https://{graph_host(tok)}/{config.IG_API_VERSION}"

    r = requests.post(f"{base}/{uid}/media", timeout=60, data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200],
        "share_to_feed": "true", "access_token": tok})
    if r.status_code != 200:
        raise RuntimeError(f"컨테이너 생성 실패: {r.text[:400]}")
    cid = r.json()["id"]
    uri = r.json().get("uri") or f"https://rupload.facebook.com/ig-api-upload/{config.IG_API_VERSION}/{cid}"

    size = os.path.getsize(video_path)
    with open(video_path, "rb") as f:
        up = requests.post(uri, data=f, timeout=600, headers={
            "Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(size)})
    if up.status_code != 200:
        if "ProcessingFailedError" in up.text:
            try:
                st = requests.get(f"{base}/{cid}", params={"fields": "status_code,status", "access_token": tok},
                                  timeout=30).json()
            except Exception:
                st = {}
            raise UploadRejected(f"영상 업로드 실패(파일 거부): {up.text[:200]} / 상태: {st}")
        raise RuntimeError(f"영상 업로드 실패: {up.text[:400]}")

    return _wait_and_publish(base, uid, tok, cid)
