# SnowVoca 파일 번들 — Claude Code CLI에 그대로 물려줄 용도

목표: 16:00 마감. **14:30까지 `python -m measure.report`가 절감률 숫자 1개를 출력**하는 것이 최우선.
프론트엔드보다 이게 먼저다. 아래 파일을 순서대로 만들고 실행한다.

의존성: `pip install httpx snowflake-connector-python python-dotenv`
(spaCy 설치하지 않는다. lemmatizer는 규칙 기반으로 자체 구현)

계측 설계 원칙: **모든 LLM 호출은 `measure/meter.py`의 `metered_call`을 통과한다.**
원장은 로컬 JSONL이 source of truth이고, Snowflake 테이블은 미러다.
(데모 직전에 SQL 연결이 죽어도 리포트가 나와야 하므로)

---

## `.env`

```bash
# Snowflake
SNOWFLAKE_ACCOUNT=<account-identifier>          # 예: abcd-xy12345
SNOWFLAKE_USER=<user>
SNOWFLAKE_PAT=<programmatic-access-token>
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=SNOWVOCA
SNOWFLAKE_SCHEMA=PUBLIC

# Cortex REST
CORTEX_BASE_URL=https://<account-identifier>.snowflakecomputing.com/api/v2/cortex/v1

# 모델 (SHOW CORTEX BASE MODELS; 로 가용성 먼저 확인)
MODEL_CHEAP=claude-haiku-4-5
MODEL_EXPENSIVE=claude-sonnet-4-5
MODEL_NAIVE=claude-opus-4-5
```

`.gitignore`에 `.env` 먼저 추가.

---

## `cortex/setup.sql`

```sql
CREATE DATABASE IF NOT EXISTS SNOWVOCA;
USE DATABASE SNOWVOCA;
USE SCHEMA PUBLIC;

-- 전 학습자 공유 어휘 캐시 (Snowflake는 PK를 강제하지 않으므로 MERGE로 중복 방지)
CREATE TABLE IF NOT EXISTS word_metadata (
  lemma            STRING,
  meaning_correct  STRING,
  distractors      VARIANT,
  difficulty       STRING,
  generated_by     STRING,
  created_at       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS exercises (
  exercise_id  STRING,
  conv_id      STRING,
  sentence     STRING,
  blank_word   STRING,
  lemma        STRING,
  translation  STRING,
  created_at   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ★ 비용 원장
CREATE TABLE IF NOT EXISTS llm_calls (
  call_id            STRING,
  run_label          STRING,   -- 'naive' | 'ours'
  stage              STRING,   -- 'exercise_gen' | 'word_meta' | 'feedback'
  model              STRING,
  input_tokens       NUMBER,
  cache_read_tokens  NUMBER,
  cache_write_tokens NUMBER,
  output_tokens      NUMBER,
  usd                NUMBER(20,10),
  created_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- 학습자 메모리 (EverOS 실패 시 폴백)
CREATE TABLE IF NOT EXISTS learner_episodes (
  learner_id   STRING,
  exercise_id  STRING,
  lemma        STRING,
  correct      BOOLEAN,
  reviewed     BOOLEAN DEFAULT FALSE,
  created_at   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
```

---

## `common/sf.py`

```python
import os, snowflake.connector
from dotenv import load_dotenv
load_dotenv()

_conn = None

def conn():
    """Snowflake 연결. 실패해도 파이프라인은 계속 돌아야 하므로 None을 반환한다."""
    global _conn
    if _conn is not None:
        return _conn
    try:
        _conn = snowflake.connector.connect(
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            user=os.environ["SNOWFLAKE_USER"],
            password=os.environ["SNOWFLAKE_PAT"],   # PAT를 password로 전달
            warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
            database=os.getenv("SNOWFLAKE_DATABASE", "SNOWVOCA"),
            schema=os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC"),
        )
    except Exception as e:
        print(f"[sf] connect failed, continuing without SQL: {e}")
        _conn = None
    return _conn

def exec_sql(sql, params=None):
    c = conn()
    if c is None:
        return None
    try:
        cur = c.cursor()
        cur.execute(sql, params or ())
        return cur
    except Exception as e:
        print(f"[sf] query failed: {e}")
        return None
```

---

## `cortex/client.py`

```python
import os, json, httpx
from dotenv import load_dotenv
load_dotenv()

BASE = os.environ["CORTEX_BASE_URL"].rstrip("/")
PAT  = os.environ["SNOWFLAKE_PAT"]
HEADERS = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

def messages(model, content_blocks, max_tokens=2048):
    """Anthropic Messages 규격 (/messages). Claude 모델만. cache_control 지원."""
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content_blocks}],
    }
    r = httpx.post(f"{BASE}/messages", headers=HEADERS, json=payload, timeout=180)
    r.raise_for_status()
    return r.json()

def chat(model, messages_list, max_tokens=2048):
    """OpenAI Chat Completions 규격 (/chat/completions). 전 모델. 캐싱 제어는 없음."""
    payload = {"model": model, "max_tokens": max_tokens, "messages": messages_list}
    r = httpx.post(f"{BASE}/chat/completions", headers=HEADERS, json=payload, timeout=180)
    r.raise_for_status()
    return r.json()

def text_of(resp):
    """두 규격의 응답에서 본문 텍스트만 뽑는다."""
    if "content" in resp:                      # Anthropic 형식
        return "".join(b.get("text", "") for b in resp["content"])
    return resp["choices"][0]["message"]["content"]   # OpenAI 형식

def parse_json_block(text):
    """모델이 코드펜스로 감싸도 파싱되게."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        if t.startswith("json"):
            t = t[4:]
    return json.loads(t.strip())
```

### 스모크 테스트 `cortex/smoke.py`

```python
import os, json
from cortex.client import messages, text_of
from dotenv import load_dotenv
load_dotenv()

resp = messages(os.environ["MODEL_CHEAP"],
                [{"type": "text", "text": "Reply with exactly: OK"}], max_tokens=16)
print("TEXT :", text_of(resp))
print("USAGE:", json.dumps(resp.get("usage", {}), indent=2))  # ← 필드명 여기서 확정
```

**13:00 게이트**: 이 스크립트가 `OK`를 출력하고 usage 객체가 보이면 통과.
usage 키 이름을 확인해서 `measure/meter.py`의 `extract_usage`가 맞는지 대조한다.

---

## `measure/pricing.py`

```python
"""USD per 1M tokens. Snowflake 가이드의 예시 rate 기준.
실제 값은 Snowflake Service Consumption Table을 따르므로, 덱에는 '예시 단가 기준 추정'으로 명시한다."""

PRICES = {
    "claude-haiku-4-5":  {"input": 1.00, "cache_read": 0.10, "output":  5.00},
    "claude-sonnet-4-5": {"input": 3.00, "cache_read": 0.30, "output": 15.00},
    "claude-sonnet-4-6": {"input": 3.00, "cache_read": 0.30, "output": 15.00},
    "claude-opus-4-5":   {"input": 5.00, "cache_read": 0.50, "output": 25.00},
    "openai-gpt-5":      {"input": 1.25, "cache_read": 0.13, "output": 10.00},
    # 캐싱 미지원 (Table 6c)
    "llama4-maverick":   {"input": 0.24, "cache_read": 0.24, "output":  0.97},
    "llama3.3-70b":      {"input": 0.72, "cache_read": 0.72, "output":  0.72},
    "mistral-large2":    {"input": 2.00, "cache_read": 2.00, "output":  6.00},
}
FALLBACK = {"input": 2.00, "cache_read": 0.20, "output": 8.00}

CACHE_DISCOUNT_MIN_TOKENS = 1024   # 이 미만이면 캐시 할인 미적용

def price(model):
    return PRICES.get(model, FALLBACK)
```

---

## `measure/meter.py`

```python
import json, uuid, pathlib, datetime
from measure.pricing import price, CACHE_DISCOUNT_MIN_TOKENS
from common.sf import exec_sql

LEDGER = pathlib.Path("results/llm_calls.jsonl")
LEDGER.parent.mkdir(parents=True, exist_ok=True)

COUNTERS = {"cache_hits": 0, "cache_misses": 0, "llm_calls_avoided": 0}

def extract_usage(resp):
    """Anthropic / OpenAI 두 형식 모두 처리. 스모크 테스트로 확인한 키에 맞춰 필요시 수정."""
    u = resp.get("usage", {}) or {}
    return {
        "input":       u.get("input_tokens", u.get("prompt_tokens", 0)) or 0,
        "output":      u.get("output_tokens", u.get("completion_tokens", 0)) or 0,
        "cache_read":  u.get("cache_read_input_tokens",
                        (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)) or 0,
        "cache_write": u.get("cache_creation_input_tokens", 0) or 0,
    }

def usd(model, u):
    p = price(model)
    inp, cr = u["input"], u["cache_read"]
    # 캐시 write 토큰은 Snowflake 공개 산식에 별도 항목이 없으므로 input 단가로 계산한다 (덱에 가정 명시)
    inp += u["cache_write"]
    # cache_read가 1024 미만이면 할인 미적용 → input 단가로 넘긴다
    if cr < CACHE_DISCOUNT_MIN_TOKENS:
        inp += cr
        cr = 0
    return (inp * p["input"] + cr * p["cache_read"] + u["output"] * p["output"]) / 1e6

def record(run_label, stage, model, u, cost):
    row = {
        "call_id": str(uuid.uuid4()), "run_label": run_label, "stage": stage, "model": model,
        "input_tokens": u["input"], "cache_read_tokens": u["cache_read"],
        "cache_write_tokens": u["cache_write"], "output_tokens": u["output"],
        "usd": cost, "created_at": datetime.datetime.utcnow().isoformat(),
    }
    with LEDGER.open("a") as f:
        f.write(json.dumps(row) + "\n")
    exec_sql("""INSERT INTO llm_calls
        (call_id, run_label, stage, model, input_tokens, cache_read_tokens,
         cache_write_tokens, output_tokens, usd)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (row["call_id"], run_label, stage, model, u["input"], u["cache_read"],
         u["cache_write"], u["output"], cost))
    return row

def metered_call(run_label, stage, model, call_fn):
    """call_fn() -> raw response dict. 모든 LLM 호출은 반드시 이걸 통과한다."""
    resp = call_fn()
    u = extract_usage(resp)
    cost = usd(model, u)
    record(run_label, stage, model, u, cost)
    print(f"  [{run_label}/{stage}] {model} in={u['input']} cr={u['cache_read']} "
          f"cw={u['cache_write']} out={u['output']} ${cost:.6f}")
    return resp
```

---

## `batch/seed_data.py`

```python
SAMPLE_CONVERSATIONS = [
    {"id": "conv_01", "title": "Morning routine", "transcript": [
        "I usually feel tired after work.",
        "Yeah, me too. I barely have energy to cook dinner.",
        "I've been trying to go to bed earlier, but it's not working.",
        "Same here. I keep scrolling on my phone until midnight."]},
    {"id": "conv_02", "title": "Work stress", "transcript": [
        "We need to fix this bug before the deadline.",
        "I know, but I can't figure out what's causing it.",
        "Have you checked the error logs yet?",
        "Not yet, I was about to when you called.",
        "Okay, let's look at it together after lunch."]},
    {"id": "conv_03", "title": "Weekend plans", "transcript": [
        "Do you have any plans for the weekend?",
        "Not really. I might just stay home and relax.",
        "That sounds nice actually. I've been so busy lately.",
        "You should join me. We could order some food and watch a movie.",
        "That sounds great, count me in."]},
    {"id": "conv_04", "title": "Cafe order", "transcript": [
        "Can I get a medium iced latte, please?",
        "Sure, would you like that with oat milk or regular?",
        "Oat milk is fine, thanks.",
        "Alright, that'll be ready in about five minutes.",
        "No rush, I'll just find a seat."]},
    {"id": "conv_05", "title": "Traffic complaint", "transcript": [
        "Sorry I'm late, the traffic was terrible today.",
        "It's okay, I figured something happened.",
        "There was an accident on the highway, so everything just stopped.",
        "That happens a lot around this time, doesn't it?",
        "Yeah, I really should start leaving earlier."]},
]

# Naive 조건에서 프롬프트에 원본 그대로 삽입되는 학습자 시도 로그.
# Ours 조건에서는 session_cache가 숫자 3개로 압축한다. 양쪽 입력은 동일하다.
RAW_ATTEMPT_LOG = [
    {"ts": f"2026-08-0{d} 09:{m:02d}:00", "exercise_id": f"ex_{i:03d}",
     "lemma": w, "correct": c, "answer_given": a}
    for i, (d, m, w, c, a) in enumerate([
        (1, 12, "feel", True, "feel"), (1, 14, "figure", False, "figured"),
        (1, 17, "fix", True, "fix"), (1, 21, "relax", True, "relax"),
        (2, 9, "figure", False, "figure"), (2, 13, "order", True, "order"),
        (2, 15, "keep", True, "keep"), (2, 19, "stop", False, "stopped"),
        (3, 10, "join", True, "join"), (3, 12, "check", True, "check"),
        (3, 16, "figure", False, "figuring"), (3, 20, "leave", False, "leaving"),
        (4, 11, "feel", True, "feel"), (4, 15, "count", True, "count"),
        (4, 18, "happen", False, "happend"), (4, 22, "find", True, "find"),
    ], start=1)
]
```

---

## `batch/lemma.py` — 규칙 기반 lemmatizer (spaCy 없이)

```python
IRREGULAR = {
    "felt": "feel", "got": "get", "went": "go", "kept": "keep", "left": "leave",
    "found": "find", "made": "make", "took": "take", "came": "come", "said": "say",
    "stopped": "stop", "figured": "figure", "checked": "check", "counted": "count",
    "happened": "happen", "ordered": "order", "relaxed": "relax", "joined": "join",
    "scrolling": "scroll", "trying": "try", "leaving": "leave", "figuring": "figure",
}

def lemmatize(word: str) -> str:
    w = word.lower().strip(".,!?\"'")
    if w in IRREGULAR:
        return IRREGULAR[w]
    for suf, cut in (("ies", 3), ("ing", 3), ("ed", 2), ("es", 2), ("s", 1)):
        if w.endswith(suf) and len(w) - cut >= 3:
            stem = w[:-cut]
            if suf == "ies":
                return stem + "y"
            if suf in ("ing", "ed") and len(stem) > 2 and stem[-1] == stem[-2]:
                stem = stem[:-1]          # stopp → stop
            if suf == "ing" and stem in ("hav", "mak", "tak", "com", "writ"):
                stem += "e"
            return stem
    return w
```

---

## `batch/blank_picker.py` — 빈칸 선정 (LLM 0회, 레버 1)

```python
from batch.lemma import lemmatize
from measure.meter import COUNTERS

STOP = set("""i you he she it we they me him her us them my your his its our their
a an the this that these those and or but so if then than as at by for from in into of
on to with about after before until while is am are was were be been being do does did
not no yes very just really too also can could would should will shall may might must
have has had get got there here what when where who how do don't didn't it's i'm i've""".split())

PHRASAL = {"figure out", "look at", "count me in", "stay home", "go to bed", "wake up"}

def pick_blank(sentence: str) -> str:
    low = sentence.lower()
    for p in PHRASAL:
        if p in low:
            COUNTERS["llm_calls_avoided"] += 1
            return p
    words = [w.strip(".,!?\"'") for w in sentence.split()]
    cands = [w for w in words if w.lower() not in STOP and len(w) > 3]
    COUNTERS["llm_calls_avoided"] += 1        # 이 판단을 LLM에 위임하지 않았다
    if not cands:
        return max(words, key=len)
    return max(cands, key=len)                # 결정적: 가장 긴 content word
```

---

## `batch/word_cache.py` — lemma 캐시 (레버 2)

```python
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
```

---

## `batch/static_prefix.py` — 캐싱될 정적 prefix (레버 3)

```python
"""cache_read 할인은 요청당 cache_read_input이 1024 토큰 이상일 때만 적용된다.
따라서 정적 prefix를 의도적으로 1024 토큰 이상으로 만든다. few-shot 4개가 그 역할을 한다."""

SCHEMA = """You are an English learning content generator for Korean learners.
For each input sentence, output one JSON object with these exact fields:
  "sentence"    : the original English sentence, unchanged
  "translation" : a natural Korean translation of the whole sentence
Return ONLY a JSON array, one object per input sentence, in the same order.
Do not add commentary, markdown fences, numbering, or any field not listed above.
Keep translations natural spoken Korean, not literal word-by-word renderings.
If a sentence contains a phrasal verb, translate the phrase as a unit."""

FEWSHOT = [
    ("I usually feel tired after work.", "나는 보통 퇴근 후에 피곤함을 느껴."),
    ("I can't figure out what's causing it.", "무엇이 그걸 유발하는지 알아낼 수가 없어."),
    ("Not really. I might just stay home and relax.", "별로. 그냥 집에서 쉴까 싶어."),
    ("Sorry I'm late, the traffic was terrible today.", "늦어서 미안해, 오늘 교통이 정말 최악이었어."),
    ("Would you like that with oat milk or regular?", "오트밀크로 드릴까요, 아니면 일반 우유로 드릴까요?"),
    ("That happens a lot around this time, doesn't it?", "이맘때면 자주 그러지, 그렇지 않아?"),
]

def build_static_prefix() -> str:
    ex = "\n\n".join(
        f'Example {i}:\nInput: {s}\nOutput: {{"sentence": "{s}", "translation": "{k}"}}'
        for i, (s, k) in enumerate(FEWSHOT, 1))
    return f"{SCHEMA}\n\nWorked examples:\n\n{ex}\n\nNow process the input sentences below."

if __name__ == "__main__":
    p = build_static_prefix()
    print(f"chars={len(p)}  approx_tokens={len(p)//4}")
    assert len(p) // 4 >= 1024, "정적 prefix가 1024 토큰 미만이면 캐시 할인이 0이다. few-shot을 더 추가하라."
```

> 실행해서 `approx_tokens`가 1024 미만이면 FEWSHOT을 늘려라. **이걸 안 하면 레버 3이 그냥 0이 된다.**
> 정확한 토큰 수는 `SELECT AI_COUNT_TOKENS('claude-haiku-4-5', $$...$$);`로 확인할 수 있다.

---

## `batch/generate_exercises.py` — Ours 파이프라인 (레버 3·4·5)

```python
import os, json
from batch.seed_data import SAMPLE_CONVERSATIONS
from batch.static_prefix import build_static_prefix
from batch.blank_picker import pick_blank
from batch.word_cache import get_or_generate_word_metadata, hit_rate
from batch.lemma import lemmatize
from cortex.client import messages, text_of, parse_json_block
from measure.meter import metered_call, COUNTERS
from common.sf import exec_sql
from dotenv import load_dotenv
load_dotenv()

CHEAP  = os.environ["MODEL_CHEAP"]
PREFIX = build_static_prefix()

def run(run_label="ours"):
    total = 0
    for conv in SAMPLE_CONVERSATIONS:                     # 22문장 → 호출 5회 (레버 5)
        body = "\n".join(f"- {s}" for s in conv["transcript"])
        blocks = [
            {"type": "text", "text": PREFIX,
             "cache_control": {"type": "ephemeral"}},      # ★ 레버 3: 여기까지 캐싱
            {"type": "text", "text": f"Input sentences:\n{body}"},
        ]
        resp = metered_call(run_label, "exercise_gen", CHEAP,
                            lambda: messages(CHEAP, blocks, max_tokens=2048))
        for i, item in enumerate(parse_json_block(text_of(resp))):
            sent = item["sentence"]
            blank = pick_blank(sent)                       # 레버 1: LLM 0회
            lem = lemmatize(blank.split()[0] if " " in blank else blank)
            meta = get_or_generate_word_metadata(blank, run_label)   # 레버 2
            ex_id = f"{conv['id']}_{i:02d}"
            exec_sql("""INSERT INTO exercises
                (exercise_id, conv_id, sentence, blank_word, lemma, translation)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (ex_id, conv["id"], sent, blank, lem, item["translation"]))
            total += 1
    print(f"\n[ours] exercises={total} cache_hit_rate={hit_rate():.1%} "
          f"llm_calls_avoided={COUNTERS['llm_calls_avoided']}")

if __name__ == "__main__":
    run()
```

---

## `measure/baseline_naive.py` — Naive 파이프라인 ("before")

```python
"""Naive 조건 6개 (덱 슬라이드 3에 이 목록을 그대로 적는다):
 1. 문장 1개당 호출 1회 (배치 없음) → 22회
 2. 모델은 전부 MODEL_NAIVE (라우팅 없음)
 3. cache_control 미사용 (프롬프트 캐싱 없음)
 4. 단어 메타데이터를 매번 재생성 (lemma 캐시 없음)
 5. 빈칸 선정도 LLM에 위임
 6. 학습자 시도 로그 원본 전체를 매 호출에 삽입 (압축 없음)
"""
import os, json
from batch.seed_data import SAMPLE_CONVERSATIONS, RAW_ATTEMPT_LOG
from cortex.client import messages, text_of
from measure.meter import metered_call
from dotenv import load_dotenv
load_dotenv()

NAIVE = os.environ["MODEL_NAIVE"]

PROMPT = """You are an English learning content generator for Korean learners.
Given one English sentence, do all of the following and return ONLY JSON:
  "sentence": the sentence unchanged
  "translation": natural Korean translation
  "blank_word": the single best word or phrase to blank out for a vocabulary quiz
  "meaning_correct": Korean meaning of blank_word
  "distractors": three plausible wrong Korean meanings
  "difficulty": easy|medium|hard
Take the learner's full attempt history into account when choosing difficulty.

Learner's full attempt history (raw):
{log}

Sentence: {sentence}"""

def run():
    log = json.dumps(RAW_ATTEMPT_LOG, ensure_ascii=False, indent=1)
    n = 0
    for conv in SAMPLE_CONVERSATIONS:
        for sent in conv["transcript"]:                  # 문장당 1회
            metered_call("naive", "exercise_gen", NAIVE,
                lambda s=sent: messages(NAIVE,
                    [{"type": "text", "text": PROMPT.format(log=log, sentence=s)}],
                    max_tokens=800))
            n += 1
    print(f"\n[naive] calls={n}")

if __name__ == "__main__":
    run()
```

---

## `measure/report.py` — ★ 제출물이 여기서 나온다

```python
import json, pathlib
from collections import defaultdict

LEDGER = pathlib.Path("results/llm_calls.jsonl")

# 투영 가정 (덱에 그대로 명시한다)
CONVS_PER_RUN     = 5      # 시드 대화 5개
LEARNER_DAYS      = 5      # 대화 1개 = 학습자 1인 1일치 콘텐츠로 간주
PROJ_LEARNERS     = 1000
PROJ_DAYS         = 30

def load():
    agg = defaultdict(lambda: defaultdict(float))
    stages = defaultdict(lambda: defaultdict(float))
    for line in LEDGER.read_text().splitlines():
        r = json.loads(line)
        a = agg[r["run_label"]]
        a["calls"] += 1
        for k in ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens"):
            a[k] += r[k]
        a["usd"] += r["usd"]
        stages[r["run_label"]][r["stage"]] += r["usd"]
    return agg, stages

def main():
    agg, stages = load()
    if "naive" not in agg or "ours" not in agg:
        print("두 run이 다 있어야 한다. baseline_naive.py 와 generate_exercises.py 를 각각 1회 실행하라.")
        print("현재:", dict((k, int(v['calls'])) for k, v in agg.items()))
        return

    hdr = f"{'run':<8}{'calls':>7}{'input':>11}{'cache_rd':>11}{'output':>10}{'USD':>12}"
    print("\n" + hdr); print("-" * len(hdr))
    for label in ("naive", "ours"):
        a = agg[label]
        print(f"{label:<8}{int(a['calls']):>7}{int(a['input_tokens']):>11,}"
              f"{int(a['cache_read_tokens']):>11,}{int(a['output_tokens']):>10,}"
              f"{a['usd']:>12.4f}")
    print("-" * len(hdr))

    n, o = agg["naive"]["usd"], agg["ours"]["usd"]
    red = (n - o) / n * 100 if n else 0
    print(f"\n>>> 비용 절감률: {red:.1f}%   (${n:.4f} → ${o:.4f})\n")

    nd, od = n / LEARNER_DAYS, o / LEARNER_DAYS
    print(f"학습자 1인 1일 원가 : naive ${nd:.6f}  →  ours ${od:.6f}")
    scale = PROJ_LEARNERS * PROJ_DAYS
    print(f"{PROJ_LEARNERS:,}명 x {PROJ_DAYS}일 : naive ${nd*scale:,.2f}  →  ours ${od*scale:,.2f}"
          f"  (월 ${(nd-od)*scale:,.2f} 절감)")

    print("\n단계별 비용 (ours):")
    for s, v in sorted(stages["ours"].items(), key=lambda x: -x[1]):
        print(f"  {s:<15} ${v:.6f}")

    print("\n가정: 대화 1개 = 학습자 1인 1일치 콘텐츠. 단가는 Snowflake 공개 예시 rate 기준 추정.")

if __name__ == "__main__":
    main()
```

---

## `measure/verify.sql` — 플랫폼 교차검증 (보조 증거)

```sql
-- 권한: USE ROLE ACCOUNTADMIN; GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE <role>;
-- 주의: ACCOUNT_USAGE는 45분~3시간 지연. 13:15에 naive를 돌려둔 이유가 이것.
SELECT MODEL_NAME,
       SUM(TOKENS_GRANULAR:"input"::NUMBER)            AS input_tokens,
       SUM(TOKENS_GRANULAR:"cache_read_input"::NUMBER) AS cache_read_tokens,
       SUM(TOKENS_GRANULAR:"output"::NUMBER)           AS output_tokens,
       COUNT(*)                                        AS requests
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_USAGE_HISTORY
WHERE START_TIME >= DATEADD(hour, -6, CURRENT_TIMESTAMP())
GROUP BY 1 ORDER BY 1;

-- 우리 원장과 대조
SELECT run_label, model, COUNT(*) calls,
       SUM(input_tokens) input_t, SUM(cache_read_tokens) cache_rd,
       SUM(output_tokens) output_t, SUM(usd) usd
FROM llm_calls GROUP BY 1,2 ORDER BY 1,2;
```

---

## 실행 순서

```bash
mkdir -p results
# 13:00 게이트
python -m cortex.smoke
snowsql -f cortex/setup.sql          # 또는 Snowsight 워크시트에 붙여넣기

# 정적 prefix가 1024 토큰 넘는지 확인 (레버 3의 전제)
python -m batch.static_prefix

# 13:15 — before 먼저 (ACCOUNT_USAGE 예열 목적)
python -m measure.baseline_naive

# 14:00 — after
python -m batch.generate_exercises

# 14:30 게이트 ★ 이 출력이 제출물
python -m measure.report

# 캐시 레버 데모용: 두 번째 학습자 = 전부 캐시 히트
python -m batch.generate_exercises      # hit_rate가 100%에 가까워지는 것을 확인
```

## 자르는 순서 (막히면 위에서부터 버린다)

1. EverOS (Snowflake `learner_episodes` 테이블로 대체)
2. Foresights / Facts
3. 오답 피드백 고가 모델 호출 → 고정 문구. 단 `report.py`에서 해당 stage 행을 빼고 재계산
4. `word_metadata` SQL 영속화 → `_MEM` 인메모리만 사용
5. 프론트엔드 전체 → `report.py` 출력 스크린샷으로 데모

**절대 자르지 않는 것**: `measure/` 전체, naive 1회 실행, `report.py` 절감률 한 줄, 덱, 15:55 제출.
