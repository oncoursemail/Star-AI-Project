"""Latency arithmetic and report formatting independently of live voice calls."""
import pytest

from star.voice.metrics import TurnMetrics, latency_summary, latency_table


def test_empty_turn_has_unknown_stage_latencies_and_empty_table():
    stages = TurnMetrics().stages()
    assert all(value is None for value in stages.values())
    assert TurnMetrics().to_dict()["stages"] == stages
    table = latency_table([])
    assert "TOTAL" in table
    assert "mean" not in table


def test_stages_use_clock_differences_and_generated_token_count():
    m = TurnMetrics(
        turn=1, speech_end=1.0, turn_end=1.25, transcript_at=1.40,
        first_token_at=1.65, first_sentence_at=1.7, first_audio_at=1.9,
        last_token_at=2.65, tokens=11,
    )
    stages = m.stages()
    assert stages["endpoint"] == pytest.approx(0.25)
    assert stages["asr"] == pytest.approx(0.15)
    assert stages["speech_end_to_transcript"] == pytest.approx(0.40)
    assert stages["transcript_to_first_token"] == pytest.approx(0.25)
    assert stages["first_token_to_first_audio"] == pytest.approx(0.25)
    assert stages["total"] == pytest.approx(0.90)
    assert stages["tokens_per_second"] == pytest.approx(10.0)


def test_negative_clock_differences_are_clamped_and_zero_generation_has_no_rate():
    m = TurnMetrics(
        speech_end=2.0, turn_end=1.0, transcript_at=0.5,
        first_token_at=0.0, first_audio_at=-1.0, last_token_at=0.0, tokens=15,
    )
    assert all(value == 0.0 for key, value in m.stages().items() if key != "tokens_per_second")
    assert m.stages()["tokens_per_second"] is None
    m.first_token_at, m.last_token_at, m.tokens = 1.0, 3.0, 2
    assert m.stages()["tokens_per_second"] is None
    m.tokens = 3
    assert m.stages()["tokens_per_second"] == pytest.approx(1.0)


def test_to_dict_retains_fields_and_rounds_only_stage_values():
    m = TurnMetrics(turn=3, user_text="hello", speech_end=0.0, turn_end=0.333333,
                    first_audio_at=1.987654, error="asr unavailable")
    result = m.to_dict()
    assert result["turn"] == 3
    assert result["user_text"] == "hello"
    assert result["turn_end"] == 0.333333
    assert result["stages"]["endpoint"] == 0.333
    assert result["stages"]["total"] == 1.988
    assert result["error"] == "asr unavailable"


def test_latency_table_only_averages_complete_turns_and_reports_failure_reasons():
    first = TurnMetrics(
        turn=1, speech_end=0.0, turn_end=0.2, transcript_at=0.3,
        first_token_at=0.5, first_audio_at=1.0, last_token_at=0.9,
        tokens=6, end_reason="model", asr_speculative=True,
    )
    second = TurnMetrics(
        turn=2, speech_end=0.0, turn_end=0.4, transcript_at=0.8,
        first_token_at=1.2, first_audio_at=2.0, last_token_at=1.8,
        tokens=4, interrupted=True, heard_seconds=0.75, interrupt_reason="barge_in",
    )
    failed = TurnMetrics(turn=3, error="E" * 100)
    table = latency_table([first, second, failed])
    assert "end=model" in table
    assert "early transcript" in table
    assert "interrupted after 0.8s (barge_in)" in table
    assert "ERROR " + "E" * 60 in table
    assert "E" * 61 not in table
    mean = table.splitlines()[-1].split()
    assert mean[0] == "mean"
    assert "1.50" in mean  # Average of complete turns: (1.0 + 2.0) / 2.


def test_latencies_do_not_silently_accept_non_numeric_timestamps():
    with pytest.raises(TypeError):
        TurnMetrics(speech_end=0.0, first_audio_at="invalid").stages()


def test_latency_summary_reports_p99_and_does_not_return_transcript_text():
    turns = [
        TurnMetrics(
            turn=i + 1, user_text="private prompt", reply_text="private reply",
            speech_end=0.0, turn_end=0.0002, transcript_at=0.0003,
            first_token_at=0.0005, first_sentence_at=0.00075,
            first_ack_at=0.0004, first_audio_at=(i + 1) / 1000,
        )
        for i in range(1000)
    ]
    summary = latency_summary(turns)
    total = summary["latency"]["speech_end_to_audio_submitted"]
    assert total == {
        "n": 1000, "mean_ms": 500.5, "p50_ms": 500.0, "p95_ms": 950.0,
        "p99_ms": 990.0, "max_ms": 1000.0,
        "p95_sample_ready": True, "p99_sample_ready": True,
    }
    perceived = summary["latency"]["speech_end_to_first_response_submitted"]
    assert perceived["p50_ms"] == 0.4
    assert summary["sample_guidance"] == {"p95_min_samples": 100, "p99_min_samples": 1000}
    assert "private prompt" not in repr(summary)
    assert "private reply" not in repr(summary)


def test_latency_summary_marks_small_tail_samples_as_descriptive_only():
    turns = [
        TurnMetrics(speech_end=0.0, first_audio_at=(i + 1) / 1000)
        for i in range(100)
    ]
    total = latency_summary(turns)["latency"]["speech_end_to_audio_submitted"]
    assert total["n"] == 100
    assert total["p95_ms"] == 95.0
    assert total["p95_sample_ready"] is True
    assert total["p99_ms"] is None
    assert total["p99_sample_ready"] is False


def test_latency_summary_keeps_partial_stage_samples_and_counts_incomplete_turns():
    turn = TurnMetrics(
        speech_end=0.0, turn_end=0.1, transcript_at=0.2,
        first_ack_at=0.15,
    )
    summary = latency_summary([turn])
    assert summary["incomplete_turns"] == 1
    assert summary["latency"]["endpointer"]["n"] == 1
    assert summary["latency"]["speech_end_to_first_response_submitted"]["p50_ms"] == 150.0
    assert summary["latency"]["speech_end_to_audio_submitted"]["n"] == 0


def test_latency_summary_rejects_nonfinite_clock_values():
    turn = TurnMetrics(speech_end=0.0, first_audio_at=float("nan"))
    summary = latency_summary([turn])
    assert summary["invalid_clock_turns"] == 1
    assert summary["latency"]["speech_end_to_audio_submitted"]["n"] == 0
