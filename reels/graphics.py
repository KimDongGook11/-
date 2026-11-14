"""영상에 얹는 그래픽 (PIL 투명 PNG). 글꼴은 Pretendard(없으면 Noto).

세로 A(에디토리얼 카드): title_a, hook_a
가로 B(인포그래픽 분할): panel_b, chapter_card, open_b
공통: number_frames(숫자 카드 카운트업), outro_card, thumbnail(유튜브)"""
import datetime as dt
import re

from PIL import Image, ImageDraw, ImageFilter

from . import config
from .fonts import pil as F
from .header import _wrap, parse_title
from .render import CARD, WINDOW

YELLOW, RED, WHITE, BLACK = (255, 212, 0), (232, 52, 52), (255, 255, 255), (0, 0, 0)
UP, DOWN = (255, 92, 92), (84, 150, 255)
NAVY = (10, 16, 32)
PANEL = (16, 24, 44, 235)
WEEK = "월화수목금토일"


def _canvas(w, h):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _wtext(word):
    return "".join(t for t, _ in word)


def _fit(d, title, max_w, sizes, max_lines, weight="Black"):
    words = parse_title(title)
    for size in sizes:
        f = F(weight, size)
        lines = _wrap(d, words, f, max_w)
        if len(lines) <= max_lines:
            return f, lines
    return f, lines


def _draw_lines(d, lines, f, x, y, align="left", width=None, fg=WHITE, hl=YELLOW, lh_ratio=1.3,
                stroke=0, block=False):
    """block=True: 강조 단어 뒤에 노란 블록(글자는 검정) — 썸네일용."""
    asc, desc = f.getmetrics()
    lh = int(f.size * lh_ratio)              # 글꼴마다 여백이 달라 글자 크기 기준으로 줄 간격 계산
    sp = d.textlength(" ", font=f)
    for ln in lines:
        lw = d.textlength(" ".join(_wtext(w) for w in ln), font=f)
        xx = x if align == "left" else x + (width - lw) / 2
        for word in ln:
            for t, is_hl in word:
                tw = d.textlength(t, font=f)
                if block and is_hl:
                    top = d.textbbox((xx, y), t, font=f)
                    d.rectangle([xx - 10, top[1] - 12, xx + tw + 10, top[3] + 12], fill=hl)
                    d.text((xx, y), t, font=f, fill=BLACK)
                else:
                    d.text((xx, y), t, font=f, fill=hl if (is_hl and not block) else fg,
                           stroke_width=stroke, stroke_fill=BLACK)
                xx += tw
            xx += sp
        y += lh
    return y


def meta_text(sc):
    if sc.get("pill") and sc.get("brand"):        # 그때 그 결정
        return f"{sc.get('tag', '')}  ·  {sc['brand'].split(' · ')[0]}  ·  {sc['pill']}"
    k = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    tag = sc.get("tag") or "오늘의 경제"
    return f"{tag}  ·  {k.month}월 {k.day}일 ({WEEK[k.weekday()]})"


# ---------------- 세로 A ----------------
def title_a(sc, out, W=1080, H=1920):
    """위쪽: 작은 메타 줄 + 노란 막대 + 왼쪽 정렬 큰 제목(최대 2줄). 반환: (경로, 제목 끝 y)"""
    img, d = _canvas(W, H)
    x, max_w = 80, W - 160
    d.text((x, 205), meta_text(sc), font=F("Medium", 34), fill=(255, 255, 255, 200))
    d.rectangle([x, 262, x + 70, 270], fill=YELLOW)
    f, lines = _fit(d, sc["hook_title"], max_w, (92, 84, 76, 68), 2)
    y = _draw_lines(d, lines, f, x, 292)
    img.save(out)
    return out, int(y)


def hook_a(sc, out, W=1080, H=1920):
    """첫 1.2초: 어두운 화면 가운데 아주 큰 제목."""
    img, d = _canvas(W, H)
    d.rectangle([0, 0, W, H], fill=(6, 9, 18, 200))
    f, lines = _fit(d, sc["hook_title"], W - 140, (132, 120, 108, 96), 3)
    block = int(f.size * 1.3) * len(lines)
    y0 = (H - block) / 2 - 60
    mt = meta_text(sc)
    mf = F("Bold", 40)
    d.text(((W - d.textlength(mt, font=mf)) / 2, y0 - 90), mt, font=mf, fill=YELLOW)
    _draw_lines(d, lines, f, 0, y0, align="center", width=W)
    img.save(out)
    return out


def card_frame(out, W=1080, H=1920):
    """영상 카드 테두리(얇은 밝은 선 + 아래 그림자)로 카드 모양을 또렷하게."""
    img, d = _canvas(W, H)
    x, y, w, h = CARD["x"], CARD["y"], CARD["w"], CARD["h"]
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x, y + 14, x + w, y + h + 14], radius=36, fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(18))
    hole = Image.new("L", (W, H), 255)
    ImageDraw.Draw(hole).rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=36, fill=0)
    img = Image.composite(sh, img, hole)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=36, outline=(255, 255, 255, 46), width=2)
    img.save(out)
    return out


# ---------------- 숫자 카드 ----------------
NUM_RE = re.compile(r"^([^\d\-+]*)([\-+]?\d[\d,]*\.?\d*)(.*)$")


def number_frames(value, label, direction, out_dir, w=820, h=480, frames=16):
    """숫자가 0에서 목표값까지 올라가는 프레임들. 반환: (파일 패턴, 프레임 수, 폭, 높이)"""
    out_dir.mkdir(parents=True, exist_ok=True)
    col = UP if direction == "up" else DOWN if direction == "down" else YELLOW
    arrow = "▲ " if direction == "up" else "▼ " if direction == "down" else ""
    m = NUM_RE.match(str(value).strip())
    big = F("Black", int(h * 0.34))
    small = F("SemiBold", int(h * 0.1))
    for i in range(frames):
        k = 1 - (1 - (i + 1) / frames) ** 3
        if m:
            pre, num, suf = m.groups()
            dec = len(num.split(".")[1]) if "." in num else 0
            target = float(num.replace(",", ""))
            cur = target * k
            txt = f"{pre}{cur:,.{dec}f}{suf}" if "," in num else f"{pre}{cur:.{dec}f}{suf}"
        else:
            txt = str(value)
        txt = arrow + txt
        img, d = _canvas(w, h)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(h * 0.09), fill=(12, 18, 34, 255),
                            outline=(255, 255, 255, 40), width=2)
        d.rectangle([0, int(h * 0.12), 8, int(h * 0.88)], fill=col)
        lw = d.textlength(label, font=small)
        d.text(((w - lw) / 2, h * 0.14), label, font=small, fill=(205, 212, 228))
        tw = d.textlength(txt, font=big)
        d.text(((w - tw) / 2, h * 0.36), txt, font=big, fill=col)
        sc = 0.9 + 0.1 * min(1.0, (i + 1) / (frames * 0.5))
        if sc < 1:
            canvas, _ = _canvas(w, h)
            s_img = img.resize((int(w * sc), int(h * sc)), Image.LANCZOS)
            canvas.paste(s_img, ((w - s_img.width) // 2, (h - s_img.height) // 2), s_img)
            img = canvas
        img.save(out_dir / f"{i:04d}.png")
    return str(out_dir / "%04d.png"), frames, w, h


# ---------------- 가로 B ----------------
PX, PW = 1320, 530        # 오른쪽 패널 x, 폭
KEY_BOX = (PX, 500, PW, 250)   # 핵심 카드 자리 (x, y, w, h)


def panel_b(lsc, ci, out, W=1920, H=1080):
    """챕터 ci(1부터)의 오른쪽 패널 + 위쪽 브랜드 줄. 핵심 카드 자리에는 챕터 요약을 넣어 둠
    (숫자 카드가 나오는 동안엔 그 위를 덮음)."""
    img, d = _canvas(W, H)
    ch = lsc["chapters"][ci - 1]
    ep, year = lsc.get("ep", ""), lsc.get("year")
    d.text((70, 42), f"경제 [원픽]   ·   그때 그 결정 {ep}", font=F("SemiBold", 30), fill=(255, 255, 255, 170))
    d.text((PX, 112), f"CHAPTER {ci}", font=F("Bold", 30), fill=YELLOW)
    tf, lines = _fit(d, ch["title"], PW, (64, 56, 50), 2)
    y = _draw_lines(d, lines, tf, PX, 156)
    d.rectangle([PX, y + 14, PX + 64, y + 21], fill=YELLOW)
    cy = ch.get("year") or year
    if cy:
        yf = F("Black", 150)
        d.text((PX - 6, 300), str(cy), font=yf, fill=(255, 255, 255, 46))
    # 핵심 카드 기본 내용: 챕터 요약
    x, yb, w, h = KEY_BOX
    d.rounded_rectangle([x, yb, x + w, yb + h], radius=22, fill=(255, 255, 255, 16),
                        outline=(255, 212, 0, 150), width=3)
    d.text((x + 28, yb + 24), "핵심", font=F("Bold", 28), fill=YELLOW)
    summ = ch.get("summary") or ch["title"]
    sf, sl = _fit(d, summ, w - 56, (40, 36, 32), 3, weight="Bold")
    _draw_lines(d, sl, sf, x + 28, yb + 72, lh_ratio=1.35)
    # 미니 타임라인
    chs = lsc["chapters"]
    ty = 820
    x0, x1 = PX + 10, PX + PW - 10
    d.line([(x0, ty), (x1, ty)], fill=(255, 255, 255, 70), width=3)
    n = len(chs)
    for k, c in enumerate(chs, start=1):
        cx = x0 + (x1 - x0) * (k - 1) / max(1, n - 1)
        cur = k == ci
        r = 11 if cur else 7
        d.ellipse([cx - r, ty - r, cx + r, ty + r], fill=YELLOW if cur else (150, 160, 180))
        lab = str(c.get("year") or "")
        if lab:
            lf = F("Bold" if cur else "Medium", 24)
            d.text((cx - d.textlength(lab, font=lf) / 2, ty + 18), lab, font=lf,
                   fill=YELLOW if cur else (170, 178, 196))
    comp = lsc.get("company") or {}
    info = "  ·  ".join(v for v in (comp.get("name_ko"), comp.get("country_ko"), comp.get("industry_ko")) if v)
    if info:
        d.text((PX, 905), info, font=F("Medium", 28), fill=(190, 198, 214))
    img.save(out)
    return out


def chapter_card(no, title, year, W, H, out):
    img, d = _canvas(W, H)
    d.rectangle([0, 0, W, H], fill=(8, 12, 24, 240))
    cy = H / 2
    lab = f"CHAPTER {no}"
    f1, f2 = F("Bold", 40), F("Black", 116)
    d.text(((W - d.textlength(lab, font=f1)) / 2, cy - 170), lab, font=f1, fill=YELLOW)
    d.text(((W - d.textlength(title, font=f2)) / 2, cy - 105), title, font=f2, fill=WHITE)
    if year:
        yf = F("SemiBold", 44)
        t = f"{year}"
        d.text(((W - d.textlength(t, font=yf)) / 2, cy + 70), t, font=yf, fill=(200, 208, 224))
    d.rectangle([W / 2 - 40, cy - 196, W / 2 + 40, cy - 190], fill=YELLOW)
    img.save(out)
    return out


def open_b(lsc, W, H, out):
    """장편 오프닝 타이틀."""
    img, d = _canvas(W, H)
    d.rectangle([0, 0, W, H], fill=(8, 12, 24, 225))
    mt = f"그때 그 결정  ·  {lsc.get('ep', '')}  ·  {lsc.get('year', '')}"
    mf = F("Bold", 40)
    f, lines = _fit(d, lsc["hook_title"], W - 400, (124, 112, 100), 2)
    block = int(f.size * 1.3) * len(lines)
    y0 = (H - block) / 2 + 20
    d.text(((W - d.textlength(mt, font=mf)) / 2, y0 - 90), mt, font=mf, fill=YELLOW)
    _draw_lines(d, lines, f, 0, y0, align="center", width=W)
    img.save(out)
    return out


# ---------------- 아웃트로 ----------------
def outro_card(W, H, out, vertical=True):
    img, d = _canvas(W, H)
    d.rectangle([0, 0, W, H], fill=(8, 10, 16, 240))
    f = F("Black", 170 if vertical else 150)
    cy = H / 2 - (120 if vertical else 80)
    parts = [("경제 ", WHITE), ("[", RED), ("원픽", YELLOW), ("]", RED)]
    tw = sum(d.textlength(t, font=f) for t, _ in parts)
    x = (W - tw) / 2
    for t, c in parts:
        d.text((x, cy - 90), t, font=f, fill=c)
        x += d.textlength(t, font=f)
    sub = "팔로우하고 매일 경제 한 개씩 받아보세요" if vertical else "구독하고 다음 이야기도 받아보세요"
    fs = F("Medium", 48 if vertical else 44)
    d.text(((W - d.textlength(sub, font=fs)) / 2, cy + 130), sub, font=fs, fill=(225, 228, 236))
    handle = config.env("BRAND_HANDLE", "@econonepick")
    fh = F("Bold", 40)
    hw = d.textlength(handle, font=fh)
    d.rounded_rectangle([(W - hw) / 2 - 26, cy + 220, (W + hw) / 2 + 26, cy + 290], radius=35, fill=WHITE)
    d.text(((W - hw) / 2, cy + 232), handle, font=fh, fill=BLACK)
    img.save(out)
    return out


# ---------------- 유튜브 썸네일 ----------------
def thumbnail(frame_png, title, year, ep, out, w=1280, h=720):
    """왼쪽: 남색 바탕 큰 두 줄 문구(강조 단어는 노란 블록) / 오른쪽: 장면 이미지가 사선으로 이어짐."""
    base = Image.new("RGB", (w, h), NAVY)
    if frame_png:
        ph = Image.open(frame_png).convert("RGB")
        PWID = 700
        r = max(PWID / ph.width, h / ph.height)
        ph = ph.resize((int(ph.width * r) + 1, int(ph.height * r) + 1), Image.LANCZOS)
        ph = ph.crop(((ph.width - PWID) // 2, (ph.height - h) // 2, (ph.width - PWID) // 2 + PWID, (ph.height - h) // 2 + h))
        from PIL import ImageEnhance
        ph = ImageEnhance.Color(ph).enhance(0.85)
        ph = ImageEnhance.Contrast(ph).enhance(1.08)
        m = Image.new("L", (PWID, h), 0)
        md = ImageDraw.Draw(m)
        md.polygon([(150, 0), (PWID, 0), (PWID, h), (0, h)], fill=255)
        m = m.filter(ImageFilter.GaussianBlur(2))
        base.paste(ph, (w - PWID, 0), m)
    img = base.convert("RGBA")
    d = ImageDraw.Draw(img)
    x = 60
    lab = "그때 그 결정"
    lf = F("Black", 40)
    lw = d.textlength(lab, font=lf)
    d.rounded_rectangle([x, 52, x + lw + 40, 112], radius=10, fill=RED)
    d.text((x + 20, 58), lab, font=lf, fill=WHITE)
    sub = "  ·  ".join(str(v) for v in (ep, year) if v)
    if sub:
        d.text((x + lw + 62, 62), sub, font=F("Bold", 36), fill=(220, 226, 238))
    f, lines = _fit(d, title, 600, (128, 116, 104, 92, 84), 2)
    lh = int(f.size * 1.22)
    y = h - 70 - lh * len(lines)
    _draw_lines(d, lines, f, x, y, lh_ratio=1.22, block=True, stroke=0)
    img.convert("RGB").save(out, quality=93)
    return out
