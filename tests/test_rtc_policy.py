import pytest
from fastapi.testclient import TestClient

from rtc_policy import TurnLedger, is_backchannel, turn_mode


def test_language_endpointing_is_explicit():
    assert turn_mode("en-IN") == "multilingual"
    assert turn_mode("hi-IN") == "multilingual"
    assert turn_mode("te-IN") == "vad"
    with pytest.raises(ValueError):
        turn_mode("fr-FR")


def test_short_acknowledgment_is_only_backchannel_during_agent_speech():
    assert is_backchannel("Okay.", True)
    assert is_backchannel("हाँ", True)
    assert is_backchannel("సరే", True)
    assert not is_backchannel("Okay.", False)
    assert not is_backchannel("Okay, but I disagree", True)


def test_duplicate_stale_cancellation_and_cleanup():
    ledger = TurnLedger()
    generation = ledger.start(1, "I built the API")
    assert generation == 1
    assert ledger.start(1, "  i built   the api  ") is None
    assert ledger.advance(generation, 1)
    assert ledger.start(1, "late first turn") is None
    second = ledger.start(2, "I tested the API")
    assert second == 2
    ledger.cancel()
    assert not ledger.valid_audio(second)
    assert not ledger.advance(second, 2)
    ledger.close()
    assert ledger.start(2, "new content") is None


def test_rtc_route_is_off_by_default(monkeypatch):
    monkeypatch.setenv("IM_LIVEKIT_ENABLED", "false")
    from main import app
    response = TestClient(app).post("/api/rtc/session", json={"track": "software", "language": "en-IN"})
    assert response.status_code == 503
    assert "token" not in response.text


def test_official_gnani_adapters_are_configured_without_a_hosted_llm(monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    try:
        from rtc_agent import provider_adapters
    except (ImportError, OSError) as exc:
        pytest.skip(f"Native LiveKit runtime unavailable on this host: {exc}")
    stt, tts = provider_adapters("te-IN")
    assert stt.provider == "Gnani"
    assert tts.provider == "Gnani"
    assert stt._opts.language == "te-IN"
    assert stt._opts.use_streaming is True
    assert tts._opts.model == "timbre-v2.5"
    assert tts._opts.voice == "Suhana"
