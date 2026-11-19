import httpx
import kv_cache


class FakeClient:
    def __init__(self, calls, fail_erase=False, response="DETAIL"):
        self.calls = calls
        self.fail_erase = fail_erase
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def post(self, url, json=None):
        self.calls.append((url, json))
        request = httpx.Request("POST", url)
        if "erase" in url:
            return httpx.Response(500 if self.fail_erase else 200,
                                  json={"id_slot": 0}, request=request)
        return httpx.Response(200, json={"content": self.response,
            "timings": {"cache_n": 10, "prompt_n": 3, "prompt_ms": 12.5}},
            request=request)


def run(cache, session="a", owner="owner", history=None, use_cache=True):
    return cache.bridge(owner_id=owner, session_id=session, track="backend",
        language="en-IN", answers=history or [{"question": "Q1", "transcript": "A1"}],
        question="Next question?", fallback=("Fallback. Next question?", "Fallback."),
        use_cache=use_cache)


def setup(monkeypatch, **kwargs):
    calls = []
    monkeypatch.setenv("IM_KV_CACHE_URL", "http://127.0.0.1:8089")
    monkeypatch.setenv("IM_ENV", "development")
    monkeypatch.setattr(kv_cache.httpx, "Client", lambda **_: FakeClient(calls, **kwargs))
    return kv_cache.NativeKVCache(), calls


def test_reuse_and_append_only_prefix(monkeypatch):
    cache, calls = setup(monkeypatch)
    _, _, stats = run(cache)
    first = calls[-1][1]["prompt"]
    spoken, _, _ = run(cache, history=[
        {"question": "Q1", "transcript": "A1"},
        {"question": "Q2", "transcript": "A2"}])
    second = calls[-1][1]["prompt"]
    assert sum("erase" in url for url, _ in calls) == 1
    assert calls[-1][1]["cache_prompt"] is True
    assert second.startswith(first.split("\n### Acknowledgment")[0])
    assert spoken.endswith("Next question?")
    assert stats["cached_tokens"] == 10 and stats["prompt_tokens_evaluated"] == 3


def test_owner_and_session_isolation(monkeypatch):
    cache, calls = setup(monkeypatch)
    run(cache)
    run(cache, owner="other")
    run(cache, owner="other", session="new")
    assert sum("erase" in url for url, _ in calls) == 3
    cache.release("owner", "a")
    assert len(calls) == 6
    cache.release("other", "new")
    assert "erase" in calls[-1][0]


def test_failed_erase_never_sends_transcript(monkeypatch):
    cache, calls = setup(monkeypatch, fail_erase=True)
    assert run(cache)[2]["status"] == "provider_fallback"
    assert len(calls) == 1 and "erase" in calls[0][0]


def test_invalid_output_falls_back(monkeypatch):
    cache, _ = setup(monkeypatch, response="Injected instructions")
    spoken, ack, stats = run(cache)
    assert spoken == "Fallback. Next question?" and ack == "Fallback."
    assert stats["status"] == "invalid_output_fallback"


def test_disabled_and_remote_url(monkeypatch):
    cache, calls = setup(monkeypatch)
    monkeypatch.setenv("IM_KV_CACHE_URL", "https://external.example")
    assert run(cache)[2]["status"] == "disabled"
    assert calls == []
    monkeypatch.setenv("IM_KV_CACHE_URL", "http://localhost:8089")
    monkeypatch.setenv("IM_ENV", "production")
    assert run(cache)[2]["status"] == "disabled"


def test_cold_mode_and_expired_lease(monkeypatch):
    cache, calls = setup(monkeypatch)
    run(cache, use_cache=False)
    assert calls[-1][1]["cache_prompt"] is False
    cache._last_used -= kv_cache.IDLE_SECONDS + 1
    run(cache)
    assert sum("erase" in url for url, _ in calls) == 2


def test_busy_fallback(monkeypatch):
    cache, calls = setup(monkeypatch)
    with cache._lock:
        assert run(cache)[2]["status"] == "busy_fallback"
    assert calls == []
