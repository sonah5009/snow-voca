"""USD per 1M tokens. 출처: OpenAI 공개 단가표 (developers.openai.com/api/docs/pricing).
덱에는 '2026-08 기준 공개 단가'로 명시한다."""

PRICES = {
    "gpt-5.6-sol":   {"input": 5.00, "cache_read": 0.50, "output": 30.00},
    "gpt-5.6-terra": {"input": 2.00, "cache_read": 0.20, "output": 12.00},
    "gpt-5.6-luna":  {"input": 0.20, "cache_read": 0.02, "output":  1.20},
    "gpt-5.4":       {"input": 2.50, "cache_read": 0.25, "output": 15.00},
    "gpt-5.4-mini":  {"input": 0.75, "cache_read": 0.075, "output": 4.50},
    "gpt-5.4-nano":  {"input": 0.20, "cache_read": 0.02, "output":  1.25},
    "gpt-5":         {"input": 1.25, "cache_read": 0.125, "output": 10.00},
    "gpt-5-mini":    {"input": 0.25, "cache_read": 0.025, "output": 2.00},
    "gpt-5-nano":    {"input": 0.05, "cache_read": 0.005, "output": 0.40},
}
FALLBACK = {"input": 2.00, "cache_read": 0.20, "output": 8.00}

CACHE_DISCOUNT_MIN_TOKENS = 1024   # 이 미만이면 캐시 할인 미적용

def price(model):
    return PRICES.get(model, FALLBACK)
