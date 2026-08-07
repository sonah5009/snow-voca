import json, uuid, pathlib, datetime
from measure.pricing import price, CACHE_DISCOUNT_MIN_TOKENS
from common.sf import exec_sql

LEDGER = pathlib.Path("results/llm_calls.jsonl")
LEDGER.parent.mkdir(parents=True, exist_ok=True)

COUNTERS = {"cache_hits": 0, "cache_misses": 0, "llm_calls_avoided": 0}

def extract_usage(resp):
    """Anthropic / OpenAI 두 형식 모두 처리. 스모크 테스트로 확인한 키에 맞춰 필요시 수정."""
    u = resp.get("usage", {}) or {}
    return {
        "input":       u.get("input_tokens", u.get("prompt_tokens", 0)) or 0,
        "output":      u.get("output_tokens", u.get("completion_tokens", 0)) or 0,
        "cache_read":  u.get("cache_read_input_tokens",
                        (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)) or 0,
        "cache_write": u.get("cache_creation_input_tokens", 0) or 0,
    }

def usd(model, u):
    p = price(model)
    inp, cr = u["input"], u["cache_read"]
    # 캐시 write 토큰은 Snowflake 공개 산식에 별도 항목이 없으므로 input 단가로 계산한다 (덱에 가정 명시)
    inp += u["cache_write"]
    # cache_read가 1024 미만이면 할인 미적용 → input 단가로 넘긴다
    if cr < CACHE_DISCOUNT_MIN_TOKENS:
        inp += cr
        cr = 0
    return (inp * p["input"] + cr * p["cache_read"] + u["output"] * p["output"]) / 1e6

def record(run_label, stage, model, u, cost):
    row = {
        "call_id": str(uuid.uuid4()), "run_label": run_label, "stage": stage, "model": model,
        "input_tokens": u["input"], "cache_read_tokens": u["cache_read"],
        "cache_write_tokens": u["cache_write"], "output_tokens": u["output"],
        "usd": cost, "created_at": datetime.datetime.utcnow().isoformat(),
    }
    with LEDGER.open("a") as f:
        f.write(json.dumps(row) + "\n")
    exec_sql("""INSERT INTO llm_calls
        (call_id, run_label, stage, model, input_tokens, cache_read_tokens,
         cache_write_tokens, output_tokens, usd)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (row["call_id"], run_label, stage, model, u["input"], u["cache_read"],
         u["cache_write"], u["output"], cost))
    return row

def metered_call(run_label, stage, model, call_fn):
    """call_fn() -> raw response dict. 모든 LLM 호출은 반드시 이걸 통과한다."""
    resp = call_fn()
    u = extract_usage(resp)
    cost = usd(model, u)
    record(run_label, stage, model, u, cost)
    print(f"  [{run_label}/{stage}] {model} in={u['input']} cr={u['cache_read']} "
          f"cw={u['cache_write']} out={u['output']} ${cost:.6f}")
    return resp
