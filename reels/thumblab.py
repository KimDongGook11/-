"""썸네일 시험 제작: 위키미디어 실제 기업 사진 썸네일 몇 장을 만들어 GitHub Release 'thumb-lab'에 올림."""
import requests

from . import config, doubleexp, graphics, realphoto, storage

SAMPLES = [(["Apple Inc.", "History of Apple Inc."], "파산 90일 전", "돌아온 창업자", "1997  ·  애플  ·  IT", "EP.4"),
           (["Nintendo", "History of Nintendo"], "소니를 버린", "닌텐도의 결정", "1991  ·  닌텐도  ·  게임", "EP.3"),
           (["Nvidia"], "월가의 비난", "사운 건 베팅", "2006  ·  엔비디아  ·  반도체", "EP.5"),
           (["Kodak", "Eastman Kodak"], "최초를 은폐한", "코닥의 몰락", "1975  ·  코닥  ·  필름", "EP.2")]


def main():
    out = config.OUTPUT_DIR / "thumblab"
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for i, (country, l1, l2, sub, ep) in enumerate(SAMPLES):
        wd = out / f"s{i}"
        wd.mkdir(exist_ok=True)
        real, credit = realphoto.company_photo(country, wd, episode=f"{sub} — {l1} {l2}")
        if real:
            p = graphics.thumbnail_photo(real, l1, l2, sub, ep, out / f"thumb_{i}.jpg")
        else:
            p = graphics.thumbnail(None, l1, l2, sub, ep, out / f"thumb_{i}.jpg",
                                   figure=doubleexp.figure_for("미국", wd, seed=i))
        print(i, credit)
        files.append(p)
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
