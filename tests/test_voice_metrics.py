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


def test_latency_summary_reports_nearest_rank_tails_and_keeps_incomplete_turns_visible():
    turns = [
        TurnMetrics(turn=1, speech_end=0.0, turn_end=0.1, transcript_at=0.2,
                    first_token_at=0.3, first_audio_at=0.5, last_token_at=0.4, tokens=3),
        TurnMetrics(turn=2, speech_end=0.0, turn_end=0.2, transcript_at=0.3,
                    first_token_at=0.5, first_audio_at=1.0, last_token_at=0.9, tokens=5,
                    interrupted=True, interrupt_reason="barge_in"),
        TurnMetrics(turn=3, speech_end=0.0, turn_end=0.4, transcript_at=0.8,
                    first_token_at=1.2, first_audio_at=2.0, last_token_at=1.8, tokens=4,
                    error="tts unavailable"),
        TurnMetrics(turn=4, error="no transcript"),
    ]
    report = latency_summary(turns)
    assert report["turns"] == 4
    assert report["complete_turns"] == 3
    assert report["interrupted_turns"] == 1
    assert report["error_turns"] == 2
    assert report["interruption_rate"] == 0.25
    assert report["error_rate"] == 0.5
    assert report["percentile_method"] == "nearest_rank"
    assert report["stages"]["total"] == {
        "count": 3, "p50": 1.0, "p95": 2.0, "p99": 2.0,
    }
    assert report["stages"]["total"]["count"] == 3
    assert report["tail_guidance"] == {
        "p95_min_samples": 20, "p99_min_samples": 100, "release_gate": False,
    }


def test_latency_summary_returns_unknown_percentiles_for_empty_or_missing_samples():
    report = latency_summary([])
    assert report["turns"] == 0
    assert report["complete_turns"] == 0
    assert report["interruption_rate"] is None
    assert report["stages"]["total"] == {
        "count": 0, "p50": None, "p95": None, "p99": None,
    }
    incomplete = latency_summary([TurnMetrics(turn=1)])
    assert incomplete["turns"] == 1
    assert incomplete["stages"]["total"]["count"] == 0


def test_latency_summary_rejects_untyped_records():
    with pytest.raises(TypeError):
        latency_summary([{"total": 1.0}])
