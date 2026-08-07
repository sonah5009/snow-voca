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
