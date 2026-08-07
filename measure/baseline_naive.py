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

NAIVE = os.getenv("MODEL_NAIVE", "claude-opus-4-5")

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
