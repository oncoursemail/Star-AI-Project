"""Owner-approved, local-only, read-only OBS WebSocket telemetry collector.

This is the missing transport edge between STAR's existing pure OBS parsers
and the trusted stream-host sampling contract. It polls OBS from a background
host worker; never call poll() from a game, render, or audio callback.

Only GetVersion, GetStreamStatus, GetStats, and GetVideoSettings are used.
The client is pinned to loopback IPv4/port 4455. No OBS write request exists in
this module, and disconnecting STAR never stops an OBS stream or recording.
Passwords are accepted for the connection only and are never persisted or
returned in status/error data.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import threading
import time
import uuid
from typing import Any, Callable, Mapping, cast

from .obs_stats import ObsStatsInterval, ObsStatsWindow, parse_get_stats_response
from .obs_stream_status import (
    ObsStreamStatusInterval,
    ObsStreamStatusWindow,
    parse_get_stream_status_response,
)
from .stream_host_sampler import MetricObservation

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z")
_REQUIRED_METHODS = ("get_version", "get_stats", "get_stream_status", "get_video_settings")


class OBSPackageMissing(RuntimeError):
    """The optional obsws-python desktop dependency is not installed."""


class OBSTelemetryUnavailable(RuntimeError):
    """A fresh, coherent OBS telemetry sample could not be produced."""


def _close_client(client: object | None) -> None:
    """Close only the OBS WebSocket transport; never issue an OBS control RPC."""
    socket = getattr(client, "ws", None)
    close = getattr(socket, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _default_client_factory(**kwargs: Any) -> Any:
    try:
        import obsws_python
    except ImportError as exc:
        raise OBSPackageMissing(
            "OBS telemetry requires STAR's optional Windows desktop dependency obsws-python."
        ) from exc
    return obsws_python.ReqClient(**kwargs)


def _clock_value(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 10**12:
        raise ValueError("host monotonic clock must return bounded integer milliseconds")
    return value


def _integer(value: object, name: str, *, minimum: int = 1, maximum: int = 100_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise OBSTelemetryUnavailable(f"OBS {name} is unavailable or invalid")
    return value


def _response_fields(response: object, aliases: Mapping[str, tuple[str, ...]]) -> dict[str, Any]:
    """Copy only known response fields; obsws-python exposes snake_case attrs()."""
    source: Mapping[str, Any] = {}
    if isinstance(response, Mapping):
        source = response
    else:
        attrs = getattr(response, "attrs", None)
        if callable(attrs):
            try:
                candidate = attrs()
            except Exception:
                candidate = None
            if isinstance(candidate, Mapping):
                source = candidate

    result: dict[str, Any] = {}
    for canonical, names in aliases.items():
        for name in (canonical, *names):
            if name in source:
                result[canonical] = source[name]
                break
            if not isinstance(response, Mapping) and hasattr(response, name):
                result[canonical] = getattr(response, name)
                break
    return result


_STATS_FIELDS = {
    "activeFps": ("active_fps",),
    "averageFrameRenderTime": ("average_frame_render_time",),
    "renderSkippedFrames": ("render_skipped_frames",),
    "renderTotalFrames": ("render_total_frames",),
    "outputSkippedFrames": ("output_skipped_frames",),
    "outputTotalFrames": ("output_total_frames",),
    "cpuUsage": ("cpu_usage",),
    "memoryUsage": ("memory_usage",),
}
_STREAM_FIELDS = {
    "outputActive": ("output_active",),
    "outputReconnecting": ("output_reconnecting",),
    "outputBytes": ("output_bytes",),
    "outputSkippedFrames": ("output_skipped_frames",),
    "outputTotalFrames": ("output_total_frames",),
    "outputCongestion": ("output_congestion",),
    "outputDuration": ("output_duration",),
    "outputTimecode": ("output_timecode",),
}
_VIDEO_FIELDS = {
    "fpsNumerator": ("fps_numerator",),
    "fpsDenominator": ("fps_denominator",),
}


@dataclass(frozen=True)
class OBSHostSample:
    """One bounded sample from OBS plus the two independent interval windows."""

    captured_ms: int
    sampled_ms: int
    sampling_skew_ms: int
    obs_epoch: str
    stream_epoch: str
    output_active: bool
    output_reconnecting: bool
    output_congestion: float | None
    active_fps: float
    target_fps: float
    average_frame_render_time_ms: float
    render_budget_ms: float
    render_time_utilization: float
    render_skip_percent: float | None
    render_skipped_delta: int | None
    render_total_delta: int | None
    output_thread_skip_percent: float | None
    output_thread_skipped_delta: int | None
    output_thread_total_delta: int | None
    output_bytes_per_second: float | None
    stream_output_skipped_delta: int | None
    stream_output_total_delta: int | None
    stats_interval_status: str
    stream_interval_status: str

    @property
    def obs_dropped_pct(self) -> float | None:
        """Worst measured OBS render/output-thread drop percentage.

        Network congestion and reconnecting are deliberately separate signals;
        they are not mislabeled as dropped-frame percentages.
        """
        if (not self.output_active or self.output_reconnecting
                or self.stats_interval_status != "ok"
                or self.stream_interval_status != "ok"):
            return None
        if self.render_skip_percent is None or self.output_thread_skip_percent is None:
            return None
        return max(self.render_skip_percent, self.output_thread_skip_percent)

    def host_observations(self, *, clock_epoch: str) -> dict[str, MetricObservation | None]:
        """Return the existing StreamHostSampler fields without inventing health.

        A baseline, counter reset, reconnect, or missing denominator produces
        obs_dropped_pct=None. While streaming, StreamHostSampler will then fail
        closed instead of treating an unknown OBS interval as zero drops.
        """
        if type(clock_epoch) is not str or not _ID.fullmatch(clock_epoch):
            raise ValueError("clock_epoch must be a bounded opaque host identifier")
        streaming = MetricObservation(
            value=self.output_active,
            captured_ms=self.captured_ms,
            clock_epoch=clock_epoch,
        )
        dropped = self.obs_dropped_pct
        drop_observation = (
            None if dropped is None else MetricObservation(
                value=dropped,
                captured_ms=self.captured_ms,
                clock_epoch=clock_epoch,
            )
        )
        return {"streaming": streaming, "obs_dropped_pct": drop_observation}


class OBSWebSocketHost:
    """Read-only local OBS collector with explicit owner connection consent.

    The owner/desktop host calls connect() after the user enters the OBS
    WebSocket password. A background worker calls poll() (default >=500 ms
    cadence). snapshot() is an in-memory, freshness-checked read with no I/O.
    """

    def __init__(
        self,
        *,
        client_factory: Callable[..., Any] | None = None,
        clock_ms: Callable[[], int] = lambda: time.monotonic_ns() // 1_000_000,
        min_poll_interval_ms: int = 500,
        max_sample_skew_ms: int = 500,
    ) -> None:
        if not callable(clock_ms):
            raise TypeError("clock_ms must be callable")
        if type(min_poll_interval_ms) is not int or not 250 <= min_poll_interval_ms <= 5_000:
            raise ValueError("min_poll_interval_ms must be 250..5000")
        if type(max_sample_skew_ms) is not int or not 50 <= max_sample_skew_ms <= 2_000:
            raise ValueError("max_sample_skew_ms must be 50..2000")
        self._client_factory = client_factory or _default_client_factory
        self._clock = clock_ms
        self._min_poll_ms = min_poll_interval_ms
        self._max_skew_ms = max_sample_skew_ms
        self._lock = threading.RLock()
        self._client: Any | None = None
        self._generation = 0
        self._polling = False
        self._polling_generation: int | None = None
        self._last_poll_ms: int | None = None
        self._last_clock_ms: int | None = None
        self._sample: OBSHostSample | None = None
        self._obs_epoch: str | None = None
        self._stream_epoch: str | None = None
        self._last_state: tuple[bool, bool] | None = None
        self._stats_window = ObsStatsWindow()
        self._stream_window = ObsStreamStatusWindow()
        self._counts = {"poll_ok": 0, "poll_failed": 0, "poll_rejected": 0}

    def _now(self) -> int:
        now = _clock_value(self._clock())
        with self._lock:
            if self._last_clock_ms is not None and now < self._last_clock_ms:
                raise ValueError("host monotonic clock moved backwards")
            self._last_clock_ms = now
        return now

    def _reset_session(self) -> None:
        self._sample = None
        self._last_state = None
        self._stats_window.reset()
        self._stream_window.reset()

    def connect(
        self,
        *,
        password: str,
        confirm: bool = False,
        owner_approved: bool = False,
    ) -> dict[str, Any]:
        if confirm is not True or owner_approved is not True:
            raise PermissionError(
                "Owner confirmation is required to connect to local OBS telemetry."
            )
        if type(password) is not str or not 1 <= len(password) <= 256:
            raise ValueError(
                "Enter the OBS WebSocket password from OBS Tools / WebSocket Server Settings."
            )
        with self._lock:
            if self._client is not None:
                raise RuntimeError("OBS telemetry is already connected.")
        client: Any | None = None
        try:
            client = self._client_factory(
                host="127.0.0.1", port=4455, password=password, timeout=3
            )
            if any(not callable(getattr(client, name, None)) for name in _REQUIRED_METHODS):
                raise RuntimeError("required read-only OBS requests are unavailable")
            client.get_version()
        except OBSPackageMissing:
            _close_client(client)
            raise
        except Exception:
            _close_client(client)
            raise ConnectionError(
                "Could not authenticate to local OBS WebSocket at 127.0.0.1:4455. "
                "Check that OBS is open and its WebSocket password is correct."
            ) from None
        with self._lock:
            self._generation += 1
            self._client = client
            self._obs_epoch = uuid.uuid4().hex[:16]
            self._stream_epoch = uuid.uuid4().hex[:16]
            self._last_poll_ms = None
            self._reset_session()
        return self.status()

    def disconnect(self, *, confirm: bool = False, owner_approved: bool = False) -> dict[str, Any]:
        if confirm is not True or owner_approved is not True:
            raise PermissionError("Owner confirmation is required to disconnect OBS telemetry.")
        with self._lock:
            client = self._client
            self._generation += 1
            self._client = None
            # An in-flight request owns the polling flag until its finally
            # block runs; a replacement connection cannot race that worker.
            self._obs_epoch = None
            self._stream_epoch = None
            self._last_poll_ms = None
            self._reset_session()
        _close_client(client)
        return self.status()

    def poll(self) -> OBSHostSample:
        """Fetch a coherent OBS sample; call only on a low-priority host worker."""
        with self._lock:
            client = self._client
            if client is None:
                raise RuntimeError("Connect to local OBS telemetry first.")
            if self._polling:
                self._counts["poll_rejected"] += 1
                raise RuntimeError("An OBS telemetry poll is already in progress.")
            start = self._now()
            if self._last_poll_ms is not None and start - self._last_poll_ms < self._min_poll_ms:
                self._counts["poll_rejected"] += 1
                raise RuntimeError("OBS telemetry polling is rate-limited.")
            self._last_poll_ms = start
            self._polling = True
            generation = self._generation
            self._polling_generation = generation
            obs_epoch = cast(str, self._obs_epoch)
            stream_epoch = cast(str, self._stream_epoch)

        try:
            # Request order is deliberate: state is observed first so a stream
            # start/reconnect transition can create a fresh counter epoch.
            stream_start_response = client.get_stream_status()
            stream_start_at = self._now()
            stats_response = client.get_stats()
            stats_at = self._now()
            video_response = client.get_video_settings()
            video_at = self._now()
            stream_end_response = client.get_stream_status()
            stream_end_at = self._now()

            stream_start_data = _response_fields(stream_start_response, _STREAM_FIELDS)
            stream_data = _response_fields(stream_end_response, _STREAM_FIELDS)
            stats_data = _response_fields(stats_response, _STATS_FIELDS)
            video_data = _response_fields(video_response, _VIDEO_FIELDS)
            state_start = parse_get_stream_status_response(
                stream_start_data,
                obs_epoch=obs_epoch,
                stream_epoch=stream_epoch,
                sampled_at_ms=stream_start_at,
            )
            state_probe = parse_get_stream_status_response(
                stream_data,
                obs_epoch=obs_epoch,
                stream_epoch=stream_epoch,
                sampled_at_ms=stream_end_at,
            )
            state = (state_probe.output_active, state_probe.output_reconnecting)
            start_state = (state_start.output_active, state_start.output_reconnecting)
            if state != start_state:
                raise OBSTelemetryUnavailable(
                    "OBS output state changed during the telemetry sampling window"
                )
            sample_times = (stream_start_at, stats_at, video_at, stream_end_at)
            skew = max(sample_times) - min(sample_times)
            if skew > self._max_skew_ms:
                raise OBSTelemetryUnavailable("OBS requests exceeded the coherent sampling window")

            numerator = _integer(video_data.get("fpsNumerator"), "fps numerator")
            denominator = _integer(video_data.get("fpsDenominator"), "fps denominator")
            target_fps = numerator / denominator
            if not math.isfinite(target_fps) or not 0.1 <= target_fps <= 1_000:
                raise OBSTelemetryUnavailable("OBS target FPS is outside the supported range")

            with self._lock:
                if generation != self._generation or client is not self._client:
                    raise OBSTelemetryUnavailable("OBS connection changed during sampling")
                if self._last_state is not None and state != self._last_state:
                    self._stream_epoch = uuid.uuid4().hex[:16]
                    stream_epoch = cast(str, self._stream_epoch)
                    self._stats_window.reset()
                    self._stream_window.reset()
                self._last_state = state

                status_snapshot = parse_get_stream_status_response(
                    stream_data,
                    obs_epoch=obs_epoch,
                    stream_epoch=stream_epoch,
                    sampled_at_ms=stream_end_at,
                )
                stats_snapshot = parse_get_stats_response(
                    stats_data,
                    obs_epoch=obs_epoch,
                    stream_epoch=stream_epoch,
                    sampled_at_ms=stats_at,
                )
                stats_interval: ObsStatsInterval = self._stats_window.push(stats_snapshot)
                stream_interval: ObsStreamStatusInterval = self._stream_window.push(status_snapshot)
                # A hidden stop/start can occur between host polls while OBS
                # reports outputActive=True at both ends. Counter rollback is
                # the evidence that the stream epoch changed. Likewise, a
                # GetStats rollback indicates an OBS-process/counter epoch.
                if stats_interval.status in {
                    "counter_reset", "invalid_interval", "inconsistent_counters"
                }:
                    if stats_interval.status == "counter_reset":
                        self._obs_epoch = uuid.uuid4().hex[:16]
                    self._stream_epoch = uuid.uuid4().hex[:16]
                    self._stats_window.reset()
                    self._stream_window.reset()
                elif stream_interval.status in {
                    "counter_reset", "invalid_interval", "state_changed"
                }:
                    self._stream_epoch = uuid.uuid4().hex[:16]
                    self._stats_window.reset()
                captured = min(sample_times)
                sampled = max(sample_times)
                render_skip = (
                    None if stats_interval.render_skip_rate is None
                    else round(stats_interval.render_skip_rate * 100.0, 6)
                )
                output_skip = (
                    None if stats_interval.output_skip_rate is None
                    else round(stats_interval.output_skip_rate * 100.0, 6)
                )
                render_time = stats_snapshot.average_frame_render_time_ms
                render_budget = 1_000.0 / target_fps
                sample = OBSHostSample(
                    captured_ms=captured,
                    sampled_ms=sampled,
                    sampling_skew_ms=skew,
                    obs_epoch=obs_epoch,
                    stream_epoch=stream_epoch,
                    output_active=status_snapshot.output_active,
                    output_reconnecting=status_snapshot.output_reconnecting,
                    output_congestion=status_snapshot.output_congestion,
                    active_fps=stats_snapshot.active_fps,
                    target_fps=target_fps,
                    average_frame_render_time_ms=render_time,
                    render_budget_ms=round(render_budget, 6),
                    render_time_utilization=round(render_time / render_budget, 6),
                    render_skip_percent=render_skip,
                    render_skipped_delta=stats_interval.render_skipped_delta,
                    render_total_delta=stats_interval.render_total_delta,
                    output_thread_skip_percent=output_skip,
                    output_thread_skipped_delta=stats_interval.output_skipped_delta,
                    output_thread_total_delta=stats_interval.output_total_delta,
                    output_bytes_per_second=stream_interval.observed_bytes_per_second,
                    stream_output_skipped_delta=stream_interval.skipped_frames_delta,
                    stream_output_total_delta=stream_interval.total_frames_delta,
                    stats_interval_status=stats_interval.status,
                    stream_interval_status=stream_interval.status,
                )
                self._sample = sample
                self._counts["poll_ok"] += 1
                return sample
        except OBSTelemetryUnavailable:
            with self._lock:
                self._counts["poll_rejected"] += 1
                if generation == self._generation and client is self._client:
                    self._sample = None
                    # Never calculate a later rate across an invalid or
                    # incoherent poll. The next sample establishes baselines.
                    self._last_state = None
                    self._stats_window.reset()
                    self._stream_window.reset()
            raise
        except ValueError:
            with self._lock:
                if generation == self._generation and client is self._client:
                    self._counts["poll_rejected"] += 1
                    self._sample = None
                    self._last_state = None
                    self._stats_window.reset()
                    self._stream_window.reset()
            raise OBSTelemetryUnavailable(
                "OBS returned invalid telemetry or the host monotonic clock regressed"
            ) from None
        except Exception:
            invalidated = False
            with self._lock:
                if generation != self._generation or client is not self._client:
                    self._counts["poll_rejected"] += 1
                    invalidated = True
                else:
                    self._counts["poll_failed"] += 1
                    self._client = None
                    self._generation += 1
                    self._reset_session()
            _close_client(client)
            if invalidated:
                raise OBSTelemetryUnavailable(
                    "OBS connection changed during sampling"
                ) from None
            raise ConnectionError(
                "OBS telemetry request failed. Reconnect from STAR after checking OBS WebSocket."
            ) from None
        finally:
            with self._lock:
                if self._polling_generation == generation:
                    self._polling = False
                    self._polling_generation = None

    def snapshot(self, *, max_age_ms: int = 1_500) -> OBSHostSample | None:
        if type(max_age_ms) is not int or not 100 <= max_age_ms <= 10_000:
            raise ValueError("max_age_ms must be 100..10000")
        with self._lock:
            sample = self._sample
            if sample is None:
                return None
            now = self._now()
            if now < sample.sampled_ms or now - sample.sampled_ms > max_age_ms:
                return None
            return sample

    def status(self) -> dict[str, Any]:
        """Content-free health only; never exposes password, scenes or source names."""
        with self._lock:
            sample_age = None
            if self._sample is not None:
                try:
                    sample_age = max(0, self._now() - self._sample.sampled_ms)
                except ValueError:
                    sample_age = None
            return {
                "connected": self._client is not None,
                "polling": self._polling,
                "sample_ready": self._sample is not None,
                "sample_age_ms": sample_age,
                "stream_active": None if self._sample is None else self._sample.output_active,
                **self._counts,
            }


__all__ = [
    "OBSHostSample",
    "OBSWebSocketHost",
    "OBSPackageMissing",
    "OBSTelemetryUnavailable",
]
