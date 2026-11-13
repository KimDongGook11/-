"""FFmpeg로 9:16 릴스 영상 합성: 배경 영상 + 그라데이션 + 차트 + 자막 + 진행 바 + 내레이션."""
import datetime as dt
import re

from . import config, header
from .utils import font_file, run

W, H, FPS = config.W, config.H, config.FPS


def _ts(sec):
    sec = max(0.0, sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(t):
    return t.replace("\\", "＼").replace("{", "(").replace("}", ")").replace("\n", " ")


NUM = re.compile(r"(\d[\d,\.]*\s?(?:%p|%포인트|%|퍼센트포인트|퍼센트|달러|원|엔|위안|유로|억|조|만|bp|포인트|배|년|개월|달)?)")


def _highlight(t):
    return NUM.sub(r"{\\c&H00D7FF&}\1{\\c&HFFFFFF&}", t)


def chunk_text(text, max_len=11):
    words, chunks, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_len:
            chunks.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(script, durs, sources, out, pad=0.25):
    f = config.FONT_NAME
    total = sum(durs)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{f},88,&H00FFFFFF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,8,3,2,50,50,470,1
Style: Source,{f},32,&H00D0D0D0,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,80,80,400,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    if sources:
        ev.append(f"Dialogue: 0,{_ts(0)},{_ts(total)},Source,,0,0,0,,{_esc('출처: ' + ', '.join(sources[:3]))}")
    t = 0.0
    for seg, d in zip(script["segments"], durs):
        speech = max(0.5, d - pad)
        chunks = chunk_text(seg["text"])
        weights = [len(c.replace(" ", "")) + 1 for c in chunks]
        acc = t
        for c, wgt in zip(chunks, weights):
            dur = speech * wgt / sum(weights)
            anim = "{\\fad(60,0)\\fscx90\\fscy90\\t(0,100,\\fscx100\\fscy100)}"
            ev.append(f"Dialogue: 1,{_ts(acc)},{_ts(acc + dur)},Sub,,0,0,0,,{anim}{_highlight(_esc(c))}")
            acc += dur
        t += d
    out.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")
    return out


def make_gradient(out):
    import numpy as np
    from PIL import Image
    a = np.zeros(H, dtype=np.float32)
    top = 760
    a[:top] = np.linspace(0.8, 0.0, top)
    bs = 1080
    a[bs:] = np.linspace(0.0, 0.72, H - bs)
    alpha = (np.tile(a[:, None], (1, W)) * 255).astype("uint8")
    img = np.zeros((H, W, 4), dtype="uint8")
    img[..., 3] = alpha
    Image.fromarray(img, "RGBA").save(out)
    return out


def _segment_video(clip, d, i, out):
    zoom_w, zoom_h = int(W * 1.1) // 2 * 2, int(H * 1.1) // 2 * 2
    pan = f"(iw-ow)*t/{d:.3f}" if i % 2 == 0 else f"(iw-ow)*(1-t/{d:.3f})"
    vf = (f"scale={zoom_w}:{zoom_h}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H}:x='{pan}':y='(ih-oh)/2',setsar=1,fps={FPS},"
          f"eq=brightness=-0.06:saturation=0.9,format=yuv420p")
    if clip:
        inp = ["-stream_loop", "-1", "-i", clip]
    else:
        inp = ["-f", "lavfi", "-i", f"color=c=0x0B1D33:s={zoom_w}x{zoom_h}:r={FPS}"]
    run(["ffmpeg", "-y", *inp, "-t", f"{d:.3f}", "-vf", vf, "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", out])


def render(script, durs, clips, narration, chart_png, sources, workdir, out_path, bgm=None):
    workdir.mkdir(parents=True, exist_ok=True)
    total = sum(durs)
    parts = []
    for i, (clip, d) in enumerate(zip(clips, durs)):
        p = workdir / f"seg_{i:02d}.mp4"
        _segment_video(clip, d, i, p)
        parts.append(p)
    lst = workdir / "seg_list.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    bg = workdir / "bg.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", bg])

    grad = make_gradient(workdir / "gradient.png")
    ass = build_ass(script, durs, sources, workdir / "subs.ass")

    head_png, head_bottom = header.make_header(script, workdir / "header.png")
    inputs = ["-i", bg, "-i", narration, "-loop", "1", "-i", grad, "-loop", "1", "-i", head_png]
    fc = ["[0:v][2:v]overlay=0:0:shortest=1[v0]",
          "[3:v]format=rgba,fade=t=in:st=0:d=0.35:alpha=1[hd]",
          "[v0][hd]overlay=0:0:shortest=1[v1]"]
    last = "v1"
    idx = 4
    if chart_png:
        # 차트를 보여줄 구간 계산 (지정 없으면 3번째 문장)
        starts = [sum(durs[:i]) for i in range(len(durs))]
        on = [i for i, s in enumerate(script["segments"]) if s.get("show_chart")] or [min(2, len(durs) - 1)]
        cond = "+".join(f"between(t,{starts[i]:.2f},{starts[i] + durs[i]:.2f})" for i in on[:2])
        inputs += ["-loop", "1", "-i", chart_png]
        chart_y = max(head_bottom + 10, 560)
        fc.append(f"[{last}][{idx}:v]overlay=x=(W-w)/2:y={chart_y}:enable='{cond}':shortest=1[v2]")
        last, idx = "v2", idx + 1
    fc.append(f"color=c=0xFFD700:s={W}x12:r={FPS}:d={total:.3f}[pb]")
    fc.append(f"[{last}][pb]overlay=x='-w+w*t/{total:.3f}':y=0:shortest=1[v3]")
    fd = font_file(True)
    fontsdir = f":fontsdir={fd.rsplit('/', 1)[0]}" if fd else ""
    fc.append(f"[v3]ass={ass}{fontsdir}[vout]")
    if bgm:
        inputs += ["-stream_loop", "-1", "-i", bgm]
        fc.append(f"[{idx}:a]volume=0.12,afade=t=out:st={max(0, total - 1.5):.2f}:d=1.5[bg_a]")
        fc.append("[1:a][bg_a]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]")
        amap = "[aout]"
    else:
        amap = "1:a"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc),
         "-map", "[vout]", "-map", amap, "-t", f"{total:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
         "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
         "-movflags", "+faststart", out_path])
    print(f"  [렌더] 완료: {out_path} ({total:.1f}초)")
    return out_path
