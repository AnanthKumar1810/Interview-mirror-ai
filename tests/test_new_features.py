"""Focused offline checks for the provider request and persisted history."""
import httpx

from gnani import GnaniClient
from storage import SQLiteStore


def test_prisma_v25_boosting_request_contract():
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={'success': True, 'transcript': 'I tested precision.'})
    client = GnaniClient(api_key='offline-test', client=httpx.Client(transport=httpx.MockTransport(handle)))
    result = client.transcribe(b'fixture-wav', 'en-IN', ['precision', 'LangGraph', 'two words', 'GPT-4', 'precision'])
    assert result['transcript'] == 'I tested precision.'
    body = requests[0].content
    assert b'name="bias_list"' in body and b'name="bias_score"' in body
    assert b'precision' in body and b'LangGraph' in body
    assert b'two words' not in body and b'GPT-4' not in body
    assert b'1.0' in body


def test_saved_progress_stays_owned_after_reopening_database(tmp_path):
    path = tmp_path / 'practice.sqlite3'
    store = SQLiteStore(path)
    first = store.create_user('first@example.com', 'hashed')
    second = store.create_user('second@example.com', 'hashed')
    state = {'track':'ai', 'language':'en-IN', 'created':'2026-11-10T00:00:00Z',
             'answers':[{'feedback':{'score':62}}]}
    store.create_session('one', state, first, 300)
    reopened = SQLiteStore(path)
    history = reopened.recent_sessions(first)
    assert history[0]['average_score'] == 62
    assert history[0]['answered'] == 1 and history[0]['completed'] is False
    assert reopened.recent_sessions(second) == []
    assert reopened.get_session('one', second) is None
