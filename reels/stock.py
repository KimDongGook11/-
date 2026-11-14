"""Pixabay 무료 스톡 영상: 문장마다 2~4초 단위로 컷을 나눠 배경 샷 목록을 만듭니다.
- 세로 영상(릴스)이면 세로 클립 → 4K/고화질 순으로 우선
- 같은 클립은 최대한 다시 쓰지 않고, 다시 쓸 때는 다른 구간을 씀"""
import random

import requests

from . import config

API = "https://pixabay.com/api/videos/"
FALLBACK_QUERIES = ["stock market", "finance business", "city skyline night", "office building", "global trade"]
MAX_MB = 70


def _search(q, cache):
    if q in cache:
        return cache[q]
    try:
        r = requests.get(API, params={"key": config.PIXABAY_API_KEY, "q": q[:100],
                                      "per_page": 30, "safesearch": "true"}, timeout=20)
        r.raise_for_status()
        hits = r.json().get("hits", [])
    except Exception as e:
        print(f"  [영상] '{q}' 검색 실패: {e}")
        hits = []
    cache[q] = hits
    return hits


def _rendition(hit, vertical):
    """해당 클립에서 쓸 파일: 화질 기준을 넘는 것 중 가장 가벼운 것, 없으면 가장 큰 것."""
    vids = hit.get("videos", {})
    cands = [vids[k] for k in ("large", "medium", "small")
             if (vids.get(k) or {}).get("url") and vids[k].get("size", 0) <= MAX_MB * 1e6]
    if not cands:
        return None

    def ok(v):
        w, h = v.get("width", 0), v.get("height", 0)
        if vertical:   # 세로 클립(폭 1080 이상) 또는 4K 가로(가운데를 잘라도 폭 1215)
            return (h > w and w >= 1080) or h >= 2160
        return w >= 1920
    good = [v for v in cands if ok(v)]
    if good:
        return min(good, key=lambda v: v.get("size", 0))
    return max(cands, key=lambda v: v.get("width", 0) * v.get("height", 0))


def _score(hit, vertical):
    v = hit.get("videos", {}).get("large") or {}
    w, h = v.get("width", 0), v.get("height", 0)
    s = 0
    if vertical and h > w:
        s += 3                      # 세로 클립 최우선
    if max(w, h) >= 3840:
        s += 2                      # 4K
    elif max(w, h) >= 1920:
        s += 1
    return s + random.random() * 0.5


def _download(url, out):
    with requests.get(url, stream=True, timeout=90) as r:
        r.raise_for_status()
        with open(out, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return out


def plan_shots(segments, durs, workdir, vertical=True, shot_len=2.8, max_clips=40):
    """반환: [(클립경로 또는 None, 클립 안 시작초, 샷 길이초)] — 전체 길이 = sum(durs)."""
    workdir.mkdir(parents=True, exist_ok=True)
    cuts = []
    for seg, d in zip(segments, durs):
        n = max(1, round(d / shot_len))
        cuts.append([d / n] * n)
    if not config.PIXABAY_API_KEY:
        print("  [영상] PIXABAY_API_KEY 없음 → 단색 배경")
        return [(None, 0.0, x) for c in cuts for x in c]

    cache, files, used_ids, plan = {}, {}, set(), []
    clip_count = 0
    for i, (seg, lens) in enumerate(zip(segments, cuts)):
        kw = seg.get("keywords") or "stock market"
        queries = [kw, " ".join(kw.split()[:2]), kw.split()[0]] + FALLBACK_QUERIES
        pool = []
        for q in dict.fromkeys(queries):
            pool = sorted(_search(q, cache), key=lambda h: -_score(h, vertical))
            if pool:
                break
        got = []
        for L in lens:
            hit = next((h for h in pool if h["id"] not in used_ids), None) if clip_count < max_clips else None
            if hit is None and files:            # 새 클립이 없으면 이미 받은 클립의 다른 구간 재사용
                hid = random.choice(list(files))
                path, dur = files[hid]
                got.append((path, random.uniform(0, max(0.0, dur - L - 0.2)), L))
                continue
            if hit is None:
                got.append((None, 0.0, L))
                continue
            used_ids.add(hit["id"])
            v = _rendition(hit, vertical)
            if not v:
                got.append((None, 0.0, L))
                continue
            out = workdir / f"clip_{hit['id']}.mp4"
            try:
                _download(v["url"], out)
                clip_count += 1
                dur = float(hit.get("duration") or 8)
                files[hit["id"]] = (out, dur)
                got.append((out, random.uniform(0, max(0.0, min(dur - L - 0.2, dur * 0.5))), L))
            except Exception as e:
                print(f"  [영상] 다운로드 실패: {e}")
                got.append((None, 0.0, L))
        plan.extend(got)
        print(f"  [영상] {i+1}번 문장 '{kw}' → 컷 {len(lens)}개")
    print(f"  [영상] 클립 {clip_count}개, 컷 {len(plan)}개")
    return plan
