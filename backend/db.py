import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "malhae_voca.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS exercises (
  id INTEGER PRIMARY KEY,
  sentence TEXT,
  answer TEXT,
  meaning_correct TEXT,
  meaning_distractors TEXT,
  difficulty TEXT,
  in_review INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY,
  exercise_id INTEGER,
  correct INTEGER,
  created_at TEXT
);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
