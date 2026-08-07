import os, snowflake.connector
from dotenv import load_dotenv
load_dotenv()

_conn = None
_attempted = False

def conn():
    """Snowflake 연결. 실패해도 파이프라인은 계속 돌아야 하므로 None을 반환한다."""
    global _conn, _attempted
    if _conn is not None:
        return _conn
    # 로컬 리허설은 Snowflake 계측 미러 없이도 JSONL 원장으로 완주한다.
    # 실제 계정 계측을 켤 때만 SNOWVOCA_USE_SNOWFLAKE=1을 지정한다.
    if os.getenv("SNOWVOCA_USE_SNOWFLAKE", "0") != "1":
        return None
    if _attempted:
        return None
    _attempted = True
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
