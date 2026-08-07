import os

import snowflake.connector

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS word_metadata (
      lemma STRING PRIMARY KEY,
      meaning_correct STRING,
      distractors ARRAY,
      difficulty STRING,
      generated_by STRING,
      created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS exercises (
      id STRING PRIMARY KEY,
      conversation_id STRING,
      sentence STRING,
      blank_word STRING,
      lemma STRING,
      meaning_correct STRING,
      distractors ARRAY,
      difficulty STRING,
      created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
    )
    """,
]


def get_connection():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
    )


def init_db(conn):
    cur = conn.cursor()
    for statement in SCHEMA_STATEMENTS:
        cur.execute(statement)
