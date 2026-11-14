"""Tests for SQLite Schema v2 migration and append-only session events audit trail."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from storage import SQLiteStore


def test_schema_v2_migration_and_events_logging(tmp_path: Path):
    db_file = tmp_path / "migration_test.sqlite3"

    # Step 1: Create a legacy v1 database
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript("""
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE interviews (
            id TEXT PRIMARY KEY,
            owner_id TEXT REFERENCES users(id) ON DELETE CASCADE,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            modified_at INTEGER NOT NULL,
            version INTEGER NOT NULL DEFAULT 0,
            state_json TEXT NOT NULL
        );
        CREATE TABLE revoked_tokens (
            jti TEXT PRIMARY KEY,
            expires_at INTEGER NOT NULL
        );
        PRAGMA user_version = 1;
    """)
    conn.commit()
    conn.close()

    # Step 2: Initialize SQLiteStore — should automatically migrate to v2
    store = SQLiteStore(db_file)
    with store.connect() as db:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        assert version == 2

        # Check session_events table exists
        cols = db.execute("PRAGMA table_info(session_events)").fetchall()
        col_names = [c["name"] for c in cols]
        assert "id" in col_names
        assert "session_id" in col_names
        assert "trace_id" in col_names
        assert "event_type" in col_names
        assert "timestamp" in col_names
        assert "payload_json" in col_names

    # Step 3: Log events
    session_id = "test-session-123"
    store.create_session(session_id, {"track": "software"}, None, 3600)

    e1 = store.log_event(session_id, "session_started", {"track": "software", "language": "en-IN"}, trace_id="tr-1")
    e2 = store.log_event(session_id, "speech_start", {"latency_ms": 120}, trace_id="tr-1")
    e3 = store.log_event(session_id, "candidate_answer_committed", {"transcript": "Used asyncio"}, trace_id="tr-1")

    assert e1 and e2 and e3

    # Step 4: Retrieve events
    events = store.get_session_events(session_id)
    assert len(events) == 3
    assert events[0]["event_type"] == "session_started"
    assert events[0]["payload"]["track"] == "software"
    assert events[1]["event_type"] == "speech_start"
    assert events[2]["event_type"] == "candidate_answer_committed"
    assert events[2]["payload"]["transcript"] == "Used asyncio"

    # Step 5: Deleting session purges events
    store.delete_session(session_id, None)
    remaining_events = store.get_session_events(session_id)
    assert len(remaining_events) == 0
