from db import get_connection
from llm import expensive_call


def get_level() -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS total, SUM(correct) AS correct FROM attempts"
    ).fetchone()
    conn.close()

    total = row["total"] or 0
    correct = row["correct"] or 0
    accuracy = correct / total if total else 0.0

    return {"total": total, "correct": correct, "accuracy": accuracy}


def next_difficulty_hint(accuracy: float) -> str:
    """One expensive-model call per session to suggest the next difficulty band."""
    prompt = (
        f"A language learner has an accuracy of {accuracy:.0%} so far. "
        'Respond with ONLY one word: "easy", "medium", or "hard" — '
        "the difficulty band they should see next."
    )
    return expensive_call(prompt).strip().lower()
