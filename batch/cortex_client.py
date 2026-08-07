import os

CHEAP_MODEL = os.environ.get("CORTEX_CHEAP_MODEL", "llama3.1-8b")


def cheap_call(conn, prompt: str) -> str:
    """Cortex COMPLETE 직접 호출. Agent를 거치지 않는 배치 생성 경로."""
    cur = conn.cursor()
    cur.execute("SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s)", (CHEAP_MODEL, prompt))
    return cur.fetchone()[0]
