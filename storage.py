"""SQLite-backed durable interview sessions and users.

No audio bytes or third-party API credentials are persisted. Uses a versioned,
optimistic concurrency update so two simultaneous answers cannot silently
overwrite one another. WAL supports ordinary single-host demo deployments;
use a managed database for horizontal scaling.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


class ConflictError(Exception):
    pass


class SQLiteStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == 'posix':
            try:
                self.path.parent.chmod(0o700)
            except OSError:
                pass
        self._migrate()
        if os.name == 'posix':
            try:
                self.path.chmod(0o600)
            except OSError:
                pass

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('PRAGMA busy_timeout = 10000')
        return db

    def _migrate(self):
        with self.connect() as db:
            db.execute('PRAGMA journal_mode = WAL')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 1:
                raise RuntimeError('The database schema is newer than this application')
            if version == 0:
                db.executescript('''
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        email TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        created_at INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS interviews (
                        id TEXT PRIMARY KEY,
                        owner_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                        created_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL,
                        modified_at INTEGER NOT NULL,
                        version INTEGER NOT NULL DEFAULT 0,
                        state_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_interviews_expiry ON interviews(expires_at);
                    CREATE INDEX IF NOT EXISTS idx_interviews_owner ON interviews(owner_id);
                    CREATE TABLE IF NOT EXISTS revoked_tokens (
                        jti TEXT PRIMARY KEY,
                        expires_at INTEGER NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_revoked_expiry ON revoked_tokens(expires_at);
                    PRAGMA user_version = 1;
                    COMMIT;
                ''')

    def create_user(self, email: str, password_hash: str) -> str:
        user_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute('INSERT INTO users(id, email, password_hash, created_at) VALUES (?, ?, ?, ?)',
                       (user_id, email, password_hash, int(time.time())))
        return user_id

    def user_by_email(self, email: str) -> dict | None:
        with self.connect() as db:
            row = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        return dict(row) if row else None

    def user_by_id(self, user_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute('SELECT id,email,created_at FROM users WHERE id=?', (user_id,)).fetchone()
        return dict(row) if row else None

    def delete_user(self, user_id: str) -> None:
        with self.connect() as db:
            db.execute('DELETE FROM users WHERE id=?', (user_id,))

    def create_session(self, session_id: str, state: dict[str, Any], owner_id: str | None,
                       ttl_seconds: int) -> None:
        now = int(time.time())
        with self.connect() as db:
            db.execute('''INSERT INTO interviews(id,owner_id,created_at,expires_at,modified_at,state_json)
                          VALUES (?,?,?,?,?,?)''',
                       (session_id, owner_id, now, now + ttl_seconds, now,
                        json.dumps(state, ensure_ascii=False, allow_nan=False)))

    def get_session(self, session_id: str, owner_id: str | None) -> dict | None:
        now = int(time.time())
        with self.connect() as db:
            if owner_id is None:
                row = db.execute('''SELECT * FROM interviews WHERE id=? AND owner_id IS NULL AND expires_at>?''',
                                 (session_id, now)).fetchone()
            else:
                row = db.execute('''SELECT * FROM interviews WHERE id=? AND owner_id=? AND expires_at>?''',
                                 (session_id, owner_id, now)).fetchone()
        if row is None:
            return None
        return {'state': json.loads(row['state_json']), 'version': row['version']}

    def update_session(self, session_id: str, owner_id: str | None, state: dict,
                       expected_version: int) -> None:
        now = int(time.time())
        with self.connect() as db:
            if owner_id is None:
                result = db.execute('''UPDATE interviews SET state_json=?,version=version+1,modified_at=?
                                       WHERE id=? AND owner_id IS NULL AND version=? AND expires_at>?''',
                                    (json.dumps(state, ensure_ascii=False, allow_nan=False), now,
                                     session_id, expected_version, now))
            else:
                result = db.execute('''UPDATE interviews SET state_json=?,version=version+1,modified_at=?
                                       WHERE id=? AND owner_id=? AND version=? AND expires_at>?''',
                                    (json.dumps(state, ensure_ascii=False, allow_nan=False), now,
                                     session_id, owner_id, expected_version, now))
        if result.rowcount != 1:
            raise ConflictError('Session has been updated elsewhere; refresh and retry')

    def delete_session(self, session_id: str, owner_id: str | None) -> bool:
        with self.connect() as db:
            if owner_id is None:
                result = db.execute('DELETE FROM interviews WHERE id=? AND owner_id IS NULL', (session_id,))
            else:
                result = db.execute('DELETE FROM interviews WHERE id=? AND owner_id=?',
                                    (session_id, owner_id))
        return result.rowcount == 1

    def recent_sessions(self, owner_id: str, limit: int = 20) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('''SELECT id,created_at,modified_at,state_json FROM interviews
                                 WHERE owner_id=? AND expires_at>? ORDER BY modified_at DESC LIMIT ?''',
                              (owner_id, int(time.time()), min(limit, 50))).fetchall()
        result = []
        for row in rows:
            state = json.loads(row['state_json'])
            scores = [answer['feedback']['score'] for answer in state['answers'] if isinstance(answer.get('feedback', {}).get('score'), (int, float))]
            result.append({'session_id': row['id'], 'track': state['track'],
                           'language': state['language'],
                           'answered': len(state['answers']),
                           'completed': len(state['answers']) >= 3,
                           'average_score': round(sum(scores) / len(scores)) if scores else None,
                           'modified_at': row['modified_at'],
                           'created': state['created']})
        return result

    def revoke_token(self, jti: str, expires_at: int) -> None:
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO revoked_tokens(jti,expires_at) VALUES(?,?)',
                       (jti, expires_at))

    def token_is_revoked(self, jti: str) -> bool:
        with self.connect() as db:
            return db.execute('SELECT 1 FROM revoked_tokens WHERE jti=? AND expires_at>?',
                              (jti, int(time.time()))).fetchone() is not None

    def cleanup(self) -> dict[str, int]:
        now = int(time.time())
        with self.connect() as db:
            sessions = db.execute('DELETE FROM interviews WHERE expires_at<=?', (now,)).rowcount
            tokens = db.execute('DELETE FROM revoked_tokens WHERE expires_at<=?', (now,)).rowcount
        return {'expired_sessions': sessions, 'expired_tokens': tokens}

