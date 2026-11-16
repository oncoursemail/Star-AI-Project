import pytest

from star import mixed_load_eval
from star.mixed_load_eval import Sample, evaluate


def row(sample_id, arm, *, case_id="door-obby", replicate_id="rep-1", **kwargs):
    fields = {"scenario": "mixed", "phase": "warm"}
    fields.update(kwargs)
    return Sample(
        sample_id=sample_id,
        case_id=case_id,
        replicate_id=replicate_id,
        arm=arm,
        **fields,
    )


def test_empty_report_keeps_unmeasured_metrics_null():
    report = evaluate([])
    assert report["samples"] == 0
    assert report["groups"] == []
    assert report["paired"]["matched_cases"] == 0
    assert report["paired"]["numeric_candidate_minus_baseline"]["ttft_ms"]["mean"] is None


def test_group_reports_distributions_deadlines_and_counters_separately():
    report = evaluate([
        row(
            "b1", "baseline", ttft_ms=120, client_heard_ms=310,
            client_heard_deadline_ms=400, decode_tokens_per_second=25,
            game_fps=58, cpu_percent=70, ram_mb=6000, vram_mb=6900,
            audio_underruns=0, obs_dropped_frames=1, avatar_dropped_frames=0,
            task_success=True,
        ),
        row(
            "b2", "baseline", replicate_id="rep-2", ttft_ms=180,
            client_heard_ms=450, client_heard_deadline_ms=400,
            decode_tokens_per_second=22, game_fps=52, cpu_percent=82,
            ram_mb=6400, vram_mb=7200, audio_underruns=2,
            obs_dropped_frames=3, avatar_dropped_frames=1, task_success=False,
        ),
    ])
    group = report["groups"][0]
    assert group["arm"] == "baseline"
    assert group["samples"] == 2
    assert group["metrics"]["ttft_ms"]["n"] == 2
    assert group["metrics"]["ttft_ms"]["p50"] == 150.0
    assert group["metrics"]["ttft_ms"]["p95"] == 180.0
    assert group["deadlines"]["client_heard"] == {
        "eligible": 2, "on_time": 1, "late": 1, "on_time_rate": 0.5,
    }
    assert group["counters"]["audio_underruns"]["total"] == 2
    assert group["task_success"] == {
        "n": 2, "passed": 1, "failed": 1, "rate": 0.5,
    }


def test_matched_pairs_report_candidate_minus_baseline_without_composite_score():
    report = evaluate([
        row("b1", "baseline", ttft_ms=120, prefill_tokens_per_second=800, decode_tokens_per_second=20, game_fps=55, task_success=False),
        row("c1", "candidate", ttft_ms=90, prefill_tokens_per_second=900, decode_tokens_per_second=25, game_fps=58, task_success=True),
        row("b2", "baseline", replicate_id="rep-2", ttft_ms=140, prefill_tokens_per_second=700, decode_tokens_per_second=18, game_fps=52, task_success=True),
        row("c2", "candidate", replicate_id="rep-2", ttft_ms=100, prefill_tokens_per_second=850, decode_tokens_per_second=23, game_fps=54, task_success=True),
    ])
    paired = report["paired"]
    assert paired["matched_cases"] == 2
    assert paired["numeric_candidate_minus_baseline"]["ttft_ms"]["mean"] == -35.0
    assert paired["numeric_candidate_minus_baseline"]["prefill_tokens_per_second"]["mean"] == 125.0
    assert paired["numeric_candidate_minus_baseline"]["decode_tokens_per_second"]["mean"] == 5.0
    assert paired["numeric_candidate_minus_baseline"]["game_fps"]["mean"] == 2.5
    assert paired["task_success"] == {
        "improved": 1, "regressed": 0, "unchanged": 1, "missing": 0,
    }
    assert "score" not in report
    assert "promotion" not in report


def test_unmatched_repetitions_are_reported_not_silently_dropped():
    report = evaluate([
        row("b1", "baseline", replicate_id="rep-1", ttft_ms=100),
        row("b2", "baseline", replicate_id="rep-2", ttft_ms=120),
        row("c2", "candidate", replicate_id="rep-2", ttft_ms=110),
        row("c3", "candidate", replicate_id="rep-3", ttft_ms=115),
    ])
    assert report["paired"]["matched_cases"] == 1
    assert report["paired"]["baseline_only_cases"] == 1
    assert report["paired"]["candidate_only_cases"] == 1
    assert report["paired"]["numeric_candidate_minus_baseline"]["ttft_ms"]["n"] == 1
    assert report["paired"]["numeric_candidate_minus_baseline"]["ttft_ms"]["missing"] == 0


def test_missing_measurements_remain_missing_and_are_not_imputed():
    report = evaluate([
        row("b1", "baseline", ttft_ms=100, client_heard_ms=None),
        row("c1", "candidate", ttft_ms=None, client_heard_ms=200),
    ])
    group_by_arm = {group["arm"]: group for group in report["groups"]}
    assert group_by_arm["baseline"]["metrics"]["client_heard_ms"]["missing"] == 1
    assert group_by_arm["candidate"]["metrics"]["ttft_ms"]["missing"] == 1
    assert report["paired"]["numeric_candidate_minus_baseline"]["ttft_ms"]["n"] == 0
    assert report["paired"]["numeric_candidate_minus_baseline"]["ttft_ms"]["missing"] == 1


def test_cold_warm_and_scenario_groups_are_kept_separate():
    report = evaluate([
        row("b1", "baseline", scenario="idle", phase="cold", ttft_ms=300),
        row("b2", "baseline", scenario="mixed", phase="warm", ttft_ms=100),
    ])
    assert [(g["scenario"], g["phase"]) for g in report["groups"]] == [
        ("idle", "cold"),
        ("mixed", "warm"),
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ttft_ms": float("nan")},
        {"ttft_ms": -1},
        {"cpu_percent": 101},
        {"audio_underruns": True},
        {"task_success": 1},
        {"client_heard_deadline_ms": 100},
        {"scenario": "unknown"},
        {"phase": "hot"},
        {"arm": "experimental"},
    ],
)
def test_invalid_measurements_and_labels_are_rejected(kwargs):
    base = dict(
        sample_id="s1", case_id="case1", replicate_id="r1",
        arm="baseline", scenario="mixed", phase="warm",
    )
    base.update(kwargs)
    with pytest.raises(ValueError):
        evaluate([Sample(**base)])


def test_duplicate_sample_and_duplicate_arm_pair_are_rejected():
    with pytest.raises(ValueError, match="sample_id"):
        evaluate([
            row("same", "baseline"),
            row("same", "candidate"),
        ])
    with pytest.raises(ValueError, match="once per arm"):
        evaluate([
            row("b1", "baseline"),
            row("b2", "baseline"),
        ])


def test_over_limit_generator_is_stopped_at_first_extra_sample(monkeypatch):
    monkeypatch.setattr(mixed_load_eval, "MAX_SAMPLES", 2)
    consumed = []

    def samples():
        for index in range(10):
            consumed.append(index)
            yield row(f"s{index}", "baseline", replicate_id=f"r{index}")

    with pytest.raises(ValueError, match="At most 2"):
        evaluate(samples())
    assert consumed == [0, 1, 2]
