"""대담 특집 캐릭터 시험 제작 (수동 실행): Gemini 이미지 모델로 서현·필재 반실사 초상을 만들어
배경을 지우고 텔레그램으로 보냄. 고른 그림만 assets/characters 에 넣어 씀."""
import base64
import io
import json
import sys
from pathlib import Path

import requests

from . import config, telegram

BASE = "https://generativelanguage.googleapis.com/v1beta"
COMMON = ("Semi-realistic digital painting portrait for a YouTube economics talk show called 'Issue Backstory', bust shot from chest up, "
          "facing the viewer, soft studio lighting, clean and friendly, high detail, plain solid dark navy "
          "background (#0E1628), no text, no logo, no watermark. Fictional person, not a real celebrity. ")
PEOPLE = {
    "seohyun": "A Korean woman in her late 20s, the show host. Shoulder-length softly wavy dark brown hair, "
               "natural makeup, bright confident smile, cream-colored blazer over a navy top, small yellow pin on the lapel.",
    "piljae": "A Korean man in his late 30s, an economics analyst. Short neat black hair, black rectangular glasses, "
              "calm warm smile, navy suit, white shirt and blue tie.",
}


def _h():
    return {"x-goog-api-key": config.GEMINI_API_KEY}


def image_models():
    r = requests.get(f"{BASE}/models", params={"pageSize": 1000}, headers=_h(), timeout=30)
    r.raise_for_status()
    gen, imagen = [], []
    for m in r.json().get("models", []):
        n, meth = m["name"].split("/")[-1], m.get("supportedGenerationMethods", [])
        if "image" in n and "generateContent" in meth:
            gen.append(n)
        elif n.startswith("imagen") and "predict" in meth:
            imagen.append(n)
    print("이미지 모델:", gen, imagen)
    return sorted(gen, reverse=True), sorted(imagen, reverse=True)


def gen_image(prompt):
    gen, imagen = image_models()
    errs = []
    for m in gen:
        try:
            r = requests.post(f"{BASE}/models/{m}:generateContent", headers=_h(), timeout=180, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}})
            r.raise_for_status()
            for part in r.json()["candidates"][0]["content"]["parts"]:
                if "inlineData" in part:
                    return base64.b64decode(part["inlineData"]["data"]), m
            errs.append(f"{m}: 그림 없음")
        except Exception as e:
            errs.append(f"{m}: {str(e)[:160]}")
    for m in imagen:
        try:
            r = requests.post(f"{BASE}/models/{m}:predict", headers=_h(), timeout=180, json={
                "instances": [{"prompt": prompt}], "parameters": {"sampleCount": 1, "aspectRatio": "3:4"}})
            r.raise_for_status()
            return base64.b64decode(r.json()["predictions"][0]["bytesBase64Encoded"]), m
        except Exception as e:
            errs.append(f"{m}: {str(e)[:160]}")
    raise RuntimeError(" / ".join(errs) or "쓸 수 있는 이미지 모델 없음")


def cutout(png_bytes):
    from PIL import Image
    try:
        from rembg import remove
        return remove(Image.open(io.BytesIO(png_bytes)).convert("RGBA"))
    except Exception as e:
        print("배경 지우기 실패(원본 사용):", e)
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def main():
    out = Path("output/characters")
    out.mkdir(parents=True, exist_ok=True)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    report = []
    for key, desc in PEOPLE.items():
        for k in range(n):
            try:
                data, model = gen_image(COMMON + desc)
                raw = out / f"{key}_{k + 1}_raw.png"
                raw.write_bytes(data)
                cut = out / f"{key}_{k + 1}.png"
                cutout(data).save(cut)
                report.append(f"{key} {k + 1}: {model}")
                if telegram.enabled():
                    telegram.send_photo(str(raw), f"🎨 캐릭터 후보 · {'서현(진행)' if key == 'seohyun' else '필재(패널)'} {k + 1}번")
            except Exception as e:
                report.append(f"{key} {k + 1}: 실패 {e}")
    print("\n".join(report))
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
