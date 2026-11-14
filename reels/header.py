"""영상 상단 헤더 이미지: [태그] [날짜] 알약 + 큰 제목(핵심 단어 강조).
TITLE_STYLE 변수로 디자인 선택: dark(검은 박스) | yellow(노란 박스) | outline(박스 없이 굵은 테두리)"""
import datetime as dt
import re

from PIL import Image, ImageDraw, ImageFont

from . import config

W, H = config.W, config.H
TOP = 230            # 인스타 상단 UI(릴스 글자 등)를 피하는 여백
YELLOW, RED, WHITE, BLACK = (255, 212, 0), (230, 30, 40), (255, 255, 255), (0, 0, 0)
WEEK = "월화수목금토일"

STYLES = {
    #        글자색  강조색   박스색(RGBA)          테두리
    "dark":    (WHITE, YELLOW, (10, 14, 24, 215),  0),
    "yellow":  (BLACK, RED,    (255, 212, 0, 255), 0),
    "outline": (WHITE, YELLOW, None,               9),
}


def _font(size, weight="Bold"):
    from .fonts import pil
    return pil(weight, size)


def parse_title(title):
    """'젠슨 황 [전격 사임], 주가 급락' → 단어 목록. 단어 = [(글자, 강조여부), ...]
    대괄호가 없으면 숫자를 강조합니다. 쉼표 등은 앞 단어에 붙여 줄바꿈되지 않게 합니다."""
    title = title.strip()
    if "[" not in title:
        title = re.sub(r"(\d[\d,\.]*\s?(?:%p|%|달러|원|엔|조|억|만|배|bp)?)", r"[\1]", title)
    words, prev_space = [], True
    for m in re.finditer(r"\[([^\]]*)\]|([^\[\]]+)", title):
        part, hl = (m.group(1), True) if m.group(1) is not None else (m.group(2), False)
        glue = bool(words) and not prev_space and not part[:1].isspace()
        prev_space = part[-1:].isspace()
        for i, tok in enumerate(part.split()):
            if i == 0 and glue:
                words[-1].append((tok, hl))
            else:
                words.append([(tok, hl)])
    return words


def _wtext(word):
    return "".join(t for t, _ in word)


def _wrap(draw, words, font, max_w):
    lines, cur = [], []
    for w in words:
        test = cur + [w]
        if cur and draw.textlength(" ".join(_wtext(x) for x in test), font=font) > max_w:
            lines.append(cur)
            cur = [w]
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def _pill(draw, x, y, text, font, bg, fg, pad=(26, 12)):
    w = draw.textlength(text, font=font)
    asc, desc = font.getmetrics()
    h = asc + desc
    draw.rounded_rectangle([x, y, x + w + pad[0] * 2, y + h + pad[1] * 2], radius=(h + pad[1] * 2) // 2, fill=bg)
    draw.text((x + pad[0], y + pad[1]), text, font=font, fill=fg)
    return w + pad[0] * 2, h + pad[1] * 2


def make_header(script, out, style=None):
    style = style or config.env("TITLE_STYLE", "dark")
    fg, hl, box, stroke = STYLES.get(style, STYLES["dark"])
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 1줄: [태그] [날짜]
    kst = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    date = script.get("pill") or f"{kst.month}월 {kst.day}일 ({WEEK[kst.weekday()]})"
    tag = (script.get("tag") or "").strip()[:8]
    pf = _font(46)
    items = ([(tag, RED, WHITE)] if tag else []) + [(date, YELLOW, BLACK)]
    widths = [d.textlength(t, font=pf) + 52 for t, _, _ in items]
    x = (W - (sum(widths) + 16 * (len(items) - 1))) / 2
    y = TOP
    for (t, bg, tc), w in zip(items, widths):
        _, ph = _pill(d, x, y, t, pf, bg, tc)
        x += w + 16
    y += ph + 12

    # 2줄: 채널 이름
    bf = _font(34)
    bt = script.get("brand") or config.BRAND_NAME
    d.text(((W - d.textlength(bt, font=bf)) / 2, y), bt, font=bf, fill=(235, 235, 235),
           stroke_width=3, stroke_fill=BLACK)
    y += 34 + 30

    # 3줄~: 큰 제목 (최대 2줄, 넘치면 글자 크기 자동 축소)
    words = parse_title(script["hook_title"])
    max_w = W - 140
    for size in (100, 92, 84, 76, 68):
        tf = _font(size)
        lines = _wrap(d, words, tf, max_w)
        if len(lines) <= 2:
            break
    asc, desc = tf.getmetrics()
    lh = int((asc + desc) * 1.08)
    block_h = lh * len(lines)
    if box:
        widest = max(d.textlength(" ".join(_wtext(w) for w in ln), font=tf) for ln in lines)
        bx0 = (W - widest) / 2 - 40
        d.rounded_rectangle([bx0, y - 18, W - bx0, y + block_h + 22], radius=28, fill=box)
    space = d.textlength(" ", font=tf)
    for ln in lines:
        lw = d.textlength(" ".join(_wtext(w) for w in ln), font=tf)
        x = (W - lw) / 2
        for word in ln:
            for t, is_hl in word:
                d.text((x, y), t, font=tf, fill=hl if is_hl else fg,
                       stroke_width=stroke, stroke_fill=BLACK)
                x += d.textlength(t, font=tf)
            x += space
        y += lh
    bottom = int(y + 30)
    img.save(out)
    return out, bottom
