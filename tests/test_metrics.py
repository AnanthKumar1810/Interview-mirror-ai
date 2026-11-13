import time
import pytest
from metrics import SessionMetrics


def test_session_metrics_defaults():
    m = SessionMetrics()
    assert m.session_start == 0.0
    assert m.speech_end == 0.0
    assert m.provider_processing == 0.0
    assert m.final_transcript == 0.0
    assert m.response_gen_start == 0.0
    assert m.first_tts_audio == 0.0
    assert m.playback_start == 0.0

    assert m.connection_successes == 0
    assert m.connection_failures == 0
    assert m.dropped_frames == 0
    assert m.vad_errors == 0
    assert m.provider_stt_calls == 0
    assert m.provider_tts_calls == 0
    assert m.frames_sent == 0
    assert m.transcripts_received == 0

    assert m.stt_latencies_ms == []
    assert m.tts_latencies_ms == []
    assert m.e2e_latencies_ms == []

    summary = m.summary()
    assert summary["session_duration_s"] == 0.0
    assert summary["connection_successes"] == 0
    assert "stt_latency" not in summary
    assert "tts_latency" not in summary
    assert "e2e_latency" not in summary


def test_counter_increments():
    m = SessionMetrics()

    m.record_connection_success()
    m.record_connection_success()
    assert m.connection_successes == 2

    m.record_connection_failure()
    assert m.connection_failures == 1

    m.record_dropped_frame()
    m.record_dropped_frame()
    m.record_dropped_frame()
    assert m.dropped_frames == 3

    m.record_vad_error()
    assert m.vad_errors == 1

    m.record_stt_call()
    assert m.provider_stt_calls == 1

    m.record_tts_call()
    assert m.provider_tts_calls == 1

    m.record_frame_sent()
    m.record_frame_sent()
    assert m.frames_sent == 2

    m.record_transcript_received()
    assert m.transcripts_received == 1

    s = m.summary()
    assert s["connection_successes"] == 2
    assert s["connection_failures"] == 1
    assert s["dropped_frames"] == 3
    assert s["vad_errors"] == 1
    assert s["provider_stt_calls"] == 1
    assert s["provider_tts_calls"] == 1
    assert s["frames_sent"] == 2
    assert s["transcripts_received"] == 1


def test_timestamp_recording_and_latencies():
    m = SessionMetrics()
    m.mark_session_start()
    assert m.session_start > 0

    m.mark_speech_end()
    assert m.speech_end >= m.session_start

    m.mark_provider_processing()
    assert m.provider_processing >= m.speech_end

    # Advance time artificially to verify calculated delta
    time.sleep(0.01)
    m.mark_final_transcript()
    assert m.final_transcript > m.speech_end
    assert len(m.stt_latencies_ms) == 1
    assert m.stt_latencies_ms[0] >= 10.0

    m.mark_response_gen_start()
    time.sleep(0.01)
    m.mark_first_tts_audio()
    assert m.first_tts_audio > m.response_gen_start
    assert len(m.tts_latencies_ms) == 1
    assert m.tts_latencies_ms[0] >= 10.0

    time.sleep(0.01)
    m.mark_playback_start()
    assert m.playback_start > m.speech_end
    assert len(m.e2e_latencies_ms) == 1
    assert m.e2e_latencies_ms[0] >= 30.0


def test_percentile_calculations_in_summary():
    m = SessionMetrics()
    m.mark_session_start()

    # Supply controlled latency samples
    m.stt_latencies_ms = [100.0, 200.0, 300.0, 400.0, 500.0]
    m.tts_latencies_ms = [50.0, 60.0, 70.0, 80.0, 90.0]
    m.e2e_latencies_ms = [150.0, 260.0, 370.0, 480.0, 590.0]

    s = m.summary()
    assert "stt_latency" in s
    assert "tts_latency" in s
    assert "e2e_latency" in s

    # voice_pipeline.summarize_latency returns samples, p50_ms, p95_ms, max_ms
    stt_summary = s["stt_latency"]
    assert stt_summary["samples"] == 5
    assert "p50_ms" in stt_summary
    assert "p95_ms" in stt_summary
    assert stt_summary["p50_ms"] == 300.0
    assert stt_summary["max_ms"] == 500.0

    tts_summary = s["tts_latency"]
    assert tts_summary["samples"] == 5
    assert tts_summary["p50_ms"] == 70.0

    e2e_summary = s["e2e_latency"]
    assert e2e_summary["samples"] == 5
    assert e2e_summary["p50_ms"] == 370.0
