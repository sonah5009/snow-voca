import json

from cortex_client import cheap_call

# 형태소 분석기 없이 흔한 불규칙 동사만 하드코딩 + 규칙 활용형은 접미사 규칙으로 처리.
# (CLAUDE.md 컷 우선순위 3: "lemmatize가 번거로우면 단순 문자열 매칭으로 축소")
IRREGULAR_LEMMAS = {
    "am": "be", "is": "be", "are": "be", "was": "be", "were": "be", "been": "be", "being": "be",
    "has": "have", "had": "have", "having": "have",
    "does": "do", "did": "do", "done": "do", "doing": "do",
    "goes": "go", "went": "go", "gone": "go", "going": "go",
    "gets": "get", "got": "get", "gotten": "get", "getting": "get",
    "makes": "make", "made": "make", "making": "make",
    "takes": "take", "took": "take", "taken": "take", "taking": "take",
    "comes": "come", "came": "come", "coming": "come",
    "sees": "see", "saw": "see", "seen": "see", "seeing": "see",
    "knows": "know", "knew": "know", "known": "know", "knowing": "know",
    "feels": "feel", "felt": "feel", "feeling": "feel",
    "keeps": "keep", "kept": "keep", "keeping": "keep",
    "leaves": "leave", "left": "leave", "leaving": "leave",
    "meets": "meet", "met": "meet", "meeting": "meet",
    "thinks": "think", "thought": "think", "thinking": "think",
    "buys": "buy", "bought": "buy", "buying": "buy",
    "brings": "bring", "brought": "bring", "bringing": "bring",
    "figures": "figure", "figured": "figure", "figuring": "figure",
}


def _undouble(stem: str) -> str:
    if len(stem) >= 3 and stem[-1] == stem[-2] and stem[-1] not in "aeiou":
        return stem[:-1]
    return stem


def lemmatize(word: str) -> str:
    w = word.lower().strip()
    if w in IRREGULAR_LEMMAS:
        return IRREGULAR_LEMMAS[w]
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ing") and len(w) > 5:
        return _undouble(w[:-3])
    if w.endswith("ed") and len(w) > 4:
        return _undouble(w[:-2])
    if w.endswith("es") and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


WORD_META_PROMPT = """Give the Korean meaning and quiz metadata for the English word "{word}".

Respond with ONLY a JSON object, no other text:
{{
  "meaning_correct": "Korean meaning of the word",
  "distractors": ["wrong Korean meaning 1", "wrong Korean meaning 2"],
  "difficulty": "easy" | "medium" | "hard"
}}
"""


def get_or_generate_word_metadata(word: str, conn) -> dict:
    lemma = lemmatize(word)
    row = conn.cursor().execute(
        "SELECT meaning_correct, distractors, difficulty FROM word_metadata WHERE lemma = %s",
        (lemma,),
    ).fetchone()

    if row is not None:
        meaning_correct, distractors, difficulty = row
        if isinstance(distractors, str):
            distractors = json.loads(distractors)
        return {
            "lemma": lemma,
            "meaning_correct": meaning_correct,
            "distractors": distractors,
            "difficulty": difficulty,
            "cache_hit": True,
        }

    raw = cheap_call(conn, WORD_META_PROMPT.format(word=lemma))
    result = json.loads(raw)

    conn.cursor().execute(
        """INSERT INTO word_metadata (lemma, meaning_correct, distractors, difficulty, generated_by)
           SELECT %s, %s, PARSE_JSON(%s), %s, %s""",
        (
            lemma,
            result["meaning_correct"],
            json.dumps(result["distractors"], ensure_ascii=False),
            result["difficulty"],
            "cheap_model_v1",
        ),
    )
    conn.commit()

    return {
        "lemma": lemma,
        "meaning_correct": result["meaning_correct"],
        "distractors": result["distractors"],
        "difficulty": result["difficulty"],
        "cache_hit": False,
    }
