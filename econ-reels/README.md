# 📈 경제 뉴스 릴스 자동 생성기

매일 아침 세계 경제 뉴스 중 가장 화제인 소식을 골라 **30~50초짜리 인스타 릴스**를 자동으로 만들고,
텔레그램으로 미리보기를 보내 줍니다. 버튼으로 승인하면 인스타그램에 게시됩니다(5단계 연결 후).
**모두 무료 서비스만 사용합니다.**

```
[매일 06:40 KST] 뉴스 수집(RSS) → AI가 뉴스 선정·대본 작성(Gemini) → 한국어 음성(edge-tts)
 → 배경 영상(Pixabay) + 시세 차트(Yahoo Finance) + 자막 합성(FFmpeg)
 → 텔레그램으로 미리보기 + [✅ 승인] [🔁 다시] [❌ 폐기] 버튼
[30분마다] 버튼 확인 → 승인 시 인스타 게시
```

---

## 1. GitHub 저장소 만들기

1. github.com 로그인 → 오른쪽 위 **+** → **New repository**
2. 이름: 예) `econ-reels`
3. 공개 범위: **Public 추천**
   - Public 저장소는 GitHub Actions(자동 실행)가 **무제한 무료**입니다.
   - Private는 월 2,000분 무료라 30분마다 확인하면 한도가 빠듯합니다. Private를 쓰려면
     `.github/workflows/approval.yml`의 `cron: "7,37 * * * *"`를 `cron: "7 * * * *"`(1시간마다)로 바꾸세요.
   - Public이어도 **API 키는 Secrets에 저장되어 공개되지 않습니다.** 공개되는 것은 코드와 승인 대기 중인 영상 파일뿐입니다.
4. **Create repository** 클릭

## 2. 파일 올리기

1. 받은 zip 파일의 압축을 풉니다.
2. 새 저장소 화면에서 **uploading an existing file** 링크(또는 **Add file → Upload files**)를 누릅니다.
3. 압축 푼 `econ-reels` 폴더 **안의 내용 전부**를 끌어다 놓고 **Commit changes**를 누릅니다.

> ⚠️ **`.github` 폴더는 숨김 폴더**라 안 보일 수 있어요.
> - Mac: Finder에서 `Cmd + Shift + .` 을 누르면 보입니다.
> - Windows: 탐색기 → 보기 → **숨긴 항목** 체크
>
> 업로드 후 저장소에 `.github/workflows/daily.yml`, `approval.yml` 두 파일이 있는지 꼭 확인하세요.

## 3. 비밀 키 등록 (Secrets)

저장소 → **Settings** → 왼쪽 **Secrets and variables** → **Actions** → **New repository secret**
아래 4개를 **이름 그대로** 하나씩 등록합니다.

| Name | Secret (값) |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio에서 받은 키 (`AIza...`) |
| `PIXABAY_API_KEY` | Pixabay API 키 |
| `TELEGRAM_BOT_TOKEN` | BotFather가 준 토큰 (`123456:ABC...`) |
| `TELEGRAM_CHAT_ID` | 내 채팅 ID (숫자) |

인스타 연결(5단계) 후에 `IG_USER_ID`, `IG_ACCESS_TOKEN` 두 개를 더 등록하게 됩니다.

### (선택) 꾸미기 설정 — Variables 탭

같은 화면의 **Variables** 탭 → **New repository variable**

| Name | 예시 값 | 설명 |
|---|---|---|
| `BRAND_NAME` | `오늘의 글로벌 경제` | 영상 위쪽 노란 글씨 |
| `TTS_VOICE` | `ko-KR-SunHiNeural` (여) / `ko-KR-InJoonNeural` (남) | 내레이션 목소리 |
| `TTS_RATE` | `+12%` | 말하기 속도 |
| `GEMINI_MODELS` | `gemini-flash-latest,gemini-2.5-flash` | 구글이 모델 이름을 바꿨을 때만 수정 |

## 4. 첫 실행

1. 저장소 → **Actions** 탭
2. "Workflows aren't being run…" 안내가 나오면 **I understand my workflows, go ahead and enable them** 클릭
3. 왼쪽 **매일 릴스 만들기** → 오른쪽 **Run workflow** → **Run workflow**
4. 5~10분 뒤 텔레그램으로 대본과 영상이 도착합니다. 🎉

이후에는 매일 **한국시간 06:40**에 자동으로 실행됩니다.
(GitHub 사정으로 실행이 몇~수십 분 늦어질 수 있어요.)

## 5. 텔레그램 사용법

| 버튼/명령 | 동작 |
|---|---|
| ✅ 승인 → 인스타 게시 | 인스타 연결 전: 승인만 기록 / 연결 후: 자동 게시 |
| 🔁 다른 뉴스로 다시 만들기 | 다른 뉴스로 새 영상 제작 (5~10분) |
| ❌ 폐기 | 오늘 영상 버림 |
| `/new` | 지금 새 영상 만들기 |
| `/status` | 승인 대기 중인 영상 확인 |
| `/help` | 도움말 |

> 버튼은 **30분마다** 확인하기 때문에 누른 뒤 반영까지 최대 30분 걸립니다.
> 바로 반영하고 싶으면 Actions → **텔레그램 승인 확인** → Run workflow를 누르세요.

**승인 전 꼭 확인할 것:** 텔레그램 메시지의 "숫자 검수용" 항목과 원문 링크를 대조하세요.
AI가 숫자를 잘못 옮길 수 있습니다.

---

## 실행 시간 바꾸기

`.github/workflows/daily.yml`의 `cron: "40 21 * * *"` 부분을 수정합니다. **시간은 UTC 기준**(한국시간 − 9시간)입니다.

| 한국시간 | cron |
|---|---|
| 06:40 | `40 21 * * *` |
| 08:00 | `0 23 * * *` |
| 12:00 | `0 3 * * *` |
| 18:00 | `0 9 * * *` |

## 배경음악 넣기 (선택)

`assets/bgm/` 폴더에 mp3 파일을 올리면 내레이션 밑에 작게 깔립니다.
Pixabay Music(무료, 상업 이용 가능)에서 잔잔한 곡을 받아 넣으세요.

## 문제 해결

| 증상 | 해결 |
|---|---|
| 텔레그램에 "❌ 생성 실패" | Actions 탭 → 실패한 실행(빨간 X) → 로그 확인. 일시적 오류면 `/new` |
| `Gemini 호출 실패: HTTP 429` | 무료 한도 초과. 잠시 후 `/new` |
| `모델을 찾을 수 없음` | Variables에 `GEMINI_MODELS`를 최신 모델 이름으로 등록 |
| 아무 메시지도 안 옴 | Secrets 이름 오타, 봇에게 먼저 메시지를 보냈는지 확인 |
| 버튼을 눌러도 반응 없음 | 최대 30분 대기. Actions에서 "텔레그램 승인 확인" 워크플로가 켜져 있는지 확인 |
| 배경이 단색으로 나옴 | Pixabay 키 확인 (키가 없거나 검색 결과가 없으면 단색 배경으로 대체) |

## 내 컴퓨터에서 테스트 (선택, 개발자용)

```bash
sudo apt install ffmpeg fonts-noto-cjk   # Mac: brew install ffmpeg
pip install -r requirements.txt
python -m reels.generate --offline --no-deliver   # 키 없이 샘플 영상만 렌더링
```

## 파일 구성

```
reels/
  generate.py   전체 흐름 (매일 실행)
  approval.py   텔레그램 버튼 처리 (30분마다)
  news.py       RSS 수집 + 화제도 점수
  script.py     뉴스 선정·대본 프롬프트
  llm.py        Gemini 호출
  tts.py        한국어 음성
  stock.py      Pixabay 배경 영상
  chart.py      시세 차트
  render.py     FFmpeg 합성 (자막·차트·진행 바)
  telegram.py   텔레그램 봇
  storage.py    승인 대기 영상 보관 (GitHub Release)
  instagram.py  인스타 게시 (5단계 연결 후 동작)
state/          지난 주제 기록, 승인 대기 상태 (자동 관리)
```
