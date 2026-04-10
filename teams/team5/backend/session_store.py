"""
Session persistence — stores GegevensModel + conversation history per session.

Uses the same SQLite DB as feedback (FEEDBACK_DB_PATH).
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import aiosqlite

from models import GegevensModel

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("FEEDBACK_DB_PATH", "data/feedback.db")


async def _ensure_sessions_table(db_path: str = DB_PATH) -> None:
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                gegevens TEXT NOT NULL,
                messages TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.commit()


async def save_session(
    session_id: str,
    gegevens: GegevensModel,
    messages: list[dict],
    db_path: str = DB_PATH,
) -> None:
    """Upsert a session with its gegevensmodel and conversation."""
    await _ensure_sessions_table(db_path)
    now = datetime.now(timezone.utc).isoformat()
    gegevens_json = gegevens.model_dump_json()
    messages_json = json.dumps(messages, ensure_ascii=False)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            INSERT INTO sessions (session_id, gegevens, messages, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                gegevens = excluded.gegevens,
                messages = excluded.messages,
                updated_at = excluded.updated_at
        """, (session_id, gegevens_json, messages_json, now, now))
        await db.commit()


async def get_session(
    session_id: str,
    db_path: str = DB_PATH,
) -> dict | None:
    """Retrieve a session. Returns dict with gegevens + messages, or None."""
    await _ensure_sessions_table(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "session_id": row["session_id"],
                "gegevens": json.loads(row["gegevens"]),
                "messages": json.loads(row["messages"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }


async def list_sessions(
    limit: int = 50,
    db_path: str = DB_PATH,
) -> list[dict]:
    """List recent sessions for admin view."""
    await _ensure_sessions_table(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT session_id, gegevens, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "session_id": row["session_id"],
                    "gegevens": json.loads(row["gegevens"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]
