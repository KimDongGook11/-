"""문장별 한국어 음성 + 단어별 타이밍.

반환: narration.wav, 문장별 길이(초), 단어 목록 [(시작초, 끝초, 단어, 문장번호)] (영상 전체 기준 시각)
- edge (기본): 마이크로소프트 음성, 단어별 타이밍을 정확히 받아 자막을 말에 맞춤
- typecast: 타입캐스트 API (유료, 감정 표현 자연스러움). 단어 타이밍을 받아 자막을 말에 맞춤.
  실패(크레딧 소진 등)하면 edge로 자동 대체. 설정: TYPECAST_API_KEY, TYPECAST_VOICE, TYPECAST_MODEL, TYPECAST_TEMPO
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
        com = edge_tts.Communicate(text, edge_voice(), rate=config.TTS_RATE, boundary="WordBoundary")
    except TypeError:   # 예전 버전은 boundary 옵션이 없고 기본이 단어 단위
        com = edge_tts.Communicate(text, edge_voice(), rate=config.TTS_RATE)
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
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": GEMINI_BY_SERIES.get(_series) or config.env("GEMINI_VOICE", "Kore")}}}}}
    r = requests.post(f"{base}/models/{models[0]}:generateContent", json=body, headers=h, timeout=120)
    r.raise_for_status()
    pcm = base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)


TC_API = "https://api.typecast.ai"
PILJAE = "tc_68257f68bc6e3c161ab5078d"
# 시리즈별 목소리 (2026-11-21 사용자 결정: 평일 콘텐츠(미국 마감·원픽·국내 마감) = 여성 서현, 그때 그 결정 = 필재). ID 또는 한글 이름
DAY_VOICE = "서현"
VOICE_BY_SERIES = {
    "news": lambda: config.env("TYPECAST_VOICE_NEWS", DAY_VOICE),
    "us": lambda: config.env("TYPECAST_VOICE_US") or config.env("TYPECAST_VOICE_NEWS", DAY_VOICE),
    "kr": lambda: config.env("TYPECAST_VOICE_KR") or config.env("TYPECAST_VOICE_NEWS", DAY_VOICE),
    # 예전 TYPECAST_VOICE 변수는 보지 않음: 다른 목소리가 남아 있어도 그때 그 결정은 필재로
    "history": lambda: config.env("TYPECAST_VOICE_HISTORY", PILJAE),
}
# 타입캐스트가 실패해 무료 음성(edge)으로 대체될 때도 같은 성별로: 평일 = 선희(여), 그때 그 결정 = 인준(남)
EDGE_BY_SERIES = {"history": lambda: config.env("EDGE_VOICE_HISTORY", "ko-KR-InJoonNeural")}
GEMINI_BY_SERIES = {"history": "Charon"}


def edge_voice():
    f = EDGE_BY_SERIES.get(_series)
    return f() if f else config.env("EDGE_VOICE_DAY", "ko-KR-SunHiNeural")
_series = "history"
_resolved = {}


def set_series(series):
    """이번 영상의 시리즈를 정함 (목소리 선택용)."""
    global _series
    _series = series if series in VOICE_BY_SERIES else "history"


def resolve_voice(name_or_id):
    """목소리 ID(tc_…) 또는 한글 이름(예: 서현) → ID. 못 찾으면 None."""
    if not name_or_id:
        return None
    if name_or_id.startswith(("tc_", "uc_")):
        return name_or_id
    if name_or_id in _resolved:
        return _resolved[name_or_id]
    import requests
    vid = None
    try:
        r = requests.get(f"{TC_API}/v3/voices", headers={"X-API-KEY": config.env("TYPECAST_API_KEY", "").strip()},
                         timeout=30)
        r.raise_for_status()
        hits = [v for v in r.json() if ((v.get("voice_name") or {}).get("kor") or "").strip() == name_or_id.strip()]
        hits.sort(key=lambda v: not any(m.get("version") == "ssfm-v31" for m in v.get("models", [])))
        vid = hits[0]["voice_id"] if hits else None
        print(f"  [음성] '{name_or_id}' → {vid or '목록에 없음'}")
    except Exception as e:
        print(f"  [음성] 목소리 목록 조회 실패: {e}")
    _resolved[name_or_id] = vid
    return vid


def current_voice():
    """이번 시리즈의 타입캐스트 목소리 ID. 원하는 목소리를 못 찾으면 필재로 (텔레그램 알림)."""
    want = VOICE_BY_SERIES[_series]()
    vid = resolve_voice(want)
    if not vid:
        vid = PILJAE
        try:
            from . import telegram
            if telegram.enabled() and not _resolved.get("_warned_" + str(want)):
                _resolved["_warned_" + str(want)] = True
                telegram.send_message(f"ℹ️ 타입캐스트 목소리 '{want}'을(를) 찾지 못해 이번 영상은 필재 목소리로 만들어요.")
        except Exception:
            pass
    return vid


class TypecastFailed(RuntimeError):
    pass


def _typecast(text, out_mp3, prev="", nxt="", voice=None, model=None, tempo=None):
    """타입캐스트: 문장 하나 → mp3 + 단어 타이밍. 앞뒤 문장을 함께 보내 감정·억양을 자연스럽게."""
    import requests
    # 목소리: 시리즈별 (원픽 서현, 그때 그 결정 필재) — 이전: 렉스 tc_6322940059d649937b97f326
    body = {"voice_id": voice or current_voice(), "text": text,
            "model": model or config.env("TYPECAST_MODEL", "ssfm-v31"), "language": "kor",
            "prompt": {"emotion_type": "smart", "previous_text": prev[-1500:], "next_text": nxt[:1500]},
            "output": {"audio_format": "mp3", "audio_tempo": float(tempo or config.env("TYPECAST_TEMPO", "1.1"))}}
    if not body["voice_id"]:
        raise RuntimeError("TYPECAST_VOICE(목소리 ID)가 비어 있음")
    def call():
        return requests.post(f"{TC_API}/v1/text-to-speech/with-timestamps", params={"granularity": "word"},
                             json=body, headers={"X-API-KEY": config.env("TYPECAST_API_KEY", "").strip()}, timeout=120)
    r = call()
    if r.status_code in (400, 404, 422) and body["model"] == "ssfm-v31" and not model:
        body["model"] = "ssfm-v30"   # 이 목소리가 최신 모델을 지원하지 않으면 한 단계 아래로
        r = call()
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    d = r.json()
    with open(out_mp3, "wb") as f:
        f.write(base64.b64decode(d["audio"]))
    words = [(float(w["start"]), float(w["end"]), w["text"].strip()) for w in (d.get("words") or []) if w["text"].strip()]
    return words


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


def align_to_script(ws, text):
    """자막 글자는 항상 대본 원문으로. 음성 엔진이 돌려준 단어(숫자를 한글로 읽은 형태, 철자 변형 등)는
    타이밍에만 쓰고, 대본 단어를 글자 위치 비율로 그 타이밍에 맞춰 얹음."""
    toks = text.split()
    if not toks or not ws:
        return ws
    if [w for _, _, w in ws] == toks:
        return ws
    if len(ws) == len(toks):
        return [(s, e, t) for (s, e, _), t in zip(ws, toks)]
    # 엔진 단어들의 글자 누적 비율 → 시각 대응표
    lens = [max(1, len(w.replace(" ", ""))) for _, _, w in ws]
    tot = sum(lens)
    def at(f):   # 글자 비율 f(0~1) → 시각
        acc = 0
        for (s, e, _), n in zip(ws, lens):
            if acc + n >= f * tot:
                return s + (e - s) * max(0.0, f * tot - acc) / n
            acc += n
        return ws[-1][1]
    tl = [max(1, len(t)) for t in toks]
    ttot = sum(tl)
    out, acc = [], 0
    for t, n in zip(toks, tl):
        out.append((at(acc / ttot), at((acc + n) / ttot), t))
        acc += n
    return out


def _one(text, out_mp3, engine, prev="", nxt=""):
    """음성 한 문장 → (오디오 파일, 단어 타이밍 또는 None)"""
    if engine == "typecast":
        last = None
        for attempt in range(2):
            try:
                words = _typecast(text, out_mp3, prev, nxt)
                if out_mp3.exists() and out_mp3.stat().st_size > 1000:
                    return out_mp3, words or None
            except Exception as e:
                last = e
                print(f"  [음성] 타입캐스트 실패({attempt+1}/2): {e}")
                if any(c in str(e) for c in ("401", "402", "403")):
                    break
        raise TypecastFailed(str(last))
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
    if engine == "typecast":
        try:
            return _synth(texts, workdir, lead, tail, engine)
        except TypecastFailed as e:   # 목소리가 섞이지 않게 처음부터 edge로 다시
            print(f"  [음성] 타입캐스트를 쓸 수 없어 전체를 edge 음성으로 다시 만듭니다: {e}")
            global LAST_FALLBACK
            LAST_FALLBACK = str(e)[:200]
            engine = "edge"
            try:
                from . import telegram
                if telegram.enabled():
                    telegram.send_message("⚠️ 타입캐스트 음성을 쓸 수 없어서 이번 영상은 기존 목소리(선희)로 만들어요.\n"
                                          f"원인: {LAST_FALLBACK}\n(크레딧 소진이면 타입캐스트 API 플랜을 확인해 주세요)")
            except Exception:
                pass
    return _synth(texts, workdir, lead, tail, engine)


LAST_FALLBACK = None


def _synth(texts, workdir, lead, tail, engine):
    wavs, durs, words = [], [], []
    t0 = 0.0
    for i, text in enumerate(texts):
        mp3 = workdir / f"tts_{i:02d}.mp3"
        wav = workdir / f"tts_{i:02d}.wav"
        src, ws = _one(text, mp3, engine, prev=" ".join(texts[max(0, i - 3):i]),
                       nxt=" ".join(texts[i + 1:i + 3]))
        pre = float(lead.get(i, 0.0))
        post = PAD + (tail if i == len(texts) - 1 else 0.0)
        af = (f"adelay={int(pre * 1000)}:all=1," if pre > 0 else "") + f"apad=pad_dur={post}"
        run(["ffmpeg", "-y", "-i", src, "-af", af, "-ar", "48000", "-ac", "1", wav])
        d = duration(wav)
        speech = d - pre - post
        if not ws:
            ws = _estimate_words(text, speech)
        else:
            ws = align_to_script(ws, text)
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
