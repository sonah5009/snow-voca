import json, os
from batch.lemma import lemmatize
from common.sf import exec_sql
from cortex.client import messages, text_of, parse_json_block
from measure.meter import metered_call, COUNTERS

CHEAP = os.environ["MODEL_CHEAP"]
_MEM = {}   # SQL이 죽어도 세션 내 캐시는 동작해야 한다

WORD_PROMPT = """Return ONLY JSON for the English word or phrase below.
{{"meaning_correct":"<Korean meaning, short>","distractors":["<Korean wrong meaning>","<Korean wrong meaning>","<Korean wrong meaning>"],"difficulty":"easy|medium|hard"}}
Word: {w}"""

def get_or_generate_word_metadata(word, run_label="ours"):
    lemma = lemmatize(word)
    if lemma in _MEM:
        COUNTERS["cache_hits"] += 1
        return _MEM[lemma]

    cur = exec_sql("SELECT meaning_correct, distractors, difficulty FROM word_metadata WHERE lemma=%s", (lemma,))
    row = cur.fetchone() if cur else None
    if row:
        COUNTERS["cache_hits"] += 1
        meta = {"meaning_correct": row[0],
                "distractors": json.loads(row[1]) if isinstance(row[1], str) else row[1],
                "difficulty": row[2]}
        _MEM[lemma] = meta
        return meta

    COUNTERS["cache_misses"] += 1
    resp = metered_call(run_label, "word_meta", CHEAP,
        lambda: messages(CHEAP, [{"type": "text", "text": WORD_PROMPT.format(w=lemma)}], max_tokens=400))
    meta = parse_json_block(text_of(resp))
    _MEM[lemma] = meta
    exec_sql("""MERGE INTO word_metadata t USING (SELECT %s AS lemma) s ON t.lemma=s.lemma
                WHEN NOT MATCHED THEN INSERT
                  (lemma, meaning_correct, distractors, difficulty, generated_by)
                  VALUES (%s,%s,PARSE_JSON(%s),%s,%s)""",
             (lemma, lemma, meta["meaning_correct"], json.dumps(meta["distractors"], ensure_ascii=False),
              meta["difficulty"], CHEAP))
    return meta

def hit_rate():
    h, m = COUNTERS["cache_hits"], COUNTERS["cache_misses"]
    return h / (h + m) if (h + m) else 0.0
