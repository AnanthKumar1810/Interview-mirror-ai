import copy
import json
import math

import pytest
from scipy.stats import pearsonr, spearmanr

from eval_harness.agreement import cohen_kappa, paired_score_metrics
from eval_harness.harness import load_dataset, run_evaluation
from eval_harness.workbench import render
from coach import evaluate


def test_correlations_match_scipy_with_tied_scores():
    predicted, reference = [2, 2, 5, 9, 8], [1, 3, 4, 4, 9]
    metrics = paired_score_metrics(predicted, reference)
    assert metrics['pearson'] == pytest.approx(pearsonr(predicted, reference).statistic)
    assert metrics['spearman'] == pytest.approx(spearmanr(predicted, reference).statistic)
    assert metrics['mae'] == pytest.approx(1.8)
    assert metrics['signed_bias'] == pytest.approx(1.0)


def test_high_correlation_does_not_hide_absolute_error():
    metrics = paired_score_metrics([21, 31, 41], [1, 11, 21])
    assert metrics['pearson'] == pytest.approx(1)
    assert metrics['mae'] == 20


@pytest.mark.parametrize('a,b', [([], []), ([1], [2]), ([4,4,4], [1,2,3])])
def test_undefined_correlations_are_null(a,b):
    metrics = paired_score_metrics(a,b)
    assert metrics['pearson'] is None and metrics['spearman'] is None
    json.dumps(metrics, allow_nan=False)


@pytest.mark.parametrize('a,b', [([1],[1,2]), ([math.nan],[1]), ([True],[1]), ([1],[math.inf])])
def test_invalid_score_pairs_fail(a,b):
    with pytest.raises(ValueError):
        paired_score_metrics(a,b)


def test_categorical_kappa_known_cases_and_degeneracy():
    assert cohen_kappa(['yes','no','yes','no'], ['yes','no','no','yes']) == 0
    assert cohen_kappa(['yes','no'], ['yes','no']) == 1
    assert cohen_kappa(['yes','no'], ['no','yes']) == -1
    assert cohen_kappa(['yes','yes'], ['yes','yes']) is None
    assert cohen_kappa([],[]) is None
    with pytest.raises(ValueError):
        cohen_kappa(['yes'],[])


def data():
    original = load_dataset('eval_harness/datasets/practice_review_queue.json')
    return {**original, 'cases': original['cases'][:1]}


def test_harness_has_no_invented_human_agreement():
    report = run_evaluation(data(), repeats=2)
    assert report['summary']['human_score_agreement']['n_pairs'] == 0
    assert report['summary']['human_score_agreement']['mae'] is None
    assert report['summary']['calls_with_evidence'] == 2


def test_harness_rejects_fabricated_quote():
    def wrong(*args):
        result = evaluate(*args)
        result['evidence_items'] = [{'dimension':'relevance', 'quote':'invented quote 927361',
                                     'observation':'Unsupported evidence'}]
        return result
    with pytest.raises(ValueError, match='verbatim'):
        run_evaluation(data(), repeats=2, scorer=wrong)


def test_generic_low_score_has_honest_structural_evidence_without_score_change():
    from coach import QUESTION_BANK
    answer = 'I like technology and want to become a strong developer.'
    result = evaluate(answer, QUESTION_BANK['agentic'][0], 'en-IN', 'agentic', 0)
    assert result['score'] == 2
    assert result['evidence_items']
    assert all(item['quote'] in answer for item in result['evidence_items'])
    assert 'not verified' in result['evidence_items'][0]['observation']


def test_gold_template_does_not_fabricate_reviewer_agreement():
    from pathlib import Path
    from eval_harness.agreement import gold_agreement
    from eval_harness.gold_workflow import load_dataset as load_gold
    report = gold_agreement(load_gold(Path('eval_harness/datasets/gold_holdout_template.json')))
    assert report['status'] == 'unmeasured'
    assert report['reviewer_pairs'] == []


def test_gold_agreement_keeps_distinct_reviewer_pairs_separate():
    from eval_harness.agreement import gold_agreement
    from eval_harness.gold_evaluation import ReviewerRating
    from test_gold_workflow import sample_dataset, rating
    dataset = sample_dataset()
    first = dataset.cases[0]
    first.reviewers = [ReviewerRating(reviewer_id=r, **rating(r)) for r in ['a','b']]
    second = copy.deepcopy(first)
    second.case_id = 'case_002'
    second.reviewers = [ReviewerRating(reviewer_id=r, **rating(r)) for r in ['a','c']]
    dataset.cases.append(second)
    result = gold_agreement(dataset)
    assert [pair['reviewer_ids'] for pair in result['reviewer_pairs']] == [['a','b'],['a','c']]
    assert all(pair['scores']['n_pairs'] == 1 for pair in result['reviewer_pairs'])
    assert result['gold_examples_count'] == 0


def test_cli_requires_evidence_when_requested(monkeypatch, tmp_path):
    import sys
    from eval_harness import run
    from eval_harness import ollama_judge
    from evaluation import DIMENSION_MAX
    monkeypatch.setattr(ollama_judge, 'ollama_score', lambda *args: {
        'dimensions':dict.fromkeys(DIMENSION_MAX,0), 'score':0})
    output = tmp_path/'report.json'
    monkeypatch.setattr(sys,'argv',['run','--scorer','ollama','--require-evidence',
                                   '--repeats','2','--output',str(output)])
    assert run.main() == 1
    assert json.loads(output.read_text())['gate']['passed'] is False


def test_cli_rejects_nonfinite_gate_before_scoring(monkeypatch, tmp_path):
    import sys
    from eval_harness import run
    monkeypatch.setattr(run, 'run_evaluation', lambda *args: pytest.fail('must not score'))
    output=tmp_path/'must-not-exist.json'
    monkeypatch.setattr(sys,'argv',['run','--max-human-mae','nan','--output',str(output)])
    with pytest.raises(SystemExit) as exc:
        run.main()
    assert exc.value.code == 2
    assert not output.exists()


def test_workbench_escapes_model_and_candidate_text():
    report = run_evaluation(data(), repeats=2)
    report['cases'][0]['evidence_by_repeat'][0][0]['quote'] = '<script>alert(1)</script>'
    html = render(report)
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert 'Null human metrics mean unmeasured' in html
