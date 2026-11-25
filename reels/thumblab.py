"""썸네일 시험 제작: 위키미디어 실제 기업 사진 썸네일 몇 장을 만들어 GitHub Release 'thumb-lab'에 올림."""
import requests

from . import config, doubleexp, graphics, realphoto, storage

# (인물, 위키 문서, 숫자, 숫자 설명, 방향, 질문, 둘째 줄, 아래 줄)  — 숫자 충격형 시험
SAMPLES = [("Steve Jobs", ["Apple Inc."], "90일", "파산까지 남은 시간", "none", "누가 살렸나?", "돌아온 창업자", "1997  ·  애플"),
           ("Jensen Huang", ["Nvidia"], "-6.16%", "코스피 하루 만에", "down", "젠슨황 효과 끝?", "반도체 동반 급락", "삼성전자  ·  SK하이닉스"),
           ("Satya Nadella", ["Microsoft"], "687억 달러", "역대 최대 인수", "up", "왜 샀을까?", "MS의 게임 베팅", "2022  ·  마이크로소프트"),
           ("Elon Musk", ["Tesla, Inc."], "1조 달러", "시가총액", "up", "거품일까?", "테슬라의 질주", "2021  ·  테슬라")]


def main():
    out = config.OUTPUT_DIR / "thumblab"
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for i, (person, titles, num, label, dr, q, l2, sub) in enumerate(SAMPLES):
        wd = out / f"s{i}"
        wd.mkdir(exist_ok=True)
        real, credit = realphoto.company_photo([person] + titles, wd, episode=f"{sub} — {q} {l2}", person=person)
        if real:
            print("  얼굴 위치:", graphics._face_x(__import__("PIL.Image", fromlist=["Image"]).open(real)))
            p = graphics.thumbnail_number(real, num, label, q, l2, sub, dr, out / f"thumb_{i}.jpg")
        else:
            p = graphics.thumbnail(None, q, l2, sub, None, out / f"thumb_{i}.jpg",
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
