"""USD per 1M tokens. Snowflake 가이드의 예시 rate 기준.
실제 값은 Snowflake Service Consumption Table을 따르므로, 덱에는 '예시 단가 기준 추정'으로 명시한다."""

PRICES = {
    "claude-haiku-4-5":  {"input": 1.00, "cache_read": 0.10, "output":  5.00},
    "claude-sonnet-4-5": {"input": 3.00, "cache_read": 0.30, "output": 15.00},
    "claude-sonnet-4-6": {"input": 3.00, "cache_read": 0.30, "output": 15.00},
    "claude-opus-4-5":   {"input": 5.00, "cache_read": 0.50, "output": 25.00},
    "openai-gpt-5":      {"input": 1.25, "cache_read": 0.13, "output": 10.00},
    # 캐싱 미지원 (Table 6c)
    "llama4-maverick":   {"input": 0.24, "cache_read": 0.24, "output":  0.97},
    "llama3.3-70b":      {"input": 0.72, "cache_read": 0.72, "output":  0.72},
    "mistral-large2":    {"input": 2.00, "cache_read": 2.00, "output":  6.00},
}
FALLBACK = {"input": 2.00, "cache_read": 0.20, "output": 8.00}

CACHE_DISCOUNT_MIN_TOKENS = 1024   # 이 미만이면 캐시 할인 미적용

def price(model):
    return PRICES.get(model, FALLBACK)
