"""Synthetic, offline tests for mixed-load streaming A/B evaluation."""
from __future__ import annotations

import hashlib
import hmac

import pytest

from star.mixed_load_eval import (
    METRIC_SPECS,
    MetricValue,
    MixedLoadEvaluator,
    MixedLoadManifest,
    MixedLoadObservation,
)

KEY = b"host-only-test-key-" + b"x" * 40
NOW = 1_800_000_000_000


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def manifest(**changes):
    values = dict(
        campaign_id="campaign-1",
        suite_revision="suite-v1",
        split="validation",
        hardware_fingerprint="machine-a",
        workload_sha256=digest("same-workload"),
        game_build="game-build-1",
        baseline_runtime_revision="runtime-a",
        candidate_runtime_revision="runtime-b",
        baseline_model_revision="model-a",
        candidate_model_revision="model-b",
        baseline_config_sha256=digest("config-a"),
        candidate_config_sha256=digest("config-b"),
        minimum_pairs=8,
        minimum_primary_improvement=20.0,
    )
    values.update(changes)
    return MixedLoadManifest(**values)


def metrics(*, audible=500.0, success=0.95, tps=40.0, game_p99=18.0,
            underruns=0.0, dropped=0.0):
    overrides = {
        "first_audible_ms_p95": audible,
        "verified_task_success_rate": success,
        "tokens_per_second": tps,
        "game_frame_time_p99_ms": game_p99,
        "audio_underruns_per_min": underruns,
        "obs_dropped_frames_per_min": dropped,
    }
    defaults = {
        "ttft_ms_p95": 300.0,
        "endpoint_delay_ms_p95": 400.0,
        "false_cutoff_rate": 0.02,
        "game_frame_time_p95_ms": 14.0,
        "speech_backlog_p95_ms": 80.0,
        "cpu_percent_p95": 65.0,
        "ram_used_mib_p95": 12000.0,
        "vram_used_mib_p95": 6500.0,
        "gpu_util_percent_p95": 80.0,
        "model_queue_wait_ms_p95": 20.0,
        "tool_completion_ms_p95": 900.0,
    }
    out = []
    for name, (unit, _direction, _tol) in METRIC_SPECS.items():
        value = overrides[name] if name in overrides else defaults[name]
        out.append(MetricValue(name, value, unit, 60))
    return tuple(out)


def observation(pair, arm, *, audible, now=NOW, split="validation",
                success=0.95, game_p99=18.0, underruns=0.0, dropped=0.0):
    baseline = arm == "baseline"
    return MixedLoadObservation(
        sample_id=f"sample-{pair}-{arm}",
        campaign_id="campaign-1",
        pair_id=f"pair-{pair}",
        arm=arm,
        split=split,
        hardware_fingerprint="machine-a",
        workload_sha256=digest("same-workload"),
        game_build="game-build-1",
        runtime_revision="runtime-a" if baseline else "runtime-b",
        model_revision="model-a" if baseline else "model-b",
        config_sha256=digest("config-a" if baseline else "config-b"),
        observed_unix_ms=now,
        window_ms=120_000,
        metrics=metrics(audible=audible, success=success, game_p99=game_p99,
                        underruns=underruns, dropped=dropped),
    )


def signed(obs):
    return hmac.new(KEY, obs.canonical_bytes(), hashlib.sha256).hexdigest()


def evaluator(**changes):
    return MixedLoadEvaluator(manifest(**changes), host_key=KEY)


def add_pair(ev, pair, *, baseline=500.0, candidate=450.0, **kwargs):
    b = observation(pair, "baseline", audible=baseline, **kwargs)
    c = observation(pair, "candidate", audible=candidate, **kwargs)
    ev.ingest(b, signed(b), now_unix_ms=NOW)
    ev.ingest(c, signed(c), now_unix_ms=NOW)


def test_matched_improvement_is_only_eligible_for_owner_review():
    ev = evaluator()
    for i in range(8):
        add_pair(ev, i)
    result = ev.evaluate()
    assert result.status == "eligible_for_owner_review"
    assert result.complete_pairs == 8
    assert result.primary_median_improvement == 50.0
    assert result.primary_sign_p_value == pytest.approx(1 / 256)
    assert result.authorized_to_change_runtime is False


def test_token_throughput_gain_cannot_hide_game_regression():
    ev = evaluator()
    for i in range(8):
        b = observation(i, "baseline", audible=500.0)
        c = observation(i, "candidate", audible=450.0, game_p99=25.0)
        ev.ingest(b, signed(b), now_unix_ms=NOW)
        ev.ingest(c, signed(c), now_unix_ms=NOW)
    result = ev.evaluate()
    assert result.status == "regressed"
    assert "game_frame_time_p99_ms" in result.reason


def test_audio_and_obs_regressions_are_protected():
    ev = evaluator()
    for i in range(8):
        b = observation(i, "baseline", audible=500.0)
        c = observation(i, "candidate", audible=450.0, underruns=1.0, dropped=3.0)
        ev.ingest(b, signed(b), now_unix_ms=NOW)
        ev.ingest(c, signed(c), now_unix_ms=NOW)
    result = ev.evaluate()
    assert result.status == "regressed"
    assert "audio_underruns_per_min" in result.reason
    assert "obs_dropped_frames_per_min" in result.reason


def test_noisy_or_small_change_does_not_claim_improvement():
    ev = evaluator()
    for i in range(8):
        add_pair(ev, i, baseline=500.0, candidate=490.0)
    result = ev.evaluate()
    assert result.status == "no_demonstrated_improvement"


def test_incomplete_pairs_are_not_counted():
    ev = evaluator()
    for i in range(7):
        add_pair(ev, i)
    b = observation(8, "baseline", audible=500.0)
    ev.ingest(b, signed(b), now_unix_ms=NOW)
    result = ev.evaluate()
    assert result.status == "insufficient_pairs"
    assert result.complete_pairs == 7
    assert result.incomplete_pairs == 1


def test_receipt_must_be_host_signed():
    ev = evaluator()
    b = observation(1, "baseline", audible=500.0)
    with pytest.raises(PermissionError):
        ev.ingest(b, "0" * 64, now_unix_ms=NOW)


def test_manifest_pins_split_hardware_workload_and_revisions():
    ev = evaluator()
    bad = observation(1, "baseline", audible=500.0)
    bad = MixedLoadObservation(**{**bad.__dict__, "hardware_fingerprint": "other-machine"})
    with pytest.raises(ValueError, match="hardware/workload"):
        ev.ingest(bad, signed(bad), now_unix_ms=NOW)


def test_validation_and_holdout_evidence_cannot_be_mixed():
    ev = evaluator()
    bad = observation(1, "baseline", audible=500.0, split="holdout")
    with pytest.raises(ValueError, match="campaign/split"):
        ev.ingest(bad, signed(bad), now_unix_ms=NOW)


def test_duplicate_arm_and_sample_are_rejected():
    ev = evaluator()
    b = observation(1, "baseline", audible=500.0)
    ev.ingest(b, signed(b), now_unix_ms=NOW)
    with pytest.raises(ValueError, match="duplicate"):
        ev.ingest(b, signed(b), now_unix_ms=NOW)


def test_future_and_stale_evidence_rejected():
    ev = evaluator()
    future = observation(1, "baseline", audible=500.0, now=NOW + 10_000)
    with pytest.raises(ValueError, match="future"):
        ev.ingest(future, signed(future), now_unix_ms=NOW)
    stale = observation(2, "baseline", audible=500.0, now=NOW - 8 * 86_400_000)
    with pytest.raises(ValueError, match="stale"):
        ev.ingest(stale, signed(stale), now_unix_ms=NOW)


def test_pair_window_and_time_gap_must_match():
    ev = evaluator()
    b = observation(1, "baseline", audible=500.0)
    c = observation(1, "candidate", audible=450.0, now=NOW - 2 * 86_400_000)
    ev.ingest(b, signed(b), now_unix_ms=NOW)
    with pytest.raises(ValueError, match="time gap"):
        ev.ingest(c, signed(c), now_unix_ms=NOW)


def test_invalid_metric_sets_units_and_ranges_rejected():
    with pytest.raises(ValueError, match="unknown mixed-load metric"):
        MetricValue("fake_metric", 1.0, "x", 5)
    with pytest.raises(ValueError, match="must use"):
        MetricValue("first_audible_ms_p95", 100.0, "seconds", 5)
    with pytest.raises(ValueError, match="between zero and one"):
        MetricValue("false_cutoff_rate", 1.5, "ratio", 5)
    with pytest.raises(ValueError, match="nonnegative"):
        MetricValue("tokens_per_second", -1.0, "tokens/s", 5)


def test_missing_required_metric_rejected():
    all_metrics = list(metrics())
    with pytest.raises(ValueError, match="exactly once"):
        MixedLoadObservation(
            sample_id="sample-1", campaign_id="campaign-1", pair_id="pair-1",
            arm="baseline", split="validation", hardware_fingerprint="machine-a",
            workload_sha256=digest("same-workload"), game_build="game-build-1",
            runtime_revision="runtime-a", model_revision="model-a",
            config_sha256=digest("config-a"), observed_unix_ms=NOW,
            window_ms=120_000, metrics=tuple(all_metrics[:-1]),
        )


def test_pairing_uses_same_window_and_requires_matching_build():
    ev = evaluator()
    b = observation(1, "baseline", audible=500.0)
    c = observation(1, "candidate", audible=450.0)
    c = MixedLoadObservation(**{**c.__dict__, "window_ms": 180_000})
    ev.ingest(b, signed(b), now_unix_ms=NOW)
    with pytest.raises(ValueError, match="windows differ"):
        ev.ingest(c, signed(c), now_unix_ms=NOW)


def test_manifest_rejects_invalid_thresholds_and_split():
    with pytest.raises(ValueError):
        manifest(split="production")
    with pytest.raises(ValueError):
        manifest(minimum_pairs=2)
    with pytest.raises(ValueError):
        manifest(maximum_guard_regression_fraction=0.5)


def test_evaluator_requires_separate_host_key():
    with pytest.raises(ValueError, match="32 bytes"):
        MixedLoadEvaluator(manifest(), host_key=b"short")


def test_clock_cannot_move_backwards():
    ev = evaluator()
    b = observation(1, "baseline", audible=500.0)
    ev.ingest(b, signed(b), now_unix_ms=NOW)
    with pytest.raises(ValueError, match="clock moved backwards"):
        ev.ingest(observation(2, "baseline", audible=500.0, now=NOW-1),
                  signed(observation(2, "baseline", audible=500.0, now=NOW-1)),
                  now_unix_ms=NOW-1)


def test_manifest_requires_a_real_candidate_change():
    with pytest.raises(ValueError, match="must differ"):
        manifest(
            candidate_runtime_revision="runtime-a",
            candidate_model_revision="model-a",
            candidate_config_sha256=digest("config-a"),
        )


def test_invalid_observation_does_not_advance_evaluator_clock():
    ev = evaluator()
    bad = observation(1, "baseline", audible=500.0, now=NOW + 60_000)
    with pytest.raises(ValueError, match="future"):
        ev.ingest(bad, signed(bad), now_unix_ms=NOW)
    good = observation(2, "baseline", audible=500.0, now=NOW)
    ev.ingest(good, signed(good), now_unix_ms=NOW)


def test_gpu_utilization_is_reported_but_not_treated_as_a_regression_by_itself():
    ev = evaluator()
    for i in range(8):
        b = observation(i, "baseline", audible=500.0)
        changed = tuple(
            MetricValue(m.name, 99.0 if m.name == "gpu_util_percent_p95" else m.value,
                        m.unit, m.samples)
            for m in metrics(audible=450.0)
        )
        c = MixedLoadObservation(**{**observation(i, "candidate", audible=450.0).__dict__,
                                    "metrics": changed})
        ev.ingest(b, signed(b), now_unix_ms=NOW)
        ev.ingest(c, signed(c), now_unix_ms=NOW)
    assert ev.evaluate().status == "eligible_for_owner_review"
