"""대본 → 완성 영상.
- short(): 세로 1080×1920 릴스, 레이아웃 A(에디토리얼 카드)
- long():  가로 1920×1080 장편, 레이아웃 B(인포그래픽 분할)"""
import random

from . import chart, config, graphics, render, stock, tts
from .render import CARD, WINDOW

HOOK = 1.3          # 세로: 첫 화면 큰 제목
OUTRO_S = 1.6       # 세로: 아웃트로
OUTRO_L = 3.0       # 가로: 아웃트로
CHAPTER_GAP = 2.2   # 가로: 챕터 카드가 나오는 동안 내레이션 쉼
OPEN_L = 3.0        # 가로: 오프닝 타이틀 최소 시간


def _starts(durs):
    out, t = [], 0.0
    for d in durs:
        out.append(t)
        t += d
    return out


def _bgm():
    d = config.ASSETS_DIR / "bgm"
    files = sorted(d.glob("*.mp3")) if d.exists() else []
    return random.choice(files) if files else None


def short(sc, workdir, out, sources, offline=False, chart_opts=None):
    """세로 릴스 (레이아웃 A). 반환: (길이초, 품질 점검용 정보)"""
    W, H = 1080, 1920
    workdir.mkdir(parents=True, exist_ok=True)
    segs = sc["segments"]
    narration, durs, words = tts.synthesize([s["text"] for s in segs], workdir, tail=OUTRO_S)
    total = sum(durs)
    starts = _starts(durs)
    shots = [(None, 0.0, d) for d in durs] if offline else \
        stock.plan_shots(segs, durs, workdir / "clips", vertical=True, shot_len=2.8, card=True)
    bg = render.build_background(shots, W, H, workdir, layout="card")

    title_png, _ = graphics.title_a(sc, workdir / "title.png")
    ovs = [{"kind": "image", "path": graphics.card_frame(workdir / "frame.png"), "start": 0, "end": total - OUTRO_S},
           {"kind": "image", "path": title_png, "start": HOOK - 0.15, "end": total - OUTRO_S, "fade_in": 0.3},
           {"kind": "image", "path": graphics.hook_a(sc, workdir / "hook.png"), "start": 0, "end": HOOK,
            "fade_out": 0.25}]
    fx = [(HOOK, "whoosh", 0.18)] + [(t, "whoosh", 0.12) for t in starts[1:]]

    busy = set()
    on = [i for i, s in enumerate(segs) if s.get("show_chart")][:1] or ([min(2, len(segs) - 1)] if sc.get("chart") else [])
    if on and sc.get("chart"):
        i = on[0]
        cf = chart.make_chart_frames(sc["chart"], workdir / "chartf", offline=offline,
                                     w=CARD["w"] - 40, h=640, **(chart_opts or {}))
        if cf:
            pat, frames, w, h = cf
            end = starts[i] + durs[i]
            if i + 1 < len(segs) and segs[i + 1].get("show_chart"):
                end += durs[i + 1]
                busy.add(i + 1)
            ovs.append({"kind": "seq", "pattern": pat, "frames": frames, "start": max(starts[i] + 0.1, HOOK + 0.1),
                        "end": end, "x": CARD["x"] + 20, "y": CARD["y"] + (CARD["h"] - h) // 2, "fade_out": 0.25})
            busy.add(i)
            fx.append((starts[i] + 0.1, "whoosh", 0.18))
    count = 0
    for i, s in enumerate(segs):
        n = s.get("number")
        if not n or i in busy or count >= 2:
            continue
        pat, frames, w, h = graphics.number_frames(n["value"], n.get("label", ""), n.get("dir", "none"),
                                                   workdir / f"num_{i}", w=CARD["w"] - 100, h=460)
        st = max(starts[i] + 0.15, HOOK + 0.1)
        en = min(starts[i] + durs[i] - 0.1, st + 2.8)
        if en - st < 1.0:
            continue
        ovs.append({"kind": "seq", "pattern": pat, "frames": frames, "start": st, "end": en,
                    "x": CARD["x"] + 50, "y": CARD["y"] + (CARD["h"] - h) // 2, "fade_out": 0.25})
        fx.append((st, "pop", 0.32))
        count += 1

    ovs.append({"kind": "image", "path": graphics.outro_card(W, H, workdir / "outro.png", vertical=True),
                "start": total - OUTRO_S, "end": total, "fade_in": 0.3})
    fx.append((total - OUTRO_S, "whoosh", 0.2))
    ass = render.build_ass(words, total, workdir / "subs.ass", layout="A", sources=sources,
                           source_until=total - OUTRO_S)
    sfx = render.build_sfx(fx, total, workdir / "sfx.wav")
    render.compose(W=W, H=H, bg=bg, narration=narration, total=total, ass=ass, overlays=ovs, out=out,
                   sfx=sfx, bgm=_bgm(), progress=True)
    return total, {"shots": shots, "words": len(words), "kind": "short"}


def long(lsc, workdir, out, sources, offline=False, chart_opts=None):
    """가로 장편 (레이아웃 B). 반환: (길이초, 챕터 시작 [(초, 제목)], 썸네일, 품질 점검용 정보)"""
    W, H = 1920, 1080
    workdir.mkdir(parents=True, exist_ok=True)
    segs, lead, ch_first = [], {}, []
    for s in lsc.get("intro", []):
        segs.append({**s, "chapter": 0})
    for ci, ch in enumerate(lsc["chapters"], start=1):
        ch_first.append(len(segs))
        lead[len(segs)] = CHAPTER_GAP
        for s in ch["segments"]:
            segs.append({**s, "chapter": ci})
    narration, durs, words = tts.synthesize([s["text"] for s in segs], workdir, lead=lead, tail=OUTRO_L)
    total = sum(durs)
    starts = _starts(durs)
    shots = [(None, 0.0, d) for d in durs] if offline else \
        stock.plan_shots(segs, durs, workdir / "clips", vertical=False, shot_len=4.0, max_clips=50, card=True)
    bg = render.build_background(shots, W, H, workdir, layout="window")

    intro_end = starts[ch_first[0]] if ch_first else OPEN_L
    ovs = [{"kind": "image", "path": graphics.open_b(lsc, W, H, workdir / "open.png"),
            "start": 0, "end": max(OPEN_L, min(intro_end, 6.0)), "fade_in": 0.3, "fade_out": 0.45}]
    fx, chapters = [], [(0.0, "오프닝")]
    for ci, first in enumerate(ch_first, start=1):
        ch = lsc["chapters"][ci - 1]
        st = starts[first]
        last = (ch_first[ci] if ci < len(ch_first) else len(segs)) - 1
        en = starts[last] + durs[last]
        chapters.append((st, ch["title"]))
        ovs.append({"kind": "image", "path": graphics.panel_b(lsc, ci, workdir / f"panel_{ci}.png"),
                    "start": st + CHAPTER_GAP - 0.2, "end": en, "fade_in": 0.3})
        ovs.append({"kind": "image", "path": graphics.chapter_card(ci, ch["title"], ch.get("year"), W, H,
                                                                   workdir / f"chap_{ci}.png"),
                    "start": st, "end": st + CHAPTER_GAP + 0.3, "fade_in": 0.3, "fade_out": 0.35})
        fx.append((st, "whoosh", 0.24))

    busy = set()
    for i in [i for i, s in enumerate(segs) if s.get("show_chart")][:2]:
        if not lsc.get("chart"):
            break
        cf = chart.make_chart_frames(lsc["chart"], workdir / f"chartf_{i}", offline=offline,
                                     w=WINDOW["w"], h=WINDOW["h"], **(chart_opts or {}))
        if not cf:
            break
        pat, frames, w, h = cf
        end = starts[i] + durs[i]
        if i + 1 < len(segs) and segs[i + 1]["chapter"] == segs[i]["chapter"]:
            end += durs[i + 1]
            busy.add(i + 1)
        ovs.append({"kind": "seq", "pattern": pat, "frames": frames, "start": starts[i] + lead.get(i, 0) + 0.1,
                    "end": end, "x": WINDOW["x"], "y": WINDOW["y"], "fade_out": 0.3})
        busy.add(i)
    kx, ky, kw, kh = graphics.KEY_BOX
    for i, s in enumerate(segs):
        n = s.get("number")
        if not n or s["chapter"] == 0:
            continue
        pat, frames, w, h = graphics.number_frames(n["value"], n.get("label", ""), n.get("dir", "none"),
                                                   workdir / f"num_{i}", w=kw, h=kh)
        st = starts[i] + lead.get(i, 0) + 0.15
        en = starts[i] + durs[i] - 0.05
        if en - st < 1.0:
            continue
        ovs.append({"kind": "seq", "pattern": pat, "frames": frames, "start": st, "end": en,
                    "x": kx, "y": ky, "fade_out": 0.3})
        fx.append((st, "pop", 0.3))

    ovs.append({"kind": "image", "path": graphics.outro_card(W, H, workdir / "outro.png", vertical=False),
                "start": total - OUTRO_L, "end": total, "fade_in": 0.4})
    fx.append((total - OUTRO_L, "whoosh", 0.22))
    ass = render.build_ass(words, total, workdir / "subs.ass", layout="B", sources=sources,
                           source_until=total - OUTRO_L)
    sfx = render.build_sfx(fx, total, workdir / "sfx.wav")
    render.compose(W=W, H=H, bg=bg, narration=narration, total=total, ass=ass, overlays=ovs, out=out,
                   sfx=sfx, bgm=_bgm(), progress=False, youtube=True)

    # 썸네일: 배경 중 관련도 높은 장면 한 컷
    frame = workdir / "thumb_bg.png"
    try:
        from .utils import run
        clip = next((c for c, _, _ in shots[len(shots) // 3:] if c), None)
        if clip:
            run(["ffmpeg", "-y", "-ss", "2", "-i", clip, "-frames:v", "1", frame])
        else:
            frame = None
    except Exception:
        frame = None
    thumb = graphics.thumbnail(frame, lsc.get("thumb_title") or lsc["hook_title"], lsc.get("year"),
                               lsc.get("ep"), workdir / "thumbnail.jpg")
    return total, chapters, thumb, {"shots": shots, "words": len(words), "kind": "long"}
