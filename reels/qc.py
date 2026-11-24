"""완성 영상 자동 품질 점검. 문제가 있으면 텔레그램 초안 메시지에 ⚠️로 알려 줌."""
import json
import re
import subprocess


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,duration:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True).stdout
    return json.loads(out or "{}")


def _detect(path, vf, until):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-t", f"{until:.2f}", "-i", str(path), "-vf", vf,
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    return p.stderr


def check(path, info, script, offline=False):
    items = []
    try:
        meta = _probe(path)
        dur = float(meta.get("format", {}).get("duration", 0))
        streams = meta.get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), {})
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        kind = info.get("kind", "short")

        # 1) 길이
        if kind == "short":
            lo, hi = info.get("range", (25, 60))
            ok = lo <= dur <= hi
            items.append(("길이", ok, f"{dur:.0f}초" + ("" if ok else f" (권장 {lo}~{hi}초)")))
        else:
            ok = dur >= 240
            items.append(("길이", ok, f"{int(dur // 60)}분 {int(dur % 60)}초" + ("" if ok else " (목표 5분보다 짧음)")))
        # 1-1) 화면이 소리보다 먼저 끝나지 않는지 (11/24: 54초에서 화면이 멈추고 소리만 나감)
        vdur = float(v.get("duration") or 0) if v else 0
        if vdur:
            items.append(("화면 끊김", vdur >= dur - 1.0, "없음" if vdur >= dur - 1.0 else f"{vdur:.0f}초에서 화면이 멈춤"))
        # 2) 화면 규격·소리
        want = (1080, 1920) if kind == "short" else (1920, 1080)
        items.append(("규격", (v.get("width"), v.get("height")) == want and has_audio,
                      f"{v.get('width')}×{v.get('height')}" + ("" if has_audio else ", 소리 없음")))
        # 3) 배경 영상 확보율
        shots = info.get("shots") or []
        if shots and not offline:
            miss = sum(1 for c, _, _ in shots if not c) / len(shots)
            items.append(("배경", miss <= 0.2, f"실사 영상 {100 - miss * 100:.0f}%"))
        # 4) 자막 타이밍
        words = info.get("words", 0)
        items.append(("자막", words > 0, f"단어 {words}개"))
        # 5) 검은 화면 / 멈춘 화면 (아웃트로 전까지)
        until = max(1.0, dur - 3.5)
        err = _detect(path, "blackdetect=d=1.0:pix_th=0.02", until)
        blacks = re.findall(r"black_duration:([\d.]+)", err)
        items.append(("검은 화면", not blacks, "없음" if not blacks else f"{len(blacks)}곳"))
        err = _detect(path, "freezedetect=n=0.002:d=8", until)
        freezes = len(re.findall(r"freeze_start", err))
        items.append(("멈춘 화면", freezes == 0, "없음" if not freezes else f"{freezes}곳 (8초 이상)"))
    except Exception as e:
        items.append(("점검", False, f"점검 중 오류: {e}"))
    return {"ok": all(ok for _, ok, _ in items), "items": items}


def summary(qc):
    if not qc:
        return ""
    if qc["ok"]:
        return "✅ 품질 점검 통과 (" + " · ".join(f"{n} {d}" for n, _, d in qc["items"][:2]) + ")"
    bad = [f"{n}: {d}" for n, ok, d in qc["items"] if not ok]
    return "⚠️ 품질 점검 확인 필요 — " + " / ".join(bad)
