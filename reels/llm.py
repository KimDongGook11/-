"""Google Gemini 무료 API 호출 (JSON 응답).
쓸 수 있는 모델 목록을 구글에서 직접 받아와 최신 flash 모델을 자동으로 고릅니다."""
import json
import re
import time

import requests

from . import config

BASE = "https://generativelanguage.googleapis.com/v1beta"
SKIP = ("image", "tts", "audio", "live", "embedding", "vision", "robotics", "computer-use", "native")
_cache = None
_bad = set()          # 이번 실행에서 한도 초과·시간 초과가 난 모델은 다시 시도하지 않음


def _headers():
    return {"x-goog-api-key": config.GEMINI_API_KEY}


def available_models():
    """내 API 키로 쓸 수 있는 모델 중 텍스트 생성용 flash 모델을 최신 순으로."""
    r = requests.get(f"{BASE}/models", params={"pageSize": 1000}, headers=_headers(), timeout=30)
    if r.status_code in (400, 401, 403):
        raise RuntimeError(f"Gemini API 키 오류 (HTTP {r.status_code}): GEMINI_API_KEY 값을 확인하세요. {r.text[:200]}")
    r.raise_for_status()
    names = []
    for m in r.json().get("models", []):
        name = m.get("name", "").split("/")[-1]
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if "flash" not in name or any(s in name for s in SKIP):
            continue
        names.append(name)

    def rank(n):
        v = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        ver = float(v.group(1)) if v else 0
        stable = not any(s in n for s in ("preview", "exp"))
        return (stable, "lite" not in n, ver, n.endswith("latest"))

    names.sort(key=rank, reverse=True)
    return names


def model_order():
    global _cache
    if _cache is None:
        try:
            found = available_models()
            print(f"  [AI] 사용 가능한 모델: {', '.join(found[:6]) or '(없음)'}")
        except RuntimeError:
            raise
        except Exception as e:
            print(f"  [AI] 모델 목록 조회 실패(설정값 사용): {e}")
            found = []
        _cache = list(dict.fromkeys(found[:5] + config.GEMINI_MODELS))
    return _cache


def _extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise


def ask_json(prompt, temperature=0.6, timeout=120, keep_models=False):
    """keep_models=True: 시간 초과가 나도 그 모델을 이번 실행 내내 빼지 않음 (긴 검증용 호출)."""
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    errors = []
    for model in [m for m in model_order() if m not in _bad] or model_order():
        for attempt in range(2):
            try:
                r = requests.post(f"{BASE}/models/{model}:generateContent", json=body,
                                  headers=_headers(), timeout=timeout)
                if r.status_code == 429:               # 무료 한도 초과 → 기다리지 말고 바로 다음 모델
                    msg = f"{model}: HTTP 429 (무료 한도 초과)"
                    print(f"  [AI] {msg}")
                    errors.append(msg)
                    _bad.add(model)
                    break
                if r.status_code in (500, 503):        # 일시적 혼잡 → 잠깐 쉬고 한 번만 다시
                    msg = f"{model}: HTTP {r.status_code} (일시적 오류)"
                    print(f"  [AI] {msg}")
                    errors.append(msg)
                    time.sleep(8)
                    continue
                if r.status_code in (400, 403, 404):   # 없는 모델/권한 없음 → 다음 모델
                    msg = f"{model}: HTTP {r.status_code} {r.text[:150]}"
                    print(f"  [AI] {msg}")
                    errors.append(msg)
                    break
                r.raise_for_status()
                data = r.json()
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                print(f"  [AI] {model} 응답 받음")
                return _extract_json(text)
            except requests.Timeout:
                msg = f"{model}: 응답 시간 초과 → 다음 모델"
                print(f"  [AI] {msg}")
                errors.append(msg)
                if not keep_models:
                    _bad.add(model)
                break
            except (requests.RequestException, KeyError, IndexError, ValueError) as e:
                msg = f"{model}: {type(e).__name__} {e}"
                print(f"  [AI] {msg}")
                errors.append(msg)
                time.sleep(3)
    raise RuntimeError("Gemini 호출 실패\n" + "\n".join(errors[-6:]))
