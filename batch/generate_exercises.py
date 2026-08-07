import json
import uuid

from cortex_client import cheap_call
from db import get_connection, init_db
from seed_data import SAMPLE_CONVERSATIONS
from word_cache import get_or_generate_word_metadata

BATCH_PROMPT_TEMPLATE = """From this conversation, turn each sentence into a vocabulary exercise by blanking out one key word per sentence.

Conversation:
{numbered_sentences}

Respond with ONLY a JSON array, one object per sentence, no other text:
[
  {{
    "sentence": "the sentence with the key word replaced by ___",
    "blank_word": "the word that was blanked out, in its original form"
  }}
]
"""


def build_batch_prompt(sentences: list) -> str:
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences))
    return BATCH_PROMPT_TEMPLATE.format(numbered_sentences=numbered)


def save_exercise(conn, conversation_id: str, exercise: dict) -> None:
    word_meta = exercise["word_meta"]
    conn.cursor().execute(
        """INSERT INTO exercises
           (id, conversation_id, sentence, blank_word, lemma, meaning_correct, distractors, difficulty)
           SELECT %s, %s, %s, %s, %s, %s, PARSE_JSON(%s), %s""",
        (
            str(uuid.uuid4()),
            conversation_id,
            exercise["sentence"],
            exercise["blank_word"],
            word_meta["lemma"],
            word_meta["meaning_correct"],
            json.dumps(word_meta["distractors"], ensure_ascii=False),
            word_meta["difficulty"],
        ),
    )
    conn.commit()


def run() -> list:
    conn = get_connection()
    init_db(conn)

    generated = []
    try:
        for conv in SAMPLE_CONVERSATIONS:
            prompt = build_batch_prompt(conv["transcript"])
            raw = cheap_call(conn, prompt)
            exercises = json.loads(raw)

            for ex in exercises:
                ex["word_meta"] = get_or_generate_word_metadata(ex["blank_word"], conn)
                save_exercise(conn, conv["id"], ex)
                generated.append(ex)

                hit = "hit" if ex["word_meta"]["cache_hit"] else "miss"
                print(f"[{conv['id']}] {ex['sentence']}  (word_cache {hit}: {ex['word_meta']['lemma']})")
    finally:
        conn.close()

    return generated


if __name__ == "__main__":
    run()
