"""SQLite persistence for Google users and their interview sessions."""

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

DATABASE_PATH = os.environ.get("DATABASE_PATH", "/data/ai_interviewer.db")
if not os.access(os.path.dirname(DATABASE_PATH) or ".", os.W_OK):
    DATABASE_PATH = str(Path(__file__).resolve().parent.parent / "data" / "ai_interviewer.db")

_db_lock = threading.RLock()
_session_list_cache = {}
CACHE_TTL_SECONDS = 30


def _connect():
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db():
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _db_lock, _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                google_sub TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                picture TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS interviews (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                company TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT '',
                started_at REAL NOT NULL,
                ended_at REAL,
                transcript_json TEXT NOT NULL,
                feedback_json TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_interviews_user_started
                ON interviews(user_id, started_at DESC);
            """
        )


def upsert_user(google_sub, email, name="", picture=""):
    now = time.time()
    with _db_lock, _connect() as connection:
        connection.execute(
            """
            INSERT INTO users (google_sub, email, name, picture, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(google_sub) DO UPDATE SET
                email=excluded.email, name=excluded.name, picture=excluded.picture,
                updated_at=excluded.updated_at
            """,
            (google_sub, email, name, picture, now, now),
        )
        row = connection.execute(
            "SELECT id, google_sub, email, name, picture FROM users WHERE google_sub = ?",
            (google_sub,),
        ).fetchone()
    return dict(row)


def get_user(user_id):
    with _db_lock, _connect() as connection:
        row = connection.execute(
            "SELECT id, google_sub, email, name, picture FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def save_interview(session_id, user_id, session, feedback=None):
    if not user_id:
        return
    transcript = [
        {"role": message["role"], "content": message["content"]}
        for message in session.get("messages", [])
        if message.get("role") in {"user", "assistant"}
    ]
    with _db_lock, _connect() as connection:
        connection.execute(
            """
            INSERT INTO interviews
                (id, user_id, mode, company, role, started_at, ended_at, transcript_json, feedback_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                ended_at=excluded.ended_at, transcript_json=excluded.transcript_json,
                feedback_json=excluded.feedback_json
            """,
            (
                session_id,
                user_id,
                session.get("mode", "behavioral"),
                session.get("company", ""),
                session.get("role", ""),
                session.get("start_time", time.time()),
                time.time() if session.get("ended") else None,
                json.dumps(transcript),
                json.dumps(feedback) if feedback is not None else None,
            ),
        )
    _session_list_cache.pop(user_id, None)


def list_interviews(user_id, limit=50):
    now = time.time()
    cached = _session_list_cache.get(user_id)
    if cached and now - cached["created_at"] < CACHE_TTL_SECONDS:
        return cached["items"]
    with _db_lock, _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, mode, company, role, started_at, ended_at,
                   CASE WHEN feedback_json IS NOT NULL THEN 1 ELSE 0 END AS has_feedback
            FROM interviews WHERE user_id = ? ORDER BY started_at DESC LIMIT ?
            """,
            (user_id, min(max(limit, 1), 100)),
        ).fetchall()
    items = [dict(row) for row in rows]
    _session_list_cache[user_id] = {"created_at": now, "items": items}
    return items


def get_interview(user_id, interview_id):
    with _db_lock, _connect() as connection:
        row = connection.execute(
            """
            SELECT id, mode, company, role, started_at, ended_at,
                   transcript_json, feedback_json
            FROM interviews WHERE id = ? AND user_id = ?
            """,
            (interview_id, user_id),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["transcript"] = json.loads(item.pop("transcript_json"))
    item["feedback"] = json.loads(item.pop("feedback_json")) if item["feedback_json"] else None
    return item
