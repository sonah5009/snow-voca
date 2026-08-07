import os, json, httpx
from dotenv import load_dotenv
load_dotenv()

BASE = os.environ["CORTEX_BASE_URL"].rstrip("/")
PAT  = os.environ["SNOWFLAKE_PAT"]
HEADERS = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

def messages(model, content_blocks, max_tokens=2048):
    """Anthropic Messages 규격 (/messages). Claude 모델만. cache_control 지원."""
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content_blocks}],
    }
    r = httpx.post(f"{BASE}/messages", headers=HEADERS, json=payload, timeout=180)
    r.raise_for_status()
    return r.json()

def chat(model, messages_list, max_tokens=2048):
    """OpenAI Chat Completions 규격 (/chat/completions). 전 모델. 캐싱 제어는 없음."""
    payload = {"model": model, "max_tokens": max_tokens, "messages": messages_list}
    r = httpx.post(f"{BASE}/chat/completions", headers=HEADERS, json=payload, timeout=180)
    r.raise_for_status()
    return r.json()

def text_of(resp):
    """두 규격의 응답에서 본문 텍스트만 뽑는다."""
    if "content" in resp:                      # Anthropic 형식
        return "".join(b.get("text", "") for b in resp["content"])
    return resp["choices"][0]["message"]["content"]   # OpenAI 형식

def parse_json_block(text):
    """모델이 코드펜스로 감싸도 파싱되게."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        if t.startswith("json"):
            t = t[4:]
    return json.loads(t.strip())
