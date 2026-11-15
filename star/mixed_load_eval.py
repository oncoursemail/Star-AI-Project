"""Offline evaluation of STAR's mixed-load streaming performance.

The evaluator compares matched baseline/candidate runs under the same
hardware, workload, game build, and stream scenario. It consumes only
host-produced, HMAC-authenticated aggregate measurements; it does not collect
telemetry, start workloads, control OBS, operate a microphone, or change
resource admission.

A positive result is only eligible for owner review. It never changes runtime
configuration, model routing, broadcast state, or permissions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import hmac
import json
import math
import re
from statistics import median

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_DOMAIN = b"star.mixed_load.observation.v1\x00"
_ARMS = frozenset({"baseline", "candidate"})
_SPLITS = frozenset({"practice", "validation", "holdout"})
_MAX_OBSERVATIONS = 2000

# Direction is +1 when larger is better and -1 when smaller is better.
# Tolerances are absolute units, not percentages.
METRIC_SPECS: dict[str, tuple[str, int, float]] = {
    "ttft_ms_p95": ("ms", -1, 40.0),
    "first_audible_ms_p95": ("ms", -1, 40.0),
    "endpoint_delay_ms_p95": ("ms", -1, 50.0),
    "false_cutoff_rate": ("ratio", -1, 0.01),
    "audio_underruns_per_min": ("count/min", -1, 0.10),
    "obs_dropped_frames_per_min": ("count/min", -1, 0.50),
    "game_frame_time_p95_ms": ("ms", -1, 1.0),
    "game_frame_time_p99_ms": ("ms", -1, 2.0),
    "speech_backlog_p95_ms": ("ms", -1, 50.0),
    "verified_task_success_rate": ("ratio", 1, 0.01),
    "tokens_per_second": ("tokens/s", 1, 0.0),
    "cpu_percent_p95": ("percent", -1, 3.0),
    "ram_used_mib_p95": ("MiB", -1, 256.0),
    "vram_used_mib_p95": ("MiB", -1, 256.0),
    "gpu_util_percent_p95": ("percent", -1, 5.0),
    "model_queue_wait_ms_p95": ("ms", -1, 50.0),
    "tool_completion_ms_p95": ("ms", -1, 100.0),
}
_REQUIRED_METRICS = frozenset(METRIC_SPECS)


def _identifier(value: object, field: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded identifier")
    return value


def _digest(value: object, field: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _timestamp(value: object, field: str) -> int:
    if type(value) is not int or not 0 < value <= 10**15:
        raise ValueError(f"{field} must be a positive Unix millisecond timestamp")
    return value


@dataclass(frozen=True)
class MetricValue:
    """One aggregate from a fixed measurement window."""

    name: str
    value: float
    unit: str
    samples: int

    def __post_init__(self) -> None:
        if self.name not in METRIC_SPECS:
            raise ValueError("unknown mixed-load metric")
        expected_unit = METRIC_SPECS[self.name][0]
        if self.unit != expected_unit:
            raise ValueError(f"{self.name} must use {expected_unit}")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ValueError("metric value must be numeric")
        if not math.isfinite(float(self.value)) or float(self.value) < 0:
            raise ValueError("metric value must be finite and nonnegative")
        if type(self.samples) is not int or not 5 <= self.samples <= 1_000_000:
            raise ValueError("metric samples must be between 5 and 1000000")
        if self.name in {"false_cutoff_rate", "verified_task_success_rate"} and self.value > 1:
            raise ValueError("ratio metrics must be between zero and one")
        if self.name in {"cpu_percent_p95", "gpu_util_percent_p95"} and self.value > 100:
            raise ValueError("percent metrics must be between zero and one hundred")


@dataclass(frozen=True)
class MixedLoadManifest:
    """Immutable comparison contract, created before either arm is run."""

    campaign_id: str
    suite_revision: str
    split: str
    hardware_fingerprint: str
    workload_sha256: str
    game_build: str
    baseline_runtime_revision: str
    candidate_runtime_revision: str
    baseline_model_revision: str
    candidate_model_revision: str
    baseline_config_sha256: str
    candidate_config_sha256: str
    primary_metric: str = "first_audible_ms_p95"
    minimum_pairs: int = 8
    minimum_primary_improvement: float = 20.0
    maximum_guard_regression_fraction: float = 0.25
    maximum_pair_gap_ms: int = 86_400_000

    def __post_init__(self) -> None:
        for field in (
            "campaign_id", "suite_revision", "hardware_fingerprint", "game_build",
            "baseline_runtime_revision", "candidate_runtime_revision",
            "baseline_model_revision", "candidate_model_revision",
        ):
            _identifier(getattr(self, field), field)
        for field in ("workload_sha256", "baseline_config_sha256", "candidate_config_sha256"):
            _digest(getattr(self, field), field)
        if self.split not in _SPLITS:
            raise ValueError("unknown evaluation split")
        if self.primary_metric not in METRIC_SPECS:
            raise ValueError("unknown primary metric")
        if type(self.minimum_pairs) is not int or not 8 <= self.minimum_pairs <= 1000:
            raise ValueError("minimum_pairs must be between 8 and 1000")
        if (isinstance(self.minimum_primary_improvement, bool)
                or not isinstance(self.minimum_primary_improvement, (int, float))
                or not math.isfinite(float(self.minimum_primary_improvement))
                or self.minimum_primary_improvement < 0):
            raise ValueError("minimum primary improvement must be finite and nonnegative")
        fraction = self.maximum_guard_regression_fraction
        if (isinstance(fraction, bool) or not isinstance(fraction, (int, float))
                or not math.isfinite(float(fraction)) or not 0 <= fraction < 0.5):
            raise ValueError("guard regression fraction must be in [0, 0.5)")
        if type(self.maximum_pair_gap_ms) is not int or not 1_000 <= self.maximum_pair_gap_ms <= 604_800_000:
            raise ValueError("invalid maximum pair gap")
        if ((self.baseline_runtime_revision, self.baseline_model_revision, self.baseline_config_sha256)
                == (self.candidate_runtime_revision, self.candidate_model_revision, self.candidate_config_sha256)):
            raise ValueError("baseline and candidate must differ in a pinned runtime/model/config revision")


@dataclass(frozen=True)
class MixedLoadObservation:
    """Host-produced aggregate for one arm of one matched pair."""

    sample_id: str
    campaign_id: str
    pair_id: str
    arm: str
    split: str
    hardware_fingerprint: str
    workload_sha256: str
    game_build: str
    runtime_revision: str
    model_revision: str
    config_sha256: str
    observed_unix_ms: int
    window_ms: int
    metrics: tuple[MetricValue, ...]

    def __post_init__(self) -> None:
        for field in ("sample_id", "campaign_id", "pair_id", "hardware_fingerprint",
                      "game_build", "runtime_revision", "model_revision"):
            _identifier(getattr(self, field), field)
        for field in ("workload_sha256", "config_sha256"):
            _digest(getattr(self, field), field)
        if self.arm not in _ARMS or self.split not in _SPLITS:
            raise ValueError("invalid arm or split")
        _timestamp(self.observed_unix_ms, "observed_unix_ms")
        if type(self.window_ms) is not int or not 60_000 <= self.window_ms <= 3_600_000:
            raise ValueError("measurement window must be between one and sixty minutes")
        if type(self.metrics) is not tuple or len(self.metrics) != len(_REQUIRED_METRICS):
            raise ValueError("all required mixed-load metrics must be supplied exactly once")
        if any(not isinstance(item, MetricValue) for item in self.metrics):
            raise ValueError("metrics must contain MetricValue records")
        names = [item.name for item in self.metrics]
        if len(set(names)) != len(names) or set(names) != _REQUIRED_METRICS:
            raise ValueError("metric set is incomplete or contains duplicates")

    def canonical_bytes(self) -> bytes:
        """Canonical, domain-separated payload for the trusted host to sign."""
        payload = asdict(self)
        payload["metrics"] = [asdict(m) for m in sorted(self.metrics, key=lambda x: x.name)]
        return _DOMAIN + json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")


@dataclass(frozen=True)
class MetricComparison:
    name: str
    unit: str
    median_improvement: float
    wins: int
    losses: int
    ties: int
    guard_regressions: int
    tolerance: float


@dataclass(frozen=True)
class MixedLoadResult:
    status: str
    reason: str
    complete_pairs: int
    incomplete_pairs: int
    primary_metric: str
    primary_median_improvement: float | None
    primary_sign_p_value: float | None
    comparisons: tuple[MetricComparison, ...]
    authorized_to_change_runtime: bool = False


def _upper_binomial_tail(wins: int, decisive: int) -> float:
    """Exact one-sided sign-test tail under P(candidate wins)=0.5."""
    if decisive <= 0 or wins <= decisive // 2:
        return 1.0
    numerator = sum(math.comb(decisive, k) for k in range(wins, decisive + 1))
    return numerator / (2 ** decisive)


class MixedLoadEvaluator:
    """Offline paired evaluator; never admits or starts a workload."""

    def __init__(
        self,
        manifest: MixedLoadManifest,
        *,
        host_key: bytes,
        maximum_age_ms: int = 7 * 86_400_000,
        maximum_future_skew_ms: int = 5_000,
    ) -> None:
        if not isinstance(manifest, MixedLoadManifest):
            raise TypeError("manifest must be MixedLoadManifest")
        if type(host_key) is not bytes or len(host_key) < 32:
            raise ValueError("host_key must be at least 32 bytes")
        if type(maximum_age_ms) is not int or not 60_000 <= maximum_age_ms <= 30 * 86_400_000:
            raise ValueError("invalid maximum evidence age")
        if type(maximum_future_skew_ms) is not int or not 0 <= maximum_future_skew_ms <= 60_000:
            raise ValueError("invalid future clock skew")
        self._manifest = manifest
        self._key = host_key
        self._maximum_age_ms = maximum_age_ms
        self._maximum_future_skew_ms = maximum_future_skew_ms
        self._samples: dict[tuple[str, str], MixedLoadObservation] = {}
        self._sample_ids: set[str] = set()
        self._last_now_ms: int | None = None

    def ingest(
        self,
        observation: MixedLoadObservation,
        receipt: str,
        *,
        now_unix_ms: int,
    ) -> None:
        if not isinstance(observation, MixedLoadObservation):
            raise TypeError("observation must be MixedLoadObservation")
        now = _timestamp(now_unix_ms, "now_unix_ms")
        if self._last_now_ms is not None and now < self._last_now_ms:
            raise ValueError("evaluator clock moved backwards")
        m = self._manifest
        if observation.campaign_id != m.campaign_id or observation.split != m.split:
            raise ValueError("observation is outside the preregistered campaign/split")
        if (observation.hardware_fingerprint != m.hardware_fingerprint
                or observation.workload_sha256 != m.workload_sha256
                or observation.game_build != m.game_build):
            raise ValueError("observation hardware/workload/game build does not match manifest")
        expected_runtime = (m.baseline_runtime_revision if observation.arm == "baseline"
                            else m.candidate_runtime_revision)
        expected_model = (m.baseline_model_revision if observation.arm == "baseline"
                          else m.candidate_model_revision)
        expected_config = (m.baseline_config_sha256 if observation.arm == "baseline"
                           else m.candidate_config_sha256)
        if (observation.runtime_revision != expected_runtime
                or observation.model_revision != expected_model
                or observation.config_sha256 != expected_config):
            raise ValueError("observation revision/configuration does not match manifest")
        age = now - observation.observed_unix_ms
        if age < -self._maximum_future_skew_ms or age > self._maximum_age_ms:
            raise ValueError("stale or future-dated observation")
        if type(receipt) is not str or _SHA.fullmatch(receipt) is None:
            raise PermissionError("invalid host receipt")
        expected = hmac.new(self._key, observation.canonical_bytes(), sha256).hexdigest()
        if not hmac.compare_digest(receipt, expected):
            raise PermissionError("host receipt signature mismatch")
        key = (observation.pair_id, observation.arm)
        if observation.sample_id in self._sample_ids or key in self._samples:
            raise ValueError("duplicate sample or arm in matched pair")
        if len(self._samples) >= _MAX_OBSERVATIONS:
            raise ValueError("campaign observation limit reached")
        other = self._samples.get((observation.pair_id,
                                   "candidate" if observation.arm == "baseline" else "baseline"))
        if other is not None:
            if other.window_ms != observation.window_ms:
                raise ValueError("matched pair measurement windows differ")
            if abs(other.observed_unix_ms - observation.observed_unix_ms) > m.maximum_pair_gap_ms:
                raise ValueError("matched pair exceeds maximum time gap")
        self._samples[key] = observation
        self._sample_ids.add(observation.sample_id)
        self._last_now_ms = now

    def evaluate(self) -> MixedLoadResult:
        pairs: dict[str, dict[str, MixedLoadObservation]] = {}
        for (pair_id, arm), sample in self._samples.items():
            pairs.setdefault(pair_id, {})[arm] = sample
        complete = [
            (rows["baseline"], rows["candidate"])
            for rows in pairs.values()
            if set(rows) == _ARMS
        ]
        incomplete = len(pairs) - len(complete)
        m = self._manifest
        if len(complete) < m.minimum_pairs:
            return MixedLoadResult(
                "insufficient_pairs",
                "not enough complete, independently matched baseline/candidate pairs",
                len(complete), incomplete, m.primary_metric, None, None, (),
            )

        comparisons: list[MetricComparison] = []
        guard_failures: list[str] = []
        primary_p: float | None = None
        primary_improvement: float | None = None
        for name in sorted(_REQUIRED_METRICS):
            unit, direction, tolerance = METRIC_SPECS[name]
            improvements: list[float] = []
            for baseline, candidate in complete:
                b = next(x for x in baseline.metrics if x.name == name)
                c = next(x for x in candidate.metrics if x.name == name)
                if b.unit != c.unit or b.samples < 5 or c.samples < 5:
                    return MixedLoadResult(
                        "contaminated", f"invalid paired metric evidence for {name}",
                        len(complete), incomplete, m.primary_metric, None, None, tuple(comparisons),
                    )
                improvements.append(direction * (float(c.value) - float(b.value)))
            wins = sum(delta > tolerance for delta in improvements)
            losses = sum(delta < -tolerance for delta in improvements)
            ties = len(improvements) - wins - losses
            median_improvement = float(median(improvements))
            summary = MetricComparison(
                name, unit, median_improvement, wins, losses, ties, losses, tolerance,
            )
            comparisons.append(summary)
            if name == m.primary_metric:
                primary_improvement = median_improvement
                primary_p = _upper_binomial_tail(wins, wins + losses)
            # GPU utilization is diagnostic, not monotonic: higher use can mean
            # more useful work rather than worse performance.
            if name not in {"tokens_per_second", "gpu_util_percent_p95"}:
                if losses / len(improvements) > m.maximum_guard_regression_fraction:
                    guard_failures.append(name)

        if guard_failures:
            return MixedLoadResult(
                "regressed",
                "guard metrics regressed beyond the preregistered fraction: " + ", ".join(guard_failures),
                len(complete), incomplete, m.primary_metric, primary_improvement,
                primary_p, tuple(comparisons),
            )
        if (primary_improvement is None or primary_p is None
                or primary_improvement < m.minimum_primary_improvement
                or primary_p > 0.05):
            return MixedLoadResult(
                "no_demonstrated_improvement",
                "primary metric did not meet both the minimum effect and one-sided paired sign-test threshold",
                len(complete), incomplete, m.primary_metric, primary_improvement,
                primary_p, tuple(comparisons),
            )
        return MixedLoadResult(
            "eligible_for_owner_review",
            "primary improvement is supported and no protected mixed-load guard crossed its regression budget",
            len(complete), incomplete, m.primary_metric, primary_improvement,
            primary_p, tuple(comparisons),
        )
