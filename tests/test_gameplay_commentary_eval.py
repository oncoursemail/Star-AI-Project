import pytest

from star import gameplay_commentary_eval
from star.gameplay_commentary_eval import Observation, evaluate


def test_empty_and_perfect_results_keep_missing_metrics_null():
    empty = evaluate([])
    assert empty["samples"] == 0
    assert empty["accuracy"] is None
    assert empty["speech_timing"]["p95_ms"] is None
    assert empty["negative_controls"]["false_speech_rate"] is None

    rows = [
        Observation("a", "comment", "comment", 100, 140, 100, False, True),
        Observation("b", "acknowledge", "acknowledge", 200, 250, 100, False, True),
        Observation("c", "silence", "silence", 300, None, None, True, None),
        Observation("d", "yield", "yield", 400, 420, None, False, None),
    ]
    report = evaluate(rows)
    assert report["accuracy"] == 1.0
    assert report["macro_f1"] == 1.0
    assert report["negative_controls"]["false_speech_rate"] == 0.0
    assert report["speech_grounding"]["rate"] == 1.0
    assert report["speech_timing"]["p50_ms"] == 40.0
    assert report["speech_timing"]["p95_ms"] == 50.0
    assert report["speech_timing"]["on_time_rate"] == 1.0


def test_negative_controls_expose_false_commentary_and_silence_misses():
    rows = [
        Observation("a", "silence", "comment", 100, 160, None, True, False),
        Observation("b", "comment", "silence", 200, None, None, False, None),
        Observation("c", "silence", "silence", 300, None, None, True, None),
    ]
    report = evaluate(rows)
    assert report["negative_controls"]["count"] == 2
    assert report["negative_controls"]["false_speech"] == 1
    assert report["negative_controls"]["false_speech_rate"] == 0.5
    assert report["silence"]["precision"] == 0.5
    assert report["silence"]["recall"] == 0.5
    assert report["actions"]["comment"]["f1"] == 0.0


def test_late_correct_speech_is_separate_from_action_accuracy():
    report = evaluate([
        Observation("on-time", "comment", "comment", 100, 180, 100),
        Observation("late", "comment", "comment", 200, 450, 100),
    ])
    assert report["accuracy"] == 1.0
    assert report["speech_timing"]["deadline_n"] == 2
    assert report["speech_timing"]["on_time"] == 1
    assert report["speech_timing"]["late"] == 1
    assert report["speech_timing"]["on_time_rate"] == 0.5


def test_missing_timestamps_and_unreviewed_grounding_are_not_imputed():
    report = evaluate([
        Observation("a", "comment", "comment", 100, None, 50, False, None),
    ])
    assert report["speech_timing"]["missing_timestamps"] == 1
    assert report["speech_timing"]["n"] == 0
    assert report["speech_grounding"]["reviewed"] == 0
    assert report["speech_grounding"]["rate"] is None


def test_oversized_iterable_is_rejected_without_consuming_unbounded_tail(monkeypatch):
    monkeypatch.setattr(gameplay_commentary_eval, "MAX_OBSERVATIONS", 3)
    consumed = []

    def observations():
        for index in range(100):
            consumed.append(index)
            yield Observation(str(index), "silence", "silence", float(index))

    with pytest.raises(ValueError, match="At most 3 observations"):
        evaluate(observations())

    # One extra item proves the limit was exceeded; the remaining generator is untouched.
    assert consumed == [0, 1, 2, 3]


@pytest.mark.parametrize("rows", [
    [Observation("", "comment", "comment", 1)],
    [Observation("a", "comment", "comment", 1),
     Observation("a", "comment", "comment", 2)],
    [Observation("a", "unknown", "comment", 1)],
    [Observation("a", "comment", "unknown", 1)],
    [Observation("a", "comment", "comment", True)],
    [Observation("a", "comment", "comment", 10, 9)],
    [Observation("a", "comment", "comment", 1, deadline_ms=-1)],
    [Observation("a", "comment", "silence", 1, negative_control=True)],
    [Observation("a", "comment", "silence", 1, negative_control=1)],
    [Observation("a", "comment", "comment", 1, grounded=1)],
    [Observation("a", "silence", "silence", 1, grounded=True)],
])
def test_invalid_observations_are_rejected(rows):
    with pytest.raises(ValueError):
        evaluate(rows)


def test_non_observation_rows_are_rejected():
    with pytest.raises(ValueError):
        evaluate([{"sample_id": "a"}])
