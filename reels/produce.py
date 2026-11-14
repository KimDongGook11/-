"""대본 → 완성 영상. 세로 릴스(1분 미만)와 가로 장편(약 5분, 유튜브) 두 가지 조립 방식."""
from . import chart, config, graphics, header, render, stock, tts

HOOK = 1.4          # 세로: 첫 화면 후킹 카드 시간
OUTRO_S = 1.6       # 세로: 아웃트로
OUTRO_L = 3.0       # 가로: 아웃트로
CHAPTER_GAP = 2.2   # 가로: 챕터 카드가 나오는 동안 내레이션 쉼


def _starts(durs):
    out, t = [], 0.0
    for d in durs:
        out.append(t)
        t += d
    return out


def _bgm():
    d = config.ASSETS_DIR / "bgm"
    files = sorted(d.glob("*.mp3")) if d.exists() else []
    if not files:
        return None
    import random
    return random.choice(files)


def _number_overlays(segs, starts, durs, workdir, vertical, W, H, skip, top=640, not_before=0.0):
    ovs, fx = [], []
    count = 0
    for i, s in enumerate(segs):
        n = s.get("number")
        if not n or i in skip or count >= (2 if vertical else 6):
            continue
        pat, frames, w, h = graphics.number_frames(n["value"], n.get("label", ""), n.get("dir", "none"),
                                                   workdir / f"num_{i}", vertical=vertical)
        st = max(starts[i] + 0.15, not_before)
        en = min(starts[i] + durs[i] - 0.1, st + 2.8)
        if en - st < 1.0:
            continue
        y = top if vertical else 250
        ovs.append({"kind": "seq", "pattern": pat, "frames": frames, "start": st, "end": en,
                    "x": (W - w) // 2, "y": y, "fade_out": 0.25})
        fx.append((st, "pop", 0.35))
        count += 1
    return ovs, fx


def short(sc, workdir, out, sources, offline=False, chart_opts=None):
    """세로 1080×1920 릴스."""
    W, H = 1080, 1920
    workdir.mkdir(parents=True, exist_ok=True)
    segs = sc["segments"]
    narration, durs, words = tts.synthesize([s["text"] for s in segs], workdir, tail=OUTRO_S)
    total = sum(durs)
    starts = _starts(durs)
    shots = [(None, 0.0, d) for d in durs] if offline else \
        stock.plan_shots(segs, durs, workdir / "clips", vertical=True, shot_len=2.8)
    bg = render.build_background(shots, W, H, workdir)

    ovs = [{"kind": "image", "path": render.make_gradient(workdir / "grad.png", W, H), "start": 0, "end": total}]
    head_png, head_bottom = header.make_header(sc, workdir / "header.png")
    ovs.append({"kind": "image", "path": head_png, "start": HOOK - 0.2, "end": total - OUTRO_S, "fade_in": 0.3})
    ovs.append({"kind": "image", "path": graphics.hook_card(sc["hook_title"], W, H, workdir / "hook.png",
                                                            tag=sc.get("tag"), pill=sc.get("pill")),
                "start": 0, "end": HOOK, "fade_out": 0.25})
    fx = [(HOOK, "whoosh", 0.2)] + [(t, "whoosh", 0.14) for t in starts[1:]]

    chart_seg = set()
    on = [i for i, s in enumerate(segs) if s.get("show_chart")][:1] or ([min(2, len(segs) - 1)] if sc.get("chart") else [])
    if on and sc.get("chart"):
        i = on[0]
        cf = chart.make_chart_frames(sc["chart"], workdir / "chartf", offline=offline, **(chart_opts or {}))
        if cf:
            pat, frames, w, h = cf
            end = starts[i] + durs[i]
            if i + 1 < len(segs) and segs[i + 1].get("show_chart"):
                end += durs[i + 1]
                chart_seg.add(i + 1)
            ovs.append({"kind": "seq", "pattern": pat, "frames": frames, "start": starts[i] + 0.1, "end": end,
                        "x": (W - w) // 2, "y": max(head_bottom + 10, 560), "fade_out": 0.25})
            chart_seg.add(i)
    nov, nfx = _number_overlays(segs, starts, durs, workdir, True, W, H, chart_seg, top=max(head_bottom + 40, 640),
                                not_before=HOOK + 0.1)
    ovs += nov
    fx += nfx

    ovs.append({"kind": "image", "path": graphics.outro_card(W, H, workdir / "outro.png", vertical=True),
                "start": total - OUTRO_S, "end": total, "fade_in": 0.3})
    fx.append((total - OUTRO_S, "whoosh", 0.22))
    ass = render.build_ass(words, total, workdir / "subs.ass", vertical=True, sources=sources,
                           source_until=total - OUTRO_S)
    sfx = render.build_sfx(fx, total, workdir / "sfx.wav")
    render.compose(W=W, H=H, bg=bg, narration=narration, total=total, ass=ass, overlays=ovs, out=out,
                   sfx=sfx, bgm=_bgm(), progress=True)
    return total


def long(lsc, workdir, out, sources, offline=False, chart_opts=None):
    """가로 1920×1080 장편 (유튜브). 반환: (길이초, 챕터 시작 시각 목록 [(초, 제목)], 썸네일 경로)"""
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
        stock.plan_shots(segs, durs, workdir / "clips", vertical=False, shot_len=4.0, max_clips=45)
    bg = render.build_background(shots, W, H, workdir)

    ep, year = lsc.get("ep", ""), lsc.get("year")
    ovs = [{"kind": "image", "path": render.make_gradient(workdir / "grad.png", W, H), "start": 0, "end": total}]
    intro_end = starts[ch_first[0]] if ch_first else min(total, 4)
    ovs.append({"kind": "image", "path": graphics.hook_card(lsc["hook_title"], W, H, workdir / "open.png",
                                                            tag=f"그때 그 결정 · {ep}", pill=f"{year}년" if year else None),
                "start": 0, "end": max(2.5, intro_end), "fade_in": 0.3, "fade_out": 0.4})
    fx, chapters = [], [(0.0, "오프닝")]
    for ci, first in enumerate(ch_first, start=1):
        ch = lsc["chapters"][ci - 1]
        st = starts[first]
        last = (ch_first[ci] if ci < len(ch_first) else len(segs)) - 1
        en = starts[last] + durs[last]
        chapters.append((st, ch["title"]))
        card = graphics.chapter_card(ci, ch["title"], ch.get("year"), W, H, workdir / f"chap_{ci}.png")
        ovs.append({"kind": "image", "path": card, "start": st, "end": st + CHAPTER_GAP + 0.3,
                    "fade_in": 0.3, "fade_out": 0.35})
        badge = graphics.long_badge("그때 그 결정", ep, ch.get("year") or year, f"{ci}장 · {ch['title']}",
                                    W, H, workdir / f"badge_{ci}.png")
        ovs.append({"kind": "image", "path": badge, "start": st + CHAPTER_GAP, "end": en, "fade_in": 0.3})
        fx.append((st, "whoosh", 0.26))

    chart_seg = set()
    for i in [i for i, s in enumerate(segs) if s.get("show_chart")][:2]:
        if not lsc.get("chart"):
            break
        cf = chart.make_chart_frames(lsc["chart"], workdir / f"chartf_{i}", offline=offline,
                                     w=1100, h=660, **(chart_opts or {}))
        if not cf:
            break
        pat, frames, w, h = cf
        end = starts[i] + durs[i]
        nxt = i + 1
        if nxt < len(segs) and segs[nxt]["chapter"] == segs[i]["chapter"] and not segs[nxt].get("number"):
            end += durs[nxt]                     # 다음 문장까지 차트를 유지
            chart_seg.add(nxt)
        ovs.append({"kind": "seq", "pattern": pat, "frames": frames, "start": starts[i] + lead.get(i, 0) + 0.1,
                    "end": end, "x": W - w - 70, "y": 170, "fade_out": 0.3})
        chart_seg.add(i)
    nov, nfx = _number_overlays(segs, starts, durs, workdir, False, W, H, chart_seg)
    ovs += nov
    fx += nfx

    ovs.append({"kind": "image", "path": graphics.outro_card(W, H, workdir / "outro.png", vertical=False),
                "start": total - OUTRO_L, "end": total, "fade_in": 0.4})
    fx.append((total - OUTRO_L, "whoosh", 0.25))
    ass = render.build_ass(words, total, workdir / "subs.ass", vertical=False, sources=sources,
                           source_until=total - OUTRO_L)
    sfx = render.build_sfx(fx, total, workdir / "sfx.wav")
    render.compose(W=W, H=H, bg=bg, narration=narration, total=total, ass=ass, overlays=ovs, out=out,
                   sfx=sfx, bgm=_bgm(), progress=False, youtube=True)

    frame = workdir / "thumb_bg.png"
    try:
        from .utils import run
        run(["ffmpeg", "-y", "-ss", f"{total * 0.4:.1f}", "-i", bg, "-frames:v", "1", frame])
    except Exception:
        frame = None
    thumb = graphics.thumbnail(frame, lsc.get("thumb_title") or lsc["hook_title"], year, ep, workdir / "thumbnail.jpg")
    return total, chapters, thumb
