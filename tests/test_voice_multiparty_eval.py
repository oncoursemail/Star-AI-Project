import pytest

from star.voice.multiparty_eval import (
    RoomReplayCase,
    RoomReplayLimits,
    RoomReplayOutcome,
    evaluate_multiparty_replay,
    roster_digest,
    sign_room_replay_outcome,
)
from star.voice.room import RoomAction


KEY = b"independent-host-validation-key-32-bytes"
NOW = 2_000_000_000
SCENARIO = "a" * 64
EVIDENCE = "b" * 64


def _case(
    case_id: str,
    category: str,
    *,
    split: str = "holdout",
    expected_response: bool | None = None,
    expected_stop: bool = False,
    expected_interrupt: bool = False,
) -> RoomReplayCase:
    if expected_response is None:
        expected_response = category in {"explicit_direct", "implicit_direct", "urgent_barge_in"}
    if category == "human_resolution":
        expected_stop = True
        expected_response = False
    if category == "urgent_barge_in":
        expected_interrupt = True
    return RoomReplayCase(
        case_id=case_id,
        scenario_sha256=SCENARIO,
        split=split,
        cue_category=category,
        participant_count=3,
        expected_response=expected_response,
        expected_stop=expected_stop,
        expected_interrupt=expected_interrupt,
    )


def _outcome(
    case_id: str,
    action: RoomAction,
    *,
    response: bool = False,
    latency: int | None = None,
    correct: bool | None = None,
    appropriate: bool | None = None,
    observed: int = NOW,
) -> RoomReplayOutcome:
    return RoomReplayOutcome(
        case_id=case_id,
        actual_action=action,
        audible_response_started=response,
        response_latency_ms=latency,
        answer_correct=correct,
        response_appropriate=appropriate,
        evidence_sha256=EVIDENCE,
        observed_unix_s=observed,
    )


def _passing_fixture():
    cases = (
        _case("direct", "explicit_direct"),
        _case("side", "side_conversation"),
        _case("resolved", "human_resolution"),
        _case("barge", "urgent_barge_in"),
    )
    outcomes = (
        _outcome("direct", RoomAction.RESPOND, response=True, latency=120, correct=True, appropriate=True),
        _outcome("side", RoomAction.IGNORE),
        _outcome("resolved", RoomAction.STOP),
        _outcome("barge", RoomAction.INTERRUPT, response=True, latency=80, correct=True, appropriate=True),
    )
    signed = tuple(sign_room_replay_outcome(item, validation_key=KEY) for item in outcomes)
    limits = RoomReplayLimits(
        min_holdout_cases=4,
        min_cases_per_category=1,
        min_answer_labels=2,
        min_appropriateness_labels=2,
        min_latency_samples=2,
    )
    return cases, signed, limits


def test_sealed_multiparty_replay_passes_all_holdout_gates():
    cases, signed, limits = _passing_fixture()
    result = evaluate_multiparty_replay(
        cases,
        signed,
        validation_key=KEY,
        expected_roster_sha256=roster_digest(cases),
        now_unix_s=NOW,
        limits=limits,
    )
    assert result["status"] == "PASS"
    assert result["holdout"]["direct_response_delivery_rate"] == 1.0
    assert result["holdout"]["silence_preservation_rate"] == 1.0
    assert result["holdout"]["human_resolution_stop_rate"] == 1.0
    assert result["holdout"]["urgent_interrupt_recall"] == 1.0
    assert result["holdout"]["answer_accuracy"] == 1.0
    assert result["holdout"]["response_appropriateness"] == 1.0


def test_development_cases_are_reported_but_do_not_drive_holdout_gates():
    cases, signed, limits = _passing_fixture()
    dev_case = _case("dev-side", "side_conversation", split="development")
    dev_outcome = _outcome("dev-side", RoomAction.RESPOND, response=True, latency=200, correct=False, appropriate=False)
    all_cases = cases + (dev_case,)
    all_signed = signed + (sign_room_replay_outcome(dev_outcome, validation_key=KEY),)
    result = evaluate_multiparty_replay(
        all_cases,
        all_signed,
        validation_key=KEY,
        expected_roster_sha256=roster_digest(all_cases),
        now_unix_s=NOW,
        limits=limits,
    )
    assert result["status"] == "PASS"
    assert result["development"]["unwanted_response_decision_rate"] == 1.0
    assert result["holdout"]["unwanted_response_decision_rate"] == 0.0


def test_missing_required_category_is_inconclusive():
    cases, signed, limits = _passing_fixture()
    reduced = tuple(case for case in cases if case.cue_category != "urgent_barge_in")
    reduced_signed = tuple(item for item in signed if item.outcome.case_id != "barge")
    result = evaluate_multiparty_replay(
        reduced,
        reduced_signed,
        validation_key=KEY,
        expected_roster_sha256=roster_digest(reduced),
        now_unix_s=NOW,
        limits=limits,
    )
    assert result["status"] == "INCONCLUSIVE"
    assert "insufficient_category:urgent_barge_in" in result["inconclusive_reasons"]


def test_unwanted_side_conversation_response_fails_silence_gates():
    cases, signed, limits = _passing_fixture()
    bad = _outcome("side", RoomAction.RESPOND, response=True, latency=90, correct=True, appropriate=False)
    changed = tuple(
        sign_room_replay_outcome(bad if item.outcome.case_id == "side" else item.outcome, validation_key=KEY)
        for item in signed
    )
    result = evaluate_multiparty_replay(
        cases,
        changed,
        validation_key=KEY,
        expected_roster_sha256=roster_digest(cases),
        now_unix_s=NOW,
        limits=limits,
    )
    assert result["status"] == "FAIL"
    assert "unwanted_response_decision_rate" in result["failed_gates"]
    assert "silence_preservation_rate" in result["failed_gates"]


def test_failure_to_stop_after_human_resolution_fails():
    cases, signed, limits = _passing_fixture()
    bad = _outcome("resolved", RoomAction.CONTINUE)
    changed = tuple(
        sign_room_replay_outcome(bad if item.outcome.case_id == "resolved" else item.outcome, validation_key=KEY)
        for item in signed
    )
    result = evaluate_multiparty_replay(
        cases,
        changed,
        validation_key=KEY,
        expected_roster_sha256=roster_digest(cases),
        now_unix_s=NOW,
        limits=limits,
    )
    assert result["status"] == "FAIL"
    assert "human_resolution_stop_rate" in result["failed_gates"]


def test_false_interrupt_fails():
    cases, signed, limits = _passing_fixture()
    bad = _outcome("direct", RoomAction.INTERRUPT, response=True, latency=100, correct=True, appropriate=True)
    changed = tuple(
        sign_room_replay_outcome(bad if item.outcome.case_id == "direct" else item.outcome, validation_key=KEY)
        for item in signed
    )
    result = evaluate_multiparty_replay(
        cases,
        changed,
        validation_key=KEY,
        expected_roster_sha256=roster_digest(cases),
        now_unix_s=NOW,
        limits=limits,
    )
    assert result["status"] == "FAIL"
    assert "false_interrupt_rate" in result["failed_gates"]


def test_stale_and_future_outcomes_are_rejected():
    cases, signed, limits = _passing_fixture()
    stale = _outcome("direct", RoomAction.RESPOND, response=True, latency=100, correct=True, appropriate=True, observed=NOW - 8 * 86400)
    changed = tuple(
        sign_room_replay_outcome(stale if item.outcome.case_id == "direct" else item.outcome, validation_key=KEY)
        for item in signed
    )
    with pytest.raises(ValueError, match="stale"):
        evaluate_multiparty_replay(
            cases, changed, validation_key=KEY, expected_roster_sha256=roster_digest(cases),
            now_unix_s=NOW, limits=limits,
        )
    future = _outcome("direct", RoomAction.RESPOND, response=True, latency=100, correct=True, appropriate=True, observed=NOW + 61)
    changed = tuple(
        sign_room_replay_outcome(future if item.outcome.case_id == "direct" else item.outcome, validation_key=KEY)
        for item in signed
    )
    with pytest.raises(ValueError, match="future"):
        evaluate_multiparty_replay(
            cases, changed, validation_key=KEY, expected_roster_sha256=roster_digest(cases),
            now_unix_s=NOW, limits=limits,
        )


def test_invalid_signature_is_rejected():
    cases, signed, limits = _passing_fixture()
    forged = type(signed[0])(signed[0].outcome, "0" * 64)
    with pytest.raises(ValueError, match="receipt"):
        evaluate_multiparty_replay(
            cases, (forged,) + signed[1:], validation_key=KEY,
            expected_roster_sha256=roster_digest(cases), now_unix_s=NOW, limits=limits,
        )


def test_duplicate_or_missing_outcomes_are_rejected():
    cases, signed, limits = _passing_fixture()
    with pytest.raises(ValueError, match="exactly one"):
        evaluate_multiparty_replay(
            cases, signed[:-1], validation_key=KEY,
            expected_roster_sha256=roster_digest(cases), now_unix_s=NOW, limits=limits,
        )
    with pytest.raises(ValueError, match="exactly one"):
        evaluate_multiparty_replay(
            cases, signed + (signed[0],), validation_key=KEY,
            expected_roster_sha256=roster_digest(cases), now_unix_s=NOW, limits=limits,
        )


def test_roster_digest_mismatch_is_rejected():
    cases, signed, limits = _passing_fixture()
    with pytest.raises(ValueError, match="roster digest"):
        evaluate_multiparty_replay(
            cases, signed, validation_key=KEY, expected_roster_sha256="0" * 64,
            now_unix_s=NOW, limits=limits,
        )


def test_case_labels_and_outcome_metrics_are_validated():
    with pytest.raises(ValueError, match="direct-address"):
        _case("bad-direct", "explicit_direct", expected_response=False)
    with pytest.raises(ValueError, match="human_resolution"):
        RoomReplayCase("bad-stop", SCENARIO, "holdout", "side_conversation", 3, False, expected_stop=True)
    with pytest.raises(ValueError, match="audible response"):
        _outcome("bad", RoomAction.IGNORE, response=True, latency=10)
    with pytest.raises(ValueError, match="response metrics"):
        _outcome("bad", RoomAction.RESPOND, response=False, latency=10)


def test_insufficient_quality_labels_and_latency_are_inconclusive():
    cases, signed, limits = _passing_fixture()
    no_labels = tuple(
        sign_room_replay_outcome(
            _outcome("direct", RoomAction.RESPOND, response=True, latency=100)
            if item.outcome.case_id == "direct" else
            _outcome("barge", RoomAction.INTERRUPT, response=True, latency=100)
            if item.outcome.case_id == "barge" else item.outcome,
            validation_key=KEY,
        )
        for item in signed
    )
    result = evaluate_multiparty_replay(
        cases, no_labels, validation_key=KEY, expected_roster_sha256=roster_digest(cases),
        now_unix_s=NOW, limits=limits,
    )
    assert result["status"] == "INCONCLUSIVE"
    assert "insufficient_answer_labels" in result["inconclusive_reasons"]
    assert "insufficient_appropriateness_labels" in result["inconclusive_reasons"]


def test_roster_digest_is_order_independent_and_ids_are_unique():
    cases, _, _ = _passing_fixture()
    assert roster_digest(cases) == roster_digest(tuple(reversed(cases)))
    with pytest.raises(ValueError, match="unique"):
        roster_digest(cases + (cases[0],))


def test_false_stop_on_unrelated_cue_fails():
    cases, signed, limits = _passing_fixture()
    bad = _outcome("direct", RoomAction.STOP)
    changed = tuple(
        sign_room_replay_outcome(bad if item.outcome.case_id == "direct" else item.outcome, validation_key=KEY)
        for item in signed
    )
    result = evaluate_multiparty_replay(
        cases,
        changed,
        validation_key=KEY,
        expected_roster_sha256=roster_digest(cases),
        now_unix_s=NOW,
        limits=limits,
    )
    assert result["status"] == "FAIL"
    assert "false_stop_rate" in result["failed_gates"]
