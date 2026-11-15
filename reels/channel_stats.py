"""유튜브 채널 성과 수집 → state/channel_stats.json (분석용).
사용: python -m reels.channel_stats
YouTube Data API(기존 YT_ 시크릿)만 사용합니다. 시청 지속률·스와이프율 같은 상세 지표는 스튜디오에서만 볼 수 있어요."""
import datetime as dt
import re

import requests

from . import youtube
from .utils import load_state, save_state

API = youtube.API


def _get(tok, path, **params):
    r = requests.get(f"{API}/{path}", params=params, headers=youtube._h(tok), timeout=30)
    r.raise_for_status()
    return r.json()


def _secs(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def collect(limit=50):
    tok = youtube._token()
    ch = _get(tok, "channels", part="snippet,statistics,contentDetails", mine="true")["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    items = _get(tok, "playlistItems", part="contentDetails", playlistId=uploads, maxResults=limit).get("items", [])
    ids = [i["contentDetails"]["videoId"] for i in items]
    videos = []
    if ids:
        for v in _get(tok, "videos", part="snippet,statistics,contentDetails,status", id=",".join(ids)).get("items", []):
            st, sn = v.get("statistics", {}), v["snippet"]
            dur = _secs(v["contentDetails"].get("duration"))
            videos.append({
                "id": v["id"], "title": sn["title"], "published": sn["publishedAt"],
                "kind": "shorts" if 0 < dur <= 180 else "long",
                "duration_s": dur, "privacy": v.get("status", {}).get("privacyStatus"),
                "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0)),
            })
    s = ch["statistics"]
    snap = {
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "channel": ch["snippet"]["title"],
        "subscribers": int(s.get("subscriberCount", 0)), "total_views": int(s.get("viewCount", 0)),
        "video_count": int(s.get("videoCount", 0)),
        "videos": sorted(videos, key=lambda x: x["published"], reverse=True),
    }
    return snap


def main():
    snap = collect()
    save_state("channel_stats", snap)
    hist = load_state("channel_stats_history", [])
    hist.append({k: snap[k] for k in ("collected_at", "subscribers", "total_views", "video_count")}
                | {"views_by_video": {v["id"]: v["views"] for v in snap["videos"]}})
    save_state("channel_stats_history", hist[-60:])
    print(f"{snap['channel']}: 구독자 {snap['subscribers']}, 총 조회수 {snap['total_views']}, 영상 {len(snap['videos'])}개")
    for v in snap["videos"][:15]:
        print(f"  {v['published'][:10]} [{v['kind']}] {v['views']:>6}회 👍{v['likes']} 💬{v['comments']}  {v['title'][:50]}")


if __name__ == "__main__":
    main()
