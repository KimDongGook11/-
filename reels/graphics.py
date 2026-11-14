"""영상에 얹는 그래픽 (PIL로 그린 투명 PNG).
후킹 카드, 숫자 카드(카운트업 프레임), 챕터 카드, 장편 배지, 아웃트로, 유튜브 썸네일."""
import re

from PIL import Image, ImageDraw, ImageFilter

from . import config
from .header import _font, _wtext, _wrap, parse_title

YELLOW, RED, WHITE, BLACK = (255, 212, 0), (230, 30, 40), (255, 255, 255), (0, 0, 0)
UP, DOWN = (255, 77, 79), (59, 130, 246)
PANEL = (10, 14, 24, 225)


def _canvas(w, h):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _title_block(d, title, cx, y, max_w, sizes, fg=WHITE, hl=YELLOW, stroke=0, max_lines=2):
    """[ ]로 감싼 단어를 강조색으로, 가운데 정렬해 그림. 반환: 끝난 y"""
    words = parse_title(title)
    for size in sizes:
        f = _font(size)
        lines = _wrap(d, words, f, max_w)
        if len(lines) <= max_lines:
            break
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 1.1)
    sp = d.textlength(" ", font=f)
    for ln in lines:
        lw = d.textlength(" ".join(_wtext(w) for w in ln), font=f)
        x = cx - lw / 2
        for word in ln:
            for t, is_hl in word:
                d.text((x, y), t, font=f, fill=hl if is_hl else fg, stroke_width=stroke, stroke_fill=BLACK)
                x += d.textlength(t, font=f)
            x += sp
        y += lh
    return y, lines, f, lh


def _pill(d, x, y, text, f, bg, fg, pad=(24, 10)):
    w = d.textlength(text, font=f)
    asc, desc = f.getmetrics()
    h = asc + desc + pad[1] * 2
    d.rounded_rectangle([x, y, x + w + pad[0] * 2, y + h], radius=h // 2, fill=bg)
    d.text((x + pad[0], y + pad[1]), text, font=f, fill=fg)
    return w + pad[0] * 2, h


def _pills_centered(d, items, cx, y, f, gap=14):
    widths = [d.textlength(t, font=f) + 48 for t, _, _ in items]
    x = cx - (sum(widths) + gap * (len(items) - 1)) / 2
    h = 0
    for (t, bg, fg), w in zip(items, widths):
        _, h = _pill(d, x, y, t, f, bg, fg)
        x += w + gap
    return h


# ---------- 후킹/오프닝 카드 ----------
def hook_card(title, W, H, out, tag=None, pill=None):
    """영상 첫 1~3초: 화면 가운데 큰 제목 (스크롤을 멈추게)."""
    img, d = _canvas(W, H)
    vertical = H > W
    max_w = W - (120 if vertical else 360)
    sizes = (132, 120, 108, 96, 84) if vertical else (120, 108, 96, 84)
    # 크기를 먼저 재서 패널 높이 계산
    tmp, td = _canvas(W, H)
    y_end, lines, f, lh = _title_block(td, title, W / 2, 0, max_w, sizes, max_lines=3)
    block = lh * len(lines)
    pill_h = 70 if (tag or pill) else 0
    top = (H - block - pill_h) / 2 - (60 if vertical else 0)
    pad = 56
    d.rounded_rectangle([60 if vertical else 160, top - pad - pill_h, W - (60 if vertical else 160), top + block + pad],
                        radius=40, fill=PANEL)
    if tag or pill:
        items = ([(tag, RED, WHITE)] if tag else []) + ([(pill, YELLOW, BLACK)] if pill else [])
        _pills_centered(d, items, W / 2, top - pill_h - 10, _font(48 if vertical else 44))
    _title_block(d, title, W / 2, top, max_w, sizes, max_lines=3)
    img.save(out)
    return out


# ---------- 숫자 카드 (카운트업) ----------
NUM_RE = re.compile(r"^([^\d\-+]*)([\-+]?\d[\d,]*\.?\d*)(.*)$")


def number_frames(value, label, direction, out_dir, vertical=True, frames=16):
    """숫자가 0에서 목표값까지 올라가는 프레임들. 반환: (파일 패턴, 프레임 수, 폭, 높이)"""
    out_dir.mkdir(parents=True, exist_ok=True)
    w, h = (900, 520) if vertical else (1000, 460)
    col = UP if direction == "up" else DOWN if direction == "down" else YELLOW
    arrow = "▲ " if direction == "up" else "▼ " if direction == "down" else ""
    m = NUM_RE.match(str(value).strip())
    big, small = _font(170 if vertical else 160), _font(52 if vertical else 50)
    for i in range(frames):
        k = 1 - (1 - (i + 1) / frames) ** 3          # 끝으로 갈수록 천천히 (ease-out)
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
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=44, fill=PANEL, outline=col + (255,), width=5)
        tw = d.textlength(txt, font=big)
        d.text(((w - tw) / 2, 70), txt, font=big, fill=col)
        lw = d.textlength(label, font=small)
        d.text(((w - lw) / 2, h - 140), label, font=small, fill=(225, 230, 240))
        sc = 0.86 + 0.14 * min(1.0, (i + 1) / (frames * 0.5))   # 살짝 커지며 등장
        if sc < 1:
            canvas, _ = _canvas(w, h)
            small_img = img.resize((int(w * sc), int(h * sc)), Image.LANCZOS)
            canvas.paste(small_img, ((w - small_img.width) // 2, (h - small_img.height) // 2), small_img)
            img = canvas
        img.save(out_dir / f"{i:04d}.png")
    return str(out_dir / "%04d.png"), frames, w, h


# ---------- 장편: 챕터 카드 / 왼쪽 위 배지 ----------
def chapter_card(no, title, year, W, H, out):
    img, d = _canvas(W, H)
    d.rectangle([0, 0, W, H], fill=(6, 9, 16, 215))
    cy = H / 2
    f1, f2 = _font(44), _font(110)
    lab = f"CHAPTER {no}"
    d.text(((W - d.textlength(lab, font=f1)) / 2, cy - 170), lab, font=f1, fill=YELLOW)
    tw = d.textlength(title, font=f2)
    d.text(((W - tw) / 2, cy - 100), title, font=f2, fill=WHITE)
    if year:
        _pills_centered(d, [(f"{year}년", YELLOW, BLACK)], W / 2, cy + 60, _font(46))
    d.line([(W / 2 - 60, cy - 190), (W / 2 + 60, cy - 190)], fill=YELLOW, width=4)
    img.save(out)
    return out


def long_badge(series, ep, year, chapter, W, H, out):
    img, d = _canvas(W, H)
    f = _font(36)
    x, y = 56, 48
    for t, bg, fg in [(series, RED, WHITE), (ep, (255, 255, 255, 235), BLACK)] + \
                     ([(f"{year}년", YELLOW, BLACK)] if year else []):
        w, h = _pill(d, x, y, t, f, bg, fg, pad=(22, 8))
        x += w + 12
    if chapter:
        d.text((60, y + 78), chapter, font=_font(34), fill=WHITE, stroke_width=3, stroke_fill=BLACK)
    img.save(out)
    return out


# ---------- 아웃트로 ----------
def outro_card(W, H, out, vertical=True):
    img, d = _canvas(W, H)
    d.rectangle([0, 0, W, H], fill=(8, 8, 10, 235))
    f = _font(170 if vertical else 150)
    cy = H / 2 - (120 if vertical else 80)
    parts = [("경제 ", WHITE), ("[", RED), ("원픽", YELLOW), ("]", RED)]
    tw = sum(d.textlength(t, font=f) for t, _ in parts)
    x = (W - tw) / 2
    for t, c in parts:
        d.text((x, cy - 90), t, font=f, fill=c)
        x += d.textlength(t, font=f)
    sub = "팔로우하고 매일 경제 한 개씩 받아보세요" if vertical else "구독하고 다음 이야기도 받아보세요"
    fs = _font(50 if vertical else 46)
    d.text(((W - d.textlength(sub, font=fs)) / 2, cy + 130), sub, font=fs, fill=(230, 230, 230))
    handle = config.env("BRAND_HANDLE", "@econonepick")
    fh = _font(44)
    _pills_centered(d, [(handle, (255, 255, 255, 235), BLACK)], W / 2, cy + 230, fh)
    img.save(out)
    return out


# ---------- 유튜브 썸네일 ----------
def thumbnail(frame_png, title, year, ep, out, w=1280, h=720):
    if frame_png:
        bg = Image.open(frame_png).convert("RGB").resize((w, h), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(2))
    else:
        bg = Image.new("RGB", (w, h), (11, 18, 32))
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for i in range(w):                                  # 왼쪽이 어두운 그라데이션
        a = int(225 * max(0.0, 1 - i / (w * 0.85)))
        sd.line([(i, 0), (i, h)], fill=(0, 0, 0, a))
    img = Image.alpha_composite(bg.convert("RGBA"), shade)
    d = ImageDraw.Draw(img)
    f = _font(40)
    x = 54
    for t, b, c in [("그때 그 결정", RED, WHITE)] + ([(f"{year}년", YELLOW, BLACK)] if year else []) + \
                   ([(ep, (255, 255, 255, 235), BLACK)] if ep else []):
        wdt, _ = _pill(d, x, 50, t, f, b, c, pad=(22, 8))
        x += wdt + 12
    words = parse_title(title)
    for size in (118, 106, 96, 86, 76):
        tf = _font(size)
        lines = _wrap(d, words, tf, w * 0.66)
        if len(lines) <= 3:
            break
    asc, desc = tf.getmetrics()
    lh = int((asc + desc) * 1.06)
    y = h - 60 - lh * len(lines)
    sp = d.textlength(" ", font=tf)
    for ln in lines:
        xx = 54
        for word in ln:
            for t, is_hl in word:
                d.text((xx, y), t, font=tf, fill=YELLOW if is_hl else WHITE, stroke_width=6, stroke_fill=BLACK)
                xx += d.textlength(t, font=tf)
            xx += sp
        y += lh
    img.convert("RGB").save(out, quality=92)
    return out
