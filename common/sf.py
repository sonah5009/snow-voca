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
