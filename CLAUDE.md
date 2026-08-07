# SnowVoca — Cortex REST API + 비용 계측 빌드 가이드

## 목표

일상 대화(영어 STT 텍스트)를 입력받아 빈칸 문제를 생성하고, 음성으로 답하면 정오답을 판정하며,
틀린 문제는 복습 큐로 넘어가는 데모를 완성한다.

**그리고 이 앱을 돌리는 추론 비용을 Naive 대비 몇 % 줄였는지 무대에서 실측 숫자로 증명한다.**

> 두 번째 문장이 제출 트랙(Track 1 · Cost of Intelligence)의 채점 기준이다.
> 앱은 비용 절감을 보여주는 무대 장치이고, 심사 대상은 절감률 숫자다.
> 앱만 완성되고 숫자가 없으면 Track 2에서 수십 팀과 싸우게 되므로 진다.

## 하드 제약

- 제출 마감 16:00 PDT (5분당 -5점). **15:55 제출**.
- 제출 폼 필수: 팀명 / 프로젝트명 / **Team Member 1,2,3 전부 필수(1~2인이면 3번은 `N/A`)** / **Slide Deck URL(필수)** / Live Demo URL(선택)
- 데모 3분 + 관객 투표
- LLM 호출은 전부 Snowflake Cortex 경로로만. Anthropic SDK(`pip install anthropic`) 사용 금지.

---

## 아키텍처 (Cortex Agent / MCP / SPCS 제거)

```
[Frontend: QuizScreen + CostHUD]
        │ (Web Speech API: voice → text)
        ▼
[gateway: FastAPI]
        ├── session_cache      : 압축 학습자 프로필(코드 카운터, LLM 0회)
        ├── grader             : 정오답 판정 = 문자열 비교 (LLM 0회)
        ├── everos_local       : EverOS를 파이썬 라이브러리로 in-process 사용 (선택)
        └── meter              : ★ 모든 LLM 호출을 통과시키는 계측 래퍼
                │
                ▼
        [Cortex REST API]  POST /api/v2/cortex/v1/messages
                │           - Anthropic 호환 엔드포인트
                │           - Claude 모델에 cache_control 명시 지정 가능
                │           - 응답 usage에서 input/output/cache_read 토큰 회수
                ▼
        [Snowflake tables]
          word_metadata  : lemma 단위 어휘 캐시 (전 학습자 공유)
          exercises      : 생성된 문제
          llm_calls      : ★ 호출별 토큰/USD 원장
```

**Cortex Agent + External MCP Server + SPCS를 왜 뺐는가**

1. **시간**: Docker 빌드 → SPCS 서비스 등록 → API Integration(OAuth) → External MCP Server 객체 →
   Agent 등록. 남은 시간이 3시간인데 이 체인은 각 단계가 hard-fail 가능하고 어느 하나만 막혀도 데모가 없다.
2. **이게 우승 서사를 망친다**: Cortex Agent의 오케스트레이션은 어떤 도구를 언제 호출할지 스스로 정한다.
   즉 호출 횟수와 모델 선택이 우리 통제 밖이라 **"Naive 대비 N% 절감"을 호출 단위로 귀속시킬 수 없다.**
   Track 1은 측정 가능성이 곧 점수다. Agent를 쓰면 측정이 흐려진다.
3. **REST API가 상위 호환**: Cortex REST API는 Claude 모델에 대해 `cache_control` 브레이크포인트를
   명시적으로 지원한다. Agent 경로에서는 노출되지 않는 제어권이 REST 경로에서는 열려 있다.

> Agent/MCP/SPCS는 "덱의 Next Steps 슬라이드"로만 등장시킨다. 코드로 시도하지 않는다.

---

## ★ 정정: 프롬프트 캐싱은 Cortex에서 쓸 수 있다

이전 설계의 전제("Cortex는 프롬프트 캐싱을 노출하지 않는다")는 **Agent/SQL 경로에만 해당**한다.
Cortex REST API에서는:

- **Claude 모델: 명시적 캐싱.** 캐싱할 content block에 `cache_control`(ephemeral, TTL 5분 또는 1시간) 지정
- **OpenAI 모델: 암묵적 캐싱.** 1,024 토큰 이상이면 자동
- **캐시 읽기 토큰은 입력 단가의 10%** (90% 할인). 단 **한 요청의 `cache_read_input`이 1,024 토큰 이상일 때만** 적용되고,
  그 미만이면 전액 과금된다.

**구현상 반드시 지킬 것**: 정적 prefix(시스템 지침 + few-shot 예시 + 출력 스키마 설명)를
**의도적으로 1,024 토큰 이상으로 만들어라.** 짧으면 할인이 0이다. few-shot 예시를 3~4개 넣으면 자연스럽게 넘긴다.
배치 실행이 5분을 넘길 수 있으면 TTL을 1시간으로 둔다.

프롬프트 구성 순서(캐시 히트를 극대화):

```
[cache_control 지정 → 여기까지 캐싱]
  1. 시스템 지침 (고정)
  2. 출력 JSON 스키마 + few-shot 예시 3~4개 (고정)
[여기부터 매번 변경]
  3. 이번 대화 4~5문장
  4. 압축 학습자 프로필 (숫자 몇 개)
```

---

## 비용 레버 5개 — 각각 구현 위치와 측정 방법

| #   | 레버              | 구현 위치                                      | 절감 메커니즘                                           | 측정                                |
| --- | ----------------- | ---------------------------------------------- | ------------------------------------------------------- | ----------------------------------- |
| 1   | **LLM 미사용**    | `gateway/grader.py`, `batch/blank_picker.py`   | 정오답 판정 = 문자열 비교. 빈칸 선정 = 규칙 기반        | `llm_calls_avoided` 카운터          |
| 2   | **lemma 캐시**    | `batch/word_cache.py` + `word_metadata` 테이블 | 단어 원형 단위 exact match. 학습자가 늘수록 히트율 상승 | 히트/미스 카운트 → 회피된 토큰      |
| 3   | **프롬프트 캐싱** | `cortex/messages.py`의 `cache_control`         | 정적 prefix를 입력 단가 10%로                           | 응답 usage의 `cache_read` 토큰      |
| 4   | **모델 라우팅**   | `cortex/router.py`                             | 어휘 메타/문제 생성 = 저가, 오답 피드백만 고가          | 모델별 USD 분해                     |
| 5   | **배치 묶음**     | `batch/generate_exercises.py`                  | 문장 22개 → 호출 5회 (대화 단위)                        | 호출 횟수 + 정적 prefix 중복 제거량 |

### 모델 선정 (실제 단가 기준, USD per 1M tokens)

`SHOW CORTEX BASE MODELS;`로 리전 가용 모델을 먼저 확인하고 아래에서 고른다.
(구 가이드의 `SHOW MODELS IN SNOWFLAKE.CORTEX;`는 틀린 명령이다.)

| 용도                     | 모델 후보           | Input | Cache read | Output |
| ------------------------ | ------------------- | ----- | ---------- | ------ |
| 저가(어휘/문제 생성)     | `claude-haiku-4-5`  | $1.00 | $0.10      | $5.00  |
| 초저가 대안(캐싱 미지원) | `llama4-maverick`   | $0.24 | —          | $0.97  |
| 고가(오답 피드백)        | `claude-sonnet-4-5` | $3.00 | $0.30      | $15.00 |
| Naive 베이스라인용       | `claude-opus-4-5`   | $5.00 | $0.50      | $25.00 |

> 위 수치는 Snowflake 가이드의 **예시 rate**다. 실제 값은 Service Consumption Table을 따르므로,
> `measure/pricing.py`에 상수로 넣되 덱에는 "예시 단가 기준 추정"이라고 명시한다.
> Naive에 opus, Ours에 haiku를 쓰면 input 5배 / output 5배 차이가 그대로 절감률로 나온다.
> llama4-maverick은 캐싱을 지원하지 않으므로 레버 3과 배타적이다. 어느 쪽이 총액이 낮은지
> `measure/report.py`로 실측해서 고른다(이 비교 자체가 덱의 좋은 슬라이드가 된다).

---

## ★ measure/ — 이 프로젝트에서 가장 먼저 만들 모듈

**모든 LLM 호출은 예외 없이 `meter`를 통과한다.** 계측되지 않은 호출이 하나라도 있으면 절감률 주장이 무너진다.

```
measure/
├── pricing.py          # 모델별 (input, cache_read, output) USD/1M 상수
├── meter.py            # 호출 래퍼: 토큰 회수 → USD 환산 → llm_calls 테이블 append
├── baseline_naive.py   # "before" 파이프라인 (아래 정의)
├── report.py           # before/after 표 + 1,000명×30일 투영
└── verify.sql          # ACCOUNT_USAGE 교차검증 쿼리
```

### Naive 베이스라인 정의 (이게 "before"다. 반드시 이 정의를 덱에 그대로 적어라)

동일한 `SAMPLE_CONVERSATIONS` 5개 / 22문장에 대해:

1. 문장 **1개당 호출 1회** (배치 없음) → 22회
2. 모델은 전부 `claude-opus-4-5` (라우팅 없음)
3. `cache_control` 미사용 (프롬프트 캐싱 없음)
4. 단어 메타데이터를 매번 재생성 (lemma 캐시 없음)
5. 빈칸 선정·정오답 판정도 LLM에 위임
6. 매 호출에 학습자 시도 로그 **원본 전체**를 삽입 (압축 없음)

### Ours

레버 1~5 전부 적용.

### llm_calls 원장

```sql
CREATE TABLE IF NOT EXISTS llm_calls (
  call_id STRING,
  run_label STRING,          -- 'naive' | 'ours'
  stage STRING,              -- 'word_meta' | 'exercise_gen' | 'feedback' | 'grade'
  model STRING,
  input_tokens NUMBER,
  cache_read_tokens NUMBER,
  output_tokens NUMBER,
  usd NUMBER(18,8),
  created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
```

```python
# measure/meter.py
from measure.pricing import PRICES

def usd(model, input_t, cache_read_t, output_t):
    p = PRICES[model]
    # cache_read가 1024 미만이면 할인 미적용 → 전액 input 단가
    if cache_read_t < 1024:
        input_t += cache_read_t
        cache_read_t = 0
    return (input_t * p["input"] + cache_read_t * p["cache_read"] + output_t * p["output"]) / 1e6

def metered_call(run_label, stage, model, payload, conn):
    resp = cortex_messages(model, payload)          # cortex/messages.py
    u = extract_usage(resp)                          # 필드명은 런타임에 1회 print해서 확인
    cost = usd(model, u["input"], u["cache_read"], u["output"])
    insert_llm_call(conn, run_label, stage, model, u, cost)
    return resp, cost
```

> `extract_usage`의 실제 키 이름(`cache_read_input_tokens` 등)은 응답을 한 번 `print`해서 확정한다.
> 여기서 5분 이상 쓰지 말고, 키를 못 찾으면 `AI_COUNT_TOKENS`로 입력 토큰을 직접 세는 폴백으로 간다.

### 실시간 측정을 주 증거로, ACCOUNT_USAGE를 보조 증거로

`SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_USAGE_HISTORY`의 `TOKENS_GRANULAR`에
`input` / `output` / `cache_read_input`이 들어오지만, **ACCOUNT_USAGE는 데이터가 뜨기까지 45분~3시간 지연된다.**
데모 시점에 비어 있을 수 있으므로:

- **주 증거**: 응답 usage 기반 `llm_calls` 테이블 (실시간, 데모 중 라이브 실행 가능)
- **보조 증거**: ACCOUNT_USAGE 뷰 (플랫폼 공식 수치로 교차검증)
- **따라서 13:00에 가장 먼저 `baseline_naive.py`를 돌려라.** 그러면 15:00~16:00 데모 때 뷰에 데이터가
  올라와 있을 가능성이 생기고, "우리 계측 = 플랫폼 계측" 슬라이드가 공짜로 나온다. 안 뜨면 그냥 안 쓴다.

```sql
-- measure/verify.sql
SELECT MODEL_NAME,
       SUM(TOKENS_GRANULAR:"input"::NUMBER)            AS input_tokens,
       SUM(TOKENS_GRANULAR:"cache_read_input"::NUMBER) AS cache_read_tokens,
       SUM(TOKENS_GRANULAR:"output"::NUMBER)           AS output_tokens
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_USAGE_HISTORY
WHERE START_TIME >= DATEADD(hour, -6, CURRENT_TIMESTAMP())
GROUP BY 1;
-- 권한: GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE <role>;
```

### report.py 출력 형태 (덱에 그대로 붙일 표)

```
                     calls   input_tok  cache_read  output_tok      USD
naive                   22      41,800           0      12,400   $0.5200
ours                     6       3,100       8,900       2,050   $0.0361
--------------------------------------------------------------------------
절감률                                                            93.1%
학습자 1인 1일 원가   naive $0.0104  →  ours $0.0007
1,000명 × 30일        naive $312     →  ours $21      (월 $291 절감)
```

숫자는 실측으로 채운다. **절감률 한 줄이 이 프로젝트의 제출물이다.**

---

## 캐싱 전략 — lemma 단위 (기존 설계 유지, 버그만 수정)

문장은 사용자마다 달라 무한하지만 단어의 뜻·오답 후보·난이도는 문장이 바뀌어도 동일하다.
캐시 키를 **단어 원형(lemma)**으로 잡으면 exact match면서 히트율이 계속 오른다. 이 판단은 그대로 간다.

```sql
CREATE TABLE IF NOT EXISTS word_metadata (
  lemma STRING,               -- Snowflake는 PRIMARY KEY를 강제하지 않는다. MERGE로 중복 방지
  meaning_correct STRING,
  distractors VARIANT,        -- ARRAY 대신 VARIANT + PARSE_JSON으로 삽입
  difficulty STRING,          -- easy | medium | hard
  generated_by STRING,
  created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
```

```python
# batch/word_cache.py — read-through + MERGE
def get_or_generate_word_metadata(word, conn, meter):
    lemma = lemmatize(word)                       # feel/feels/felt/feeling → feel
    row = conn.cursor().execute(
        "SELECT meaning_correct, distractors, difficulty FROM word_metadata WHERE lemma = %s",
        (lemma,)).fetchone()
    if row:
        CACHE_HITS.inc()                          # ★ 히트 카운터: 데모 HUD와 리포트에 쓰임
        return {"meaning_correct": row[0], "distractors": row[1], "difficulty": row[2]}

    CACHE_MISSES.inc()
    result = meter("ours", "word_meta", CHEAP_MODEL, build_word_prompt(lemma))
    conn.cursor().execute("""
        MERGE INTO word_metadata t USING (SELECT %s AS lemma) s ON t.lemma = s.lemma
        WHEN NOT MATCHED THEN INSERT (lemma, meaning_correct, distractors, difficulty, generated_by)
        VALUES (%s, %s, PARSE_JSON(%s), %s, %s)
    """, (lemma, lemma, result["meaning_correct"], json.dumps(result["distractors"]),
          result["difficulty"], CHEAP_MODEL))
    return result
```

**무효화**: `DELETE FROM word_metadata WHERE lemma = 'feel';` → 다음 배치에서 자동 재생성. 이 규모에선 TTL 불필요.

**데모 필수 연출**: 학습자 A로 한 바퀴 돌린 뒤 학습자 B를 돌려서
`캐시 히트율 0% → 78%`로 올라가는 걸 화면에서 보여준다. 이게 관객이 이해하는 유일한 비용 그래프다.

---

## 압축 전략 — 모델 없이 코드로 (기존 설계 유지)

원본 시도 로그 전체 대신 파이썬으로 누적한 숫자 몇 개만 넘긴다. 압축에 모델 호출이 없어 비용 0,
시도 횟수가 늘어도 프롬프트 길이가 고정된다.

```python
# gateway/session_cache.py
{
  "accuracy_rate": 0.7,
  "recent_sequence": ["O", "O", "X"],
  "weak_word_tags": {"feel": 2, "figure_out": 1}
}

def update_on_attempt(profile, correct: bool, word: str):
    profile["total"] += 1
    if correct:
        profile["correct"] += 1
    else:
        profile["weak_word_tags"][word] = profile["weak_word_tags"].get(word, 0) + 1
    profile["accuracy_rate"] = profile["correct"] / profile["total"]
    profile["recent_sequence"] = profile["recent_sequence"][-2:] + ["O" if correct else "X"]
```

|            | 방식                                                      | 비용      |
| ---------- | --------------------------------------------------------- | --------- |
| 기본       | 코드로 카운터/리스트만 누적                               | 0         |
| 확장(선택) | 세션 종료 시 1회 싼 모델로 질적 요약 1문장 → EverOS Facts | 아주 낮음 |

---

## 배치 생성 — 대화 단위 (기존 설계 유지 + 캐싱 결합)

```python
# batch/generate_exercises.py
STATIC_PREFIX = build_static_prefix()   # 시스템 지침 + 스키마 + few-shot 3~4개, 1024토큰 이상 필수

for conv in SAMPLE_CONVERSATIONS:                 # 22문장 → 호출 5회
    payload = {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": STATIC_PREFIX,
                 "cache_control": {"type": "ephemeral"}},        # ★ 여기까지 캐싱
                {"type": "text", "text": render(conv["transcript"])},
            ],
        }],
    }
    resp, cost = metered_call("ours", "exercise_gen", CHEAP_MODEL, payload, conn)
    for ex in parse(resp):
        ex["blank_word"] = pick_blank(ex["sentence"])            # 규칙 기반, LLM 0회
        ex["word_meta"] = get_or_generate_word_metadata(ex["blank_word"], conn, meter)
        save_exercise(ex)
```

첫 대화는 cache write, 2~5번째 대화가 cache read로 들어가면서 정적 prefix 비용이 10%로 떨어진다.
**호출 5회 중 4회가 캐시 히트**이므로 배치와 캐싱 레버가 서로를 강화한다.

---

## 시드 데이터 (변경 없음)

```python
# batch/seed_data.py
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
```

---

## 기술 스택

- LLM 호출: **Cortex REST API** `POST https://<account>.snowflakecomputing.com/api/v2/cortex/v1/messages`
  (Anthropic 호환. 인증은 PAT 권장 — Snowsight → My Profile → Programmatic Access Tokens)
- 호출 라이브러리: `httpx` 또는 `requests` 직접 사용. `anthropic` 패키지 설치 금지
- 배치/캐시/원장: Snowflake 테이블 + `snowflake-connector-python`
- gateway: FastAPI
- 기억 레이어: EverOS를 gateway 프로세스 내 파이썬 라이브러리로 사용 (선택 · 아래 판단 참고)
- 프론트엔드: React(Vite), QuizScreen + **CostHUD**, Web Speech API로 STT
- 계측: `measure/` 자체 구현. wandb 사용하지 않음

### EverOS 사용 여부 판단

Evermind가 공동 호스트라 스폰서 정렬 가치가 있다. 다만 EverOS는 Python 3.12+, OpenRouter 키,
DeepInfra 키가 필요하다.

- **키가 이미 있다**: `pip install everos` → `everos init` → `everos server start` 후
  학습자 Profile/Episode/Facts 저장에만 사용. 20분 안에 안 되면 즉시 폐기.
- **키가 없다**: EverOS를 건너뛰고 `learner_profile` / `learner_episodes` Snowflake 테이블로 대체.
  덱에서는 "메모리 레이어는 교체 가능한 인터페이스"로 프레이밍하고, EverOS 연동은 Next Steps에 둔다.

**어느 쪽이든 EverOS는 비용 절감 레버가 아니다.** 절감은 레버 1~5에서 나온다.
EverOS 때문에 measure/가 늦어지면 잘못된 트레이드다.

---

## 프로젝트 구조

```
snowvoca/
├── cortex/
│   ├── client.py                 # Cortex REST /messages 호출 (PAT 인증, httpx)
│   ├── router.py                 # ★ stage → 모델 매핑 (저가/고가)
│   └── setup.sql                 # 테이블 생성 (word_metadata, exercises, llm_calls, learner_*)
│
├── measure/                      # ★★ 신규. 이 프로젝트의 제출물이 여기서 나온다
│   ├── pricing.py
│   ├── meter.py
│   ├── baseline_naive.py
│   ├── report.py
│   └── verify.sql
│
├── batch/
│   ├── seed_data.py
│   ├── blank_picker.py           # ★ 규칙 기반 빈칸 선정 (LLM 0회)
│   ├── word_cache.py             # lemma 캐시 read-through (MERGE)
│   └── generate_exercises.py     # 대화 단위 배치 + cache_control
│
├── gateway/
│   ├── main.py                   # /exercise/next, /exercise/{id}/answer, /metrics
│   ├── grader.py                 # ★ 정오답 판정 = 문자열 비교 (LLM 0회)
│   ├── session_cache.py          # 압축 프로필
│   └── memory.py                 # EverOS 또는 Snowflake 테이블 (동일 인터페이스)
│
├── frontend/
│   └── src/
│       ├── QuizScreen.jsx        # 빈칸 문장 + 뜻 목록(정답 뜻 하이라이트) + 마이크 버튼
│       ├── CostHUD.jsx           # ★ 실시간 비용/캐시 히트율/LLM 회피 횟수
│       ├── useSpeechInput.js
│       └── api.js
│
└── README.md
```

### CostHUD — 화면 우측 고정 패널

```
이 세션            $0.0007
캐시 히트율            78%
LLM 호출 회피          42회
Naive 대비            -93%
```

**이 패널 하나가 "영어 학습 앱"을 "Track 1 프로젝트"로 읽히게 만든다.** 관객 투표에서 이게 결정적이다.
`/metrics` 엔드포인트가 `llm_calls` 테이블과 캐시 카운터를 집계해서 반환하면 된다.

---

## 학습자 메모리 매핑 (EverOS 사용 시)

EverOS에는 학습자 개인에 관한 것만 저장한다. `word_metadata`는 전 학습자 공유 어휘 지식이라 스코프 밖이다.

**Profile — 압축된 스냅샷 (세션 종료 시 갱신)**

```markdown
- ability_level: 3
- accuracy_rate: 0.72
- weak_words: [feel, figure_out, fix]
```

**Episode — 개별 시도 원본 로그**

```markdown
- 2026-08-07T09:12:00 | ex_014 | feel | correct: true
- 2026-08-07T09:13:10 | ex_022 | figure_out | correct: false
```

압축 방향은 Episode(원본) → Profile(요약)이다.

**Facts — 카운터로 안 잡히는 질적 패턴 (세션 종료 시 1회, 싼 모델)**

```markdown
- 2026-08-07: "구동사(phrasal verb)에서 특히 자주 틀림 (figure out, turn down 등)"
```

**Foresights — 시간 남을 때만.** `predicted_forget_date` 기반 복습 우선순위, 예측적 프리페치(다음에 만날
단어의 `word_metadata`를 미리 캐싱), 레벨업 예상치. **예측적 프리페치는 캐시 히트율을 올리므로
레버 2를 강화한다** — 여기까지 되면 덱에 한 줄 추가하되, 이것 때문에 일정을 밀지 않는다.

**안 쓰는 필드**: Cases/Skills (에이전트 측 메모리) — 이 시나리오에 해당 없음.
**복습 큐**: 별도 저장 없이 Episode에서 `correct: false`이고 미복습인 것만 조회.

---

## 실행 순서와 시계 게이트

체크포인트로 진행하되, **벽시계 시각에 도달하면 완료 여부와 무관하게 다음으로 넘어간다.**

| 시각  | 게이트                                                                                 | 미달 시 조치                                                   |
| ----- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| 13:00 | `SHOW CORTEX BASE MODELS;` + `/messages` 스모크 콜 1회 성공 + `setup.sql` 실행         | 인증 문제면 PAT 재발급. 여기서 20분 넘기면 데모 자체가 위험    |
| 13:15 | **`baseline_naive.py` 실행 (ACCOUNT_USAGE 예열 목적)**                                 | 미완이어도 다음으로. 단 반드시 오늘 중 1회는 돌려야 함         |
| 14:00 | `generate_exercises.py`로 문제 22개 생성 + `word_metadata` 채워짐 + `llm_calls` 기록됨 | 캐싱(레버 3)을 빼고 레버 1·2·4·5만으로 진행                    |
| 14:30 | **`report.py`가 절감률 숫자 1개를 출력**                                               | 여기가 마감 우선순위 1위. 미달이면 프론트를 버리고 여기에 올인 |
| 15:00 | 프론트 QuizScreen + CostHUD 동작. **코딩 동결**                                        | 프론트 미완이면 터미널 데모 + 스크린샷으로 전환                |
| 15:40 | 덱 8장 완성 + 리허설 2회                                                               | 리허설 1회로 축소                                              |
| 15:55 | **제출**                                                                               | 없음                                                           |

```bash
# 0. 스모크 + 스키마
python -m cortex.smoke && snowsql -f cortex/setup.sql

# 1. before 파이프라인 (가장 먼저)
python -m measure.baseline_naive

# 2. after 파이프라인
python -m batch.generate_exercises

# 3. 숫자 뽑기  ← 이게 제출물
python -m measure.report

# 4. 서버 + 프론트
uvicorn gateway.main:app --port 8000
cd frontend && npm install && npm run dev
```

---

## 막히면 자르는 순서 (위에서부터 먼저 버린다)

1. Foresights / 예측적 프리페치
2. EverOS 전체 → Snowflake 테이블로 대체
3. Facts 질적 요약
4. 오답 피드백 고가 모델 호출 → 고정 문구 `"Let's try that again."`
   (단 라우팅 레버가 사라지므로 report에서 해당 행을 빼고 절감률을 재계산)
5. lemmatize → 소문자 변환 + 단순 매칭
6. Web Speech API → 텍스트 입력창
7. 프론트엔드 전체 → 터미널 출력 + `report.py` 표를 스크린샷으로

**절대 자르지 않는 것**: `measure/` 전체, Naive 베이스라인 1회 실행, `report.py`의 절감률 한 줄, 덱, 15:55 제출.

---

## 데모 3분 대본

| 시간      | 내용                                                                                                     |
| --------- | -------------------------------------------------------------------------------------------------------- |
| 0:00-0:25 | 문제: 대화형 영어 학습은 학습자 1인당 하루 추론 비용이 마진을 결정한다. Naive로 만들면 1,000명에 월 $312 |
| 0:25-1:15 | 앱 시연: 내 어제 대화에서 나온 문장, 빈칸, 뜻 목록, 마이크로 답하기, 틀리면 복습 큐로                    |
| 1:15-1:50 | **두 번째 학습자 투입.** 캐시 히트율 0% → 78%로 오르는 CostHUD를 보여준다                                |
| 1:50-2:35 | `report.py` 라이브 실행. before/after 표와 **절감률 한 줄**. 레버 5개가 각각 얼마를 줄였는지             |
| 2:35-3:00 | 1,000명 × 30일 투영. $312 → $21. 이게 이 앱이 흑자가 되는 조건이다                                       |

앱으로 시작해서 숫자로 끝낸다. 순서를 바꾸면 관객 투표에서 진다.

## 덱 8장

1. 대화형 영어 학습의 원가 구조 (1인당 하루 추론 비용)
2. SnowVoca 화면 1컷
3. Naive 파이프라인 원가 분해 (6개 조건 명시)
4. 레버 5개
5. **before / after 표 + 절감률** ← 헤드라인 슬라이드
6. 계측 방법 (llm_calls 실시간 + ACCOUNT_USAGE 교차검증)
7. 단위경제와 $10 ARR/user 경로
8. Next Steps (Cortex Agent + EverOS MCP + SPCS 확장, 실제 학습자 온보딩)
