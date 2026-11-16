"""목소리 비교 샘플: 지금 목소리(edge) + 타입캐스트 후보들로 같은 문장을 읽혀 텔레그램·Release 'voice-lab'에 올림.
후보 지정: TYPECAST_CANDIDATES="tc_xxx,tc_yyy" (없으면 내레이션·뉴스용 목소리를 자동으로 남녀 3개씩)"""
import os
import re
import subprocess
import tempfile
from pathlib import Path

import requests

from . import config, storage, telegram, tts

SENTENCES = [
    "국제 유가가 하루 만에 7% 넘게 올랐습니다.",
    "중동 긴장이 다시 커지면서 원유 공급이 줄어들 수 있다는 걱정 때문인데요.",
    "기름값이 오르면 비행기표부터 택배비까지 줄줄이 영향을 받습니다.",
    "1975년, 코닥의 젊은 엔지니어가 세계 최초의 디지털카메라를 만들었습니다.",
    "하지만 회사는 이 발명을 반기지 않았죠. 필름으로 버는 돈이 너무 컸기 때문입니다.",
    "그리고 37년 뒤, 코닥은 결국 파산보호를 신청하게 됩니다.",
]
GOOD = ("news", "narrat", "document", "announc", "audiobook", "education", "explain", "e-learning", "podcast")


def voices():
    key = config.env("TYPECAST_API_KEY", "").strip()
    r = requests.get(f"{tts.TC_API}/v3/voices", headers={"X-API-KEY": key}, timeout=30)
    r.raise_for_status()
    return r.json()


def best_model(v):
    vs = [m.get("version") for m in v.get("models", [])]
    for m in ("ssfm-v31", "ssfm-v30", "ssfm-v21"):
        if m in vs:
            return m
    return "ssfm-v30"


def pick(vs):
    want = [x.strip() for x in config.env("TYPECAST_CANDIDATES", "").split(",") if x.strip()]
    if want:
        ids = [w for w in want if w.startswith(("tc_", "uc_"))]
        names = [w for w in want if not w.startswith(("tc_", "uc_"))]
        hit = [v for v in vs if v["voice_id"] in ids or
               any(n in ((v.get("voice_name") or {}).get("kor") or "") for n in names)]
        print("찾은 목소리:", [((v.get("voice_name") or {}).get("kor"), v["voice_id"]) for v in hit] or "없음")
        return hit
    def score(v):
        uc = " ".join(v.get("use_cases") or []).lower()
        s = sum(k in uc for k in GOOD) * 2
        s += {"young_adult": 2, "middle_age": 2}.get(v.get("age"), 0)
        s += 1 if any(m.get("version") in ("ssfm-v30", "ssfm-v31") for m in v.get("models", [])) else 0
        return s
    out = []
    for g in ("male", "female"):
        cand = sorted([v for v in vs if v.get("gender") == g and (v.get("voice_name") or {}).get("kor")],
                      key=score, reverse=True)
        out += cand[:3]
    return out


def render(name, parts, d):
    lst = d / f"{name}.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    out = d / f"{name}.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-af", "apad=pad_dur=0.3,loudnorm=I=-16", "-ar", "44100", "-b:a", "160k", out], check=True)
    return out


def main():
    d = Path(tempfile.mkdtemp())
    vs = voices()
    print(f"전체 목소리 {len(vs)}개")
    ucs = {}
    for v in vs:
        for u in v.get("use_cases") or []:
            ucs[u] = ucs.get(u, 0) + 1
    print("용도 분류:", dict(sorted(ucs.items(), key=lambda x: -x[1])[:30]))
    cands = pick(vs)
    files = []
    # 지금 목소리(edge)
    parts = []
    for i, t in enumerate(SENTENCES):
        mp3 = d / f"edge_{i}.mp3"
        tts._one(t, mp3, "edge")
        parts.append(mp3)
    files.append(("0_지금목소리_edge_선희", render("0_edge", parts, d), "지금 쓰는 목소리 (edge · 선희)"))
    for n, v in enumerate(cands, 1):
        nm = (v.get("voice_name") or {}).get("kor") or v["voice_id"]
        model = best_model(v)
        parts = []
        try:
            for i, t in enumerate(SENTENCES):
                mp3 = d / f"tc{n}_{i}.mp3"
                words = tts._typecast(t, mp3, prev=" ".join(SENTENCES[max(0, i - 3):i]),
                                      nxt=" ".join(SENTENCES[i + 1:i + 3]), voice=v["voice_id"], model=model)
                parts.append(mp3)
            if n == 1:
                print("  단어 타이밍 예시:", words[:4])
        except Exception as e:
            print(f"  {nm} 실패: {e}")
            continue
        label = f"{n}_{nm}_{v.get('gender')}_{v.get('age')}"
        safe = re.sub(r"[^\w가-힣]+", "_", label)
        files.append((safe, render(safe, parts, d),
                      f"{n}. {nm} ({'남' if v.get('gender') == 'male' else '여'}, {v.get('age')}, {model})\n"
                      f"ID: {v['voice_id']}\n용도: {', '.join(v.get('use_cases') or [])}"))
        print(f"  {label} {v['voice_id']} {model} {v.get('use_cases')}")
    tag = "voice-lab"
    storage.delete(tag)
    for k, (safe, path, cap) in enumerate(files):
        if k == 0:
            storage.upload(str(path), tag, title="목소리 비교")
        else:
            storage.add_asset(tag, str(path), f"{safe}.mp3")
        if telegram.enabled():
            telegram.send_document(str(path), "🎙 " + cap)
    print("완료:", [f[0] for f in files])


if __name__ == "__main__":
    main()
