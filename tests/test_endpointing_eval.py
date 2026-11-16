import pytest

from star import endpointing_eval
from star.endpointing_eval import Decision, evaluate


def decision(
    policy_id,
    sample_id,
    label,
    action,
    *,
    language="en",
    cohort="general",
    timeout_ms=600,
    decision_latency_ms=None,
):
    return Decision(
        policy_id=policy_id,
        sample_id=sample_id,
        language=language,
        cohort=cohort,
        label=label,
        action=action,
        timeout_ms=timeout_ms,
        decision_latency_ms=decision_latency_ms,
    )


def test_empty_report_has_no_frontier_or_invented_scores():
    report = evaluate([])
    assert report["decisions"] == 0
    assert report["policies"] == []
    assert report["paired_coverage"]["complete"] is False
    assert report["pareto_frontier"] == []


def test_policy_tradeoff_preserves_false_cutoffs_misses_and_latency():
    rows = [
        decision("fast", "eot-a", "eot", "trigger", decision_latency_ms=100),
        decision("fast", "hold-a", "hold", "trigger", decision_latency_ms=50),
        decision("fast", "eot-b", "eot", "trigger", decision_latency_ms=250),
        decision("fast", "hold-b", "hold", "trigger", decision_latency_ms=70),
        decision("careful", "eot-a", "eot", "trigger", decision_latency_ms=250),
        decision("careful", "hold-a", "hold", "hold"),
        decision("careful", "eot-b", "eot", "hold"),
        decision("careful", "hold-b", "hold", "hold"),
    ]
    report = evaluate(rows)
    policies = {item["policy_id"]: item for item in report["policies"]}
    assert policies["fast"]["mid_turn_hold"]["false_cutoff_rate"] == 1.0
    assert policies["fast"]["end_of_turn"]["missed_rate"] == 0.0
    assert policies["careful"]["mid_turn_hold"]["false_cutoff_rate"] == 0.0
    assert policies["careful"]["end_of_turn"]["missed_rate"] == 0.5
    assert policies["careful"]["end_of_turn"]["endpoint_delay_ms"]["p95"] == 600.0
    assert report["paired_coverage"]["complete"] is True
    assert report["pareto_frontier"] == ["careful", "fast"]


def test_missed_turn_is_censored_at_timeout_not_omitted_from_latency():
    report = evaluate([
        decision("p", "eot-a", "eot", "trigger", decision_latency_ms=100),
        decision("p", "eot-b", "eot", "hold", timeout_ms=800),
        decision("p", "hold-a", "hold", "hold"),
    ])
    policy = report["policies"][0]
    assert policy["end_of_turn"]["endpoint_delay_ms"]["n"] == 2
    assert policy["end_of_turn"]["endpoint_delay_ms"]["mean"] == 450.0
    assert policy["end_of_turn"]["endpoint_delay_ms"]["p95"] == 800.0
    assert policy["end_of_turn"]["missed"] == 1


def test_language_and_cohort_metrics_are_kept_separate():
    report = evaluate([
        decision("p", "en-a", "eot", "trigger", decision_latency_ms=120),
        decision("p", "es-a", "hold", "trigger", language="es", cohort="accented",
                 decision_latency_ms=90),
    ])
    policy = report["policies"][0]
    assert policy["by_language"]["en"]["end_of_turn"]["triggered"] == 1
    assert policy["by_language"]["es"]["mid_turn_hold"]["false_cutoffs"] == 1
    assert policy["by_cohort"]["accented"]["mid_turn_hold"]["pauses"] == 1


def test_incomplete_policy_coverage_disables_frontier():
    report = evaluate([
        decision("a", "sample-1", "eot", "trigger", decision_latency_ms=100),
        decision("b", "sample-1", "eot", "trigger", decision_latency_ms=120),
        decision("b", "sample-2", "hold", "hold"),
    ])
    assert report["paired_coverage"]["complete"] is False
    assert report["paired_coverage"]["common_samples"] == 1
    assert report["pareto_frontier"] == []


def test_duplicate_policy_sample_and_metadata_disagreement_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        evaluate([
            decision("p", "same", "eot", "trigger", decision_latency_ms=100),
            decision("p", "same", "eot", "trigger", decision_latency_ms=120),
        ])
    with pytest.raises(ValueError, match="disagree"):
        evaluate([
            decision("a", "same", "eot", "trigger", decision_latency_ms=100),
            decision("b", "same", "hold", "hold"),
        ])


@pytest.mark.parametrize(
    "row",
    [
        decision("p", "s", "unknown", "hold"),
        decision("p", "s", "eot", "trigger"),
        decision("p", "s", "eot", "hold", decision_latency_ms=10),
        decision("p", "s", "eot", "trigger", timeout_ms=0, decision_latency_ms=0),
        decision("p", "s", "eot", "trigger", timeout_ms=100, decision_latency_ms=101),
        decision("p", "s", "eot", "trigger", language="English", decision_latency_ms=10),
        decision("../p", "s", "eot", "trigger", decision_latency_ms=10),
        decision("p", "s", "eot", "trigger", decision_latency_ms=float("nan")),
    ],
)
def test_invalid_decision_rows_are_rejected(row):
    with pytest.raises(ValueError):
        evaluate([row])


def test_oversized_generator_stops_at_first_extra(monkeypatch):
    monkeypatch.setattr(endpointing_eval, "MAX_DECISIONS", 2)
    consumed = []

    def rows():
        for index in range(10):
            consumed.append(index)
            yield decision(
                "p", f"s{index}", "eot", "trigger", decision_latency_ms=100
            )

    with pytest.raises(ValueError, match="At most 2"):
        evaluate(rows())
    assert consumed == [0, 1, 2]
