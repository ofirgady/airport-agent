from pathlib import Path

from agents import SQLiteSession

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SESSIONS_DB_PATH = str(DATA_DIR / "sessions.db")


def get_session(session_id: str) -> SQLiteSession:
    return SQLiteSession(session_id=session_id, db_path=SESSIONS_DB_PATH)
