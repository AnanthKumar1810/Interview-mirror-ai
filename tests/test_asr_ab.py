import io
import wave

import numpy as np

import eval_harness.asr_ab as asr_ab
from gnani import GnaniError


def _wav_bytes():
    samples = (np.zeros(8000, dtype="<i2")).tobytes()
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(samples)
    return output.getvalue()


def test_live_ab_continues_after_one_provider_no_speech_result(tmp_path, monkeypatch):
    (tmp_path / "clip.wav").write_bytes(_wav_bytes())

    class MockGnaniClient:
        enabled = True

        def __init__(self):
            self.client = self
            self.calls = []

        def transcribe(self, audio, language):
            self.calls.append(language)
            if len(self.calls) == 1:
                raise GnaniError("No speech detected. Please record a clearer, longer answer.")
            return {"transcript": "hello there"}

        def close(self):
            pass

    mock_client = MockGnaniClient()
    monkeypatch.setattr(asr_ab, "GnaniClient", lambda: mock_client)
    manifest = {"cases": [{
        "id": "synthetic-one",
        "path": "clip.wav",
        "language": "en-US",
        "provider_language": "en-IN",
        "reference_transcript": "hello there",
        "consent_for_provider": True,
    }]}

    report = asr_ab.run_live(manifest, tmp_path, max_clips=1)

    assert mock_client.calls == ["en-IN", "en-IN"]
    assert report["provider_calls"] == 2
    assert report["provider_failures"] == 1
    assert report["wer_n_raw"] == 0
    assert report["mean_wer_raw"] is None
    assert report["wer_n_spectral"] == 1
    assert report["mean_wer_spectral"] == 0
    assert report["cases"][0]["errors"]["off"].startswith("No speech detected")
