"""YouTube Data API v3 업로드 (requests만 사용).
필요한 Secrets: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
(OAuth Playground에서 범위 https://www.googleapis.com/auth/youtube 로 받은 refresh token)"""
import json
import os

import requests

from . import config

UPLOAD = "https://www.googleapis.com/upload/youtube/v3"
API = "https://www.googleapis.com/youtube/v3"


def enabled():
    return all(config.env(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def _token():
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": config.env("YT_CLIENT_ID").strip(),
        "client_secret": config.env("YT_CLIENT_SECRET").strip(),
        "refresh_token": config.env("YT_REFRESH_TOKEN").strip(),
        "grant_type": "refresh_token"})
    if r.status_code != 200:
        raise RuntimeError(f"유튜브 로그인 토큰 갱신 실패: {r.text[:300]}")
    return r.json()["access_token"]


def _h(tok, extra=None):
    return {"Authorization": f"Bearer {tok}", **(extra or {})}


def channel(tok=None):
    tok = tok or _token()
    r = requests.get(f"{API}/channels", params={"part": "snippet", "mine": "true"}, headers=_h(tok), timeout=30)
    r.raise_for_status()
    items = r.json().get("items", [])
    return items[0]["snippet"]["title"] if items else None


def upload(path, title, description, tags=(), privacy="public", thumb=None, category="27", made_with_ai=True,
           publish_at=None):
    """영상 업로드 → (video_id, 실제 공개 상태). category 27 = 교육, 25 = 뉴스/정치.
    publish_at(ISO 8601 UTC 문자열)을 주면 비공개로 올린 뒤 그 시각에 자동 공개됩니다."""
    tok = _token()
    meta = {
        "snippet": {"title": title[:100], "description": description[:4900], "tags": list(tags)[:30],
                    "categoryId": category, "defaultLanguage": "ko", "defaultAudioLanguage": "ko"},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": bool(made_with_ai)},
    }
    if publish_at:
        meta["status"].update({"privacyStatus": "private", "publishAt": publish_at})
    size = os.path.getsize(path)
    r = requests.post(f"{UPLOAD}/videos", params={"uploadType": "resumable", "part": "snippet,status"},
                      headers=_h(tok, {"Content-Type": "application/json; charset=UTF-8",
                                       "X-Upload-Content-Type": "video/mp4",
                                       "X-Upload-Content-Length": str(size)}),
                      data=json.dumps(meta), timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"유튜브 업로드 준비 실패: {r.text[:400]}")
    loc = r.headers["Location"]
    with open(path, "rb") as f:
        up = requests.put(loc, data=f, timeout=1800, headers={"Content-Type": "video/mp4",
                                                              "Content-Length": str(size)})
    if up.status_code not in (200, 201):
        raise RuntimeError(f"유튜브 영상 업로드 실패: {up.text[:400]}")
    vid = up.json()["id"]
    status = up.json().get("status", {}).get("privacyStatus")
    if thumb and os.path.exists(thumb):
        with open(thumb, "rb") as f:
            t = requests.post(f"{UPLOAD}/thumbnails/set", params={"videoId": vid}, timeout=120,
                              headers=_h(tok, {"Content-Type": "image/jpeg"}), data=f)
        if t.status_code != 200:
            print(f"  [유튜브] 썸네일 등록 실패(영상은 올라감): {t.text[:300]}")
    return vid, status


def update_snippet(vid, title, description, tags=(), category="27", tok=None):
    """올린 영상의 제목·설명·태그 수정 (snippet 전체를 다시 보냄)."""
    tok = tok or _token()
    body = {"id": vid, "snippet": {"title": title[:100], "description": description[:4900], "tags": list(tags)[:30],
                                   "categoryId": category, "defaultLanguage": "ko", "defaultAudioLanguage": "ko"}}
    r = requests.put(f"{API}/videos", params={"part": "snippet"}, json=body, headers=_h(tok), timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"유튜브 정보 수정 실패: {r.text[:300]}")
    return True


def status(vid, tok=None):
    tok = tok or _token()
    r = requests.get(f"{API}/videos", params={"part": "status,processingDetails", "id": vid},
                     headers=_h(tok), timeout=30)
    r.raise_for_status()
    items = r.json().get("items", [])
    return items[0] if items else {}


def delete(vid, tok=None):
    tok = tok or _token()
    return requests.delete(f"{API}/videos", params={"id": vid}, headers=_h(tok), timeout=30).status_code


def add_to_playlist(vid, title, tok=None):
    """내 채널에서 이름이 title인 재생목록을 찾아 영상 추가. 성공하면 재생목록 ID, 못 찾거나 실패하면 None."""
    tok = tok or _token()
    try:
        r = requests.get(f"{API}/playlists", params={"part": "snippet", "mine": "true", "maxResults": 50},
                         headers=_h(tok), timeout=30)
        r.raise_for_status()
        pl = next((x["id"] for x in r.json().get("items", []) if x["snippet"]["title"].strip() == title.strip()), None)
        if not pl:
            print(f"  [유튜브] 재생목록 '{title}' 없음")
            return None
        r = requests.post(f"{API}/playlistItems", params={"part": "snippet"}, headers=_h(tok), timeout=30, json={
            "snippet": {"playlistId": pl, "resourceId": {"kind": "youtube#video", "videoId": vid}}})
        r.raise_for_status()
        return pl
    except Exception as e:
        print(f"  [유튜브] 재생목록 추가 실패: {e}")
        return None
