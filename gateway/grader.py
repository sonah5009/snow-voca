import re


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def grade(answer: str, expected: str) -> bool:
    """정오답은 LLM 없이 문자열 비교한다."""
    return normalize(answer) == normalize(expected)
