"""문장별 한국어 음성 생성 → 문장별 길이(초) 측정 → 하나의 내레이션 파일로 합치기."""
import asyncio

from . import config
from .utils import duration, run

PAD = 0.25  # 문장 사이 쉬는 시간(초)


async def _edge(text, out):
    import edge_tts
    await edge_tts.Communicate(text, config.TTS_VOICE, rate=config.TTS_RATE).save(str(out))


def _one(text, out_mp3, engine):
    if engine == "dummy":
        # 테스트용: 실제 음성 대신 글자 수에 비례한 무음
        secs = max(1.5, len(text.replace(" ", "")) / 6.5)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100",
             "-af", "volume=0.03", "-t", f"{secs:.2f}", out_mp3])
        return
    if engine == "edge":
        for attempt in range(3):
            try:
                asyncio.run(_edge(text, out_mp3))
                if out_mp3.exists() and out_mp3.stat().st_size > 1000:
                    return
            except Exception as e:
                print(f"  [음성] edge-tts 실패({attempt+1}/3): {e}")
        print("  [음성] gTTS로 대체합니다")
    from gtts import gTTS
    gTTS(text, lang="ko").save(str(out_mp3))


def synthesize(texts, workdir):
    workdir.mkdir(parents=True, exist_ok=True)
    engine = config.TTS_ENGINE
    wavs, durs = [], []
    for i, t in enumerate(texts):
        mp3 = workdir / f"tts_{i:02d}.mp3"
        wav = workdir / f"tts_{i:02d}.wav"
        _one(t, mp3, engine)
        run(["ffmpeg", "-y", "-i", mp3, "-af", f"apad=pad_dur={PAD}", "-ar", "44100", "-ac", "1", wav])
        wavs.append(wav)
        durs.append(duration(wav))
    lst = workdir / "tts_list.txt"
    lst.write_text("".join(f"file '{w.resolve()}'\n" for w in wavs))
    narration = workdir / "narration.wav"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", narration])
    print(f"  [음성] {len(texts)}문장, 총 {sum(durs):.1f}초")
    return narration, durs
