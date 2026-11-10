"""Offline end-to-end and adversarial tests for interpretable coaching."""
import pytest
from fastapi.testclient import TestClient

import main
from adaptive import select_followup
from coach import QUESTION_BANK, evaluate
from evaluation import DIMENSION_MAX

client = TestClient(main.app)


def test_scoring_is_bounded_and_does_not_pretend_to_verify_facts():
    q = QUESTION_BANK['agentic'][0]
    short = evaluate('hello everyone', q, 'en-IN', 'agentic', 0)
    relevant = evaluate(
        'I built an agent using tools, and restricted permissions because it can edit repositories. '
        'I tested 5 cases and verified the changes with a Docker validation run.',
        q, 'en-IN', 'agentic', 0)
    assert 0 <= short['score'] < relevant['score'] <= 100
    assert relevant['dimensions'].keys() == DIMENSION_MAX.keys()
    assert sum(relevant['dimensions'].values()) == relevant['score']
    assert all(0 <= relevant['dimensions'][d] <= cap for d, cap in DIMENSION_MAX.items())
    assert relevant['factual_assessment'] == 'not_verified'
    assert 'not proof' in relevant['disclaimer'].lower()
    assert relevant['coverage']


def test_every_quoted_evidence_fragment_is_verbatim_from_answer():
    text = ('I built an agent with tool access, but restricted its permissions because edits can fail. '
            'We ran 5/5 tests before approval.')
    result = evaluate(text, QUESTION_BANK['agentic'][0], 'en-IN', 'agentic', 0)
    assert result['evidence_items']
    for evidence in result['evidence_items']:
        assert evidence['quote'] in text
        assert evidence['dimension'] in DIMENSION_MAX
    for coverage in result['coverage']:
        assert coverage['quote'] is None or coverage['quote'] in text


def test_irrelevant_keyword_stuffing_cannot_gain_full_score():
    text = 'Hello friends. ' * 60
    result = evaluate(text, QUESTION_BANK['agentic'][0], 'en-IN', 'agentic', 0)
    assert result['dimensions']['technical_coverage'] == 0
    assert result['dimensions']['relevance'] == 0
    assert result['score'] < 30


@pytest.mark.parametrize('track', ['ai', 'agentic', 'software'])
@pytest.mark.parametrize('language', ['en-IN', 'te-IN', 'hi-IN'])
def test_every_track_has_localized_adaptive_question(track, language):
    q = QUESTION_BANK[track][0]
    f = evaluate('I learned a lot.', q, language, track, 0)
    next_question, reason, reason_code = select_followup(track, language, f)
    assert reason_code == 'technical'
    assert next_question[language]
    assert reason
    assert len(next_question['concepts']) == 3


def test_question_two_is_contextual_and_question_three_is_broad():
    response = client.post('/api/session', json={'track': 'agentic', 'language': 'en-IN'})
    sid = response.json()['session_id']
    original = response.json()['question']
    weak = client.post('/api/answer', json={'session_id': sid, 'text': 'I built something.'})
    assert weak.status_code == 200
    j = weak.json()
    assert j['next_question_kind'] == 'adaptive'
    assert j['next_question_reason']
    assert 'tool' in j['next_question'].lower()
    assert j['next_question'] != original
    assert j['feedback']['follow_up'] == j['next_question']
    second = client.post('/api/answer', json={
        'session_id': sid,
        'text': 'The agent tool required approval and validation before any restricted edit.'
    })
    j2 = second.json()
    assert j2['next_question_kind'] == 'core'
    assert j2['next_question'] == QUESTION_BANK['agentic'][1]['en-IN']
    assert not j2['completed']
    third = client.post('/api/answer', json={
        'session_id': sid,
        'text': 'I evaluated reliability with benchmark tests and observed one failure, then repaired it.'
    })
    assert third.json()['completed']
    report = client.get(f'/api/report/{sid}').json()
    assert [item['question_kind'] for item in report['results']] == ['core', 'adaptive', 'core']
    assert report['dimension_averages']['relevance'] >= 0
    assert report['dimension_max'] == dict(DIMENSION_MAX)
    assert report['method'] == 'risk_aware_rubric_v3'
    assert isinstance(report['review_priorities'], list)
    assert report['results'][1]['question'] == j['next_question']


def test_strong_answer_gets_tradeoff_adaptive_followup():
    response = client.post('/api/session', json={'track': 'agentic', 'language': 'en-IN'})
    sid = response.json()['session_id']
    answer = ('First I built an agent workflow that calls a file editing tool. '
              'I restricted permissions because a model might change unrelated code. '
              'Then I tested the output and verified 5/5 regression tests, resulting in a clear audit record.')
    next_response = client.post('/api/answer', json={'session_id': sid, 'text': answer}).json()
    assert next_response['feedback']['dimensions']['technical_coverage'] >= 20
    assert next_response['feedback']['dimensions']['evidence'] >= 12
    assert next_response['next_question_kind'] == 'adaptive'
    assert 'alternative' in next_response['next_question'].lower()


def test_telegu_transcript_and_followup_have_correct_locale():
    response = client.post('/api/session', json={'track': 'ai', 'language': 'te-IN'})
    sid = response.json()['session_id']
    answer = client.post('/api/answer', json={'session_id': sid,
        'text': 'నేను మోడల్ రూపొందించాను. డేటా ఉపయోగించి పరీక్ష చేశాను.'})
    assert answer.status_code == 200
    j = answer.json()
    assert 'మీ' in j['next_question']
    assert 'మీ' in j['next_question_reason'] or 'ముందటి' in j['next_question_reason']
    assert j['feedback']['method'] == 'risk_aware_rubric_v3'
