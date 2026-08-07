from db import get_connection


def mark_for_review(exercise_id: int) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE exercises SET in_review = 1 WHERE id = ?", (exercise_id,)
    )
    conn.commit()
    conn.close()


def clear_review(exercise_id: int) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE exercises SET in_review = 0 WHERE id = ?", (exercise_id,)
    )
    conn.commit()
    conn.close()


def pick_next_exercise():
    """Review queue first, then any exercise not yet attempted."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM exercises WHERE in_review = 1 LIMIT 1"
    ).fetchone()
    if row is None:
        row = conn.execute(
            """SELECT * FROM exercises
               WHERE id NOT IN (SELECT exercise_id FROM attempts)
               LIMIT 1"""
        ).fetchone()
    conn.close()
    return row
