"""문장별 한국어 음성 + 단어별 타이밍.

반환: narration.wav, 문장별 길이(초), 단어 목록 [(시작초, 끝초, 단어, 문장번호)] (영상 전체 기준 시각)
- edge (기본): 마이크로소프트 음성, 단어별 타이밍을 정확히 받아 자막을 말에 맞춤
- gemini: 구글 Gemini 음성(더 자연스러움, 무료 한도 안에서). 단어 타이밍은 글자 수로 추정
- gtts / dummy: 대체용·테스트용
"""
import asyncio
import base64
import wave

from . import config
from .utils import duration, run

PAD = 0.25  # 문장 사이 쉬는 시간(초)


async def _edge(text, out_mp3):
    import edge_tts
    try:
        com = edge_tts.Communicate(text, config.TTS_VOICE, rate=config.TTS_RATE, boundary="WordBoundary")
    except TypeError:   # 예전 버전은 boundary 옵션이 없고 기본이 단어 단위
        com = edge_tts.Communicate(text, config.TTS_VOICE, rate=config.TTS_RATE)
    words = []
    with open(out_mp3, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                words.append((s, s + ch["duration"] / 1e7, ch["text"]))
    return words


def _gemini(text, out_wav):
    """Gemini TTS (응답: 24kHz 16bit PCM). 사용 가능한 tts 모델을 자동으로 찾음."""
    import requests
    base = "https://generativelanguage.googleapis.com/v1beta"
    h = {"x-goog-api-key": config.GEMINI_API_KEY}
    models = [m["name"].split("/")[-1] for m in
              requests.get(f"{base}/models", params={"pageSize": 1000}, headers=h, timeout=30).json().get("models", [])
              if "tts" in m.get("name", "")]
    if not models:
        raise RuntimeError("Gemini 음성 모델을 쓸 수 없음")
    models.sort(key=lambda n: ("flash" not in n, n), reverse=False)
    body = {"contents": [{"parts": [{"text": f"차분하고 또렷한 뉴스 내레이터 톤으로 읽어 주세요: {text}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": config.env("GEMINI_VOICE", "Kore")}}}}}
    r = requests.post(f"{base}/models/{models[0]}:generateContent", json=body, headers=h, timeout=120)
    r.raise_for_status()
    pcm = base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)


def _estimate_words(text, total):
    """단어 타이밍을 글자 수 비율로 추정 (타이밍을 못 받는 음성 엔진용)."""
    ws = text.split()
    weights = [len(w) + 1 for w in ws]
    t, out = 0.05, []
    span = max(0.3, total - 0.1)
    for w, k in zip(ws, weights):
        d = span * k / sum(weights)
        out.append((t, t + d, w))
        t += d
    return out


def _one(text, out_mp3, engine):
    """음성 한 문장 → (오디오 파일, 단어 타이밍 또는 None)"""
    if engine == "dummy":
        secs = max(1.5, len(text.replace(" ", "")) / 6.5)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100",
             "-af", "volume=0.03", "-t", f"{secs:.2f}", out_mp3])
        return out_mp3, None
    if engine == "gemini":
        try:
            wav = out_mp3.with_suffix(".gem.wav")
            _gemini(text, wav)
            return wav, None
        except Exception as e:
            print(f"  [음성] Gemini 음성 실패 → edge로 대체: {e}")
            engine = "edge"
    if engine == "edge":
        for attempt in range(3):
            try:
                words = asyncio.run(_edge(text, out_mp3))
                if out_mp3.exists() and out_mp3.stat().st_size > 1000:
                    return out_mp3, words or None
            except Exception as e:
                print(f"  [음성] edge-tts 실패({attempt+1}/3): {e}")
        print("  [음성] gTTS로 대체합니다")
    from gtts import gTTS
    gTTS(text, lang="ko").save(str(out_mp3))
    return out_mp3, None


def synthesize(texts, workdir, lead=None, tail=0.0):
    """lead: 문장번호 → 문장 앞에 넣을 쉼(초) (장편의 챕터 카드용). tail: 끝에 붙일 쉼(아웃트로용)."""
    workdir.mkdir(parents=True, exist_ok=True)
    lead = lead or {}
    engine = config.TTS_ENGINE
    wavs, durs, words = [], [], []
    t0 = 0.0
    for i, text in enumerate(texts):
        mp3 = workdir / f"tts_{i:02d}.mp3"
        wav = workdir / f"tts_{i:02d}.wav"
        src, ws = _one(text, mp3, engine)
        pre = float(lead.get(i, 0.0))
        post = PAD + (tail if i == len(texts) - 1 else 0.0)
        af = (f"adelay={int(pre * 1000)}:all=1," if pre > 0 else "") + f"apad=pad_dur={post}"
        run(["ffmpeg", "-y", "-i", src, "-af", af, "-ar", "48000", "-ac", "1", wav])
        d = duration(wav)
        speech = d - pre - post
        if not ws:
            ws = _estimate_words(text, speech)
        for s, e, w in ws:
            words.append((t0 + pre + s, t0 + pre + min(e, speech), w, i))
        wavs.append(wav)
        durs.append(d)
        t0 += d
    lst = workdir / "tts_list.txt"
    lst.write_text("".join(f"file '{w.resolve()}'\n" for w in wavs))
    narration = workdir / "narration.wav"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", narration])
    print(f"  [음성] {len(texts)}문장, 총 {sum(durs):.1f}초, 단어 {len(words)}개 ({engine})")
    return narration, durs, words
