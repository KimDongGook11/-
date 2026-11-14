"""FFmpeg 합성 엔진 (세로 릴스 1080×1920 / 가로 장편 1920×1080 공용).

배경 컷(2~4초) → 그라데이션 → 헤더/배지 → 후킹 카드 → 차트(그려지기) → 숫자 카드(카운트업)
→ 챕터 카드 → 아웃트로 → 진행 바 → 단어별 카라오케 자막, 소리: 내레이션 + 효과음 + 배경음악(자동으로 줄임)
"""
import wave

from . import config
from .utils import font_file, run

FPS = config.FPS

# 인스타 릴스 규격: H.264 main, 4:2:0, 30fps, 2초 키프레임 / AAC 48kHz 128kbps 스테레오
IG_VIDEO = ["-c:v", "libx264", "-preset", "veryfast", "-profile:v", "main", "-level:v", "4.0",
            "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", str(FPS * 2), "-keyint_min", str(FPS * 2),
            "-sc_threshold", "0", "-crf", "20", "-maxrate", "8M", "-bufsize", "16M"]
IG_AUDIO = ["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"]
# 유튜브 장편: high 프로파일, 조금 더 높은 화질
YT_VIDEO = ["-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-g", str(FPS * 2), "-crf", "19", "-maxrate", "12M", "-bufsize", "24M"]
YT_AUDIO = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


def make_ig_safe(src, dst):
    run(["ffmpeg", "-y", "-i", src, *IG_VIDEO, *IG_AUDIO, "-movflags", "+faststart", dst])
    return dst


# ---------------- 자막 (단어별 카라오케) ----------------
def _ts(sec):
    sec = max(0.0, sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(t):
    return t.replace("\\", "＼").replace("{", "(").replace("}", ")").replace("\n", " ")


def _chunks(words, max_len):
    """단어들을 한 화면 분량으로 묶기 (문장 경계는 넘지 않음)."""
    out, cur = [], []
    for w in words:
        if cur and (w[3] != cur[-1][3] or len(" ".join(x[2] for x in cur + [w])) > max_len):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def build_ass(words, total, out, vertical=True, sources=None, source_until=None):
    f = config.FONT_NAME
    if vertical:
        W, H, size, ol, mv, max_len = 1080, 1920, 88, 8, 470, 11
    else:
        W, H, size, ol, mv, max_len = 1920, 1080, 66, 6, 64, 24
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{f},{size},&H00FFFFFF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,{ol},3,2,50,50,{mv},1
Style: Source,{f},{30 if vertical else 26},&H00D0D0D0,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,{2 if vertical else 3},60,60,{400 if vertical else 24},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    if sources:
        label = "참고: " if not vertical else "출처: "
        ev.append(f"Dialogue: 0,{_ts(0)},{_ts(source_until or total)},Source,,0,0,0,,"
                  f"{_esc(label + ', '.join(sources[:3]))}")
    chunks = _chunks(words, max_len)
    for ci, ch in enumerate(chunks):
        nxt = chunks[ci + 1][0] if ci + 1 < len(chunks) else None
        same_seg_next = nxt is not None and nxt[3] == ch[-1][3]
        c_end = nxt[0] if same_seg_next else ch[-1][1] + 0.2
        for j, w in enumerate(ch):
            s = ch[0][0] if j == 0 else w[0]
            e = ch[j + 1][0] if j + 1 < len(ch) else c_end
            if e - s < 0.04:
                continue
            parts = []
            for k, x in enumerate(ch):
                t = _esc(x[2])
                parts.append("{\\c&H00D7FF&}" + t + "{\\c&HFFFFFF&}" if k == j else t)
            pre = "{\\fad(60,0)}" if j == 0 else ""
            ev.append(f"Dialogue: 1,{_ts(s)},{_ts(e)},Sub,,0,0,0,,{pre}{' '.join(parts)}")
    out.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")
    return out


# ---------------- 배경 ----------------
def make_gradient(out, W, H):
    import numpy as np
    from PIL import Image
    a = np.zeros(H, dtype=np.float32)
    if H > W:
        a[:760] = np.linspace(0.8, 0.0, 760)
        a[1080:] = np.linspace(0.0, 0.75, H - 1080)
    else:
        a[:260] = np.linspace(0.65, 0.0, 260)
        a[H - 380:] = np.linspace(0.0, 0.8, 380)
    alpha = (np.tile(a[:, None], (1, W)) * 255).astype("uint8")
    img = np.zeros((H, W, 4), dtype="uint8")
    img[..., 3] = alpha
    Image.fromarray(img, "RGBA").save(out)
    return out


def build_background(shots, W, H, workdir):
    """샷 목록 → 하나의 배경 영상. 좌우 이동 없이 가운데를 잘라 고정, 원본 움직임은 BG_SPEED 배속."""
    speed = float(config.env("BG_SPEED", "0.8"))
    parts = []
    for i, (clip, ss, L) in enumerate(shots):
        p = workdir / f"shot_{i:03d}.mp4"
        vf = (f"setpts=PTS/{speed:.3f},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"setsar=1,fps={FPS},eq=brightness=-0.07:saturation=0.92,format=yuv420p")
        if clip:
            inp = ["-ss", f"{ss:.2f}", "-stream_loop", "-1", "-i", clip]
        else:
            inp = ["-f", "lavfi", "-i", f"gradients=s={W}x{H}:c0=0x0B1D33:c1=0x1B3A6B:x0=0:y0=0:x1={W}:y1={H}"
                                        f":speed=0.01:r={FPS}:seed={i}"]
        run(["ffmpeg", "-y", *inp, "-t", f"{L:.3f}", "-vf", vf, "-an",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", p])
        parts.append(p)
    lst = workdir / "shots.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    bg = workdir / "bg.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", bg])
    return bg


# ---------------- 효과음 (직접 합성, 저작권 걱정 없음) ----------------
SR = 48000


def _whoosh(np):
    n = int(SR * 0.42)
    noise = np.random.default_rng(1).standard_normal(n)
    spec = np.fft.rfft(noise)
    fr = np.fft.rfftfreq(n, 1 / SR)
    spec *= np.exp(-((np.log(fr + 1) - np.log(1800)) ** 2) / 0.9)
    x = np.fft.irfft(spec, n)
    t = np.linspace(0, 1, n)
    env = np.minimum(t / 0.35, 1) * np.exp(-np.maximum(t - 0.35, 0) * 9)
    x = x * env
    return x / (np.abs(x).max() + 1e-9)


def _pop(np):
    n = int(SR * 0.16)
    t = np.arange(n) / SR
    f = 880 + 700 * t / t[-1]
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 28)
    return x / (np.abs(x).max() + 1e-9)


def build_sfx(events, total, out):
    """events: [(시각초, 'whoosh'|'pop', 볼륨)]"""
    import numpy as np
    buf = np.zeros(int(SR * (total + 1)))
    lib = {"whoosh": _whoosh(np), "pop": _pop(np)}
    for t, kind, vol in events:
        s = lib[kind] * vol
        i = int(max(0, t - (0.3 if kind == "whoosh" else 0)) * SR)
        j = min(len(buf), i + len(s))
        buf[i:j] += s[: j - i]
    buf = np.clip(buf, -1, 1)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((buf * 32000).astype("<i2").tobytes())
    return out


# ---------------- 합성 ----------------
def compose(*, W, H, bg, narration, total, ass, overlays, out, sfx=None, bgm=None,
            progress=True, youtube=False):
    """overlays: dict 목록
       {"kind": "image", "path", "start", "end", "x", "y", "fade_in", "fade_out"}
       {"kind": "seq", "pattern", "frames", "start", "end", "x", "y", "fade_out"}"""
    inputs = ["-i", bg, "-i", narration]
    fc, last, idx = [], "0:v", 2
    for k, o in enumerate(overlays):
        x, y = o.get("x", 0), o.get("y", 0)
        if o["kind"] == "image":
            inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{o['end']:.3f}", "-i", o["path"]]
            ch = f"[{idx}:v]format=rgba"
            if o.get("fade_in"):
                ch += f",fade=t=in:st={o['start']:.3f}:d={o['fade_in']}:alpha=1"
            if o.get("fade_out"):
                ch += f",fade=t=out:st={o['end'] - o['fade_out']:.3f}:d={o['fade_out']}:alpha=1"
            fc.append(ch + f"[o{k}]")
            fc.append(f"[{last}][o{k}]overlay=x={x}:y={y}:eof_action=pass:"
                      f"enable='between(t,{o['start']:.3f},{o['end']:.3f})'[v{k}]")
        else:
            inputs += ["-framerate", str(FPS), "-i", o["pattern"]]
            dur = o["end"] - o["start"]
            hold = max(0.0, dur - o["frames"] / FPS)
            fo = o.get("fade_out", 0.25)
            fc.append(f"[{idx}:v]format=rgba,tpad=stop_mode=clone:stop_duration={hold:.3f},"
                      f"fade=t=out:st={max(0, dur - fo):.3f}:d={fo}:alpha=1,setpts=PTS+{o['start']:.3f}/TB[o{k}]")
            fc.append(f"[{last}][o{k}]overlay=x={x}:y={y}:eof_action=pass[v{k}]")
        last, idx = f"v{k}", idx + 1
    if progress:
        fc.append(f"color=c=0xFFD700:s={W}x12:r={FPS}:d={total:.3f}[pb]")
        fc.append(f"[{last}][pb]overlay=x='-w+w*t/{total:.3f}':y=0:shortest=1[vp]")
        last = "vp"
    fd = font_file(True)
    fontsdir = f":fontsdir={fd.rsplit('/', 1)[0]}" if fd else ""
    fc.append(f"[{last}]ass={ass}{fontsdir}[vout]")

    fc.append(f"[1:a]apad=whole_dur={total:.3f},aresample=48000,asplit=2[n1][n2]")
    mix = ["[n1]"]
    if sfx:
        inputs += ["-i", sfx]
        fc.append(f"[{idx}:a]aresample=48000[fx]")
        mix.append("[fx]")
        idx += 1
    if bgm:
        inputs += ["-stream_loop", "-1", "-i", bgm]
        fc.append(f"[{idx}:a]aresample=48000,volume=0.32,afade=t=out:st={max(0, total - 2):.2f}:d=2[bg0]")
        fc.append("[bg0][n2]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[bgd]")
        mix.append("[bgd]")
        idx += 1
    else:
        fc.append("[n2]anullsink")
    fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:dropout_transition=0:normalize=0,"
              f"alimiter=limit=0.95[aout]")
    v, a = (YT_VIDEO, YT_AUDIO) if youtube else (IG_VIDEO, IG_AUDIO)
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
         "-t", f"{total:.3f}", *v, *a, "-movflags", "+faststart", out])
    print(f"  [렌더] 완료: {out} ({total:.1f}초)")
    return out


def preview(src, dst, height=360, vbit="600k"):
    """텔레그램용 저화질 미리보기 (봇 전송 50MB 제한)."""
    run(["ffmpeg", "-y", "-i", src, "-vf", f"scale=-2:{height}", "-c:v", "libx264", "-preset", "veryfast",
         "-b:v", vbit, "-maxrate", vbit, "-bufsize", "1200k", "-c:a", "aac", "-b:a", "64k", "-ac", "1",
         "-movflags", "+faststart", dst])
    return dst

