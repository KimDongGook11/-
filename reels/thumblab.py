"""썸네일 시험 제작: 실제 무료 사진으로 이중 노출 썸네일 몇 장을 만들어 GitHub Release 'thumb-lab'에 올림."""
import requests

from . import config, doubleexp, graphics, storage

SAMPLES = [("미국", "파산 90일 전", "돌아온 창업자", "1997  ·  애플  ·  IT", "EP.4"),
           ("일본", "소니를 버린", "닌텐도의 결정", "1991  ·  닌텐도  ·  게임", "EP.3"),
           ("한국", "반도체에 건", "이건희의 도박", "1983  ·  삼성  ·  반도체", "EP.5"),
           ("미국", "5천만 달러를", "거절한 대가", "2000  ·  블록버스터  ·  유통", "EP.2")]


def main():
    out = config.OUTPUT_DIR / "thumblab"
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for i, (country, l1, l2, sub, ep) in enumerate(SAMPLES):
        wd = out / f"s{i}"
        wd.mkdir(exist_ok=True)
        fig = doubleexp.figure_for(country, wd, seed=i)
        p = graphics.thumbnail(None, l1, l2, sub, ep, out / f"thumb_{i}.jpg", figure=fig)
        files.append(p)
        if fig:
            files.append(fig.rename(out / f"figure_{i}.png"))
    if not storage.enabled():
        print("로컬 실행: 저장만 함", files)
        return
    tag = "thumb-lab"
    storage.delete(tag)
    r = requests.post(f"{storage.API}/repos/{storage._repo()}/releases", headers=storage._h(), timeout=30,
                      json={"tag_name": tag, "name": "썸네일 시험", "prerelease": True, "body": "썸네일 시험 결과"})
    r.raise_for_status()
    up = r.json()["upload_url"].split("{")[0]
    for f in files:
        ctype = "image/jpeg" if str(f).endswith(".jpg") else "image/png"
        with open(f, "rb") as fh:
            requests.post(f"{up}?name={f.name}", data=fh, timeout=120,
                          headers=storage._h({"Content-Type": ctype})).raise_for_status()
    print("올림:", [f.name for f in files])


if __name__ == "__main__":
    main()
