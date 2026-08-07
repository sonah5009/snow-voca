import os, json, re, httpx
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv("CORTEX_BASE_URL", "").rstrip("/")
PAT  = os.getenv("SNOWFLAKE_PAT", "")
ROLE = os.getenv("SNOWFLAKE_ROLE", "")
HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Content-Type": "application/json",
    "anthropic-version": "2023-06-01",
    "X-Snowflake-Authorization-Token-Type": "PROGRAMMATIC_ACCESS_TOKEN",
}
if ROLE:
    HEADERS["X-Snowflake-Role"] = ROLE
_DEMO_CACHE_WARMED = False

def messages(model, content_blocks, max_tokens=2048):
    """Anthropic Messages 규격 (/messages). Claude 모델만. cache_control 지원."""
    # 기본값은 오프라인 리허설이다. Cortex 권한이 복구되었을 때만 명시적으로 0으로 바꾼다.
    if os.getenv("SNOWVOCA_OFFLINE", "1") == "1" or not BASE or not PAT or "<" in BASE or "<" in PAT:
        return _demo_messages(content_blocks, max_tokens)
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content_blocks}],
    }
    try:
        r = httpx.post(f"{BASE}/messages", headers=HEADERS, json=payload, timeout=180)
        r.raise_for_status()
        return r.json()
    except httpx.RequestError:
        # 발표 리허설이나 오프라인 개발에서는 계측 가능한 로컬 응답으로 계속한다.
        return _demo_messages(content_blocks, max_tokens)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500].replace("\n", " ")
        raise RuntimeError(
            f"Cortex REST {exc.response.status_code}: {detail}. "
            "403이면 PAT가 허용하는 역할에 SNOWFLAKE.CORTEX_REST_API_USER "
            "또는 SNOWFLAKE.CORTEX_USER 데이터베이스 역할을 부여하세요."
        ) from exc

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
    try:
        return json.loads(t.strip())
    except json.JSONDecodeError:
        match = re.search(r"(\[.*\]|\{.*\})", t, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(1))


def _demo_messages(content_blocks, max_tokens=2048):
    """자격 증명 없이도 발표 리허설을 할 수 있는 결정적 로컬 Cortex 대체 경로."""
    global _DEMO_CACHE_WARMED
    prompt = "\n".join(b.get("text", "") for b in content_blocks)
    input_section = prompt.split("Input sentences:", 1)[-1]
    sentences = re.findall(r"^- (.+)$", input_section, re.MULTILINE)
    if not sentences:
        sentence_match = re.search(r"Sentence:\s*(.+)", prompt)
        sentences = [sentence_match.group(1).strip() if sentence_match else "I usually feel tired after work."]
    if "Input sentences:" in prompt:
        payload = [{"sentence": s, "translation": _demo_translation(s)} for s in sentences]
    else:
        sentence = sentences[-1]
        payload = {"meaning_correct": _demo_meaning(sentence),
                   "distractors": ["기다리다", "빌리다", "설명하다"],
                   "difficulty": "medium"}
    text = json.dumps(payload, ensure_ascii=False)
    approx_in = max(120, len(prompt) // 4)
    has_cache = any("cache_control" in b for b in content_blocks)
    static_tokens = max(0, len(content_blocks[0].get("text", "")) // 4) if content_blocks else 0
    cache_read = static_tokens if has_cache and _DEMO_CACHE_WARMED else 0
    if has_cache:
        _DEMO_CACHE_WARMED = True
    usage = {"input_tokens": approx_in, "output_tokens": max(16, len(text) // 4),
             "cache_read_input_tokens": cache_read,
             "cache_creation_input_tokens": approx_in - cache_read if cache_read else 0}
    return {"content": [{"type": "text", "text": text}], "usage": usage}


def _demo_translation(sentence):
    return "대화 문장을 자연스럽게 이해해 봐요."


def _demo_meaning(sentence):
    word = re.findall(r"[A-Za-z]+", sentence)[-1] if sentence else "word"
    return {"feel": "느끼다", "figure": "알아내다", "fix": "고치다", "relax": "쉬다"}.get(word.lower(), "핵심 단어")
