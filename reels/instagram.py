"""Instagram Graph API로 릴스 게시 (영상 파일을 직접 업로드하는 resumable 방식).
5단계(인스타 연결)에서 IG_USER_ID, IG_ACCESS_TOKEN을 등록하면 동작합니다.
통합 로그인(EAA… 토큰)과 인스타 로그인(IG… 토큰)을 모두 지원합니다."""
import os
import time

import requests

from . import config


def enabled():
    return bool(config.IG_USER_ID and config.IG_ACCESS_TOKEN)


def graph_host(token):
    """통합 로그인(EAA… 토큰)은 graph.facebook.com, 인스타 로그인(IG… 토큰)은 graph.instagram.com."""
    forced = os.environ.get("IG_GRAPH_HOST")
    if forced:
        return forced
    return "graph.facebook.com" if token.startswith("EAA") else "graph.instagram.com"


def publish_reel(video_path, caption):
    """업로드에서 Meta가 파일을 거부하면(ProcessingFailedError) 인스타 규격으로 다시 인코딩해 한 번 더 시도."""
    try:
        return _publish(video_path, caption)
    except UploadRejected as e:
        import shutil
        if not shutil.which("ffmpeg"):
            raise RuntimeError(f"{e} (다시 인코딩할 ffmpeg가 없어요. /new 로 새 영상을 만들어 승인해 주세요)")
        safe = str(video_path).replace(".mp4", "_ig.mp4")
        print("  [인스타] 파일 거부 → 인스타 규격으로 다시 인코딩해 재시도")
        _ig_safe(video_path, safe)
        return _publish(safe, caption)


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
            raise UploadRejected(f"영상 업로드 실패(파일 거부): {up.text[:300]}")
        raise RuntimeError(f"영상 업로드 실패: {up.text[:400]}")

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
