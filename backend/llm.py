import os
import snowflake.connector

CHEAP_MODEL = os.environ.get("CORTEX_CHEAP_MODEL", "llama3.1-8b")
EXPENSIVE_MODEL = os.environ.get("CORTEX_EXPENSIVE_MODEL", "claude-sonnet-4-6")


def _get_connection():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
    )


def _complete(model: str, prompt: str) -> str:
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s)", (model, prompt)
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


def cheap_call(prompt: str) -> str:
    return _complete(CHEAP_MODEL, prompt)


def expensive_call(prompt: str) -> str:
    return _complete(EXPENSIVE_MODEL, prompt)
