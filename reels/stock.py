"""Pixabay 무료 스톡 영상: 문장마다 2~4초 단위로 컷을 나눠 배경 샷 목록을 만듭니다.
- 세로 영상(릴스)이면 세로 클립 → 4K/고화질 순으로 우선
- 같은 클립은 최대한 다시 쓰지 않고, 다시 쓸 때는 다른 구간을 씀
- 최근 영상들에 쓴 클립·같은 촬영자(같은 배우가 나오는 시리즈)는 피함 (state/clips_used.json)"""
import random

import requests

from . import config
from .utils import load_state, save_state

API = "https://pixabay.com/api/videos/"
FALLBACK_QUERIES = ["business meeting", "stock market screen", "city skyline", "office building", "container port"]
# 실사 경제 영상과 어울리지 않는 클립(만화·이모지·추상 그래픽 등)은 제외
BLOCK_TAGS = {"cartoon", "animation", "animated", "emoji", "emoticon", "smiley", "anime", "illustration", "3d",
              "render", "rendering", "abstract", "fractal", "kaleidoscope", "tunnel", "particles", "particle",
              "neon", "loop", "pattern", "motion graphics", "background", "wallpaper", "halloween", "spider",
              "monster", "zombie", "horror", "fantasy", "magic", "cgi", "vj", "glitch", "hologram"}
# 사용자 규칙(2026-11-22): 담배·향정신성 약물·약품, 사회 통념에서 벗어나는 장면(술 취함·선정·폭력·도박 등)은 배경에 쓰지 않음
SENSITIVE_TAGS = {
    "cigarette", "cigarettes", "cigar", "cigars", "tobacco", "smoking", "smoker", "smokers", "vape", "vaping",
    "e-cigarette", "hookah", "shisha", "nicotine", "ashtray",
    "drug", "drugs", "narcotic", "narcotics", "cocaine", "heroin", "meth", "marijuana", "cannabis", "weed",
    "hemp", "joint", "psychedelic", "lsd", "mushrooms", "overdose", "addiction", "addict", "syringe",
    "injection", "needle", "pill", "pills", "capsule", "capsules", "tablet pills", "medicine", "medicines",
    "medication", "medications", "pharmacy", "pharmaceutical", "prescription", "drugstore", "painkiller",
    "drunk", "hangover", "alcoholic", "alcoholism", "intoxicated",
    "sexy", "sensual", "erotic", "nude", "naked", "lingerie", "bikini", "underwear", "stripper", "seductive",
    "gun", "guns", "pistol", "rifle", "weapon", "weapons", "shooting", "blood", "bloody", "violence",
    "violent", "corpse", "dead body", "suicide", "knife", "gambling", "casino", "poker", "slot machine",
}
MAX_MB = 70
MIN_REL = 0.5          # 검색어 단어 중 이 비율 이상이 태그에 있어야 '관련 있는 영상'으로 씀
LAST_MISSING = set()   # 직전 plan_shots에서 관련 영상을 못 찾은 문장 번호 (그 자리는 그래픽으로 채움)


def _search(q, cache):
    if q in cache:
        return cache[q]
    try:
        r = requests.get(API, params={"key": config.PIXABAY_API_KEY, "q": q[:100], "video_type": "film",
                                      "per_page": 100, "safesearch": "true"}, timeout=20)
        r.raise_for_status()
        hits = [h for h in r.json().get("hits", []) if not _blocked(h)]
    except Exception as e:
        print(f"  [영상] '{q}' 검색 실패: {e}")
        hits = []
    cache[q] = hits
    return hits


def _rendition(hit, vertical, card=False):
    """해당 클립에서 쓸 파일: 화질 기준을 넘는 것 중 가장 가벼운 것, 없으면 가장 큰 것."""
    vids = hit.get("videos", {})
    cands = [vids[k] for k in ("large", "medium", "small")
             if (vids.get(k) or {}).get("url") and vids[k].get("size", 0) <= MAX_MB * 1e6]
    if not cands:
        return None

    def ok(v):
        w, h = v.get("width", 0), v.get("height", 0)
        if card:       # 가운데 카드/창에 넣는 경우: 짧은 변이 720 이상이면 충분
            return min(w, h) >= 720
        if vertical:   # 세로 클립(폭 1080 이상) 또는 4K 가로(가운데를 잘라도 폭 1215)
            return (h > w and w >= 1080) or h >= 2160
        return w >= 1920
    good = [v for v in cands if ok(v)]
    if good:
        return min(good, key=lambda v: v.get("size", 0))
    return max(cands, key=lambda v: v.get("width", 0) * v.get("height", 0))


def _tags(hit):
    return {t.strip().lower() for t in str(hit.get("tags", "")).split(",") if t.strip()}


def _blocked(hit):
    tags = _tags(hit)
    words = {w for t in tags for w in t.split()}
    bad = BLOCK_TAGS | SENSITIVE_TAGS
    return bool(tags & bad or words & bad)


def _sensitive_query(q):
    ql = q.lower()
    return any(w in SENSITIVE_TAGS for w in ql.split()) or any(t in ql for t in SENSITIVE_TAGS if " " in t)


def _relevance(hit, query):
    """검색어 단어가 클립 태그에 얼마나 들어 있는지 (0~1)."""
    q = {w for w in query.lower().split() if len(w) > 2}
    if not q:
        return 0.0
    words = {w for t in _tags(hit) for w in t.split()}
    return len(q & words) / len(q)


def _score(hit, vertical, query=""):
    v = hit.get("videos", {}).get("large") or {}
    w, h = v.get("width", 0), v.get("height", 0)
    s = 4 * _relevance(hit, query)
    if vertical and h > w:
        s += 1                      # 세로 클립 약간 우선
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


def plan_shots(segments, durs, workdir, vertical=True, shot_len=2.8, max_clips=40, card=False):
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
    missing = set()
    LAST_MISSING.clear()
    clip_count = 0
    hist = load_state("clips_used", {}) or {}
    recent_ids = set(hist.get("ids", []))           # 최근 영상들에 쓴 클립
    recent_users = set(hist.get("users", []))       # 최근 영상들에 쓴 촬영자
    user_n = {}                                     # 이번 영상에서 촬영자별 클립 수
    new_ids, new_users = [], []

    def choose(pool):
        """같은 사람이 반복해서 나오지 않게: 새 클립·새 촬영자 → 최근 촬영자 → 최근 클립 순으로 고름."""
        fresh = [h for h in pool if h["id"] not in used_ids]
        tiers = [
            [h for h in fresh if h["id"] not in recent_ids and h.get("user_id") not in recent_users
             and user_n.get(h.get("user_id"), 0) < 1],
            [h for h in fresh if h["id"] not in recent_ids and user_n.get(h.get("user_id"), 0) < 2],
            [h for h in fresh if user_n.get(h.get("user_id"), 0) < 2],
            fresh,
        ]
        top = {h["id"] for h in pool[:30]}   # 관련도 순 상위 안에서만 (엉뚱한 화면 방지)
        for k, t in enumerate(tiers):
            t = [h for h in t if h["id"] in top] or (t if k == len(tiers) - 1 else [])
            if t:
                return t[0]
        return None
    for i, (seg, lens) in enumerate(zip(segments, cuts)):
        kw = (seg.get("keywords") or "business meeting").strip()
        if _sensitive_query(kw):
            print(f"  [영상] {i + 1}번 문장 검색어 '{kw}'는 금지 장면이라 일반 장면으로 바꿈")
            kw = "business meeting"
        ws = kw.split()
        # 일반 장면(FALLBACK_QUERIES)으로 채우지 않음: 멘트와 관련 없는 화면이 나가지 않게 (사용자 요청 11/22)
        queries = [kw, " ".join(ws[-2:]), " ".join(ws[:2])]
        pool = []
        for q in dict.fromkeys(q for q in queries if q):
            rel_hits = [h for h in _search(q, cache) if _relevance(h, q) >= MIN_REL]
            if rel_hits:
                pool = sorted(rel_hits, key=lambda h: -_score(h, vertical, q))
                break
        got, seg_files = [], []
        for L in lens:
            hit = choose(pool) if clip_count < max_clips and pool else None
            if hit is None and seg_files:        # 새 클립이 없으면 이 문장에서 받은 클립의 다른 구간 재사용
                path, dur = random.choice(seg_files)
                got.append((path, random.uniform(0, max(0.0, dur - L - 0.2)), L))
                continue
            if hit is None:
                got.append((None, 0.0, L))
                continue
            used_ids.add(hit["id"])
            user_n[hit.get("user_id")] = user_n.get(hit.get("user_id"), 0) + 1
            new_ids.append(hit["id"])
            new_users.append(hit.get("user_id"))
            v = _rendition(hit, vertical, card)
            if not v:
                got.append((None, 0.0, L))
                continue
            out = workdir / f"clip_{hit['id']}.mp4"
            try:
                _download(v["url"], out)
                clip_count += 1
                dur = float(hit.get("duration") or 8)
                files[hit["id"]] = (out, dur)
                seg_files.append((out, dur))
                got.append((out, random.uniform(0, max(0.0, min(dur - L - 0.2, dur * 0.5))), L))
            except Exception as e:
                print(f"  [영상] 다운로드 실패: {e}")
                got.append((None, 0.0, L))
        plan.extend(got)
        if any(c is None for c, _, _ in got):
            missing.add(i)
        print(f"  [영상] {i+1}번 문장 '{kw}' → " + ("관련 영상 없음 → 그래픽" if i in missing else f"컷 {len(lens)}개"))
    LAST_MISSING.update(missing)
    reused = sum(1 for i in new_ids if i in recent_ids)
    print(f"  [영상] 클립 {clip_count}개, 컷 {len(plan)}개 (최근 영상과 겹친 클립 {reused}개, 촬영자 {len(set(new_users))}명)")
    if new_ids:
        save_state("clips_used", {"ids": (hist.get("ids", []) + new_ids)[-600:],
                                  "users": [u for u in (hist.get("users", []) + list(dict.fromkeys(new_users)))
                                            if u is not None][-200:]})
    return plan
