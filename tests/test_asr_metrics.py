from eval_harness.asr_ab import word_error_rate, normalized_words, edit_distance
import pytest


def test_wer_exact_and_deletions():
    assert word_error_rate('I built a model', 'I built a model') == 0.0
    assert word_error_rate('I built a model', 'I built model') == 0.25
    assert word_error_rate('I built a model', 'I built a different model') == 0.25
    assert edit_distance(['a','b'], ['c','d']) == 2


def test_telugu_words_remain_whole_with_combining_marks():
    reference = 'నేను మోడల్ తయారు చేశాను.'
    assert normalized_words(reference) == ['నేను', 'మోడల్', 'తయారు', 'చేశాను']
    assert word_error_rate(reference, 'నేను మోడల్ చేశాను') == 0.25


def test_empty_reference_fails_closed():
    with pytest.raises(ValueError):
        word_error_rate('', 'some transcript')
