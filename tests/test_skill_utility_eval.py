import pytest

from star.skill_utility_eval import Trial, evaluate


HASH = "a" * 64


def trial(arm, *, case="case-1", replicate=0, split="holdout", success=False,
          latency=100.0, input_tokens=100, output_tokens=20, deadline=200.0, **changes):
    values = dict(
        skill_id="roblox-ui-layout",
        case_id=case,
        replicate=replicate,
        split=split,
        arm=arm,
        model_id="star-fast",
        model_revision="model-r1",
        harness_revision="harness-r1",
        dataset_revision="dataset-r1",
        task_revision="task-r1",
        base_prompt_sha256=HASH,
        success=success,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency,
        deadline_ms=deadline,
    )
    values.update(changes)
    return Trial(**values)


def test_paired_outcomes_and_costs_are_reported_separately():
    rows = [
        trial("off", case="a", success=False, latency=100, input_tokens=100),
        trial("on", case="a", success=True, latency=120, input_tokens=130),
        trial("off", case="b", success=True, latency=200),
        trial("on", case="b", success=False, latency=180),
        trial("off", case="c", success=False, latency=150),
        trial("on", case="c", success=False, latency=155),
    ]
    report = evaluate(rows)["skills"][0]
    assert report["pairs"] == 3
    assert report["success"]["wins"] == 1
    assert report["success"]["regressions"] == 1
    assert report["success"]["ties"] == 1
    assert report["success"]["delta_on_minus_off"] == 0.0
    assert report["latency_delta_ms_on_minus_off"]["p50"] == 5.0
    assert report["input_token_delta_on_minus_off"]["p50"] == 0.0
    assert report["deadline"]["off_rate"] == 1.0
    assert report["deadline"]["on_rate"] == 1.0


def test_unpaired_trials_are_counted_but_not_used_as_outcomes():
    report = evaluate([
        trial("off", case="a", success=True),
        trial("on", case="b", success=True),
    ])["skills"][0]
    assert report["pairs"] == 0
    assert report["unpaired_off"] == 1
    assert report["unpaired_on"] == 1
    assert report["success"]["delta_on_minus_off"] is None
    assert report["coverage"] == 0.0


def test_paired_arms_must_have_identical_provenance():
    with pytest.raises(ValueError, match="identical model"):
        evaluate([
            trial("off"),
            trial("on", model_revision="model-r2"),
        ])


def test_same_task_cannot_leak_across_splits():
    with pytest.raises(ValueError, match="more than one split"):
        evaluate([
            trial("off", split="train"),
            trial("on", split="train"),
            trial("off", split="holdout", replicate=1),
        ])


def test_duplicate_arm_for_a_replicate_is_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        evaluate([trial("off"), trial("off")])


@pytest.mark.parametrize("changes", [
    {"success": 1},
    {"input_tokens": True},
    {"output_tokens": -1},
    {"latency_ms": float("nan")},
    {"deadline_ms": 0},
    {"base_prompt_sha256": "not-a-hash"},
    {"replicate": -1},
    {"split": "validation-ish"},
    {"split": []},
    {"arm": []},
])
def test_invalid_trial_fields_are_rejected(changes):
    with pytest.raises(ValueError):
        evaluate([trial("off", **changes)])


def test_generator_input_is_supported():
    rows = (trial(arm, case=str(i), success=(arm == "on"))
            for i in range(2) for arm in ("off", "on"))
    assert evaluate(rows)["trials"] == 4


def test_empty_input_is_an_empty_report():
    report = evaluate([])
    assert report["trials"] == 0
    assert report["skills"] == []


def test_multiple_skills_and_splits_are_kept_separate():
    rows = [
        trial("off", split="train"),
        trial("on", split="train", success=True),
        trial("off", split="validation", case="val"),
        trial("on", split="validation", case="val", success=True),
        trial("off", split="holdout", case="test"),
        trial("on", split="holdout", case="test", success=True),
        Trial("eng-debugging", "x", 0, "holdout", "off", "star-fast", "model-r1", "harness-r1",
              "dataset-r1", "task-r1", HASH, False, 100, 20, 100.0, 200.0),
        Trial("eng-debugging", "x", 0, "holdout", "on", "star-fast", "model-r1", "harness-r1",
              "dataset-r1", "task-r1", HASH, True, 110, 20, 105.0, 200.0),
    ]
    reports = {(row["skill_id"], row["split"]): row for row in evaluate(rows)["skills"]}
    assert set(reports) == {
        ("roblox-ui-layout", "train"),
        ("roblox-ui-layout", "validation"),
        ("roblox-ui-layout", "holdout"),
        ("eng-debugging", "holdout"),
    }


def test_token_overhead_is_reported_as_total_extra_input_tokens_over_baseline():
    report = evaluate([
        trial("off", input_tokens=100),
        trial("on", input_tokens=150),
    ])["skills"][0]
    assert report["input_token_delta_on_minus_off"]["mean"] == 50.0
    assert report["input_token_overhead_rate"] == 0.5


def test_oversized_generator_is_stopped_at_first_excess_row(monkeypatch):
    import star.skill_utility_eval as module

    monkeypatch.setattr(module, "MAX_TRIALS", 2)
    consumed = []

    def rows():
        for i in range(20):
            consumed.append(i)
            yield trial("off", case=f"case-{i}")

    with pytest.raises(ValueError, match="At most 2"):
        module.evaluate(rows())
    assert consumed == [0, 1, 2]
