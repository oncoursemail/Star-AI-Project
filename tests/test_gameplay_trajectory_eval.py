import pytest

from star import gameplay_trajectory_eval
from star.gameplay_trajectory_eval import Episode, Event, evaluate


def event(index, kind, at_ms, **kwargs):
    return Event(index=index, kind=kind, at_ms=at_ms, **kwargs)


def episode(
    episode_id="e1",
    *,
    task_id="obby",
    case_id="seed-a",
    attempt_index=0,
    split="holdout",
    events=(),
    goal_reached=True,
    save_reload_verified=None,
    requires_save_reload=False,
):
    return Episode(
        episode_id=episode_id,
        task_id=task_id,
        case_id=case_id,
        attempt_index=attempt_index,
        split=split,
        events=events,
        goal_reached=goal_reached,
        save_reload_verified=save_reload_verified,
        requires_save_reload=requires_save_reload,
    )


def test_empty_report_keeps_all_splits_and_metrics_empty():
    report = evaluate([])
    assert report["episodes"] == 0
    assert report["overall"]["verified_acceptance"]["rate"] is None
    assert report["by_split"]["holdout"]["repeatability"]["1"]["eligible_cases"] == 0


def test_observe_before_action_recovery_and_save_reload_acceptance():
    report = evaluate([
        episode(
            events=(
                event(0, "observe", 0, target_id="door"),
                event(1, "edit", 10, target_id="door", valid_action=True, latency_ms=8),
                event(2, "act", 20, target_id="door", valid_action=False, latency_ms=12),
                event(3, "verify", 30, passed=True),
                event(4, "recover", 40),
                event(5, "verify_final", 50, passed=True),
            ),
            save_reload_verified=True,
            requires_save_reload=True,
        )
    ])
    summary = report["by_split"]["holdout"]
    assert summary["verified_acceptance"]["accepted"] == 1
    assert summary["actions"]["total"] == 2
    assert summary["actions"]["invalid"] == 1
    assert summary["actions"]["target_observation_rate"] == 1.0
    assert summary["subgoal_verification"]["pass_rate"] == 1.0
    assert summary["recovery"]["episodes_with_recovery"] == 1
    assert summary["event_latency_ms"]["p50"] == 10.0


def test_unobserved_target_and_missing_final_verification_are_not_accepted():
    report = evaluate([
        episode(events=(
            event(0, "edit", 0, target_id="hidden-door", valid_action=True),
        ))
    ])
    summary = report["by_split"]["holdout"]
    assert summary["actions"]["target_observation_rate"] == 0.0
    assert summary["verified_acceptance"]["accepted"] == 0
    assert summary["final_verification"]["missing"] == 1


def test_failed_save_reload_blocks_complete_game_acceptance():
    report = evaluate([
        episode(
            events=(event(0, "verify_final", 10, passed=True),),
            save_reload_verified=False,
            requires_save_reload=True,
        )
    ])
    assert report["by_split"]["holdout"]["final_verification"]["passed"] == 1
    assert report["by_split"]["holdout"]["verified_acceptance"]["accepted"] == 0
    assert report["by_split"]["holdout"]["save_reload"]["failed"] == 1


def test_empirical_pass_at_k_and_all_at_k_use_ordered_attempts():
    rows = []
    outcomes = {
        "case-a": (False, True, True),
        "case-b": (True, True, True),
    }
    index = 0
    for case_id, values in outcomes.items():
        for attempt_index, accepted in enumerate(values):
            rows.append(episode(
                f"e{index}",
                case_id=case_id,
                attempt_index=attempt_index,
                events=(event(0, "verify_final", 1, passed=accepted),),
                goal_reached=accepted,
            ))
            index += 1
    summary = evaluate(rows)["by_split"]["holdout"]["repeatability"]
    assert summary["1"]["eligible_cases"] == 2
    assert summary["1"]["empirical_pass_at_k"] == 0.5
    assert summary["3"]["empirical_pass_at_k"] == 1.0
    assert summary["3"]["empirical_all_at_k"] == 0.5


def test_holdout_and_training_results_are_not_combined():
    report = evaluate([
        episode("train", split="train", goal_reached=True,
                events=(event(0, "verify_final", 1, passed=True),)),
        episode("test", split="holdout", goal_reached=False,
                events=(event(0, "verify_final", 1, passed=False),)),
    ])
    assert report["by_split"]["train"]["verified_acceptance"]["rate"] == 1.0
    assert report["by_split"]["holdout"]["verified_acceptance"]["rate"] == 0.0


@pytest.mark.parametrize(
    "bad_event",
    [
        event(0, "edit", 0, target_id="x"),
        event(0, "verify", 0),
        event(0, "observe", float("nan"), target_id="x"),
        event(0, "observe", 0, target_id="../escape"),
        event(-1, "observe", 0, target_id="x"),
    ],
)
def test_invalid_events_are_rejected(bad_event):
    with pytest.raises(ValueError):
        evaluate([episode(events=(bad_event,))])


def test_action_after_final_verification_is_rejected():
    with pytest.raises(ValueError, match="follow final"):
        evaluate([episode(events=(
            event(0, "verify_final", 1, passed=True),
            event(1, "act", 2, target_id="player", valid_action=True),
        ))])


def test_duplicate_attempt_index_is_rejected():
    with pytest.raises(ValueError, match="attempt_index"):
        evaluate([
            episode("e1", attempt_index=1),
            episode("e2", attempt_index=1),
        ])


def test_unbounded_episode_generator_stops_at_first_extra(monkeypatch):
    monkeypatch.setattr(gameplay_trajectory_eval, "MAX_EPISODES", 2)
    consumed = []

    def episodes():
        for index in range(10):
            consumed.append(index)
            yield episode(f"e{index}", case_id=f"case-{index}")

    with pytest.raises(ValueError, match="At most 2"):
        evaluate(episodes())
    assert consumed == [0, 1, 2]


def test_unbounded_event_generator_stops_at_first_extra(monkeypatch):
    monkeypatch.setattr(gameplay_trajectory_eval, "MAX_EVENTS_PER_EPISODE", 2)
    consumed = []

    def events():
        for index in range(10):
            consumed.append(index)
            yield event(index, "observe", index, target_id=f"target-{index}")

    with pytest.raises(ValueError, match="At most 2 events"):
        evaluate([episode(events=events())])
    assert consumed == [0, 1, 2]
