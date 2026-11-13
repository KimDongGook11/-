import json
import subprocess
from pathlib import Path

from . import config


def run(cmd, quiet=True):
    """ffmpeg 등 외부 명령 실행. 실패하면 마지막 에러 로그를 보여줍니다."""
    cmd = [str(c) for c in cmd]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-25:])
        raise RuntimeError(f"명령 실패: {' '.join(cmd[:6])} ...\n{tail}")
    if not quiet:
        print(p.stdout)
    return p.stdout


def duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", path])
    return float(out.strip())


def font_file(bold=True):
    """시스템에 설치된 한글 폰트 파일 경로를 찾습니다."""
    style = ":style=Bold" if bold else ""
    try:
        p = run(["fc-match", "-f", "%{file}", f"{config.FONT_NAME}{style}"]).strip()
        if p and Path(p).exists():
            return p
    except Exception:
        pass
    for cand in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                 "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"]:
        if Path(cand).exists():
            return cand
    return None


# --- 상태 파일 (state/*.json, 저장소에 커밋되어 다음 실행으로 이어짐) ---
def load_state(name, default):
    p = config.STATE_DIR / f"{name}.json"
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_state(name, data):
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    p = config.STATE_DIR / f"{name}.json"
    if data is None:
        if p.exists():
            p.unlink()
        return
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
