"""OpenAI Chat Completions 래퍼.

호출부는 Anthropic Messages 형태(content blocks)를 그대로 쓰고, 여기서 OpenAI 규격으로 변환한다.
usage도 Anthropic 형태로 정규화해서 돌려주므로 measure/meter.py는 수정 없이 동작한다.

OpenAI의 프롬프트 캐싱은 자동이다. cache_control 지시자가 따로 없고, 프롬프트 앞부분 1024 토큰
이상이 직전 요청과 동일하면 cached_tokens로 잡힌다. 그래서 static_prefix를 맨 앞에 두는 것이
그대로 캐시 레버로 작동한다.
"""

import json
import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY", "")
BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "low")


def messages(model, content_blocks, max_tokens=2048, cache_key=None):
    if not API_KEY:
        raise RuntimeError("OPENAI_API_KEY가 없다. .env를 확인하라.")

    prompt = "\n\n".join(b.get("text", "") for b in content_blocks)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": max_tokens,
        "reasoning_effort": REASONING_EFFORT,
    }
    # 같은 prefix를 쓰는 요청을 같은 캐시 노드로 보내야 cached_tokens가 잡힌다.
    if cache_key:
        payload["prompt_cache_key"] = cache_key
    r = httpx.post(
        f"{BASE}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=180,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:500]}")
    return _normalize(r.json())


def _normalize(resp):
    """OpenAI 응답을 Anthropic 형태로 변환한다.

    OpenAI의 cached_tokens는 prompt_tokens에 포함된 부분집합이라,
    빼주지 않으면 캐시 토큰이 input 단가로 한 번 더 계산된다.
    """
    u = resp.get("usage", {}) or {}
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    return {
        "content": [{"type": "text", "text": resp["choices"][0]["message"]["content"] or ""}],
        "usage": {
            "input_tokens": (u.get("prompt_tokens", 0) or 0) - cached,
            "output_tokens": u.get("completion_tokens", 0) or 0,
            "cache_read_input_tokens": cached,
            "cache_creation_input_tokens": 0,
        },
    }


def text_of(resp):
    return "".join(b.get("text", "") for b in resp["content"])


def parse_json_block(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        if t.startswith("json"):
            t = t[4:]
    try:
        return json.loads(t.strip())
    except json.JSONDecodeError:
        match = re.search(r"(\[.*\]|\{.*\})", t, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(1))
