# SQLite persistence, multiuser access and security model

## What is implemented and tested
- **SQLite persistent sessions** in `.data/interviewmirror.sqlite3` by default; session records survive a process restart. The database stores the user's answer transcripts, scoring evidence and session status; it does **not** store WAV audio or provider API keys.
- A versioned database schema (`PRAGMA user_version=1`) with users, sessions, and token revocations. Tables have owner/expiry indexes and foreign-key cascading deletion.
- **Ownership enforced inside SQL queries**, not only in the frontend. Another authenticated user cannot read, mutate or delete your interview by knowing its UUID.
- **Optimistic concurrency control** using a version check, rejecting overlapping answers instead of silently overwriting them.
- A configurable retention time (`IM_SESSION_TTL_SECONDS`, default 86,400 seconds), lazy expiry on reads, and `SQLiteStore.cleanup()` to remove expired rows.
- Registration, login, profile, logout/token revocation, account deletion, recent-session listing, and session restoration in the browser.
- Argon2id password hashing and HS256 JWT with fixed issuer, audience, expiration, signing algorithm and opaque `jti`. Access token lasts one hour and stays in browser memory rather than localStorage.
- Basic per-process auth throttling. This is not shared multi-replica abuse protection.

## Enable authenticated local use

Copy `.env.example` to `.env`, then set:

```
IM_AUTH_REQUIRED=true
IM_ENV=development
IM_JWT_SECRET=<random 32+ char secret generated with secrets.token_urlsafe(48)>
IM_DATABASE_PATH=.data/interviewmirror.sqlite3
```

PowerShell secret generation:

```
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

Never check secrets or the `.data/` folder into Git. Run `python -m pytest -q` and start `python -m uvicorn main:app --host 127.0.0.1 --port 8001`. Sign up on the web page and start/resume an interview.

`IM_AUTH_REQUIRED=false` is a **local, unauthenticated demo**: sessions are still stored in SQLite but not associated with an account. It must never be used on a public internet-facing deployment.

## Production fail-closed check

Set `IM_ENV=production`. The application refuses to start if authentication is not enabled or if the signing secret is missing/short. Production must use HTTPS termination upstream; set a shared abuse-prevention limit at the gateway, secure secret manager, encrypted DB backup, regular cleanup, log redaction, and audit access. Account recovery, verified emails, MFA, OIDC, Postgres migration path, multi-replica coordination, a consent receipt ledger, and external security assessment remain unimplemented. These are explicit deployment blockers rather than finished features.

SQLite WAL supports single-host, modest write concurrency. For multi-host deployment migrate to PostgreSQL with formal migrations and pooling. Protect the persistent volume with host-level permissions and backups; file-level chmod is not encryption at rest.

## Maintenance

Expired records are not returned by API reads. To reclaim expired records from the database, run:

```
python -m maintenance --cleanup
```

Schedule this CLI through a secure host scheduler or CI job, not an unauthenticated HTTP endpoint. Retention does not remove copies present in external backups; configure backup deletion policies separately.
