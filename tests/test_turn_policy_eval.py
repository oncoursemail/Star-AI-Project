import pytest

from star.voice.turn_policy_eval import Observation, evaluate


def test_empty_report_keeps_unobserved_metrics_null():
    report = evaluate([])
    assert report["samples"] == 0
    assert report["accuracy"] is None
    assert report["macro_f1"] is None
    assert report["decision_timing"]["p95_ms"] is None
    assert report["interruption"]["missed_yield_rate"] is None
    assert report["follow_through"]["rate"] is None
    assert report["addressee"]["accuracy"] is None


def test_perfect_policy_reports_intent_playback_and_follow_through_separately():
    rows = [
        Observation(
            "request", "addressed_request", False, "respond", "respond",
            100, 145, 100, True, True,
        ),
        Observation(
            "interrupt", "addressed_interruption", True, "yield", "yield",
            200, 225, 60, True, True, True,
        ),
        Observation(
            "backchannel", "backchannel", True, "backchannel", "backchannel",
            300, 320, 100, None, None,
        ),
        Observation(
            "side-chat", "side_conversation", True, "ignore", "ignore",
            400, 430, 150, False, False,
        ),
        Observation(
            "handoff", "floor_handoff", True, "yield", "yield",
            500, 520, 80, True, True, True,
        ),
        Observation(
            "uncertain", "uncertain", False, "hold", "hold",
            600, 650, 120, None, None,
        ),
    ]
    report = evaluate(rows)

    assert report["accuracy"] == 1.0
    assert report["macro_f1"] == 1.0
    assert report["by_intent"]["addressed_interruption"]["accuracy"] == 1.0
    assert report["by_playback_state"]["assistant_speaking"]["accuracy"] == 1.0
    assert report["by_playback_state"]["assistant_listening"]["accuracy"] == 1.0
    assert report["interruption"]["missed_yield_rate"] == 0.0
    assert report["interruption"]["false_yield_rate"] == 0.0
    assert report["follow_through"]["rate"] == 1.0
    assert report["addressee"]["accuracy"] == 1.0
    assert report["decision_timing"]["on_time_rate"] == 1.0


def test_false_yields_on_backchannels_and_side_conversations_are_visible():
    rows = [
        Observation("backchannel", "backchannel", True, "backchannel", "yield", 100, 130),
        Observation("side-chat", "side_conversation", True, "ignore", "yield", 200, 240),
        Observation("real-interrupt", "addressed_interruption", True, "yield", "hold", 300, 390),
    ]
    report = evaluate(rows)

    assert report["accuracy"] == 0.0
    assert report["interruption"]["non_takeover_events"] == 2
    assert report["interruption"]["false_yields"] == 2
    assert report["interruption"]["false_yield_rate"] == 1.0
    assert report["interruption"]["missed_yields"] == 1
    assert report["interruption"]["missed_yield_rate"] == 1.0


def test_addressee_errors_are_not_hidden_by_action_accuracy():
    report = evaluate([
        Observation(
            "wrong-target", "addressed_request", False, "respond", "respond",
            100, 140, 100, False, True,
        ),
        Observation(
            "missed-target", "addressed_request", False, "respond", "respond",
            200, 240, 100, True, False,
        ),
    ])
    assert report["accuracy"] == 1.0
    assert report["addressee"]["accuracy"] == 0.0
    assert report["addressee"]["false_target_rate"] == 1.0
    assert report["addressee"]["missed_target_rate"] == 1.0


def test_follow_through_and_missing_reviews_are_reported_separately():
    report = evaluate([
        Observation(
            "completed", "addressed_interruption", True, "yield", "yield",
            100, 120, 50, True, True, True,
        ),
        Observation(
            "failed", "floor_handoff", True, "yield", "yield",
            200, 230, 50, True, True, False,
        ),
        Observation(
            "unreviewed", "addressed_interruption", True, "yield", "yield",
            300, 330, 50, True, True, None,
        ),
    ])
    assert report["accuracy"] == 1.0
    assert report["follow_through"]["correct_yields"] == 3
    assert report["follow_through"]["reviewed"] == 2
    assert report["follow_through"]["completed"] == 1
    assert report["follow_through"]["missing"] == 1
    assert report["follow_through"]["rate"] == 0.5


def test_latency_and_deadline_metrics_do_not_change_action_accuracy():
    report = evaluate([
        Observation("on-time", "addressed_request", False, "respond", "respond", 100, 150, 100),
        Observation("late", "addressed_request", False, "respond", "respond", 200, 450, 100),
        Observation("missing", "addressed_request", False, "respond", "respond", 300, None, 100),
    ])
    assert report["accuracy"] == 1.0
    assert report["decision_timing"]["n"] == 2
    assert report["decision_timing"]["missing_timestamps"] == 1
    assert report["decision_timing"]["p50_ms"] == 50.0
    assert report["decision_timing"]["p95_ms"] == 250.0
    assert report["decision_timing"]["deadline_n"] == 2
    assert report["decision_timing"]["on_time"] == 1
    assert report["decision_timing"]["late"] == 1
    assert report["decision_timing"]["on_time_rate"] == 0.5


@pytest.mark.parametrize("rows", [
    [Observation("", "addressed_request", False, "respond", "respond", 1)],
    [
        Observation("duplicate", "addressed_request", False, "respond", "respond", 1),
        Observation("duplicate", "addressed_request", False, "respond", "respond", 2),
    ],
    [Observation("a", "unknown", False, "respond", "respond", 1)],
    [Observation("a", "addressed_request", 1, "respond", "respond", 1)],
    [Observation("a", "addressed_request", False, "unknown", "respond", 1)],
    [Observation("a", "addressed_request", False, "respond", "unknown", 1)],
    [Observation("a", "addressed_request", False, "respond", "respond", True)],
    [Observation("a", "addressed_request", False, "respond", "respond", 10, 9)],
    [Observation("a", "addressed_request", False, "respond", "respond", 1, deadline_ms=-1)],
    [Observation("a", "addressed_request", False, "respond", "respond", 1, followed_through=True)],
    [Observation("a", "addressed_request", False, "respond", "respond", 1, expected_addressee=1)],
    [Observation("a", "addressed_request", False, "respond", "respond", 1, predicted_addressee=0)],
])
def test_invalid_observations_are_rejected(rows):
    with pytest.raises(ValueError):
        evaluate(rows)


def test_non_observation_rows_are_rejected():
    with pytest.raises(ValueError):
        evaluate([{"sample_id": "not-a-dataclass"}])


def test_generator_input_is_supported():
    rows = (
        Observation(str(index), "uncertain", False, "hold", "hold", index)
        for index in range(3)
    )
    assert evaluate(rows)["samples"] == 3
