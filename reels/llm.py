"""Google Gemini 무료 API 호출 (JSON 응답)."""
import json
import re
import time

import requests

from . import config

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


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


def ask_json(prompt, temperature=0.6):
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    last_err = None
    for model in config.GEMINI_MODELS:
        for attempt in range(3):
            try:
                r = requests.post(URL.format(model=model), json=body, timeout=120,
                                  headers={"x-goog-api-key": config.GEMINI_API_KEY})
                if r.status_code in (429, 500, 503):
                    last_err = f"{model}: HTTP {r.status_code} {r.text[:200]}"
                    time.sleep(10 * (attempt + 1))
                    continue
                if r.status_code == 404:          # 모델 이름이 없어진 경우 다음 모델로
                    last_err = f"{model}: 모델을 찾을 수 없음"
                    break
                r.raise_for_status()
                data = r.json()
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts)
                print(f"  [AI] {model} 응답 받음")
                return _extract_json(text)
            except (requests.RequestException, KeyError, ValueError) as e:
                last_err = f"{model}: {e}"
                time.sleep(5)
    raise RuntimeError(f"Gemini 호출 실패: {last_err}")
