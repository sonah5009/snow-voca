from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from batch.seed_data import SAMPLE_CONVERSATIONS
from batch.blank_picker import pick_blank
from batch.lemma import lemmatize
from gateway.grader import grade
from gateway.session_cache import SessionCache
from measure.meter import COUNTERS


app = FastAPI(title="SnowVoca Cost-Efficient Gateway")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

session = SessionCache()
exercises = []
attempted = set()

for conv in SAMPLE_CONVERSATIONS:
    for index, sentence in enumerate(conv["transcript"]):
        blank = pick_blank(sentence)
        exercises.append({"id": f"{conv['id']}_{index:02d}", "sentence": sentence,
                          "blank_word": blank, "lemma": lemmatize(blank),
                          "meaning_correct": "핵심 단어의 뜻", "meaning_distractors": ["기다리다", "빌리다", "설명하다"],
                          "difficulty": "medium", "in_review": False})


class AnswerRequest(BaseModel):
    spoken_text: str


@app.get("/exercise/next")
def next_exercise():
    candidates = [e for e in exercises if e["in_review"] or e["id"] not in attempted]
    if not candidates:
        raise HTTPException(404, "no exercises left")
    e = candidates[0]
    return {k: e[k] for k in ("id", "sentence", "blank_word", "meaning_correct", "meaning_distractors", "difficulty", "in_review")}


@app.post("/exercise/{exercise_id}/answer")
def answer(exercise_id: str, body: AnswerRequest):
    e = next((item for item in exercises if item["id"] == exercise_id), None)
    if e is None:
        raise HTTPException(404, "exercise not found")
    correct = grade(body.spoken_text, e["blank_word"])
    attempted.add(e["id"])
    e["in_review"] = not correct
    session.update(e["lemma"], correct)
    if correct:
        feedback = "좋아요! 다음 문제로 가볼게요."
    else:
        feedback = f"정답은 '{e['blank_word']}'예요. 한 번 더 복습해 볼까요?"
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
    attempted.clear()
    for e in exercises:
        e["in_review"] = False
    return {"status": "ok"}
