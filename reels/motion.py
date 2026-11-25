"""모션 그래픽 카드 (2026-11-25 사용자 결정, 국내 증시 마감 브리핑부터).
기존 A안 레이아웃(제목·카드·자막·음성)은 그대로 두고, 가운데 카드 안 배경 영상을 모션 그래픽으로 대체.
- 문장마다 장면 하나: counter / tiles / bars / gauge / headline / point (motionlab/src/Card.tsx)
- AI가 장면 종류와 값을 고르되, 숫자는 그 문장(또는 숫자 카드)에 실제로 있는 것만 허용 — 없으면 point로 바꿈
- Remotion으로 920×860 영상을 렌더 → 배경 영상의 카드 자리에 덮음. 실패하면 기존 방식 그대로."""
import json
import re
import shutil
from pathlib import Path

from . import config, llm
from .utils import run

ROOT = Path(__file__).resolve().parent.parent / "motionlab"
CARD = {"x": 80, "y": 600, "w": 920, "h": 860}
TYPES = ("counter", "tiles", "bars", "gauge", "headline", "point")


def enabled(series):
    on = [s.strip() for s in config.env("MOTION_SERIES", "kr").split(",") if s.strip()]
    return series in on and (ROOT / "node_modules").exists() and shutil.which("npx") is not None


def _digits(t):
    return re.sub(r"[^0-9]", "", str(t or ""))


def _num_ok(value, allowed):
    d = _digits(value)
    return not d or any(d in a for a in allowed)


def _safe(t):
    """웹 글꼴에서 깨질 수 있는 기호를 보통 기호로."""
    return (str(t or "").replace("∼", "~").replace("〜", "~").replace("～", "~").replace("‧", "·")
            .replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'"))


def _short_key(text, n=20):
    """문장 → 핵심 문구 대신 쓸 짧은 앞부분 (AI가 못 골랐을 때). 같은 카드가 반복되지 않게 문장마다 다름."""
    t = re.split(r"[,.?!]", text.strip())[0].strip()
    if len(t) > n:
        cut = t[:n].rsplit(" ", 1)[0]
        t = (cut if len(cut) >= 8 else t[:n]) + "…"
    return t


def _check(sc_, seg, heads):
    """장면 값 검사: 숫자는 문장·숫자 카드에 있는 것만. 통과 못 하면 None."""
    allowed = [_digits(seg["text"])] + ([_digits(seg["number"].get("value")), _digits(seg["number"].get("change"))]
                                        if seg.get("number") else [])
    t = sc_.get("type")
    if t not in TYPES:
        return None
    if t == "counter":
        if not sc_.get("value") or not _num_ok(sc_["value"], allowed) or not _num_ok(sc_.get("change"), allowed):
            return None
    elif t in ("tiles", "bars"):
        items = [it for it in (sc_.get("items") or [])[:4]
                 if it.get("value") and _num_ok(it["value"], allowed) and _num_ok(it.get("change"), allowed)]
        if len(items) < (1 if t == "bars" else 2):
            return None
        sc_["items"] = items
    elif t == "gauge":
        if not _num_ok(sc_.get("text"), allowed) or not _num_ok(sc_.get("badge"), allowed):
            return None
    elif t == "headline":
        h = sc_.get("h")
        if not isinstance(h, int) or not (0 <= h < len(heads)):
            return None
        sc_.update({"source": heads[h].get("source", ""), "date": heads[h].get("date", ""),
                    "text": _safe((heads[h].get("ko") or heads[h].get("orig") or "").replace(" / ", " "))})
    elif t == "point":
        if not sc_.get("key") or not _num_ok(sc_["key"], allowed):
            return None
    return sc_


def _plan_llm(segs, heads, tag):
    lines = []
    for i, s in enumerate(segs):
        n = s.get("number")
        lines.append(f"{i}. {s['text']}" + (f"  (숫자 카드: {n.get('label')} {n.get('value')} {n.get('change', '')} {n.get('dir', '')})" if n else ""))
    hl = "\n".join(f"h={k}: [{h.get('source')}] {h.get('ko') or h.get('orig')}" for k, h in enumerate(heads)) or "(없음)"
    prompt = f"""경제 쇼츠 영상의 가운데 카드에 들어갈 모션 그래픽 장면을 문장마다 하나씩 골라 줘. 주제: {tag}

[장면 종류]
- counter: 큰 숫자 하나가 세어지며 등장 + 등락 배지 + 선 그래프. {{"type":"counter","label":"코스피 종가","value":"4,708.53","change":"-3.31%","dir":"down"}}
- tiles: 지표 2~3개를 타일로 차례로. {{"type":"tiles","title":"","items":[{{"label":"코스닥","value":"635.49","change":"-1.58%","dir":"down","icon":"Q"}},{{"label":"원/달러 환율","value":"1,343.7원","change":"+8.9원","dir":"up","icon":"₩"}}]}}
- bars: 종목·항목별 등락률 막대 1~4개. {{"type":"bars","title":"대형주 하락률","items":[{{"name":"삼성전자","value":"3.06%","dir":"down"}},{{"name":"SK하이닉스","value":"2.52%","dir":"down"}}]}}
- gauge: 충격·불안·과열을 보여 주는 계기판. {{"type":"gauge","label":"시장 충격","level":0.9,"text":"장중 -5% 이상","badge":"매도 사이드카 발동"}} (level 0~1, 1이 가장 위험)
- headline: 아래 기사 헤드라인 카드. {{"type":"headline","h":0}}
- point: 핵심 문구 크게. 강조할 말은 [대괄호]. {{"type":"point","key":"외국인 [매도 폭탄]","sub":"하락 이유"}} (key 18자 이내)

[규칙]
- 숫자는 그 문장(또는 그 문장의 숫자 카드)에 나온 숫자만 그대로 써. 계산하거나 새 숫자를 만들지 마.
- dir: 오르면 "up", 내리면 "down", 둘 다 아니면 "none". change는 부호 포함(예: "-3.31%", "+8.9원").
- 숫자가 2개 이상 나오는 문장은 tiles나 bars, 숫자 하나면 counter를 우선.
- 숫자가 없는 문장은 point(핵심 문구) 또는 gauge(충격·불안 이야기일 때만). headline은 그 기사 내용을 말하는 문장에만, 기사마다 한 번만.
- gauge의 text·badge는 문장에 나온 사실만 (예: "매도 사이드카 발동"). "매수 기회", "매수 고민 구간"처럼 투자 판단·권유로 읽히는 말은 절대 쓰지 마.
- point의 key도 문장 내용을 줄인 말만. 투자 권유·예측을 덧붙이지 마.
- 같은 종류를 세 번 연속 쓰지 마. icon은 글자 1개(₩ $ % Q K ▲ 등).
- 마지막 문장(인사·구독 멘트)은 point로, key는 "내일 [또 만나요]"처럼 짧게.

[문장]
{chr(10).join(lines)}

[기사 헤드라인]
{hl}

JSON으로만: {{"scenes": [{{"i": 문장번호, ...장면}}]}}"""
    data = llm.ask_json(prompt, temperature=0.3)
    return {int(x["i"]): x for x in data.get("scenes", []) if str(x.get("i", "")).isdigit()}


def plan(sc, starts, durs, words, hook, end, number_word_time):
    """문장별 장면 목록 (모션 영상 기준 시간, 초)."""
    segs, heads = sc["segments"], sc.get("headlines") or []
    tag = sc.get("tag") or "오늘의 원픽"
    try:
        picks = _plan_llm(segs, heads, sc.get("hook_title", "").replace("[", "").replace("]", ""))
    except Exception as e:
        print(f"  [모션] 장면 고르기 실패 → 기본 장면: {e}")
        picks = {}
    scenes, used_h, bad = [], set(), 0
    for i, s in enumerate(segs):
        a0 = max(starts[i], hook)
        a1 = min(starts[i] + durs[i], end) if i < len(segs) - 1 else end
        if a1 - a0 < 0.5:
            continue
        p = dict(picks.get(i) or {})
        p.pop("i", None)
        if p.get("type") == "headline" and p.get("h") in used_h:
            p = {}
        chk = _check(p, s, heads) if p else None
        if chk is None:
            if p:
                bad += 1
            n = s.get("number")
            chk = ({"type": "counter", "label": n.get("label", ""), "value": n["value"], "change": n.get("change", ""),
                    "dir": n.get("dir", "none")} if n and n.get("value") and _digits(n["value"])[:3] in _digits(s["text"])
                   else {"type": "point", "key": _short_key(s["text"]), "sub": tag})
        if chk["type"] == "headline":
            used_h.add(chk["h"])
        for it in chk.get("items") or []:   # 그 값을 말하는 순간에 등장
            at = number_word_time(it.get("value", ""), s["text"], words, i)
            it["at"] = round(max(0.2, (at - a0)) if at is not None else 0.2, 2)
            v = re.findall(r"\d+(?:\.\d+)?", (it.get("value") or "").replace(",", ""))
            it["pct"] = float(v[0]) if v else 0
        for k in ("key", "text", "label", "title", "badge", "sub", "value", "change"):
            if isinstance(chk.get(k), str):
                chk[k] = _safe(chk[k])
        for it in chk.get("items") or []:
            for k in ("label", "name", "value", "change"):
                if isinstance(it.get(k), str):
                    it[k] = _safe(it[k])
        chk.update({"from": round(a0 - hook, 3), "to": round(a1 - hook, 3), "seg": i})
        scenes.append(chk)
    print(f"  [모션] 장면 {len(scenes)}개: " + ", ".join(x["type"] for x in scenes)
          + (f" (규칙 위반으로 바꾼 장면 {bad}개)" if bad else ""))
    return scenes


def render(scenes, length, tag, workdir):
    """Remotion으로 카드 영상 렌더. 실패하면 None."""
    workdir.mkdir(parents=True, exist_ok=True)
    props = workdir / "motion_props.json"
    props.write_text(json.dumps({"scenes": scenes, "tag": tag, "total": round(length, 3)}, ensure_ascii=False), "utf-8")
    out = workdir / "motion.mp4"
    try:
        run(["npx", "remotion", "render", "src/index.ts", "Card", str(out.resolve()), f"--props={props.resolve()}",
             "--codec=h264", "--crf=16", "--concurrency=4", "--log=error"],
            timeout=max(900, int(length * 12)), cwd=ROOT)
    except Exception as e:
        print(f"  [모션] 렌더 실패 → 기존 배경 영상 그대로: {e}")
        return None
    return out if out.exists() and out.stat().st_size > 10000 else None


def apply(bg, motion, start, ranges, workdir):
    """배경 영상(카드 레이아웃)의 카드 자리에 모션 영상을 덮음 (둥근 모서리). ranges: 덮을 구간 [(시작, 끝)] (영상 기준 초)."""
    from PIL import Image, ImageDraw
    mask = workdir / "motion_mask.png"
    m = Image.new("L", (CARD["w"], CARD["h"]), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, CARD["w"] - 1, CARD["h"] - 1], radius=36, fill=255)
    m.save(mask)
    out = workdir / "bg_motion.mp4"
    en = "+".join(f"between(t,{a:.3f},{b - 0.02:.3f})" for a, b in ranges)
    fc = (f"[1:v]setpts=PTS+{start:.3f}/TB,format=rgba[m];[2:v]format=gray[k];[m][k]alphamerge[mk];"
          f"[0:v][mk]overlay={CARD['x']}:{CARD['y']}:enable='{en}':eof_action=pass[v]")
    run(["ffmpeg", "-nostdin", "-y", "-i", bg, "-i", motion, "-loop", "1", "-i", mask, "-filter_complex", fc,
         "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", out],
        timeout=900)
    return out
