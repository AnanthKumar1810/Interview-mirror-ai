import json

import httpx
import pytest

from gnani_semantic import Case, InvalidModelOutput, LocalEvon, ProviderUnavailable, evaluate_paths
from eval_harness.gnani_paths import validate_manifest, summarize
from gnani import GnaniClient, GnaniError


class ScriptedEvon:
    model = "gnani/gnani-evon-v3.3-30B-A3B"

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def ask(self, system, payload):
        self.calls.append(payload)
        return json.dumps(next(self.replies))


def grade(score, verdict, quote):
    return {"score": score, "verdict": verdict, "evidence": [quote], "rationale": "Short reason"}


def test_three_paths_preserve_original_and_abstain_on_disagreement():
    model = ScriptedEvon([grade(3, "uncertain", "తెలుగు"),
                          {"translation": "English technical answer"},
                          grade(8, "correct", "technical")])
    result = evaluate_paths(Case("Question?", "Reference", "తెలుగు answer", "x"), model)
    assert result["transcript"] == "తెలుగు answer"
    assert result["translated"]["evidence_source"] == "translation_only"
    assert result["hybrid"]["status"] == "needs_review"
    assert result["hybrid"]["score"] is None
    assert model.calls[0]["candidate_answer"] == "తెలుగు answer"


def test_direct_mode_makes_one_call_and_does_not_translate():
    model = ScriptedEvon([grade(7, "correct", "answer")])
    result = evaluate_paths(Case("Question", "Reference", "answer"), model,
                            include_translation=False)
    assert len(model.calls) == 1
    assert result["translated"] is None
    assert result["hybrid"]["status"] == "direct"


def test_invalid_quote_rejected():
    model = ScriptedEvon([grade(8, "correct", "invented")])
    with pytest.raises(InvalidModelOutput):
        evaluate_paths(Case("Question", "Reference", "answer"), model)


def test_remote_or_non_gnani_model_rejected():
    with pytest.raises(ProviderUnavailable):
        LocalEvon("https://api.openai.com")
    with pytest.raises(ProviderUnavailable):
        LocalEvon("http://127.0.0.1:8000", model="qwen")


def test_local_transport_posts_published_model_only():
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert body["model"] == "gnani/gnani-evon-v3.3-30B-A3B"
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
    model = LocalEvon("http://127.0.0.1:8000", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert model.ask("system", {"x": 1}) == "{}"


def case(id, split, person, variant):
    return {"id": id, "dataset": "test", "split": split, "person_id": person,
            "variant_group_id": variant, "question": "Q", "reference": "R",
            "transcript": "A", "label_kind": "numeric", "label": 4, "label_max": 5}


def test_split_leakage_rejected():
    with pytest.raises(ValueError, match="leaks"):
        validate_manifest({"cases": [case("a", "development", "p", "v1"),
                                     case("b", "test", "p", "v2")]})
    with pytest.raises(ValueError, match="leaks"):
        validate_manifest({"cases": [case("a", "development", "p1", "v"),
                                     case("b", "test", "p2", "v")]})


def test_fresh_holdout_needs_review_and_consent():
    c = case("a", "test", "p", "v")
    c["dataset"] = "fresh_mixed_holdout"
    with pytest.raises(ValueError, match="Fresh"):
        validate_manifest({"cases": [c]})


def test_native_scale_metrics_separate():
    c = case("a", "test", "p", "v")
    result = {"id": "a", "direct": {"score": 8, "verdict": "correct"},
              "translated": None, "hybrid": {"score": None, "verdict": "uncertain"},
              "timing_ms": {"direct": 10, "translation_plus_score": None,
                            "hybrid_counterfactual": 10}}
    s = summarize([c], [result])["test"]["paths"]
    assert s["direct"]["numeric_mae_by_native_scale"]["5"] == 0
    assert s["hybrid"]["n_abstained"] == 1


def test_prisma_v3_uses_documented_model_and_codemix_fields():
    def handler(request):
        assert request.headers["X-API-Key-ID"] == "test-key"
        body = request.read().decode("utf-8")
        for expected in ("prisma-v3.0", "indic-auto", "codemix", "keyterms"):
            assert expected in body
        assert "bias_score" not in body
        return httpx.Response(200, json={"success": True, "transcript": "test మాట",
                                          "model": "prisma-v3.0", "detected_language_code": "te-IN"})
    client = GnaniClient("test-key", httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.transcribe(b"audio", "indic-auto", ["Python"], model_version="prisma-v3.0")
    assert result["detected_language_code"] == "te-IN"


def test_prisma_truncated_result_never_scored():
    client = GnaniClient("test-key", httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"success": True, "transcript": "partial",
                                                   "truncated": True}))))
    with pytest.raises(GnaniError, match="truncated"):
        client.transcribe(b"audio", "en-IN", model_version="prisma-v3.0")

