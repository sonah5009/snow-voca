import json
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import ability
import review_queue
from db import get_connection, init_db
from generate_exercises import run as run_generate
from llm import expensive_call

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


class AnswerRequest(BaseModel):
    spoken_text: str


def _exercise_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "sentence": row["sentence"],
        "meaning_correct": row["meaning_correct"],
        "meaning_distractors": json.loads(row["meaning_distractors"]),
        "difficulty": row["difficulty"],
        "in_review": bool(row["in_review"]),
    }


@app.post("/generate")
def generate():
    run_generate()
    return {"status": "ok"}


@app.get("/exercise/next")
def next_exercise():
    row = review_queue.pick_next_exercise()
    if row is None:
        raise HTTPException(status_code=404, detail="no exercises left")
    return _exercise_to_dict(row)


@app.post("/exercise/{exercise_id}/answer")
def answer(exercise_id: int, body: AnswerRequest):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM exercises WHERE id = ?", (exercise_id,)
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="exercise not found")

    is_correct = body.spoken_text.strip().lower() == row["answer"].strip().lower()

    conn.execute(
        "INSERT INTO attempts (exercise_id, correct, created_at) VALUES (?, ?, ?)",
        (exercise_id, int(is_correct), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()

    if is_correct:
        review_queue.clear_review(exercise_id)
        feedback = None
    else:
        review_queue.mark_for_review(exercise_id)
        try:
            feedback = expensive_call(
                f'The learner said "{body.spoken_text}" but the correct answer '
                f'was "{row["answer"]}" for the sentence "{row["sentence"]}". '
                "Give one short encouraging Korean sentence of feedback."
            )
        except Exception:
            feedback = "다시 들어볼까요?"

    return {
        "correct": is_correct,
        "answer": row["answer"],
        "feedback": feedback,
    }


@app.get("/learner/level")
def learner_level():
    return ability.get_level()
