import json
import pathlib

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from batch.seed_data import SAMPLE_CONVERSATIONS
from batch.blank_picker import pick_blank
from batch.lemma import lemmatize
from gateway.grader import grade
from gateway.session_cache import SessionCache
from measure.meter import COUNTERS

GENERATED = pathlib.Path("results/exercises.json")
REVIEW_DELAY = 3   # 오답은 3문제 뒤에 다시 등장한다 ("next few questions")

app = FastAPI(title="SnowVoca Cost-Efficient Gateway")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

session = SessionCache()


def load_exercises():
    if GENERATED.exists():
        data = json.loads(GENERATED.read_text(encoding="utf-8"))
        return {e["id"]: e for e in data}
    exercises = {}
    for conv in SAMPLE_CONVERSATIONS:
        for index, sentence in enumerate(conv["transcript"]):
            blank = pick_blank(sentence)
            ex_id = f"{conv['id']}_{index:02d}"
            exercises[ex_id] = {
                "id": ex_id, "sentence": sentence, "blank_word": blank,
                "lemma": lemmatize(blank), "meaning_correct": "핵심 단어의 뜻",
                "meaning_distractors": ["기다리다", "빌리다", "설명하다"], "difficulty": "medium",
            }
    return exercises


exercises = load_exercises()
queue = list(exercises.keys())


class AnswerRequest(BaseModel):
    spoken_text: str


@app.get("/exercise/next")
def next_exercise():
    if not queue:
        raise HTTPException(404, "no exercises left")
    e = exercises[queue[0]]
    payload = {k: e[k] for k in ("id", "meaning_correct", "meaning_distractors", "difficulty")}
    payload["in_review"] = e.get("in_review", False)
    payload["sentence"] = e["sentence"].replace(e["blank_word"], "___", 1)
    return payload


@app.post("/exercise/{exercise_id}/answer")
def answer(exercise_id: str, body: AnswerRequest):
    e = exercises.get(exercise_id)
    if e is None:
        raise HTTPException(404, "exercise not found")
    # 큐 맨 앞이 아니어도 받는다. 탭 두 개·중복 제출·새로고침으로 순서가 어긋나도
    # 데모가 404 루프에 빠지지 않도록 위치와 무관하게 제거한다.
    if exercise_id in queue:
        queue.remove(exercise_id)
    correct = grade(body.spoken_text, e["blank_word"])
    session.update(e["lemma"], correct)
    if correct:
        e["in_review"] = False
        feedback = "Nice! Let's move on to the next one."
    else:
        e["in_review"] = True
        queue.insert(min(REVIEW_DELAY, len(queue)), exercise_id)
        feedback = f"The answer is '{e['blank_word']}'. Let's review it once more."
    return {"correct": correct, "answer": e["blank_word"], "feedback": feedback}


@app.get("/metrics")
def metrics():
    hits = COUNTERS["cache_hits"]
    misses = COUNTERS["cache_misses"]
    calls = hits + misses
    return {"session_usd": 0.0, "cache_hit_rate": hits / calls if calls else 0.0,
            "cache_hits": hits, "cache_misses": misses,
            "llm_calls_avoided": COUNTERS["llm_calls_avoided"],
            "profile": session.profile()}


@app.post("/reset")
def reset():
    queue[:] = list(exercises.keys())
    for e in exercises.values():
        e["in_review"] = False
    return {"status": "ok"}
