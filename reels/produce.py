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


def _cards(segs, starts, durs, busy, headlines, topic, box, workdir, show_at=None, lead=None, after=0.0):
    """관련 영상이 없는 문장(stock.LAST_MISSING)과 show_at 문장에 헤드라인 카드(없으면 주제 카드)를 띄움.
    같은 그림은 한 번만 만들고 여러 구간(ranges)으로 켬 → 영상 합성 입력 수를 줄임."""
    lead = lead or {}
    want = sorted((set(stock.LAST_MISSING) | ({show_at} if show_at is not None else set())) - set(busy))
    want = [i for i in want if 0 <= i < len(segs)]
    if not want:
        return []
    cw, ch = box["w"] - 60, min(box["h"] - 60, int((box["w"] - 60) * 0.58))
    x, y = box["x"] + (box["w"] - cw) // 2, box["y"] + (box["h"] - ch) // 2
    spans, k = {}, 0
    for i in want:
        st = max(starts[i] + lead.get(i, 0), after)
        en = starts[i] + durs[i]
        if en - st < 0.8:
            continue
        if headlines:
            key = 0 if i == show_at else (k % len(headlines))
            if i != show_at:
                k += 1
        else:
            key = "topic"
        spans.setdefault(key, []).append((st, en))
    ovs = []
    for key, rr in spans.items():
        path = (graphics.headline_card(headlines[key], workdir / f"headline_{key}.png", w=cw, hgt=ch) if key != "topic"
                else graphics.topic_card(topic[0], topic[1], workdir / "topic.png", w=cw, hgt=ch))
        ovs.append({"kind": "image", "path": path, "ranges": rr, "start": rr[0][0], "end": rr[-1][1], "x": x, "y": y})
    print(f"  [그래픽] 헤드라인·주제 카드 {sum(len(r) for r in spans.values())}곳 (관련 영상 없음 {len(stock.LAST_MISSING)}문장)")
    return ovs


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
                        "end": end, "x": CARD["x"] + 20, "y": CARD["y"] + (CARD["h"] - h) // 2, "fade_out": 0.25,
                        "chart": True})
            busy.add(i)
            fx.append((starts[i] + 0.1, "whoosh", 0.18))
    count = 0
    for i, s in enumerate(segs):
        n = s.get("number")
        if not n or i in busy or count >= (3 if len(segs) > 10 else 2):   # 1분 30초 원픽은 숫자 카드 3개까지
            continue
        pat, frames, w, h = graphics.number_frames(n["value"], n.get("label", ""), n.get("dir", "none"), change=n.get("change", ""),
                                                   out_dir=workdir / f"num_{i}", w=CARD["w"] - 100, h=460)
        st = max(starts[i] + 0.15, HOOK + 0.1)
        en = min(starts[i] + durs[i] - 0.1, st + 2.8)
        if en - st < 1.0:
            continue
        ovs.append({"kind": "seq", "pattern": pat, "frames": frames, "start": st, "end": en,
                    "x": CARD["x"] + 50, "y": CARD["y"] + (CARD["h"] - h) // 2, "fade_out": 0.25})
        fx.append((st, "pop", 0.32))
        busy.add(i)
        count += 1
    if offline:
        stock.LAST_MISSING.clear()
    ovs += _cards(segs, starts, durs, busy | {len(segs) - 1}, sc.get("headlines") or [],
                  (sc.get("hook_title", ""), sc.get("tag", "")), CARD, workdir,
                  show_at=1 if sc.get("headlines") and len(segs) > 3 else None, after=HOOK + 0.1)

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
    speakers = lsc.get("speakers")   # 대담 특집: {"host": {"name": "서현", ...}, "panel": {...}}
    voices = [(lambda sp: sp.get("voice") or sp["name"])(speakers[s.get("speaker", "panel")]) for s in segs] \
        if speakers else None
    narration, durs, words = tts.synthesize([s["text"] for s in segs], workdir, lead=lead, tail=OUTRO_L,
                                            voices=voices)
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
    # 문장별 차트(이슈 뒷담화: 업종·기업마다, 최대 6개) + 기존 방식(대표 차트를 show_chart 문장에, 최대 2개)
    plan = [(i, s["chart"]) for i, s in enumerate(segs) if isinstance(s.get("chart"), dict)][:6]
    if not plan and lsc.get("chart"):
        plan = [(i, lsc["chart"]) for i, s in enumerate(segs) if s.get("show_chart")][:2]
    for i, ch in plan:
        if i in busy:
            continue
        cf = chart.make_chart_frames(ch, workdir / f"chartf_{i}", offline=offline,
                                     w=WINDOW["w"], h=WINDOW["h"], **(chart_opts or {}))
        if not cf:
            continue
        pat, frames, w, h = cf
        end = starts[i] + durs[i]
        if (i + 1 < len(segs) and segs[i + 1]["chapter"] == segs[i]["chapter"]
                and not segs[i + 1].get("chart")):     # 다음 문장에 자기 차트가 없으면 이어서 보여 줌
            end += durs[i + 1]
            busy.add(i + 1)
        ovs.append({"kind": "seq", "pattern": pat, "frames": frames, "start": starts[i] + lead.get(i, 0) + 0.1,
                    "end": end, "x": WINDOW["x"], "y": WINDOW["y"], "fade_out": 0.3, "chart": True})
        busy.add(i)
    kx, ky, kw, kh = graphics.KEY_BOX
    for i, s in enumerate(segs):
        n = s.get("number")
        if not n or s["chapter"] == 0:
            continue
        pat, frames, w, h = graphics.number_frames(n["value"], n.get("label", ""), n.get("dir", "none"), change=n.get("change", ""),
                                                   out_dir=workdir / f"num_{i}", w=kw, h=kh)
        st = starts[i] + lead.get(i, 0) + 0.15
        en = starts[i] + durs[i] - 0.05
        if en - st < 1.0:
            continue
        ovs.append({"kind": "seq", "pattern": pat, "frames": frames, "start": st, "end": en,
                    "x": kx, "y": ky, "fade_out": 0.3})
        fx.append((st, "pop", 0.3))

    if offline:
        stock.LAST_MISSING.clear()
    ovs += _cards(segs, starts, durs, busy, lsc.get("headlines") or [],
                  (lsc.get("hook_title", ""), lsc.get("series_name", "그때 그 결정")), WINDOW, workdir,
                  show_at=(ch_first[0] if ch_first and lsc.get("headlines") else None), lead=lead)
    if speakers:   # 말하는 사람 이름표: 사람마다 그림 하나, 그 사람이 말하는 구간마다 켜기 (캐릭터 그림은 쓰지 않음)
        for key, sp in speakers.items():
            spans = [(starts[i] + lead.get(i, 0), starts[i] + durs[i]) for i, s in enumerate(segs)
                     if s.get("speaker", "panel") == key]
            if spans:
                ovs.append({"kind": "image", "ranges": spans, "start": spans[0][0], "end": spans[-1][1],
                            "path": graphics.speaker_badge(sp["name"], sp["role"], tuple(sp["color"]),
                                                           workdir / f"badge_{key}.png"),
                            "x": WINDOW["x"] + 24, "y": WINDOW["y"] + WINDOW["h"] - 84 - 24})   # 영상 창 왼쪽 아래
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
    from . import doubleexp, realphoto
    comp = lsc.get("company") or {}
    l1, l2 = graphics.split_thumb(lsc)
    sub = "  ·  ".join(str(v) for v in (lsc.get("year"), comp.get("name_ko"), comp.get("industry_ko")) if v)
    real, credit = (None, None) if offline else realphoto.company_photo(
        lsc.get("wiki_titles") or [], workdir, episode=f"{comp.get('name_ko', '')} {lsc.get('year', '')}년 — {lsc.get('hook_title', '')}")
    if real:   # 1순위: 위키미디어 공용의 실제 기업 사진 (합성 없음)
        lsc["thumb_credit"] = credit
        thumb = graphics.thumbnail_photo(real, l1, l2, sub, lsc.get("ep"), workdir / "thumbnail.jpg")
    else:
        fig = None if offline else doubleexp.figure_for(comp.get("country_ko"), workdir, seed=lsc.get("ep"))
        thumb = graphics.thumbnail(frame, l1, l2, sub, lsc.get("ep"), workdir / "thumbnail.jpg", figure=fig)
    return total, chapters, thumb, {"shots": shots, "words": len(words), "kind": "long"}
