import json

from db import get_connection, init_db
from llm import cheap_call
from seed_data import SAMPLE_DIALOGUES

PROMPT_TEMPLATE = """From this sentence, pick one key word to blank out and turn it into a vocabulary exercise.
Sentence: "{sentence}"

Respond with ONLY a JSON object, no other text:
{{
  "sentence": "the sentence with the key word replaced by ___",
  "answer": "the blanked-out word",
  "meaning_correct": "Korean meaning of the word",
  "meaning_distractors": ["wrong Korean meaning 1", "wrong Korean meaning 2"],
  "difficulty": "easy" | "medium" | "hard"
}}
"""


def generate_one(sentence: str) -> dict:
    raw = cheap_call(PROMPT_TEMPLATE.format(sentence=sentence))
    return json.loads(raw)


def run():
    init_db()
    conn = get_connection()
    for sentence in SAMPLE_DIALOGUES:
        exercise = generate_one(sentence)
        conn.execute(
            """INSERT INTO exercises
               (sentence, answer, meaning_correct, meaning_distractors, difficulty, in_review)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (
                exercise["sentence"],
                exercise["answer"],
                exercise["meaning_correct"],
                json.dumps(exercise["meaning_distractors"], ensure_ascii=False),
                exercise["difficulty"],
            ),
        )
        print(f"generated: {exercise['sentence']}")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    run()
