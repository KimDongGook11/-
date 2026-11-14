"""글꼴: Pretendard(무료·상업 이용 가능, SIL OFL)를 우선 사용하고, 없으면 Noto Sans CJK로 대체.
GitHub Actions에서는 워크플로가 Pretendard를 자동 설치합니다."""
import functools
import subprocess
from pathlib import Path

from . import config

WEIGHTS = ("Black", "ExtraBold", "Bold", "SemiBold", "Medium", "Regular")
NOTO = {"Black": "Black", "ExtraBold": "Black", "Bold": "Bold", "SemiBold": "Bold",
        "Medium": "Medium", "Regular": "Regular"}


def _fc(pattern):
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}|%{family}", pattern],
                             capture_output=True, text=True).stdout
        f, fam = out.split("|", 1)
        return f, fam
    except Exception:
        return None, ""


@functools.lru_cache(None)
def path(weight="Bold"):
    """굵기별 글꼴 파일 경로."""
    local = config.ASSETS_DIR / "fonts" / f"Pretendard-{weight}.otf"
    if local.exists():
        return str(local)
    f, fam = _fc(f"Pretendard:style={weight}")
    if f and "Pretendard" in fam and Path(f).exists():
        return f
    for cand in [f"/usr/share/fonts/opentype/noto/NotoSansCJK-{NOTO[weight]}.ttc",
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]:
        if Path(cand).exists():
            return cand
    f, _ = _fc(f"Noto Sans CJK KR:style={NOTO[weight]}")
    return f


@functools.lru_cache(None)
def family():
    """자막(ASS)에서 쓸 글꼴 이름."""
    p = path("Bold") or ""
    return "Pretendard" if "Pretendard" in p else "Noto Sans CJK KR"


def has_pretendard():
    return "Pretendard" in (path("Bold") or "")


@functools.lru_cache(None)
def pil(weight, size):
    from PIL import ImageFont
    p = path(weight)
    if not p:
        return ImageFont.load_default()
    if p.endswith(".ttc"):
        for idx in (1, 0):   # Noto CJK: 1번이 한국어(KR)
            try:
                return ImageFont.truetype(p, size, index=idx)
            except Exception:
                pass
    return ImageFont.truetype(p, size)


def fonts_dir():
    p = path("Bold")
    return str(Path(p).parent) if p else None
