"""Metadata-only adapter for LiveKit's public end-of-turn benchmark artifacts.

The adapter consumes normalized span-set and prediction rows. It never loads audio,
transcripts, model credentials, or raw conversation content. It preserves short-turn
rows with no observed EoT as right-censored evidence instead of inventing a final turn.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import math
from numbers import Integral, Real

from .stream_turntaking_eval import (
    EndOfTurnScore,
    PauseKind,
    ScoreSource,
    SilenceSpan,
    TurnPolicy,
    TurnPolicyResult,
    TurnTakingSweep,
    evaluate_turn_policy,
    sweep_turn_policies,
)

_MAX_SPAN_ROWS = 20_000
_MAX_PREDICTION_ROWS = 1_000_000
_MAX_POINTS_PER_SPAN = 2_048
_MAX_TOTAL_POINTS = 1_000_000
_MAX_DURATION_MS = 120_000
_EPSILON_SECONDS = 0.002


@dataclass(frozen=True)
class _SpanMeta:
    row_id: str
    span_index: int
    language: str
    cohort: str
    label: str
    start_s: float
    duration_s: float
    duration_ms: int
    retained: bool


@dataclass(frozen=True)
class EotBenchAdaptation:
    """Content-free conversion summary; source row IDs are never returned."""

    spans: tuple[SilenceSpan, ...]
    source_turn_count: int
    source_span_count: int
    retained_turn_count: int
    retained_span_count: int
    retained_hold_span_count: int
    retained_eot_span_count: int
    censored_turn_count: int
    excluded_hold_span_count: int
    prediction_row_count: int
    score_point_count: int
    missing_score_span_count: int
    language_count: int
    cohort_count: int


def _records(
    rows: Sequence[Mapping[str, object]],
    *,
    name: str,
    maximum: int,
    allow_empty: bool,
) -> tuple[Mapping[str, object], ...]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be a sequence of mapping rows")
    if len(rows) > maximum:
        raise ValueError(f"{name} exceeds its bounded row limit")
    if not rows and not allow_empty:
        raise ValueError(f"{name} must not be empty")
    result = tuple(rows)
    if any(not isinstance(row, Mapping) for row in result):
        raise TypeError(f"every {name} entry must be a mapping")
    return result


def _text(value: object, *, name: str, maximum: int = 512) -> str:
    if type(value) is not str:
        raise ValueError(f"{name} must be text")
    result = value.strip()
    if not result or len(result) > maximum or any(ord(char) < 32 for char in result):
        raise ValueError(f"{name} must be nonempty bounded text")
    return result


def _index(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("span_index must be a nonnegative integer")
    result = int(value)
    if not 0 <= result <= 100_000:
        raise ValueError("span_index is outside the supported range")
    return result


def _number(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _cohort(value: object) -> str:
    if value is None:
        return "general"
    if isinstance(value, Real) and not isinstance(value, bool) and math.isnan(float(value)):
        return "general"
    return _text(value, name="cohort", maximum=64).lower()


def _score(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("p_eot must be a number or missing")
    result = float(value)
    if math.isnan(result):
        return None
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError("p_eot must be finite and in 0..1")
    return result


def _opaque(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def adapt_eot_bench_predictions(
    span_rows: Sequence[Mapping[str, object]],
    prediction_rows: Sequence[Mapping[str, object]],
    *,
    min_hold_span_duration_ms: int = 200,
    max_hold_span_duration_ms: int = 5_000,
) -> EotBenchAdaptation:
    """Convert eot-bench span_set/predictions rows into STAR's causal pause types.

    Input rows follow LiveKit eot-bench's public artifact schema:
    span rows contain id/language/span_index/label/start/end/duration and optional
    cohort; prediction rows contain id/language/span_index/label/timestamp/
    silence_dur/p_eot. Values should be ordinary mapping records, e.g.
    DataFrame.to_dict("records").

    The default HOLD duration filter mirrors eot-bench's policy-metric defaults.
    EOT spans are always retained. A turn with only HOLD spans is preserved as
    right-censored: its pauses contribute to false-cutoff measurement, but it
    contributes neither a fabricated final-turn miss nor invented endpoint latency.
    """
    if type(min_hold_span_duration_ms) is not int or type(max_hold_span_duration_ms) is not int:
        raise ValueError("hold-span duration limits must be integers")
    if not 1 <= min_hold_span_duration_ms <= max_hold_span_duration_ms <= _MAX_DURATION_MS:
        raise ValueError("hold-span duration limits must be ordered and within 1..120000 ms")

    spans_input = _records(
        span_rows, name="span_rows", maximum=_MAX_SPAN_ROWS, allow_empty=False
    )
    predictions_input = _records(
        prediction_rows, name="prediction_rows",
        maximum=_MAX_PREDICTION_ROWS, allow_empty=True,
    )

    metadata: dict[tuple[str, int], _SpanMeta] = {}
    turn_metadata: dict[str, tuple[str, str]] = {}
    excluded_hold_count = 0

    for row in spans_input:
        row_id = _text(row.get("id"), name="span id")
        language = _text(row.get("language"), name="language", maximum=32).lower()
        cohort = _cohort(row.get("cohort"))
        span_index = _index(row.get("span_index"))
        label = _text(row.get("label"), name="span label", maximum=16).lower()
        if label not in {"hold", "eot"}:
            raise ValueError("span label must be hold or eot")

        start_s = _number(row.get("start"), name="span start")
        end_s = _number(row.get("end"), name="span end")
        duration_s = _number(row.get("duration"), name="span duration")
        if start_s < 0.0 or end_s <= start_s or duration_s <= 0.0:
            raise ValueError("span timing must be positive and ordered")
        if abs((end_s - start_s) - duration_s) > _EPSILON_SECONDS:
            raise ValueError("span duration does not match start/end")
        duration_ms = int(round(duration_s * 1_000.0))
        if not 1 <= duration_ms <= _MAX_DURATION_MS:
            raise ValueError("span duration is outside the supported range")

        previous = turn_metadata.get(row_id)
        current = (language, cohort)
        if previous is not None and previous != current:
            raise ValueError("one turn cannot change language or cohort")
        turn_metadata[row_id] = current

        key = (row_id, span_index)
        if key in metadata:
            raise ValueError("duplicate span-set row")
        retained = (
            label == "eot"
            or min_hold_span_duration_ms <= duration_ms <= max_hold_span_duration_ms
        )
        if label == "hold" and not retained:
            excluded_hold_count += 1
        metadata[key] = _SpanMeta(
            row_id=row_id,
            span_index=span_index,
            language=language,
            cohort=cohort,
            label=label,
            start_s=start_s,
            duration_s=duration_s,
            duration_ms=duration_ms,
            retained=retained,
        )

    scores_by_span: dict[tuple[str, int], list[EndOfTurnScore]] = defaultdict(list)
    seen_elapsed: dict[tuple[str, int], set[int]] = defaultdict(set)
    score_point_count = 0

    for row in predictions_input:
        row_id = _text(row.get("id"), name="prediction id")
        language = _text(row.get("language"), name="prediction language", maximum=32).lower()
        span_index = _index(row.get("span_index"))
        key = (row_id, span_index)
        span = metadata.get(key)
        if span is None:
            raise ValueError("prediction references an unknown span")
        if language != span.language:
            raise ValueError("prediction language does not match its span")
        label = _text(row.get("label"), name="prediction label", maximum=16).lower()
        if label != span.label:
            raise ValueError("prediction label does not match its span")

        timestamp_s = _number(row.get("timestamp"), name="prediction timestamp")
        silence_s = _number(row.get("silence_dur"), name="silence duration")
        if timestamp_s < 0.0 or silence_s < 0.0:
            raise ValueError("prediction timing must be nonnegative")
        if abs(timestamp_s - (span.start_s + silence_s)) > _EPSILON_SECONDS:
            raise ValueError("prediction timestamp is not aligned to its silence span")
        if silence_s > span.duration_s + _EPSILON_SECONDS:
            raise ValueError("prediction exceeds its observed silence span")

        score = _score(row.get("p_eot"))
        if score is None or not span.retained:
            continue

        elapsed_ms = int(round(silence_s * 1_000.0))
        if elapsed_ms > span.duration_ms:
            if silence_s <= span.duration_s + 0.001:
                elapsed_ms = span.duration_ms
            else:
                raise ValueError("prediction score exceeds its observed silence span")
        if elapsed_ms in seen_elapsed[key]:
            raise ValueError("duplicate prediction time within a span")
        seen_elapsed[key].add(elapsed_ms)
        scores_by_span[key].append(EndOfTurnScore(elapsed_ms, score))
        score_point_count += 1
        if len(scores_by_span[key]) > _MAX_POINTS_PER_SPAN:
            raise ValueError("per-span prediction point limit exceeded")
        if score_point_count > _MAX_TOTAL_POINTS:
            raise ValueError("total prediction point limit exceeded")

    converted: list[SilenceSpan] = []
    retained_turn_ids: set[str] = set()
    final_turn_ids: set[str] = set()
    languages: set[str] = set()
    cohorts: set[str] = set()
    hold_count = 0
    eot_count = 0
    missing_score_count = 0

    for key, meta in metadata.items():
        if not meta.retained:
            continue
        row_id, span_index = key
        turn_id = _opaque("turn", row_id)
        span_id = _opaque("span", f"{row_id}\0{span_index}")
        environment_id = _opaque("env", f"{meta.language}\0{meta.cohort}")
        points = tuple(sorted(scores_by_span.get(key, ()), key=lambda item: item.elapsed_ms))
        if not points:
            missing_score_count += 1
        kind = PauseKind.HOLD if meta.label == "hold" else PauseKind.END_OF_TURN
        if kind is PauseKind.HOLD:
            hold_count += 1
        else:
            eot_count += 1
            final_turn_ids.add(turn_id)
        retained_turn_ids.add(turn_id)
        languages.add(meta.language)
        cohorts.add(meta.cohort)
        converted.append(SilenceSpan(
            span_id=span_id,
            turn_id=turn_id,
            environment_id=environment_id,
            kind=kind,
            duration_ms=meta.duration_ms,
            scores=points,
        ))

    if not converted:
        raise ValueError("no spans remain after the hold-duration filters")

    return EotBenchAdaptation(
        spans=tuple(converted),
        source_turn_count=len(turn_metadata),
        source_span_count=len(metadata),
        retained_turn_count=len(retained_turn_ids),
        retained_span_count=len(converted),
        retained_hold_span_count=hold_count,
        retained_eot_span_count=eot_count,
        censored_turn_count=len(retained_turn_ids - final_turn_ids),
        excluded_hold_span_count=excluded_hold_count,
        prediction_row_count=len(predictions_input),
        score_point_count=score_point_count,
        missing_score_span_count=missing_score_count,
        language_count=len(languages),
        cohort_count=len(cohorts),
    )


def evaluate_eot_bench_policy(
    adaptation: EotBenchAdaptation,
    policy: TurnPolicy,
    *,
    score_source: ScoreSource = ScoreSource.MODEL,
) -> TurnPolicyResult:
    """Evaluate complete and right-censored turns without inventing EOT labels."""
    if not isinstance(adaptation, EotBenchAdaptation):
        raise TypeError("adaptation must be EotBenchAdaptation")
    return evaluate_turn_policy(
        adaptation.spans,
        policy,
        score_source=score_source,
        allow_censored_turns=True,
    )


def sweep_eot_bench_policies(
    adaptation: EotBenchAdaptation,
    *,
    thresholds: Sequence[float],
    action_delays_ms: Sequence[int],
    timeouts_ms: Sequence[int],
    include_silence_baseline: bool = True,
) -> TurnTakingSweep:
    """Sweep the same causal policy grid across complete and censored turns."""
    if not isinstance(adaptation, EotBenchAdaptation):
        raise TypeError("adaptation must be EotBenchAdaptation")
    return sweep_turn_policies(
        adaptation.spans,
        thresholds=thresholds,
        action_delays_ms=action_delays_ms,
        timeouts_ms=timeouts_ms,
        include_silence_baseline=include_silence_baseline,
        allow_censored_turns=True,
    )


__all__ = [
    "EotBenchAdaptation",
    "adapt_eot_bench_predictions",
    "evaluate_eot_bench_policy",
    "sweep_eot_bench_policies",
]
