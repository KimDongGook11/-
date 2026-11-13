"""Pixabay 무료 스톡 영상 검색·다운로드."""
import requests

from . import config

API = "https://pixabay.com/api/videos/"
FALLBACK_QUERIES = ["stock market", "finance business", "city skyline night", "money", "global trade"]


def _search(q, cache):
    if q in cache:
        return cache[q]
    try:
        r = requests.get(API, params={"key": config.PIXABAY_API_KEY, "q": q[:100],
                                      "per_page": 20, "safesearch": "true"}, timeout=20)
        r.raise_for_status()
        hits = r.json().get("hits", [])
    except Exception as e:
        print(f"  [영상] '{q}' 검색 실패: {e}")
        hits = []
    cache[q] = hits
    return hits


def _pick_file(hit):
    vids = hit.get("videos", {})
    for size in ("medium", "large", "small"):
        v = vids.get(size) or {}
        if v.get("url") and v.get("width", 0) >= 960:
            return v["url"]
    v = vids.get("small") or {}
    return v.get("url")


def fetch_clips(segments, durs, workdir):
    """문장마다 배경 영상 1개. 못 구하면 None (렌더링 단계에서 단색 배경으로 대체)."""
    workdir.mkdir(parents=True, exist_ok=True)
    if not config.PIXABAY_API_KEY:
        print("  [영상] PIXABAY_API_KEY 없음 → 단색 배경 사용")
        return [None] * len(segments)
    cache, used, paths = {}, set(), []
    for i, (seg, d) in enumerate(zip(segments, durs)):
        path = None
        for q in [seg["keywords"], " ".join(seg["keywords"].split()[:1])] + FALLBACK_QUERIES:
            for hit in _search(q, cache):
                if hit["id"] in used:
                    continue
                url = _pick_file(hit)
                if not url:
                    continue
                out = workdir / f"clip_{i:02d}.mp4"
                try:
                    with requests.get(url, stream=True, timeout=60) as r:
                        r.raise_for_status()
                        with open(out, "wb") as f:
                            for chunk in r.iter_content(1 << 16):
                                f.write(chunk)
                    used.add(hit["id"])
                    path = out
                    break
                except Exception as e:
                    print(f"  [영상] 다운로드 실패: {e}")
            if path:
                break
        print(f"  [영상] {i+1}번 문장 '{seg['keywords']}' → {'OK' if path else '단색 배경'}")
        paths.append(path)
    return paths
