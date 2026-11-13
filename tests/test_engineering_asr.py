import struct

from eval_harness.engineering_asr import error_counts, normalize, percentile, summarize, wav_duration


def test_indic_normalization_and_script_sensitive_errors():
    assert normalize("  తెలుగు, మాటలు!  ") == "తెలుగు మాటలు"
    assert error_counts("ఫ్రాన్స్ తో", "France తో")["word_edits"] == 1
    assert error_counts("తెలుగు మాటలు", "తెలుగు మాటలు")["char_edits"] == 0


def test_aggregate_uses_word_totals_and_paired_latency():
    cases = []
    for i, words in enumerate((10, 20)):
        cases.append({"language": "hi_in", "duration_s": 2.0,
                      "prisma-v2.5": {"word_edits": 1, "reference_words": words,
                                      "char_edits": 2, "reference_chars": words * 3,
                                      "elapsed_ms": 1000 + i * 100},
                      "prisma-v3.0": {"word_edits": 3, "reference_words": words,
                                      "char_edits": 5, "reference_chars": words * 3,
                                      "elapsed_ms": 800 + i * 100}})
    result = summarize(cases)["languages"]["hi_in"]
    assert result["models"]["prisma-v2.5"]["micro_wer"] == 0.0667
    assert result["models"]["prisma-v3.0"]["micro_wer"] == 0.2
    assert result["paired_clips"] == 2
    assert result["paired_exact_script_wer"] == {"prisma-v2.5": 0.0667,
                                                  "prisma-v3.0": 0.2}
    assert result["v3_minus_v2_latency_p50_ms"] == -200
    assert percentile([1, 3, 5], .5) == 3


def test_ieee_float_wav_duration_without_pcm_decoder():
    fmt = struct.pack("<HHIIHH", 3, 1, 16000, 64000, 4, 32)
    data = bytes(64000)
    wav = (b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(data)) +
           b"WAVEfmt " + struct.pack("<I", len(fmt)) + fmt +
           b"data" + struct.pack("<I", len(data)) + data)
    assert wav_duration(wav) == 1.0


def test_retry_is_reported_separately_from_first_attempt():
    success = {"word_edits": 1, "reference_words": 10,
               "char_edits": 2, "reference_chars": 30, "elapsed_ms": 800}
    cases = [{"language": "te_in", "duration_s": 2.0,
              "prisma-v2.5": {"error": "temporary 504", "elapsed_ms": 5000,
                              "retry": success},
              "prisma-v3.0": success}]
    result = summarize(cases)["languages"]["te_in"]
    assert "paired_clips" not in result
    assert result["post_retry_paired_clips"] == 1
    assert result["post_retry_paired_exact_script_wer"]["prisma-v2.5"] == 0.1

