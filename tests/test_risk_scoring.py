"""Risk-aware scoring must handle synthetic adversarial cases without claiming human accuracy."""
from coach import QUESTION_BANK, evaluate
from robust_evaluation import evaluate_robust
from eval_harness.compare_robust import comparison
from eval_harness.harness import load_dataset


def test_known_synthetic_risks_downgraded_and_technical_answers_preserved():
    data = load_dataset('eval_harness/datasets/practice_review_queue.json')
    items = {item['id']: item for item in data['cases']}
    for risk_id in ('agentic_en_keyword_stuffing', 'ai_en_false_claim'):
        c = items[risk_id]; q = QUESTION_BANK[c['track']][c['question_index']]
        old = evaluate(c['answer'], q, c['language'], c['track'], c['question_index'])
        new = evaluate_robust(c['answer'], q, c['language'], c['track'], c['question_index'])
        assert new['score'] < old['score']
        assert new['risk_flags']
        assert all(f['quote'] in c['answer'] for f in new['risk_flags'])
        assert sum(new['dimensions'].values()) == new['score']
    for good_id in ('agentic_en_strong', 'agentic_te_terms', 'ai_en_measurement'):
        c = items[good_id]; q = QUESTION_BANK[c['track']][c['question_index']]
        old = evaluate(c['answer'], q, c['language'], c['track'], c['question_index'])
        new = evaluate_robust(c['answer'], q, c['language'], c['track'], c['question_index'])
        assert new['score'] == old['score']
        assert not new['risk_flags']


def test_llm_signal_must_quote_exact_candidate_words():
    q = QUESTION_BANK['ai'][1]
    answer = 'I measured accuracy using a held-out set and investigated precision.'
    forged = evaluate_robust(answer, q, 'en-IN', 'ai', 1,
                             semantic_judge=lambda *args: {'verdict': 'contradicted', 'quote': 'NEVER SAID THIS', 'reason': 'bad'})
    assert forged['semantic_signal'] is None
    assert not any(f['code'] == 'model_flagged_possible_contradiction' for f in forged['risk_flags'])
    grounded = evaluate_robust(answer, q, 'en-IN', 'ai', 1,
                               semantic_judge=lambda *args: {'verdict': 'contradicted', 'quote': 'precision', 'reason': 'needs review'})
    assert grounded['semantic_signal']['quote'] == 'precision'
    assert grounded['score'] <= forged['score']
    assert grounded['factual_assessment'] == 'model_assessed_not_verified'
    assert grounded['human_review_recommended']


def test_dataset_has_no_human_accuracy_claim_and_synthetic_gate_passes():
    data = load_dataset('eval_harness/datasets/practice_review_queue.json')
    output = comparison(data)
    assert output['n_human_reviewed'] == 0
    assert output['human_mae'] is None
    assert output['synthetic_risk_probes']['baseline_high_scores'] == 1
    assert output['synthetic_risk_probes']['improved_high_scores'] == 0
    assert output['gate']['passed']


def test_basic_technical_misconception_is_flagged_without_claiming_verified_facts():
    q = QUESTION_BANK['ai'][1]
    answer = 'Precision is TP/(TP+FN), and I used my test set to train the model.'
    result = evaluate_robust(answer, q, 'en-IN', 'ai', 1)
    codes = {x['code'] for x in result['risk_flags']}
    assert 'known_metric_confusion' in codes
    assert 'data_leakage_claim' in codes
    assert result['factual_assessment'] == 'not_verified'


def test_unique_word_salad_cannot_earn_a_strong_practice_score():
    q = QUESTION_BANK['ai'][0]
    answer = ('First project model dataset training accuracy validation feature selection '
              'baseline pipeline deployment monitoring evaluation inference improved measured '
              '92 percent results compared tested reviewed final')
    result = evaluate_robust(answer, q, 'en-IN', 'ai', 0)
    assert result['score'] < 60
    assert any(flag['code'] == 'disconnected_keyword_list' for flag in result['risk_flags'])
    assert all(flag['quote'] in answer for flag in result['risk_flags'])


def test_coherent_explanation_is_not_flagged_as_keyword_list():
    q = QUESTION_BANK['ai'][0]
    answer = ('I trained a baseline model on a cleaned dataset because the original labels were noisy. '
              'Then I compared validation accuracy across three runs, documented the result, and checked '
              'whether the improvement held on unseen samples.')
    result = evaluate_robust(answer, q, 'en-IN', 'ai', 0)
    assert not any(flag['code'] == 'disconnected_keyword_list' for flag in result['risk_flags'])

