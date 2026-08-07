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
