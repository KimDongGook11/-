"""썸네일용 이중 노출(더블 익스포저) 인물: 사람 옆모습 실루엣 안에서 왼쪽은 얼굴, 오른쪽은 도시 건물.
사진은 Pixabay 무료 사진(상업 이용 가능)에서 가져오고, 사람 오려내기는 rembg(없으면 OpenCV GrabCut)."""
import random

import numpy as np
import requests
from PIL import Image, ImageFilter, ImageOps

from . import config

API = "https://pixabay.com/api/"
CITY = {"미국": "new york skyline", "일본": "tokyo skyline", "한국": "seoul skyline", "중국": "shanghai skyline",
        "영국": "london skyline", "독일": "frankfurt skyline", "프랑스": "paris skyline", "대만": "taipei skyline",
        "네덜란드": "amsterdam city", "스위스": "zurich city", "스웨덴": "stockholm city", "핀란드": "helsinki city",
        "캐나다": "toronto skyline", "인도": "mumbai skyline", "싱가포르": "singapore skyline", "홍콩": "hong kong skyline"}
FACE_QUERIES = ["businessman suit portrait white background", "man suit portrait isolated",
                "businessman portrait studio", "man suit standing portrait"]
BLOCK = {"illustration", "cartoon", "drawing", "vector", "anime", "3d", "render", "clipart", "painting", "art"}


def _search(q, orientation="all", n=40):
    if not config.PIXABAY_API_KEY:
        return []
    r = requests.get(API, params={"key": config.PIXABAY_API_KEY, "q": q, "image_type": "photo",
                                  "orientation": orientation, "per_page": n, "safesearch": "true",
                                  "min_width": 1000}, timeout=20)
    r.raise_for_status()
    hits = []
    for h in r.json().get("hits", []):
        tags = {t.strip().lower() for t in h.get("tags", "").split(",")}
        if tags & BLOCK:
            continue
        hits.append(h)
    return hits


def _download(url):
    from io import BytesIO
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return Image.open(BytesIO(r.content)).convert("RGB")


def cutout(img):
    """사람만 남긴 RGBA."""
    try:
        from rembg import new_session, remove
        return remove(img, session=new_session("u2net_human_seg")).convert("RGBA")
    except Exception as e:
        print(f"  [썸네일] rembg 사용 불가 → GrabCut: {e}")
    import cv2
    a = np.array(img)[:, :, ::-1].copy()
    h, w = a.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    rect = (int(w * 0.08), int(h * 0.04), int(w * 0.84), int(h * 0.95))
    bg, fg = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(a, mask, rect, bg, fg, 5, cv2.GC_INIT_WITH_RECT)
    m = np.where((mask == 1) | (mask == 3), 255, 0).astype("uint8")
    out = img.convert("RGBA")
    out.putalpha(Image.fromarray(m))
    return out


def _smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def compose(person_rgba, city_rgb, height=900, blur=1.0):
    """정장 인물 실루엣 안에 도시: 위·왼쪽은 얼굴과 셔츠, 아래·오른쪽으로 갈수록 건물. 따뜻한 세피아 톤."""
    p = person_rgba.crop(person_rgba.getbbox())
    alpha = np.array(p.split()[-1]).astype(float) / 255
    cols = alpha[: int(alpha.shape[0] * 0.5)].sum(axis=0)
    cx = (cols * np.arange(len(cols))).sum() / max(cols.sum(), 1)
    if cx > len(cols) * 0.55:                  # 인물이 오른쪽으로 치우쳐 있으면 반전 (얼굴이 왼쪽 위로)
        p = ImageOps.mirror(p)
    r = height / p.height
    p = p.resize((int(p.width * r), height), Image.LANCZOS)
    w, h = p.size
    a = p.split()[-1].filter(ImageFilter.GaussianBlur(2.5))
    face = ImageOps.autocontrast(ImageOps.grayscale(p.convert("RGB")), cutoff=2)
    face = np.array(ImageOps.colorize(face, (38, 30, 22), (248, 240, 222))).astype(float)
    cr = max(w / city_rgb.width, h / city_rgb.height)
    city = city_rgb.resize((int(city_rgb.width * cr) + 1, int(city_rgb.height * cr) + 1), Image.LANCZOS)
    city = city.crop(((city.width - w) // 2, city.height - h, (city.width - w) // 2 + w, city.height))
    cg = ImageOps.grayscale(city)
    city_warm = np.array(ImageOps.colorize(cg, (30, 22, 14), (255, 236, 196))).astype(float) * 0.55 + \
        np.array(city).astype(float) * 0.45          # 색은 살리되 따뜻한 톤으로
    screen = 255 - (255 - face) * (255 - city_warm) / 255
    yy, xx = np.mgrid[0:h, 0:w]
    t = (0.65 * yy / h + 0.35 * xx / w)[:, :, None]   # 위·왼쪽 0 → 아래·오른쪽 1
    g = _smoothstep(t, 0.32, 0.70)
    upper = face * 0.8 + screen * 0.2
    lower = city_warm * 0.75 + screen * 0.25
    out = upper * (1 - g) + lower * g
    img = Image.fromarray(np.clip(out, 0, 255).astype("uint8")).convert("RGBA")
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    img.putalpha(a)
    return img


def figure_for(country_ko, workdir, seed=None):
    """에피소드용 인물+도시 합성 이미지 경로 (실패하면 None)."""
    rnd = random.Random(seed)
    try:
        faces = []
        for q in FACE_QUERIES:
            faces = _search(q, "vertical")
            if faces:
                break
        city_q = CITY.get((country_ko or "").strip(), "city skyline")
        cities = _search(city_q, "vertical") or _search(city_q, "horizontal") or _search("city skyline", "all")
        if not faces or not cities:
            return None
        face = _download(rnd.choice(faces[:12])["largeImageURL"])
        city = _download(rnd.choice(cities[:12])["largeImageURL"])
        fig = compose(cutout(face), city)
        out = workdir / "thumb_figure.png"
        fig.save(out)
        print(f"  [썸네일] 이중 노출 인물 완성 ({city_q})")
        return out
    except Exception as e:
        print(f"  [썸네일] 인물 합성 실패(장면 사진으로 대체): {e}")
        return None
