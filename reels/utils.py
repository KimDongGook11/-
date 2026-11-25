import json
import subprocess
from pathlib import Path

from . import config


RUN_TIMEOUT = 1800   # 외부 명령 하나가 30분 넘게 걸리면 멈춘 것으로 보고 중단 (11/20 1분 요약 렌더가 3.5시간 멈춰 작업이 통째로 취소됨)


def run(cmd, quiet=True, timeout=RUN_TIMEOUT, cwd=None):
    """ffmpeg 등 외부 명령 실행. 실패하면 마지막 에러 로그를 보여줍니다."""
    cmd = [str(c) for c in cmd]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    except subprocess.TimeoutExpired as e:
        # 멈춘 지점을 알 수 있게 ffmpeg 마지막 진행 로그를 남김 (frame=…, time=… 줄)
        err = e.stderr.decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        tail = "\n".join(err.replace("\r", "\n").strip().splitlines()[-8:])
        if tail:
            print(f"  [멈춘 명령 마지막 로그]\n{tail}")
        raise RuntimeError(f"명령 시간 초과({timeout // 60}분, 멈춤): {' '.join(cmd[:6])} ...")
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


def git_push_state(msg):
    """GitHub Actions 안에서만: state 폴더를 바로 커밋·푸시 (실패해도 계속 진행)."""
    import os
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    try:
        subprocess.run(["git", "add", "state"], check=True, cwd=config.ROOT)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=config.ROOT).returncode == 0:
            return
        subprocess.run(["git", "commit", "-q", "-m", msg], check=True, cwd=config.ROOT)
        for _ in range(3):
            subprocess.run(["git", "pull", "-q", "--rebase"], cwd=config.ROOT)
            if subprocess.run(["git", "push", "-q"], cwd=config.ROOT).returncode == 0:
                return
    except Exception as e:
        print(f"  [상태] 푸시 실패(무시): {e}")
