"""Auth, session isolation, persistence, expiry, optimistic concurrency and logout."""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

import main
from auth_service import AUDIENCE, ISSUER
from storage import SQLiteStore, ConflictError


@pytest.fixture
def authenticated_app(monkeypatch, tmp_path):
    db_file = tmp_path / 'interviewmirror_auth_test.sqlite3'
    monkeypatch.setenv('IM_AUTH_REQUIRED', 'true')
    monkeypatch.setenv('IM_JWT_SECRET', 'test_only_' + 'a' * 48)
    monkeypatch.setattr(main, 'STORE', SQLiteStore(db_file))
    yield TestClient(main.app), db_file


def _headers(token):
    return {'Authorization': 'Bearer ' + token}


def _register(client, email):
    res = client.post('/api/auth/register', json={'email': email, 'password': 'strong test password 123!'})
    assert res.status_code == 201, res.text
    return res.json()['access_token']


def test_auth_and_ownership_enforced_on_all_session_interfaces(authenticated_app):
    client, _ = authenticated_app
    assert client.post('/api/session', json={'track': 'ai'}).status_code == 401
    assert client.post('/api/sessions', json={'track': 'ai'}).status_code == 401
    assert client.post('/api/transcribe').status_code == 401
    a = _register(client, 'a@example.com')
    b = _register(client, 'b@example.com')
    sid = client.post('/api/session', headers=_headers(a),
                      json={'track': 'agentic', 'language': 'en-IN'}).json()['session_id']
    assert client.get(f'/api/sessions/{sid}', headers=_headers(b)).status_code == 404
    assert client.get(f'/api/report/{sid}', headers=_headers(b)).status_code == 404
    assert client.post('/api/answer', headers=_headers(b),
                       json={'session_id': sid, 'text': 'I ran an agent.'}).status_code == 404
    assert client.delete(f'/api/session/{sid}', headers=_headers(b)).status_code == 404
    assert client.post('/api/answer', headers=_headers(a), json={
        'session_id': sid, 'text': 'I used restricted tools and validated changes.'}).status_code == 200
    assert client.get(f'/api/report/{sid}', headers=_headers(a)).json()['answered'] == 1
    assert len(client.get('/api/my/sessions', headers=_headers(a)).json()['sessions']) == 1


def test_sessions_survive_store_reinitialization_and_are_durable(authenticated_app, monkeypatch):
    client, path = authenticated_app
    token = _register(client, 'persist@example.com')
    sid = client.post('/api/session', headers=_headers(token), json={'track':'ai'}).json()['session_id']
    client.post('/api/answer', headers=_headers(token), json={
        'session_id':sid, 'text':'I validated models with held-out test data.'})
    monkeypatch.setattr(main, 'STORE', SQLiteStore(path))  # Reopen like a server restart.
    report = client.get(f'/api/report/{sid}', headers=_headers(token))
    assert report.status_code == 200
    assert report.json()['results'][0]['transcript'].startswith('I validated')
    assert client.delete(f'/api/session/{sid}', headers=_headers(token)).json()['deleted']
    assert client.get(f'/api/report/{sid}', headers=_headers(token)).status_code == 404


def test_login_logout_and_account_deletion(authenticated_app):
    client, _ = authenticated_app
    token = _register(client, 'gone@example.com')
    assert client.post('/api/auth/register', json={
        'email':'gone@example.com','password':'strong test password 123!'}).status_code == 409
    assert client.post('/api/auth/login', json={
        'email':'gone@example.com','password':'wrong password here'}).status_code == 401
    assert client.get('/api/auth/me', headers=_headers(token)).json()['email'] == 'gone@example.com'
    assert client.post('/api/auth/logout', headers=_headers(token)).json()['signed_out']
    assert client.get('/api/auth/me', headers=_headers(token)).status_code == 401
    token2 = client.post('/api/auth/login', json={
        'email':'gone@example.com','password':'strong test password 123!'}).json()['access_token']
    sid = client.post('/api/session', headers=_headers(token2), json={'track':'ai'}).json()['session_id']
    assert client.delete('/api/auth/me', headers=_headers(token2)).json()['deleted']
    assert client.get(f'/api/report/{sid}', headers=_headers(token2)).status_code == 401
    assert client.get('/api/auth/me', headers=_headers(token2)).status_code == 401


def test_expired_and_tampered_tokens(authenticated_app, monkeypatch):
    client, _ = authenticated_app
    token = _register(client, 'expired@example.com')
    assert client.get('/api/auth/me', headers=_headers(token + 'x')).status_code == 401
    claims = jwt.decode(token, 'test_only_' + 'a' * 48, algorithms=['HS256'],
                        issuer=ISSUER, audience=AUDIENCE)
    claims['exp'] = int(time.time()) - 2
    expired = jwt.encode(claims, 'test_only_' + 'a' * 48, algorithm='HS256')
    assert client.get('/api/auth/me', headers=_headers(expired)).status_code == 401


def test_optimistic_concurrency_expiry_and_old_schema_safety(tmp_path):
    db = SQLiteStore(tmp_path / 'test.sqlite3')
    state = asdict(main.Session(track='ai', language='en-IN'))
    db.create_session('session-1', state, None, 300)
    old1, old2 = db.get_session('session-1', None), db.get_session('session-1', None)
    old1['state']['question_index'] = 1
    db.update_session('session-1', None, old1['state'], old1['version'])
    with pytest.raises(ConflictError):
        db.update_session('session-1', None, old2['state'], old2['version'])
    with db.connect() as con:
        con.execute('UPDATE interviews SET expires_at=? WHERE id=?', (int(time.time())-3, 'session-1'))
    assert db.get_session('session-1', None) is None
    assert db.cleanup()['expired_sessions'] == 1


def test_progress_history_is_owned_and_summarizes_saved_answers(authenticated_app):
    client, _ = authenticated_app
    first = _register(client, 'history-first@example.com')
    second = _register(client, 'history-second@example.com')
    sid = client.post('/api/session', headers=_headers(first), json={'track': 'ai'}).json()['session_id']
    assert client.post('/api/answer', headers=_headers(first), json={
        'session_id': sid, 'text': 'I built a model with training data and tested it on a held-out validation set.'
    }).status_code == 200
    own = client.get('/api/my/sessions', headers=_headers(first)).json()['sessions']
    assert own[0]['session_id'] == sid and own[0]['answered'] == 1
    assert isinstance(own[0]['average_score'], int) and not own[0]['completed']
    assert client.get('/api/my/sessions', headers=_headers(second)).json()['sessions'] == []
    assert client.get(f'/api/report/{sid}', headers=_headers(second)).status_code == 404

