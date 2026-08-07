# SnowVoca — Cortex Agent + EverOS(MCP) 빌드 가이드

## 목표
SnowVoca — 일상 대화(STT 텍스트, 영어)를 입력받아 빈칸 문제를 생성하고, 음성으로 답하면 정오답을 판정하며,
틀린 문제는 복습 큐로 넘어가는 데모를 완성한다. 오케스트레이션은 Snowflake Cortex Agent가 맡고,
학습자 기억(능력치, 오답 이력)은 EverOS를 MCP 도구로 연결해 관리한다.

> OAuth/컨테이너 배포가 들어가므로 정확한 시간 예측 대신 "완료 기준 체크포인트"로 진행한다.
> 막히는 단계가 나오면 그 시점까지 되는 것만으로 데모 범위를 좁힌다.

## 아키텍처
```
[Frontend: QuizScreen]
        │ (voice → text)
        ▼
[gateway] ── session_cache: 학습자 압축 프로필 보관 ──┐
        │ REST                                          │
        ▼                                               │
[Cortex Agent] ── orchestration ──┬── everos_memory(MCP tool) ──▶ [EverOS service on SPCS]
        │                          └── code execution tool          Profile / Episode / 복습 큐
        ▼
[Cortex COMPLETE] (문제 생성은 대화 단위 배치로, Agent 안 거치고 직접 호출)
        │
        ▼
   word_cache (단어 원형 단위 캐시)
```

## 캐싱 전략 — 문장이 아니라 "단어 원형(lemma)" 단위로 캐싱

Cortex Agent는 프롬프트 캐싱을 노출하지 않고, 문장 단위 캐싱은 완전 일치가 거의 안 일어나서
히트율이 낮다. 대신 **문제를 구성하는 부품 중 재사용 가능한 부품만 캐싱**한다.

- 문장은 사용자마다 달라 사실상 무한하지만, 단어의 뜻·오답 후보·난이도는 문장이 바뀌어도
  거의 동일하다 (`feel`이 어느 문장에 나오든 뜻/오답은 재사용 가능).
- 캐시 키를 문장이 아니라 **단어 원형(lemma)**으로 잡으면, 일상 대화에 쓰이는 단어 종류는
  유한하므로 완전 일치(exact match) 캐싱이면서도 히트율이 시간이 지날수록 계속 올라간다.

**저장소는 인메모리 딕셔너리가 아니라 Snowflake 테이블** — 단어 메타데이터는 특정 학습자가 아니라
모두가 공유하는 어휘 지식이라 EverOS의 개인별 Profile/Episode와는 성격이 다르다. 프로세스 재시작에도
남아야 하고, SQL로 직접 조회/검증할 수 있어야 하므로 테이블로 관리한다.

```sql
CREATE TABLE IF NOT EXISTS word_metadata (
  lemma STRING PRIMARY KEY,
  meaning_correct STRING,
  distractors ARRAY,
  difficulty STRING,        -- easy | medium | hard
  generated_by STRING,      -- 어떤 모델이 만들었는지 (감사용)
  created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
```

```python
# batch/word_cache.py — read-through 패턴
def get_or_generate_word_metadata(word: str, conn) -> dict:
    lemma = lemmatize(word)               # feel/feels/felt/feeling → feel
    row = conn.cursor().execute(
        "SELECT meaning_correct, distractors, difficulty FROM word_metadata WHERE lemma = %s", (lemma,)
    ).fetchone()
    if row:
        return {"meaning_correct": row[0], "distractors": row[1], "difficulty": row[2]}  # 캐시 히트

    result = cheap_model_call(lemma)      # 캐시 미스: 이번만 호출
    conn.cursor().execute(
        "INSERT INTO word_metadata (lemma, meaning_correct, distractors, difficulty, generated_by) VALUES (%s, %s, %s, %s, %s)",
        (lemma, result["meaning_correct"], result["distractors"], result["difficulty"], "cheap_model_v1")
    )
    return result
```

**체크 방법**:
```sql
-- 캐시가 실제로 쌓이고 있는지
SELECT lemma, difficulty, created_at FROM word_metadata ORDER BY created_at DESC LIMIT 20;
```

**무효화**: 잘못된 메타데이터를 고치고 싶으면 해당 행을 삭제만 하면 다음 배치 실행 시 자동 재생성된다
(`DELETE FROM word_metadata WHERE lemma = 'feel';`). 이 규모에서는 정교한 TTL보다 이 정도로 충분하다.

## 압축 전략 — 모델 없이 코드로 하는 게 기본

학습자 히스토리를 비싼 모델에게 넘길 때, 원본 시도 로그 전체 대신 **파이썬 코드로 누적한
숫자 몇 개**만 넘긴다. 압축 자체에 모델 호출이 없어 비용이 거의 0이고, 시도 횟수가 늘어나도
프롬프트 길이가 고정된다.

```python
# gateway/session_cache.py — 압축된 프로필 형태
{
  "accuracy_rate": 0.7,                          # 정답/전체 누적 카운터
  "recent_sequence": ["O", "O", "X"],             # 최근 정오답 (고정 길이 리스트)
  "weak_word_tags": {"feel": 2, "figure_out": 1}  # 오답 단어별 카운트
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

**선택 확장 → EverOS Facts로 구현**: 숫자 집계로 안 되는 질적 요약(예: "자주 틀리는 패턴 한 줄 요약")이
필요하면, 아주 드물게(예: 세션 종료 시 1번) 싼 모델을 호출해 요약 문장을 만들고 EverOS Facts에 저장한다
(자세한 예시는 아래 "EverOS 메모리 매핑" 참고). 매번 비싼 모델에 원본을 보내는 것보다는 여전히 훨씬 저렴하다.

| | 방식 | 비용 |
|---|---|---|
| 기본 | 코드로 카운터/리스트만 누적 | 거의 0 |
| 확장(선택) | 드물게 싼 모델로 질적 요약 1문장 생성 후 캐싱 | 아주 낮음 |

## 배치 생성 — 대화 단위로 묶어서 한 번에 호출

문장을 하나씩 호출하지 않고, 대화(4~5문장) 단위로 묶어 한 프롬프트에 넣어 요청한다.
`SAMPLE_CONVERSATIONS` 5개, 총 22문장이면 호출 22번이 아니라 5번으로 끝난다.

```python
# batch/generate_exercises.py 개념
for conv in SAMPLE_CONVERSATIONS:
    sentences = conv["transcript"]
    prompt = build_batch_prompt(sentences)   # 여러 문장을 한 번에 요청
    exercises = cheap_model_call(prompt)      # 문장별 결과가 JSON 배열로 돌아옴
    for ex in exercises:
        blank_word = ex["blank_word"]
        ex["word_meta"] = get_or_generate_word_metadata(blank_word, conn)  # word_metadata 테이블 조회/생성
        save_to_everos_or_db(ex)
```

## 시드 데이터 (영어로만 구성)
```python
# batch/seed_data.py

SAMPLE_CONVERSATIONS = [
    {
        "id": "conv_01",
        "title": "Morning routine",
        "transcript": [
            "I usually feel tired after work.",
            "Yeah, me too. I barely have energy to cook dinner.",
            "I've been trying to go to bed earlier, but it's not working.",
            "Same here. I keep scrolling on my phone until midnight.",
        ],
    },
    {
        "id": "conv_02",
        "title": "Work stress",
        "transcript": [
            "We need to fix this bug before the deadline.",
            "I know, but I can't figure out what's causing it.",
            "Have you checked the error logs yet?",
            "Not yet, I was about to when you called.",
            "Okay, let's look at it together after lunch.",
        ],
    },
    {
        "id": "conv_03",
        "title": "Weekend plans",
        "transcript": [
            "Do you have any plans for the weekend?",
            "Not really. I might just stay home and relax.",
            "That sounds nice actually. I've been so busy lately.",
            "You should join me. We could order some food and watch a movie.",
            "That sounds great, count me in.",
        ],
    },
    {
        "id": "conv_04",
        "title": "Cafe order",
        "transcript": [
            "Can I get a medium iced latte, please?",
            "Sure, would you like that with oat milk or regular?",
            "Oat milk is fine, thanks.",
            "Alright, that'll be ready in about five minutes.",
            "No rush, I'll just find a seat.",
        ],
    },
    {
        "id": "conv_05",
        "title": "Traffic complaint",
        "transcript": [
            "Sorry I'm late, the traffic was terrible today.",
            "It's okay, I figured something happened.",
            "There was an accident on the highway, so everything just stopped.",
            "That happens a lot around this time, doesn't it?",
            "Yeah, I really should start leaving earlier.",
        ],
    },
]
```

## 기술 스택
- 오케스트레이션: Snowflake Cortex Agent (모델/도구 자동 선택, orchestration instruction으로 제어)
- 기억 레이어: EverOS, Snowpark Container Services에 컨테이너로 배포 후 MCP 도구로 Agent에 연결
- 문제 생성(배치): Cortex `COMPLETE` 직접 호출, 대화 단위 배치 + 단어 캐시 조합
- gateway: FastAPI, Cortex Agent REST API 중계 + session_cache(압축 프로필) 보관
- 프론트엔드: React (Vite), QuizScreen(빈칸 문장+뜻 목록+마이크 버튼), Web Speech API로 STT
- LLM 호출 방식: Anthropic SDK 사용 금지. 전부 Cortex 경로로만 호출

## 프로젝트 구조
```
snowvoca/
├── cortex/
│   ├── agent_spec.yaml            # Agent 정의: model, tools(everos_memory, code execution), instructions
│   ├── setup.sql                  # Network Rule, Secret, API Integration, External MCP Server 객체
│   └── deploy_agent.py            # Cortex Agent REST API로 생성/업데이트
│
├── everos_service/
│   ├── Dockerfile
│   ├── app.py                     # EverOS memorize/retrieve를 감싸는 MCP 서버 레이어
│   ├── memory_schema.py           # 학습자 Profile(능력치)·Episode(풀이기록)를 EverOS 스키마에 매핑
│   └── spcs_service.yaml          # Snowpark Container Services 서비스 정의
│
├── gateway/
│   ├── main.py                    # /exercise/next, /exercise/{id}/answer → Cortex Agent REST 호출
│   ├── cortex_client.py           # Cortex Agent REST API 래퍼
│   └── session_cache.py           # ★ 압축된 학습자 프로필(카운터 기반) 세션 캐시
│
├── batch/
│   ├── seed_data.py                # 샘플 대화 5개 (영어)
│   ├── word_cache.py               # ★ 단어 원형(lemma) 캐시, word_metadata 테이블 read-through
│   └── generate_exercises.py       # 대화 단위 배치 호출 + word_cache 조합
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── QuizScreen.jsx          # 빈칸 문장 + 뜻 목록 + 마이크 버튼
│   │   ├── useSpeechInput.js       # Web Speech API 훅
│   │   └── api.js
│   └── index.html
│
└── README.md
```

## EverOS 메모리 매핑
EverOS에는 학습자 개인에 관한 것만 저장한다. 단어 메타데이터(word_metadata)는 모두가 공유하는
어휘 지식이라 Snowflake 테이블에 있고, EverOS 스코프 밖이다.

**Profile — 학습자 현재 상태(압축된 스냅샷, 세션 종료 시 갱신)**
```markdown
---
learner_id: learner_001
---
- ability_level: 3
- accuracy_rate: 0.72
- weak_words: [feel, figure_out, fix]
- last_updated: 2026-08-07
```

**Episode — 개별 시도 원본 로그(압축하지 않음)**
```markdown
- 2026-08-07T09:12:00 | exercise_id: ex_014 | word: feel | correct: true
- 2026-08-07T09:13:10 | exercise_id: ex_022 | word: figure_out | correct: false
```
Profile의 `accuracy_rate`, `weak_words`는 이 Episode 로그를 집계한 결과물이다.
즉 압축은 "Episode(원본) → Profile(요약)" 방향으로 일어난다.

**Facts — 카운터로는 안 잡히는 질적 패턴 (세션 종료 시 1회, 싼 모델로 요약)**
```markdown
- 2026-08-05: "구동사(phrasal verb)에서 특히 자주 틀림 (figure out, turn down 등)"
- 2026-08-07: "STT가 과거시제 동사 발음을 자주 놓침 — 발음 자체의 문제일 수도 있음"
```
Profile의 `weak_words`는 "무엇을 틀렸는지"만 알려주고, Facts는 "어떤 패턴으로 틀리는지"를 채운다.
Cortex Agent가 다음 문제를 고를 때 Profile 숫자뿐 아니라 최근 Facts 한두 줄을 함께 참고하게 하면
"구동사 위주로 문제를 늘려라" 같은, 순수 카운터로는 안 되는 판단이 가능해진다.

**Foresights — 예측이라서 "미리 준비"가 가능해짐 (5세션마다 1회 정도, 비싼 모델로 트렌드 추론)**
```markdown
- predicted_forget_date: {"feel": "2026-08-10", "figure_out": "2026-08-09"}
- predicted_next_focus: "구동사 집중 학습 필요"
- predicted_level_up: "약 8세션 후 Lv.4 도달 예상"
```
활용 세 가지:
1. **복습 타이밍 개인화** — 고정 SM-2 간격 대신 `predicted_forget_date`를 참고해 잊기 전에 복습 배치
2. **예측적 프리페치** — `predicted_next_focus`가 가리키는 단어들의 `word_metadata`를 학습자가 마주치기
   전에 미리 캐싱해둠 (캐시 미스 타이밍을 예측해서 선제적으로 채우는 것)
3. **레벨업 예상치** — 동기부여용 UI 문구에 바로 활용

**복습 큐** — 별도 저장 없이 Episode에서 `correct: false`이고 아직 복습 완료 처리 안 된 것만 조회해 대체.
Foresight의 `predicted_forget_date`가 있으면 단순 필터링 대신 그 날짜 기준으로 우선순위를 매긴다.

**이 프로젝트에서 안 쓰는 EverOS 필드**
- Cases/Skills (에이전트 측 메모리) — 코딩 에이전트가 절차를 학습하는 시나리오가 아니므로 해당 없음

## Cortex Agent 오케스트레이션 지침 (agent_spec.yaml 초안)
- "다음 문제 난이도를 정할 때는 반드시 everos_memory 도구로 학습자의 압축된 프로필(정답률, 최근 기록)을 먼저 조회하라"
- "오답 피드백 문구가 필요할 때만 고성능 모델로 생성하고, 정답일 때는 피드백 생성을 생략하라"
- "동일 세션 내에서 능력치가 바뀌지 않았다면 everos_memory를 다시 조회하지 말고 이전 결과를 재사용하라"
  (지침만으로 강제되지 않을 수 있으므로, 실제 강제는 `gateway/session_cache.py`가 담당)

## 단계별 체크포인트 (시간이 아니라 완료 기준으로 진행)
1. **Cortex 접속/모델 확인** — `SHOW MODELS IN SNOWFLAKE.CORTEX;`로 사용 가능 모델 확정
2. **word_cache + 배치 생성 로직** — Agent/EverOS 없이 독립적으로 먼저 완료 가능한 파트, seed_data로 테스트
3. **EverOS 컨테이너 배포** — Dockerfile 빌드 → SPCS에 서비스로 등록, 엔드포인트 헬스체크 통과 확인
4. **External MCP Server 등록** — API Integration(OAuth) + External MCP Server 객체 생성, Agent에서 도구로 보이는지 확인
5. **Cortex Agent 생성** — agent_spec.yaml 기반으로 REST API 호출, everos_memory 도구가 목록에 뜨는지 확인
6. **gateway 완성** — session_cache 포함 두 엔드포인트 구현, curl로 Agent 왕복 확인
7. **프론트엔드 연결** — QuizScreen + Web Speech API
8. **전체 리허설**

## 막히면 이렇게 잘라낸다 (우선순위 낮은 것부터 제거)
1. External MCP Server(OAuth) 등록이 막히면 → `gateway`에서 EverOS를 파이썬 라이브러리로 직접 import
   (네트워크/MCP 계층 생략, Cortex Agent도 생략하고 Cortex COMPLETE 직접 호출로 축소)
2. EverOS 컨테이너 배포가 막히면 → EverOS를 gateway 프로세스 안에서 로컬 실행 (SPCS 배포만 스킵)
3. word_cache lemmatize가 번거로우면 → 소문자 변환 + 단순 문자열 매칭으로 축소 (형태소 분석기 생략)
4. 학습자 능력치 정밀 추정 → session_cache의 accuracy_rate만으로 대체
5. 오답 피드백 문구 → 고정 문구로 대체 ("Let's try that again.")
6. Web Speech API 호환 문제 → 텍스트 입력창으로 대체

## 실행 방법
```bash
# 배치 생성 (Agent 없이 독립 실행 가능, 가장 먼저 검증)
cd batch && python generate_exercises.py

# EverOS 서비스 (컨테이너)
cd everos_service && docker build -t everos-svc .
# → SPCS 배포는 setup.sql 실행 후 snow cli 또는 Python API로 서비스 생성

# Cortex Agent 등록
cd cortex && python deploy_agent.py

# gateway
cd gateway && pip install fastapi uvicorn snowflake-connector-python --break-system-packages
uvicorn main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev
```
