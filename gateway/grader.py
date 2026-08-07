import re


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def grade(answer: str, expected: str) -> bool:
    """정오답은 LLM 없이 문자열 비교한다.

    answer는 음성 인식 후보 여러 개가 줄바꿈으로 이어져 올 수 있다.
    후보 중 하나라도 정답 단어를 (단어 경계 기준으로) 포함하면 정답.
    "I zoned out"처럼 문장으로 말해도 통과한다.
    """
    exp = normalize(expected)
    if not exp:
        return False
    for candidate in answer.splitlines():
        cand = normalize(candidate)
        if cand == exp or f" {exp} " in f" {cand} ":
            return True
    return False
