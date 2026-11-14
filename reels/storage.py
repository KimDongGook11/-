"""승인 대기 중인 영상을 GitHub Release에 보관합니다 (실행과 실행 사이에 파일을 유지하기 위해)."""
import os

import requests

API = "https://api.github.com"


def enabled():
    return bool(os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPOSITORY"))


def _h(extra=None):
    h = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
         "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    h.update(extra or {})
    return h


def _repo():
    return os.environ["GITHUB_REPOSITORY"]


def upload(path, tag, title):
    r = requests.post(f"{API}/repos/{_repo()}/releases", headers=_h(), timeout=30, json={
        "tag_name": tag, "name": title[:100], "body": "승인 대기 중인 릴스 영상", "prerelease": True})
    r.raise_for_status()
    up = r.json()["upload_url"].split("{")[0]
    with open(path, "rb") as f:
        r2 = requests.post(f"{up}?name={tag}.mp4", data=f, timeout=300,
                           headers=_h({"Content-Type": "video/mp4"}))
    r2.raise_for_status()
    return tag


def download(tag, dest, name=None):
    """보관본 내려받기. name을 주면 그 이름의 파일, 아니면 첫 번째 .mp4(없으면 첫 파일)."""
    r = requests.get(f"{API}/repos/{_repo()}/releases/tags/{tag}", headers=_h(), timeout=30)
    r.raise_for_status()
    assets = r.json()["assets"]
    pick = [a for a in assets if a["name"] == name] if name else [a for a in assets if a["name"].endswith(".mp4")]
    if name and not pick:
        raise FileNotFoundError(f"{tag}에 {name} 파일이 없어요")
    asset = (pick or assets)[0]["url"]
    with requests.get(asset, headers=_h({"Accept": "application/octet-stream"}), stream=True, timeout=300) as d:
        d.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in d.iter_content(1 << 16):
                f.write(chunk)
    return dest


def delete(tag):
    try:
        r = requests.get(f"{API}/repos/{_repo()}/releases/tags/{tag}", headers=_h(), timeout=30)
        if r.status_code == 200:
            requests.delete(f"{API}/repos/{_repo()}/releases/{r.json()['id']}", headers=_h(), timeout=30)
        requests.delete(f"{API}/repos/{_repo()}/git/refs/tags/{tag}", headers=_h(), timeout=30)
    except Exception as e:
        print(f"  [보관] 삭제 실패(무시): {e}")


def add_asset(tag, path, name):
    try:
        r = requests.get(f"{API}/repos/{_repo()}/releases/tags/{tag}", headers=_h(), timeout=30)
        r.raise_for_status()
        up = r.json()["upload_url"].split("{")[0]
        ctype = "image/jpeg" if name.endswith(".jpg") else "application/octet-stream"
        with open(path, "rb") as f:
            requests.post(f"{up}?name={name}", data=f, timeout=120, headers=_h({"Content-Type": ctype})).raise_for_status()
    except Exception as e:
        print(f"  [보관] 파일 추가 실패(무시): {e}")


def public_url(tag, name):
    """공개 저장소면 누구나 받을 수 있는 다운로드 주소."""
    return f"https://github.com/{_repo()}/releases/download/{tag}/{name}"


def prune(prefix, keep=6):
    """오래된 보관본 정리 (prefix로 시작하는 것 중 최근 keep개만 남김)."""
    try:
        r = requests.get(f"{API}/repos/{_repo()}/releases", params={"per_page": 100}, headers=_h(), timeout=30)
        r.raise_for_status()
        rels = sorted([x for x in r.json() if x["tag_name"].startswith(prefix)],
                      key=lambda x: x["created_at"], reverse=True)
        for x in rels[keep:]:
            delete(x["tag_name"])
    except Exception as e:
        print(f"  [보관] 정리 실패(무시): {e}")
