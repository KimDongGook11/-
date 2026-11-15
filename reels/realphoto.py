"""유튜브 썸네일용 실제 기업 사진: 영어 위키백과 문서에 실린 위키미디어 공용 사진(자유 라이선스)을 가져옵니다.
로고·지도·도표·아이콘은 빼고, 가로로 크고 선명한 실제 사진만 고릅니다. 출처 문구도 함께 돌려줍니다."""
import random
import re
from io import BytesIO

import requests
from PIL import Image

from .utils import load_state, save_state

WIKI = "https://en.wikipedia.org/w/api.php"
UA = {"User-Agent": "EconOnePickBot/1.0 (personal YouTube economics channel; contact via GitHub)"}
SKIP = re.compile(r"logo|icon|map|flag|chart|graph|diagram|signature|seal|coat.of.arms|symbol|wordmark|"
                  r"screenshot|banner|plot|revenue|stock|share.price|org.?chart|commons-|wiki|edit-|question",
                  re.I)
FREE = re.compile(r"^(cc|public domain|pd)", re.I)


def _strip(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _candidates(title):
    r = requests.get(WIKI, headers=UA, timeout=20, params={
        "action": "query", "format": "json", "formatversion": 2, "redirects": 1, "titles": title,
        "generator": "images", "gimlimit": 60, "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1600})
    r.raise_for_status()
    out = []
    for p in r.json().get("query", {}).get("pages", []):
        ii = (p.get("imageinfo") or [{}])[0]
        name = p.get("title", "")
        if ii.get("mime") != "image/jpeg" or SKIP.search(name):
            continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if w < 1000 or h < 560 or w < h * 1.15:           # 가로 사진만 (썸네일 16:9에 맞게)
            continue
        meta = ii.get("extmetadata", {})
        lic = _strip(meta.get("LicenseShortName", {}).get("value"))
        if not FREE.search(lic) or meta.get("NonFree", {}).get("value") == "true":
            continue
        out.append({"name": name, "url": ii.get("thumburl") or ii["url"], "area": w * h,
                    "credit": f"{_strip(meta.get('Artist', {}).get('value'))[:60] or 'Unknown'} / {lic} / Wikimedia Commons",
                    "page": ii.get("descriptionurl", "")})
    return out


def company_photo(titles, workdir, episode=""):
    """(사진 경로, 출처 문구) 또는 (None, None)."""
    used = set(load_state("thumb_used", []))
    cands, seen = [], set()
    for t in [t for t in dict.fromkeys(titles) if t][:4]:
        try:
            for c in _candidates(t):
                if c["name"] not in seen:
                    seen.add(c["name"])
                    cands.append(c)
        except Exception as e:
            print(f"  [썸네일] 위키 사진 검색 실패({t}): {e}")
    fresh = [c for c in cands if c["name"] not in used] or cands
    if not fresh:
        print("  [썸네일] 쓸 만한 실제 사진 없음 → 기존 방식")
        return None, None
    fresh.sort(key=lambda c: c["area"], reverse=True)
    order = random.sample(fresh[:5], min(5, len(fresh[:5])))
    if episode and len(fresh) > 1:     # 에피소드 내용·시대와 가장 어울리는 사진을 AI가 고름 (실패하면 무작위)
        try:
            from . import llm
            lst = "\n".join(f"{i}. {c['name']}" for i, c in enumerate(fresh[:25]))
            ans = llm.ask_json(f"""유튜브 경제 다큐 썸네일 배경 사진을 고르려고 해.
에피소드: {episode}
아래 위키미디어 사진 파일 이름 중 이 에피소드(그 회사, 그 시대, 그 사건)와 가장 잘 어울리는 사진 번호를 순서대로 최대 3개.
시대가 안 맞는 최신 제품, 추모·행사 사진, 사건과 무관한 인물 사진은 빼. 적당한 게 없으면 빈 목록.
{lst}
JSON으로만: {{"pick": [번호, ...]}}""", temperature=0.2)
            picks = [fresh[int(i)] for i in ans.get("pick", []) if str(i).isdigit() and int(i) < len(fresh[:25])]
            order = picks + [c for c in order if c not in picks]
        except Exception as e:
            print(f"  [썸네일] 사진 고르기 AI 실패(무작위): {e}")
    for c in order:
        try:
            r = requests.get(c["url"], headers=UA, timeout=60)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert("RGB")
        except Exception as e:
            print(f"  [썸네일] 사진 내려받기 실패: {e}")
            continue
        out = workdir / "thumb_real.jpg"
        img.save(out, quality=95)
        save_state("thumb_used", (load_state("thumb_used", []) + [c["name"]])[-60:])
        print(f"  [썸네일] 실제 사진: {c['name']} ({c['credit']})")
        return out, f"{c['credit']} — {c['page']}"
    return None, None
