import pytest

from star.eot_bench_adapter import (
    adapt_eot_bench_predictions,
    evaluate_eot_bench_policy,
    sweep_eot_bench_policies,
)
from star.stream_turntaking_eval import ScoreSource, TurnPolicy


def span_row(row_id, span_index, label, start, duration, *, cohort="general"):
    return {
        "id": row_id,
        "language": "en",
        "span_index": span_index,
        "label": label,
        "start": start,
        "end": start + duration,
        "duration": duration,
        "cohort": cohort,
    }


def prediction(row_id, span_index, label, start, silence, score):
    return {
        "id": row_id,
        "language": "en",
        "span_index": span_index,
        "label": label,
        "timestamp": start + silence,
        "silence_dur": silence,
        "p_eot": score,
    }


def test_short_turn_without_eot_is_preserved_as_censored_hold_evidence():
    spans = [
        span_row("turn-secret-1", 0, "hold", 0.1, 0.5),
        span_row("turn-secret-1", 1, "eot", 0.8, 0.6),
        span_row("turn-secret-2", 0, "hold", 0.1, 0.5, cohort="short_turns"),
    ]
    predictions = [
        prediction("turn-secret-1", 0, "hold", 0.1, 0.25, 0.9),
        prediction("turn-secret-1", 1, "eot", 0.8, 0.3, 0.85),
        prediction("turn-secret-2", 0, "hold", 0.1, 0.25, 0.9),
    ]

    adapted = adapt_eot_bench_predictions(spans, predictions)
    result = evaluate_eot_bench_policy(
        adapted, TurnPolicy(threshold=0.8, action_delay_ms=200, timeout_ms=1000)
    )

    assert adapted.source_turn_count == 2
    assert adapted.retained_turn_count == 2
    assert adapted.censored_turn_count == 1
    assert adapted.retained_hold_span_count == 2
    assert adapted.retained_eot_span_count == 1
    assert result.turn_count == 2
    assert result.censored_turn_count == 1
    assert result.hold_pause_count == 2
    assert result.false_cutoffs == 2
    assert result.final_turn_count == 1
    assert result.detected_final_turns == 1
    assert result.missed_final_turns == 0
    assert result.p50_observed_latency_ms == 300
    assert "turn-secret" not in repr(adapted)


def test_default_hold_duration_filter_matches_eot_bench_policy_metrics():
    spans = [
        span_row("turn-1", 0, "hold", 0.0, 0.1),
        span_row("turn-1", 1, "eot", 0.2, 0.3),
        span_row("turn-2", 0, "hold", 0.0, 6.0),
        span_row("turn-3", 0, "hold", 0.0, 0.5),
    ]
    predictions = [
        prediction("turn-1", 0, "hold", 0.0, 0.05, 0.99),
        prediction("turn-1", 1, "eot", 0.2, 0.1, 0.9),
        prediction("turn-2", 0, "hold", 0.0, 1.0, 0.99),
        prediction("turn-3", 0, "hold", 0.0, 0.25, 0.9),
    ]

    adapted = adapt_eot_bench_predictions(spans, predictions)

    assert adapted.source_turn_count == 3
    assert adapted.source_span_count == 4
    assert adapted.excluded_hold_span_count == 2
    assert adapted.retained_span_count == 2
    assert adapted.retained_turn_count == 2
    assert adapted.retained_hold_span_count == 1
    assert adapted.retained_eot_span_count == 1
    assert adapted.censored_turn_count == 1
    assert adapted.prediction_row_count == 4
    assert adapted.score_point_count == 2


def test_missing_prediction_scores_are_counted_not_fabricated():
    spans = [
        span_row("turn-1", 0, "hold", 0.0, 0.5),
        span_row("turn-1", 1, "eot", 0.8, 0.5),
    ]
    predictions = [
        prediction("turn-1", 0, "hold", 0.0, 0.25, float("nan")),
    ]
    adapted = adapt_eot_bench_predictions(spans, predictions)

    assert adapted.score_point_count == 0
    assert adapted.missing_score_span_count == 2
    result = evaluate_eot_bench_policy(
        adapted, TurnPolicy(threshold=0.9, action_delay_ms=200, timeout_ms=400)
    )
    assert result.detected_final_turns == 1
    assert result.p50_observed_latency_ms == 400


def test_sweep_includes_silence_baseline_and_censored_turns():
    spans = [
        span_row("turn-1", 0, "hold", 0.0, 0.5),
        span_row("turn-1", 1, "eot", 0.8, 0.5),
        span_row("turn-2", 0, "hold", 0.0, 0.5, cohort="short_turns"),
    ]
    predictions = [
        prediction("turn-1", 0, "hold", 0.0, 0.25, 0.9),
        prediction("turn-1", 1, "eot", 0.8, 0.3, 0.9),
        prediction("turn-2", 0, "hold", 0.0, 0.25, 0.9),
    ]
    adapted = adapt_eot_bench_predictions(spans, predictions)
    result = sweep_eot_bench_policies(
        adapted,
        thresholds=(0.5, 0.9),
        action_delays_ms=(100, 300),
        timeouts_ms=(800,),
    )

    assert len(result.evaluations) == 6
    assert any(item.score_source is ScoreSource.SILENCE_ONLY for item in result.evaluations)
    assert all(item.censored_turn_count == 1 for item in result.evaluations)


def test_all_censored_rows_cannot_claim_endpoint_latency():
    spans = [span_row("turn-1", 0, "hold", 0.0, 0.5)]
    predictions = [prediction("turn-1", 0, "hold", 0.0, 0.25, 0.9)]
    adapted = adapt_eot_bench_predictions(spans, predictions)

    with pytest.raises(ValueError, match="both hold pauses and final turns"):
        evaluate_eot_bench_policy(
            adapted, TurnPolicy(threshold=0.8, action_delay_ms=100, timeout_ms=500)
        )


def test_missing_cohort_is_normalized_to_general():
    row = span_row("turn-1", 0, "hold", 0.0, 0.5)
    row["cohort"] = float("nan")
    final = span_row("turn-1", 1, "eot", 0.8, 0.5)
    final["cohort"] = None
    adapted = adapt_eot_bench_predictions([row, final], [])
    assert adapted.cohort_count == 1


def test_unknown_prediction_span_is_rejected():
    spans = [span_row("turn-1", 0, "hold", 0.0, 0.5)]
    predictions = [prediction("turn-2", 0, "hold", 0.0, 0.25, 0.9)]
    with pytest.raises(ValueError, match="unknown span"):
        adapt_eot_bench_predictions(spans, predictions)


def test_prediction_label_and_language_must_match_span():
    spans = [span_row("turn-1", 0, "hold", 0.0, 0.5)]
    wrong_label = prediction("turn-1", 0, "eot", 0.0, 0.25, 0.9)
    with pytest.raises(ValueError, match="label does not match"):
        adapt_eot_bench_predictions(spans, [wrong_label])

    wrong_language = prediction("turn-1", 0, "hold", 0.0, 0.25, 0.9)
    wrong_language["language"] = "ja"
    with pytest.raises(ValueError, match="language does not match"):
        adapt_eot_bench_predictions(spans, [wrong_language])


def test_duplicate_span_rows_and_duplicate_prediction_times_are_rejected():
    row = span_row("turn-1", 0, "hold", 0.0, 0.5)
    with pytest.raises(ValueError, match="duplicate span-set"):
        adapt_eot_bench_predictions([row, dict(row)], [])

    predictions = [
        prediction("turn-1", 0, "hold", 0.0, 0.25, 0.7),
        prediction("turn-1", 0, "hold", 0.0, 0.25, 0.8),
    ]
    with pytest.raises(ValueError, match="duplicate prediction time"):
        adapt_eot_bench_predictions([row], predictions)


def test_prediction_timestamps_must_be_causal_and_aligned():
    spans = [span_row("turn-1", 0, "hold", 0.2, 0.5)]
    bad = prediction("turn-1", 0, "hold", 0.2, 0.25, 0.9)
    bad["timestamp"] = 0.8
    with pytest.raises(ValueError, match="not aligned"):
        adapt_eot_bench_predictions(spans, [bad])


@pytest.mark.parametrize("score", [True, -0.1, 1.1, float("inf"), "0.5"])
def test_invalid_eot_scores_are_rejected(score):
    spans = [span_row("turn-1", 0, "hold", 0.0, 0.5)]
    with pytest.raises(ValueError, match="p_eot"):
        adapt_eot_bench_predictions(
            spans, [prediction("turn-1", 0, "hold", 0.0, 0.25, score)]
        )


@pytest.mark.parametrize("duration", [0.0, -0.1, 121.0, float("nan")])
def test_invalid_span_durations_are_rejected(duration):
    spans = [span_row("turn-1", 0, "hold", 0.0, duration)]
    with pytest.raises(ValueError):
        adapt_eot_bench_predictions(spans, [])


def test_empty_or_unbounded_inputs_are_rejected():
    with pytest.raises(ValueError, match="must not be empty"):
        adapt_eot_bench_predictions([], [])
    with pytest.raises(ValueError, match="hold-span duration limits"):
        adapt_eot_bench_predictions(
            [span_row("turn-1", 0, "hold", 0.0, 0.5)], [],
            min_hold_span_duration_ms=5_001,
            max_hold_span_duration_ms=5_000,
        )
