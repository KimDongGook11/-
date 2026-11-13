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


def download(tag, dest):
    r = requests.get(f"{API}/repos/{_repo()}/releases/tags/{tag}", headers=_h(), timeout=30)
    r.raise_for_status()
    asset = r.json()["assets"][0]["url"]
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
