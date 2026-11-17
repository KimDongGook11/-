"""진단: ① 오늘 뉴스 후보별로 근거 본문을 얼마나 확보하는지 (보강 검색 포함) ② 1위 뉴스로 대본을 써서 팩트체크까지 시험.
영상·음성은 만들지 않음 (타입캐스트 크레딧 사용 없음)."""
import copy
from collections import Counter

from . import config, factcheck, news, script
from .utils import load_state


def main():
    items = news.fetch_all()
    hist = load_state("history", [])
    cands, pool = news.rank(items, hist, top=25)
    print(f"\n수집 기사 {len(items)}개, 후보 {len(cands)}개\n")
    got, src_ok = [], Counter()
    for c in cands[:12]:
        mats = script.gather_materials(pool, c)
        n = sum(1 for m in mats if m.get("body"))
        got.append(n)
        for m in mats:
            if m.get("body"):
                src_ok[m["source"]] += 1
        print(f"   → [{c['source']}] {c['title'][:60]} | 본문 {n}개\n")
    print("===== 근거 본문 확보 요약 (상위 12개 후보) =====")
    print(f"후보당 평균 본문 {sum(got) / max(len(got), 1):.1f}개, 본문 0개인 후보 {got.count(0)}개, 2개 이상 {sum(1 for g in got if g >= 2)}개")
    print("본문을 준 매체:", dict(src_ok.most_common()))

    print("\n===== 1위 뉴스로 대본 + 팩트체크 시험 =====")
    idx, pick = script.pick_story(cands, hist)
    main_item = cands[idx]
    print("선정:", main_item["title"], "/", pick.get("reason"))
    mats = script.gather_materials(pool, main_item)
    sc = script.write_script(mats, pick.get("topic") or main_item["title"], config.BRAND_NAME)
    before = copy.deepcopy(sc["segments"])
    sc, rep = factcheck.run(sc, mats)
    print("\n" + factcheck.summary(rep))
    print("\n[대본 — 고친 문장은 '→'로 표시]")
    after = [s["text"] for s in sc["segments"]]
    for s in before:
        mark = "" if s["text"] in after else "  ✎"
        print(f" - {s['text']}{mark}")
    changed = [t for t in after if t not in [b["text"] for b in before]]
    for t in changed:
        print(f"   → {t}")


if __name__ == "__main__":
    main()
