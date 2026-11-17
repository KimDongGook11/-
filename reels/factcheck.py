"""대본 팩트체크: ① 숫자 자동 대조(대본 숫자가 근거 기사에 실제로 있는지) ② AI 문장 검증 ③ 걸린 문장만 근거로 다시 쓰기.
결과는 텔레그램 초안 메시지에 함께 표시됩니다."""
import re

from . import llm

KO_UNIT = {"십": 10, "백": 100, "천": 1e3, "만": 1e4, "억": 1e8, "조": 1e12}
EN_UNIT = {"thousand": 1e3, "k": 1e3, "million": 1e6, "mn": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9,
           "trillion": 1e12, "tn": 1e12, "t": 1e12}
DATEISH = ("년", "월", "일", "시", "분", "초", "세기", "개월", "주년", "분기", "차", "번째", "위")
CHECK_AFTER = ("원", "달러", "엔", "위안", "유로", "파운드", "배", "명", "건", "개", "대", "톤", "배럴", "포인트", "bp",
               "피", "선")


def _f(x):
    return float(x.replace(",", ""))


def ko_numbers(text):
    """한국어 문장 속 숫자 → [(값, 종류, 원문)]. 종류: pct(%) / pt(%포인트) / num."""
    out = []
    pat = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([십백천만억조]*)")
    pos = 0
    while True:
        m = pat.search(text, pos)
        if not m:
            break
        start, val, scale_used = m.start(), 0.0, False
        end = m.end()
        # "1조 2천억", "3천 500억"처럼 이어지는 단위를 합산
        cur = m
        while cur:
            num, units = _f(cur.group(1)), cur.group(2)
            mult = 1.0
            for u in units:
                mult *= KO_UNIT[u]
            scale_used = scale_used or bool(units)
            val += num * mult
            end = cur.end()
            nxt = pat.match(text, end + (1 if text[end:end + 1] == " " else 0))
            if nxt and units and units[-1] in "조억만" and nxt.group(2):
                cur = nxt
            else:
                cur = None
        tail = text[end:end + 6].lstrip()
        raw = text[start:end].strip()
        pos = end
        if tail.startswith(("%포인트", "%p", "퍼센트포인트")):
            out.append((val, "pt", raw + "%p"))
        elif tail.startswith(("%", "퍼센트", "프로")):
            out.append((val, "pct", raw + "%"))
        elif tail.startswith(DATEISH) and not scale_used:
            continue                                    # 날짜·순서는 검사 제외
        elif scale_used or val >= 100 or tail.startswith(CHECK_AFTER):
            if 1900 <= val <= 2100 and not scale_used and not tail.startswith(CHECK_AFTER):
                continue                                # 연도
            out.append((val, "num", raw))
    return out


def src_numbers(text):
    """근거 기사(영어·한국어) 속 숫자 값들."""
    vals = []
    for m in re.finditer(r"\$?(\d[\d,]*(?:\.\d+)?)\s*(%|percent|per cent|percentage points?|basis points?|bps?|"
                         r"trillion|billion|million|thousand|tn|bn|mn|[kmbt])?\b", text, flags=re.I):
        try:
            v = _f(m.group(1))
        except ValueError:
            continue
        u = (m.group(2) or "").lower()
        if u in ("%", "percent", "per cent"):
            vals.append((v, "pct"))
        elif u.startswith("percentage point"):
            vals.append((v, "pt"))
        elif u.startswith("bp") or u.startswith("basis point"):
            vals.append((v / 100, "pt"))
            vals.append((v, "num"))
        else:
            vals.append((v * EN_UNIT.get(u, 1), "num"))
    vals += [(v, k) for v, k, _ in ko_numbers(text)]
    return vals


def _match(v, kind, pool):
    for s, k in pool:
        if kind in ("pct", "pt") and k not in ("pct", "pt"):
            continue
        if kind == "num" and k != "num":
            continue
        if s == 0 and v == 0:
            return True
        if s and abs(abs(v) - abs(s)) / abs(s) <= 0.03:     # 반올림 허용(3%)
            return True
        if kind in ("pct", "pt") and abs(abs(v) - abs(s)) <= 0.051:
            return True
    return False


def check_numbers(sc, sources_text):
    pool = src_numbers(sources_text)
    res = []
    for i, seg in enumerate(sc["segments"]):
        nums = ko_numbers(seg["text"])
        if seg.get("number") and seg["number"].get("value"):
            nums += ko_numbers(seg["number"]["value"])
        bad = [raw for v, k, raw in nums if not _match(v, k, pool)]
        res.append({"i": i, "total": len(nums), "bad": bad})
    return res


def _sources_block(mats, limit=3500):
    out = []
    for j, m in enumerate(mats):
        b = f"[자료 {j+1}] {m['source']} — {m['title']}\n{m.get('summary') or ''}"
        if m.get("body"):
            b += "\n" + m["body"][:limit]
        out.append(b)
    return "\n\n".join(out)


def ai_verify(sc, mats, idx=None):
    idx = list(range(len(sc["segments"]))) if idx is None else idx
    lines = "\n".join(f"{i}. {sc['segments'][i]['text']}" for i in idx)
    prompt = f"""너는 경제 뉴스 팩트체커야. 아래 [대본] 문장 하나하나가 [자료]로 뒷받침되는지 판정해.
- ok: 자료에 그 사실이 있음 (쉬운 말 풀이·요약·통화 단위 환산은 괜찮음)
- partial: 대체로 맞지만 숫자·시점·주체 중 하나가 자료와 다르거나 과장됨
- unsupported: 자료에 없는 사실·숫자·인과관계를 지어냄
- skip: 질문·인사·일반 상식·감상처럼 확인할 사실이 없는 문장
투자 일반론("금리가 오르면 대출 이자가 늘어요" 같은 상식)은 skip으로 봐.

[대본]
{lines}

[자료]
{_sources_block(mats)}

JSON으로만: {{"results": [{{"i": 문장번호, "verdict": "ok|partial|unsupported|skip", "why": "다르면 무엇이 다른지 20자 내외"}}]}}"""
    data = llm.ask_json(prompt, temperature=0.1)
    return {int(r.get("i", -1)): r for r in data.get("results", []) if str(r.get("i", "")).lstrip("-").isdigit()}


def fix(sc, mats, problems):
    """걸린 문장만 근거에 맞게 다시 쓰기. problems: {i: 이유}"""
    lines = "\n".join(f"{i}. {sc['segments'][i]['text']}  ← 문제: {why}" for i, why in problems.items())
    prompt = f"""아래 대본 문장들이 근거 자료와 맞지 않아. [자료]에 있는 사실만으로 각 문장을 다시 써.
- 길이·말투(친근한 존댓말)·문장 역할은 비슷하게 유지
- 자료로 확인되는 숫자가 없으면 숫자를 빼고 써
- 자료로 아예 뒷받침할 수 없으면 text를 빈 문자열로 (문장 삭제)
- number 카드가 있던 문장이면 number도 자료에 있는 값으로 고치거나 null

[고칠 문장]
{lines}

[자료]
{_sources_block(mats)}

JSON으로만: {{"fixes": [{{"i": 번호, "text": "고친 문장", "number": null 또는 {{"value": "4.3%", "label": "설명", "dir": "up|down|none"}}}}]}}"""
    data = llm.ask_json(prompt, temperature=0.3)
    return data.get("fixes", [])


def run(sc, mats, skip_last=0):
    """대본을 검사하고 걸린 문장은 한 번 고침. 반환: (대본, 보고 dict)"""
    from .script import _number
    n = len(sc["segments"]) - skip_last
    text = "\n".join((m.get("title") or "") + " " + (m.get("summary") or "") + " " + (m.get("body") or "")
                     for m in mats)
    bodies = sum(1 for m in mats if m.get("body"))
    nums = check_numbers(sc, text)[:n]
    try:
        ver = ai_verify(sc, mats, list(range(n)))
    except Exception as e:
        print(f"  [팩트체크] AI 검증 실패: {e}")
        ver = {}
    problems = {}
    for r in nums:
        if r["bad"]:
            problems[r["i"]] = "근거에 없는 숫자: " + ", ".join(r["bad"])
    for i, v in ver.items():
        if 0 <= i < n and v.get("verdict") in ("partial", "unsupported"):
            problems[i] = (problems.get(i, "") + " / " if i in problems else "") + f"{v['verdict']}: {v.get('why', '')}"
    fixed, dropped = 0, 0
    if problems:
        print(f"  [팩트체크] 고칠 문장 {len(problems)}개: {problems}")
        try:
            for f in fix(sc, mats, problems):
                i = int(f.get("i", -1))
                if i not in problems:
                    continue
                t = str(f.get("text", "")).strip()
                if t:
                    sc["segments"][i]["text"] = t
                    sc["segments"][i]["number"] = _number(f.get("number"))
                    fixed += 1
                else:
                    sc["segments"][i]["text"] = ""
                    dropped += 1
        except Exception as e:
            print(f"  [팩트체크] 고치기 실패: {e}")
        sc["segments"] = [s for s in sc["segments"] if s["text"]]
        n = len(sc["segments"]) - skip_last
    # 고친 뒤 최종 확인 (숫자는 다시 대조, 남은 문제는 텔레그램에 ⚠️로)
    nums2 = check_numbers(sc, text)[:n]
    remain = [f"{r['i']+1}번 문장 숫자 {', '.join(r['bad'])}" for r in nums2 if r["bad"]]
    if fixed:
        try:
            changed = [i for i in range(n) if sc["segments"][i]["text"]]
            ver2 = ai_verify(sc, mats, changed)
            remain += [f"{i+1}번 문장 {v['verdict']}: {v.get('why', '')}" for i, v in ver2.items()
                       if 0 <= i < n and v.get("verdict") in ("partial", "unsupported")]
        except Exception:
            pass
    total = sum(r["total"] for r in nums2)
    bad = sum(len(r["bad"]) for r in nums2)
    report = {"bodies": bodies, "sources": len(mats), "numbers": total, "numbers_ok": total - bad,
              "checked": n, "fixed": fixed, "dropped": dropped, "remain": remain[:6]}
    print(f"  [팩트체크] {summary(report)}")
    return sc, report


def summary(r):
    if not r:
        return ""
    head = "✅ 팩트체크 통과" if not r["remain"] else "⚠️ 팩트체크 확인 필요"
    s = (f"{head} — 근거 본문 {r['bodies']}/{r['sources']}개, 숫자 {r['numbers_ok']}/{r['numbers']}개 일치"
         + (f", 고친 문장 {r['fixed']}개" if r["fixed"] else "") + (f", 뺀 문장 {r['dropped']}개" if r["dropped"] else ""))
    if r["remain"]:
        s += "\n" + "\n".join("  · " + x for x in r["remain"])
    if r["bodies"] < 2:
        s += "\n  · 본문 근거가 적어요(제목·요약 위주). 숫자를 한 번 더 봐 주세요."
    return s
