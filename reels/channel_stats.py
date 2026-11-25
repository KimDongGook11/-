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


# 채널 소개글 (2026-11-21 운영 개편). 글을 바꾸면 BRANDING_VERSION을 올리세요: 한 번만 적용되고,
# 그 뒤 스튜디오에서 직접 고친 내용은 덮어쓰지 않습니다.
BRANDING_VERSION = 1
CHANNEL_DESCRIPTION = """매일 경제 뉴스를 쉽고 빠르게, 경제원픽입니다.

⏰ 아침 7시 · 미국 증시 마감 브리핑
☀️ 낮 12시 · 오늘의 원픽 (그날 가장 뜨거운 경제 이슈 하나)
🌆 오후 5시 · 국내 증시 마감 브리핑과 뉴스 정리
📚 주말 · 그때 그 결정 (기업의 운명을 바꾼 결정적 순간)

"그래서 내 돈은 어떻게 되는데?" 주식, 환율, 금리에 미치는 영향까지 짚어 드려요.

모든 영상은 원문 기사와 시세 데이터를 근거로 AI가 제작합니다. 투자 권유가 아닙니다.
틀린 내용 제보나 다뤄 줬으면 하는 주제는 댓글로 남겨 주세요.
📷 인스타그램 @econonepick"""


def apply_branding(tok=None):
    """채널 소개글을 위 내용으로 한 번 바꿈 (state/channel_branding.json에 적용한 버전 기록)."""
    done = load_state("channel_branding", {})
    if done.get("version") == BRANDING_VERSION:
        return
    tok = tok or youtube._token()
    ch = _get(tok, "channels", part="brandingSettings", mine="true")["items"][0]
    channel = dict((ch.get("brandingSettings") or {}).get("channel") or {})
    channel["description"] = CHANNEL_DESCRIPTION
    body = {"id": ch["id"], "brandingSettings": {**(ch.get("brandingSettings") or {}), "channel": channel}}
    r = requests.put(f"{API}/channels", params={"part": "brandingSettings"}, json=body,
                     headers=youtube._h(tok), timeout=30)
    if r.status_code != 200:
        print(f"  [채널 소개] 수정 실패(다음 실행에 다시 시도): {r.text[:300]}")
        return
    save_state("channel_branding", {"version": BRANDING_VERSION,
                                    "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
    print("  [채널 소개] 새 운영 시간표로 바꿨어요")


def main():
    try:
        apply_branding()
    except Exception as e:
        print(f"  [채널 소개] 건너뜀: {e}")
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
