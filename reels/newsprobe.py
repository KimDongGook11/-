"""진단: 오늘 뉴스 후보 상위 기사들의 본문을 실제로 얼마나 가져올 수 있는지 (팩트체크 가능성 점검)."""
from collections import defaultdict

from . import news
from .utils import load_state


def main():
    items = news.fetch_all()
    cands, pool = news.rank(items, load_state("history", []), top=25)
    print(f"수집 기사 {len(items)}개, 후보 {len(cands)}개")
    by_src = defaultdict(lambda: [0, 0, 0])
    for c in cands:
        group = [c] + [pool[j] for j in c.get("related", [])]
        ok = 0
        for it in group[:6]:
            body = news.fetch_article_text(it["link"])
            s = by_src[it["source"]]
            s[0] += 1
            if len(body) >= 800:
                s[1] += 1
                ok += 1
            s[2] += len(body)
        print(f"- [{c['source']}] {c['title'][:70]} | 같은 주제 기사 {len(group)}개, 본문 확보 {ok}개")
    print("\n매체별 본문 확보 (800자 이상)")
    for src, (n, ok, tot) in sorted(by_src.items(), key=lambda x: -x[1][0]):
        print(f"  {src}: {ok}/{n} (평균 {tot // max(n, 1)}자)")


if __name__ == "__main__":
    main()
