"""SQLite-backed structured audit log."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from config import DATABASE_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                content_id TEXT PRIMARY KEY,
                creator_id TEXT NOT NULL,
                text_snippet TEXT NOT NULL,
                attribution TEXT NOT NULL,
                confidence REAL NOT NULL,
                llm_score REAL NOT NULL,
                style_score REAL NOT NULL,
                label TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'classified',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_type TEXT NOT NULL,
                content_id TEXT NOT NULL,
                creator_id TEXT,
                timestamp TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _ensure_db() -> None:
    """Create tables if they don't exist (safe to call repeatedly)."""
    init_db()


def save_submission(
    content_id: str,
    creator_id: str,
    text: str,
    attribution: str,
    confidence: float,
    llm_score: float,
    style_score: float,
    label: str,
) -> None:
    snippet = text[:200] + ("..." if len(text) > 200 else "")
    now = datetime.now(timezone.utc).isoformat()

    _ensure_db()

    entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": now,
        "attribution": attribution,
        "confidence": round(confidence, 4),
        "llm_score": round(llm_score, 4),
        "style_score": round(style_score, 4),
        "label": label,
        "status": "classified",
    }

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO submissions
                (content_id, creator_id, text_snippet, attribution, confidence,
                 llm_score, style_score, label, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'classified', ?)
            """,
            (
                content_id,
                creator_id,
                snippet,
                attribution,
                confidence,
                llm_score,
                style_score,
                label,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO audit_log (entry_type, content_id, creator_id, timestamp, payload)
            VALUES ('classification', ?, ?, ?, ?)
            """,
            (content_id, creator_id, now, json.dumps(entry)),
        )
        conn.commit()


def save_appeal(content_id: str, creator_reasoning: str) -> dict[str, Any] | None:
    _ensure_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM submissions WHERE content_id = ?", (content_id,)
        ).fetchone()
        if row is None:
            return None

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE submissions SET status = 'under_review' WHERE content_id = ?",
            (content_id,),
        )

        appeal_entry = {
            "content_id": content_id,
            "creator_id": row["creator_id"],
            "timestamp": now,
            "entry_type": "appeal",
            "status": "under_review",
            "appeal_reasoning": creator_reasoning,
            "original_attribution": row["attribution"],
            "original_confidence": row["confidence"],
            "original_llm_score": row["llm_score"],
            "original_style_score": row["style_score"],
            "original_label": row["label"],
        }

        conn.execute(
            """
            INSERT INTO audit_log (entry_type, content_id, creator_id, timestamp, payload)
            VALUES ('appeal', ?, ?, ?, ?)
            """,
            (content_id, row["creator_id"], now, json.dumps(appeal_entry)),
        )
        conn.commit()
        return appeal_entry


def get_submission(content_id: str) -> dict[str, Any] | None:
    _ensure_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM submissions WHERE content_id = ?", (content_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)


def get_log_entries(limit: int = 50) -> list[dict[str, Any]]:
    _ensure_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT payload FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [json.loads(row["payload"]) for row in rows]
