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


def number_frames(value, label, direction, out_dir, w=820, h=480, frames=16, change=""):
    """숫자가 0에서 목표값까지 올라가는 프레임들. 반환: (파일 패턴, 프레임 수, 폭, 높이)
    change(등락폭)가 있으면 가격 아래 줄에 따로 표시."""
    out_dir.mkdir(parents=True, exist_ok=True)
    col = UP if direction == "up" else DOWN if direction == "down" else YELLOW
    arrow = "▲ " if direction == "up" else "▼ " if direction == "down" else ""
    m = NUM_RE.match(str(value).strip())
    small = F("SemiBold", int(h * 0.1))
    # 최종 숫자(가장 긴 문자열)가 카드 폭의 88% 안에 들어오도록 글자 크기 자동 축소
    final = arrow + str(value).strip()
    size = int(h * 0.34)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    while size > 20 and probe.textlength(final, font=F("Black", size)) > w * 0.88:
        size -= 2
    if change:   # 두 줄: 가격은 조금 작게, 등락폭은 그 아래
        size = min(size, int(h * 0.27))
    big = F("Black", size)
    cf = None
    if change:
        csize = int(size * 0.6)
        while csize > 16 and probe.textlength(change, font=F("Bold", csize)) > w * 0.8:
            csize -= 2
        cf = F("Bold", csize)
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
        d.text(((w - tw) / 2, h * (0.31 if cf else 0.36)), txt, font=big, fill=col)
        if cf:
            cw = d.textlength(change, font=cf)
            d.text(((w - cw) / 2, h * 0.31 + big.size * 1.12), change, font=cf, fill=col)
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
    series = lsc.get("series_name", "그때 그 결정")
    d.text((70, 42), f"경제 [원픽]   ·   {series} {ep}".rstrip(), font=F("SemiBold", 30), fill=(255, 255, 255, 170))
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
    mt = lsc.get("open_meta") or f"그때 그 결정  ·  {lsc.get('ep', '')}  ·  {lsc.get('year', '')}"
    mf = F("Bold", 40)
    f, lines = _fit(d, lsc["hook_title"], W - 400, (124, 112, 100), 2)
    block = int(f.size * 1.3) * len(lines)
    y0 = (H - block) / 2 + 20
    d.text(((W - d.textlength(mt, font=mf)) / 2, y0 - 90), mt, font=mf, fill=YELLOW)
    _draw_lines(d, lines, f, 0, y0, align="center", width=W)
    img.save(out)
    return out


def speaker_badge(name, role, color, out, w=360, h=84):
    """이슈 뒷담화: 지금 말하는 사람 이름표 (영상 창 왼쪽 아래)."""
    img, d = _canvas(w, h)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=(8, 12, 24, 215), outline=color + (255,), width=3)
    d.ellipse([22, h / 2 - 13, 48, h / 2 + 13], fill=color + (255,))
    rf, nf = F("SemiBold", 26), F("Black", 38)
    d.text((66, h / 2 - 15), role, font=rf, fill=(200, 208, 224))
    d.text((66 + d.textlength(role, font=rf) + 14, h / 2 - 25), name, font=nf, fill=WHITE)
    img.save(out)
    return out


def _line_w(d, ln, f):
    return d.textlength(" ".join(_wtext(x) for x in ln), font=f)


def _headline_lines(d, text, max_w, sizes):
    """헤드라인 줄바꿈: 의미 단위로 끊음 (사용자 요청 11/22).
    1) AI가 표시한 ' / ' 자리에서 끊고, 각 줄이 들어가는 가장 큰 글자 크기를 고름
    2) 표시가 없으면 한 줄로 들어가는지 보고, 안 되면 쉼표 뒤 → 두 줄 길이가 비슷한 단어 경계 순으로 두 줄로
    3) 그래도 안 들어가면 기존 방식(세 줄까지 자동 줄바꿈)"""
    parts = [p.strip() for p in text.split(" / ") if p.strip()] if " / " in text else None
    if parts and len(parts) <= 3:
        lines = [parse_title(p) for p in parts]
        for size in sizes:
            f = F("Black", size)
            if all(_line_w(d, ln, f) <= max_w for ln in lines):
                return f, lines
        text = " ".join(parts)
    words = parse_title(text.replace(" / ", " "))
    if _line_w(d, words, F("Black", int(sizes[0] * 0.75))) <= max_w:   # 짧으면 한 줄
        for size in sizes:
            f = F("Black", size)
            if _line_w(d, words, f) <= max_w:
                return f, [words]
    commas = [k for k in range(1, len(words)) if _wtext(words[k - 1]).endswith((",", "·", ":", "…"))]
    # 1순위: 쉼표 뒤 (글자를 조금 줄여서라도), 2순위: 두 줄 길이가 비슷한 자리
    for ks, floor in ((commas, 0.6), (range(1, len(words)), 0.0)):
        for size in sizes:
            if size < sizes[0] * floor:
                break
            f = F("Black", size)
            cands = []
            for k in ks:
                wa, wb = _line_w(d, words[:k], f), _line_w(d, words[k:], f)
                if max(wa, wb) <= max_w:
                    cands.append((len(words) - k == 1, abs(wa - wb), k))   # 마지막 한 단어만 떨어지는 건 피함
            if cands:
                k = min(cands)[2]
                return f, [words[:k], words[k:]]
    return _fit(d, text.replace(" / ", " "), max_w, sizes, 3)


def headline_card(h, out, w=1000, hgt=560):
    """온라인 기사 헤드라인 카드: 흰 종이 위에 매체·날짜, 한국어 헤드라인(크게), 원문(작게).
    h = {"ko": 번역, "orig": 원문, "source": 매체, "date": "2026-11-21"}"""
    img, d = _canvas(w, hgt)
    d.rounded_rectangle([6, 10, w - 1, hgt - 1], radius=18, fill=(0, 0, 0, 90))            # 그림자
    d.rounded_rectangle([0, 0, w - 8, hgt - 10], radius=18, fill=(250, 248, 242, 255))
    pad = 44
    d.rectangle([pad, 40, pad + 10, 88], fill=RED)
    sf = F("Black", 40)
    d.text((pad + 26, 40), h.get("source", "")[:30], font=sf, fill=(20, 20, 24))
    if h.get("date"):
        df = F("Medium", 30)
        d.text((w - 8 - pad - d.textlength(h["date"], font=df), 48), h["date"], font=df, fill=(110, 110, 118))
    d.line([(pad, 112), (w - 8 - pad, 112)], fill=(20, 20, 24), width=3)
    ko = h.get("ko") or h.get("orig") or ""
    orig = h.get("orig") or ""
    bottom = hgt - 10 - (150 if orig and orig != ko else 80)
    big = int(min(96, w * 0.085))
    tf, lines = _headline_lines(d, ko, w - 8 - pad * 2, tuple(range(big, 40, -4)))
    block = int(tf.size * 1.32) * len(lines)
    _draw_lines(d, lines, tf, pad, 130 + max(0, (bottom - 130 - block) // 2), fg=(16, 16, 20), hl=RED, lh_ratio=1.32)
    if orig and orig != ko:
        ol = _fit(d, orig, w - 8 - pad * 2, (30, 28, 26, 24), 2, weight="Medium")
        _draw_lines(d, ol[1], ol[0], pad, bottom + 4, fg=(105, 105, 112), hl=(105, 105, 112), lh_ratio=1.3)
    d.text((pad, hgt - 10 - 50), "온라인 기사 헤드라인", font=F("SemiBold", 24), fill=(150, 150, 156))
    img.save(out)
    return out


def topic_card(title, sub, out, w=1000, hgt=560):
    """관련 영상도 헤드라인도 없을 때 채우는 주제 카드 (그때 그 결정 등)."""
    img, d = _canvas(w, hgt)
    d.rounded_rectangle([0, 0, w - 1, hgt - 1], radius=22, fill=(14, 22, 42, 245), outline=YELLOW + (200,), width=3)
    if sub:
        d.text((48, 44), sub[:40], font=F("Bold", 34), fill=YELLOW)
    tf, lines = _fit(d, title, w - 96, (84, 72, 62, 54), 3)
    block = int(tf.size * 1.3) * len(lines)
    _draw_lines(d, lines, tf, 48, (hgt - block) / 2 + 20)
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
THUMB_YEL = (255, 204, 0)


def thumbnail(frame_png, line1, line2, sub, ep, out, figure=None, w=1280, h=720):
    """노란 배경 + 쌓인 제목 상자(검정/노랑, 흰/검정) + EP 빨간 상자 + 오른쪽 이중 노출 인물 + 채널 로고."""
    base = Image.new("RGB", (w, h), THUMB_YEL)
    if frame_png:
        ph = Image.open(frame_png).convert("RGB")
        r = max(w / ph.width, h / ph.height)
        ph = ph.resize((int(ph.width * r) + 1, int(ph.height * r) + 1), Image.LANCZOS).crop((0, 0, w, h))
        from PIL import ImageOps
        ph = ImageOps.colorize(ImageOps.grayscale(ph), (120, 70, 0), (255, 214, 60))
        base = Image.blend(base, ph.filter(ImageFilter.GaussianBlur(3)), 0.32)
    img = base.convert("RGBA")
    if figure:
        fig = Image.open(figure).convert("RGBA")
        sc = min(600 / fig.width, 760 / fig.height)          # 오른쪽 600×760 상자에 맞춤 (상반신)
        fig = fig.resize((int(fig.width * sc), int(fig.height * sc)), Image.LANCZOS)
        fx, fy = w - fig.width - 10, h - fig.height + 30
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sh.paste((0, 0, 0, 110), (fx + 12, fy + 16), fig.split()[-1])
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))
        img.alpha_composite(fig, (fx, fy))
    d = ImageDraw.Draw(img)
    ef = F("Black", 44)
    if ep:
        tw = d.textlength(ep, font=ef)
        d.rectangle([56, 112, 56 + tw + 36, 176], fill=(178, 34, 34))
        d.text((74, 116), ep, font=ef, fill=WHITE)
    y = 196
    for text, bg, fg in [(line1, BLACK, THUMB_YEL), (line2, WHITE, BLACK)]:
        if not text:
            continue
        for size in (108, 96, 86, 76):
            f1 = F("Black", size)
            if d.textlength(text, font=f1) <= 640:
                break
        bb = d.textbbox((0, 0), text, font=f1)
        th = bb[3] - bb[1]
        tw = d.textlength(text, font=f1)
        d.rectangle([56, y, 56 + tw + 48, y + th + 44], fill=bg)
        d.text((80, y + 22 - bb[1]), text, font=f1, fill=fg)
        y += th + 44
    if sub:
        d.text((60, y + 24), sub, font=F("Black", 40), fill=BLACK)
    lf = F("Black", 34)
    parts = [("경제 ", WHITE), ("[", (230, 60, 50)), ("원픽", THUMB_YEL), ("]", (230, 60, 50))]
    lw = sum(d.textlength(t, font=lf) for t, _ in parts)
    d.rounded_rectangle([w - lw - 70, 30, w - 30, 92], radius=31, fill=BLACK)
    x = w - lw - 50
    for t, c in parts:
        d.text((x, 38), t, font=lf, fill=c)
        x += d.textlength(t, font=lf)
    img.convert("RGB").save(out, quality=93)
    return out


def thumbnail_photo(photo, line1, line2, sub, ep, out, w=1280, h=720):
    """실제 사진을 화면 가득 + 왼쪽 어둡게 + 기존과 같은 제목 상자·EP·채널 로고 (합성 없이 사진 그대로)."""
    from PIL import ImageEnhance
    ph = Image.open(photo).convert("RGB")
    r = max(w / ph.width, h / ph.height)
    ph = ph.resize((int(ph.width * r) + 1, int(ph.height * r) + 1), Image.LANCZOS)
    x0 = max(0, int((ph.width - w) * 0.6))                 # 가운데보다 살짝 오른쪽을 살림 (왼쪽은 글자)
    y0 = max(0, (ph.height - h) // 2)
    ph = ph.crop((x0, y0, x0 + w, y0 + h))
    ph = ImageEnhance.Contrast(ImageEnhance.Color(ph).enhance(1.08)).enhance(1.06)
    img = ph.convert("RGBA")
    grad = Image.new("L", (w, 1))
    grad.putdata([int(200 * max(0.0, 1 - x / (w * 0.62)) ** 1.4) for x in range(w)])
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    shade.putalpha(grad.resize((w, h)))
    img.alpha_composite(shade)
    d = ImageDraw.Draw(img)
    ef = F("Black", 44)
    if ep:
        tw = d.textlength(ep, font=ef)
        d.rectangle([56, 112, 56 + tw + 36, 176], fill=(178, 34, 34))
        d.text((74, 116), ep, font=ef, fill=WHITE)
    y = 196
    for text, bg, fg in [(line1, BLACK, THUMB_YEL), (line2, WHITE, BLACK)]:
        if not text:
            continue
        for size in (108, 96, 86, 76):
            f1 = F("Black", size)
            if d.textlength(text, font=f1) <= 640:
                break
        bb = d.textbbox((0, 0), text, font=f1)
        th = bb[3] - bb[1]
        tw = d.textlength(text, font=f1)
        d.rectangle([56, y, 56 + tw + 48, y + th + 44], fill=bg)
        d.text((80, y + 22 - bb[1]), text, font=f1, fill=fg)
        y += th + 44
    if sub:
        sf = F("Black", 40)
        d.text((62, y + 26), sub, font=sf, fill=(0, 0, 0, 160))
        d.text((60, y + 24), sub, font=sf, fill=WHITE)
    lf = F("Black", 34)
    parts = [("경제 ", WHITE), ("[", (230, 60, 50)), ("원픽", THUMB_YEL), ("]", (230, 60, 50))]
    lw = sum(d.textlength(t, font=lf) for t, _ in parts)
    d.rounded_rectangle([w - lw - 70, 30, w - 30, 92], radius=31, fill=BLACK)
    x = w - lw - 50
    for t, c in parts:
        d.text((x, 38), t, font=lf, fill=c)
        x += d.textlength(t, font=lf)
    img.convert("RGB").save(out, quality=93)
    return out


def split_thumb(lsc):
    """썸네일 두 줄 문구 (AI가 준 두 줄, 없으면 thumb_title을 반으로)."""
    l1, l2 = lsc.get("thumb_line1"), lsc.get("thumb_line2")
    if l1 and l2:
        return l1[:10], l2[:10]
    t = re.sub(r"[\[\]]", "", lsc.get("thumb_title") or lsc.get("hook_title", "")).split()
    k = max(1, len(t) // 2)
    return " ".join(t[:k]), " ".join(t[k:])
