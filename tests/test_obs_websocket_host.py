from __future__ import annotations

import threading

import pytest

from star.obs_websocket_host import (
    OBSWebSocketHost,
    OBSTelemetryUnavailable,
)


class Clock:
    def __init__(self, start=1_000):
        self.value = start

    def __call__(self):
        value = self.value
        self.value += 10
        return value

    def advance(self, ms):
        self.value += ms


class FakeSocket:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.ws = FakeSocket()
        self.active = True
        self.reconnecting = False
        self.congestion = 0.0
        self.bytes = 1_000_000
        self.stream_skipped = 10
        self.stream_total = 1_000
        self.render_skipped = 5
        self.render_total = 1_000
        self.output_skipped = 8
        self.output_total = 1_000
        self.fps_num = 60_000
        self.fps_den = 1_001
        self.calls = []
        self.stopped = False

    def get_version(self):
        self.calls.append("version")
        return {}

    def get_stream_status(self):
        self.calls.append("stream")
        return {
            "outputActive": self.active,
            "outputReconnecting": self.reconnecting,
            "outputBytes": self.bytes,
            "outputSkippedFrames": self.stream_skipped,
            "outputTotalFrames": self.stream_total,
            "outputCongestion": self.congestion,
            "outputDuration": 999999999,
            "outputTimecode": "99:99:99.999",
            "sourceName": "must-not-escape",
        }

    def get_stats(self):
        self.calls.append("stats")
        return {
            "activeFps": 59.8,
            "averageFrameRenderTime": 5.0,
            "renderSkippedFrames": self.render_skipped,
            "renderTotalFrames": self.render_total,
            "outputSkippedFrames": self.output_skipped,
            "outputTotalFrames": self.output_total,
            "cpuUsage": 4.0,
            "memoryUsage": 512.0,
            "secret": "must-not-escape",
        }

    def get_video_settings(self):
        self.calls.append("video")
        return {
            "fpsNumerator": self.fps_num,
            "fpsDenominator": self.fps_den,
            "width": 1920,
        }


def build(*, clock=None, client=None, min_poll=250, skew=500):
    clock = clock or Clock()
    client = client or FakeClient()
    seen = {}

    def factory(**kwargs):
        seen.update(kwargs)
        return client

    host = OBSWebSocketHost(
        client_factory=factory,
        clock_ms=clock,
        min_poll_interval_ms=min_poll,
        max_sample_skew_ms=skew,
    )
    return host, client, clock, seen


def connect(host):
    return host.connect(password="secret-not-returned", confirm=True, owner_approved=True)


def test_connect_is_owner_confirmed_and_loopback_only():
    host, client, clock, seen = build()
    with pytest.raises(PermissionError):
        host.connect(password="pw")
    connect(host)
    assert seen == {
        "host": "127.0.0.1",
        "port": 4455,
        "password": "secret-not-returned",
        "timeout": 3,
    }
    assert client.calls == ["version"]


def test_connect_rejects_bad_password_without_calling_factory():
    host, client, clock, seen = build()
    with pytest.raises(ValueError):
        host.connect(password="", confirm=True, owner_approved=True)
    assert seen == {}


def test_connect_requires_all_read_only_request_methods():
    class Incomplete:
        def get_version(self):
            return {}

    host = OBSWebSocketHost(client_factory=lambda **kw: Incomplete(), clock_ms=Clock())
    with pytest.raises(ConnectionError):
        connect(host)


def test_poll_uses_only_read_only_requests_and_reports_rational_fps():
    host, client, clock, seen = build()
    connect(host)
    sample = host.poll()
    assert client.calls == ["version", "stream", "stats", "video", "stream"]
    assert sample.output_active is True
    assert sample.target_fps == pytest.approx(60000 / 1001)
    assert sample.render_budget_ms == pytest.approx(1000 / (60000 / 1001))
    assert sample.stats_interval_status == "baseline"
    assert sample.stream_interval_status == "baseline"
    assert sample.obs_dropped_pct is None


def test_second_sample_computes_worst_render_or_output_thread_drop_rate():
    host, client, clock, seen = build()
    connect(host)
    host.poll()
    clock.advance(600)
    client.render_skipped += 1
    client.render_total += 60
    client.output_skipped += 3
    client.output_total += 60
    client.bytes += 100_000
    client.stream_skipped += 1
    client.stream_total += 60
    second = host.poll()
    assert second.render_skip_percent == pytest.approx(100 / 60)
    assert second.output_thread_skip_percent == pytest.approx(300 / 60)
    assert second.render_skipped_delta == 1
    assert second.render_total_delta == 60
    assert second.output_thread_skipped_delta == 3
    assert second.output_thread_total_delta == 60
    assert second.obs_dropped_pct == pytest.approx(5.0)
    assert second.output_bytes_per_second == pytest.approx(100_000_000 / 650, rel=0.02)
    assert second.stream_output_skipped_delta == 1
    assert second.stream_output_total_delta == 60


def test_congestion_null_is_unknown_not_zero():
    host, client, clock, seen = build()
    connect(host)
    client.congestion = None
    sample = host.poll()
    assert sample.output_congestion is None


def test_stream_start_changes_epoch_and_requires_new_baseline():
    host, client, clock, seen = build()
    connect(host)
    host.poll()
    clock.advance(600)
    client.active = False
    inactive = host.poll()
    assert inactive.output_active is False
    clock.advance(600)
    client.active = True
    started = host.poll()
    assert started.stream_epoch != inactive.stream_epoch
    assert started.stats_interval_status == "baseline"
    assert started.stream_interval_status == "baseline"
    assert started.obs_dropped_pct is None


def test_reconnect_transition_discards_both_intervals():
    host, client, clock, seen = build()
    connect(host)
    host.poll()
    clock.advance(600)
    client.reconnecting = True
    reconnecting = host.poll()
    assert reconnecting.output_reconnecting is True
    assert reconnecting.obs_dropped_pct is None
    assert reconnecting.stats_interval_status == "baseline"
    assert reconnecting.stream_interval_status == "baseline"


def test_output_inactive_never_exports_drop_metric():
    host, client, clock, seen = build()
    connect(host)
    client.active = False
    sample = host.poll()
    obs = sample.host_observations(clock_epoch="boot-1")
    assert obs["streaming"].value is False
    assert obs["obs_dropped_pct"] is None


def test_host_sampler_bridge_exports_only_measured_drop_rate():
    host, client, clock, seen = build()
    connect(host)
    host.poll()
    clock.advance(600)
    client.render_total += 60
    client.output_total += 60
    client.stream_total += 60
    client.bytes += 50_000
    sample = host.poll()
    observations = sample.host_observations(clock_epoch="boot-1")
    assert observations["streaming"].value is True
    assert observations["obs_dropped_pct"].value == 0.0
    assert observations["obs_dropped_pct"].captured_ms == sample.captured_ms


def test_host_bridge_rejects_invalid_clock_epoch():
    host, client, clock, seen = build()
    connect(host)
    sample = host.poll()
    with pytest.raises(ValueError):
        sample.host_observations(clock_epoch="bad epoch")


def test_poll_is_rate_limited_without_second_rpc():
    host, client, clock, seen = build()
    connect(host)
    host.poll()
    before = len(client.calls)
    with pytest.raises(RuntimeError, match="rate-limited"):
        host.poll()
    assert len(client.calls) == before


def test_snapshot_is_memory_only_and_expires():
    host, client, clock, seen = build()
    connect(host)
    sample = host.poll()
    before = len(client.calls)
    assert host.snapshot() == sample
    assert len(client.calls) == before
    clock.advance(2_000)
    assert host.snapshot() is None
    assert len(client.calls) == before


def test_status_is_content_free_and_does_not_poll():
    host, client, clock, seen = build()
    connect(host)
    before = len(client.calls)
    status = host.status()
    assert status["connected"] is True
    assert "password" not in status and "secret" not in status and "sourceName" not in status
    assert len(client.calls) == before


def test_disconnect_does_not_stop_stream_or_recording():
    host, client, clock, seen = build()
    connect(host)
    host.poll()
    host.disconnect(confirm=True, owner_approved=True)
    assert host.status()["connected"] is False
    assert client.active is True
    assert client.stopped is False
    assert client.ws.closed is True
    assert not any("stop" in call for call in client.calls)


def test_transport_failure_is_sanitized_and_drops_connection():
    host, client, clock, seen = build()
    connect(host)
    client.get_stats = lambda: (_ for _ in ()).throw(RuntimeError("secret-not-returned"))
    with pytest.raises(ConnectionError) as error:
        host.poll()
    assert "secret-not-returned" not in str(error.value)
    assert host.status()["connected"] is False


def test_invalid_response_clears_sample_and_reestablishes_baseline():
    host, client, clock, seen = build()
    connect(host)
    host.poll()
    clock.advance(600)
    client.fps_num = 0
    with pytest.raises(OBSTelemetryUnavailable):
        host.poll()
    assert host.snapshot() is None
    client.fps_num = 60_000
    clock.advance(600)
    sample = host.poll()
    assert sample.stats_interval_status == "baseline"


def test_sampling_skew_is_bounded():
    values = iter([1000, 1010, 2000, 2010, 2020, 2030])
    clock = lambda: next(values)
    host, client, _, seen = build(clock=clock, skew=100)
    connect(host)
    with pytest.raises(OBSTelemetryUnavailable, match="coherent sampling"):
        host.poll()
    assert host.snapshot() is None


def test_invalid_counter_reset_does_not_become_zero_drop():
    host, client, clock, seen = build()
    connect(host)
    host.poll()
    clock.advance(600)
    client.render_skipped = 1
    client.render_total = 10
    client.output_skipped = 1
    client.output_total = 10
    client.bytes = 10
    client.stream_skipped = 1
    client.stream_total = 10
    reset = host.poll()
    assert reset.obs_dropped_pct is None


def test_fractional_or_invalid_video_fps_is_rejected():
    host, client, clock, seen = build()
    connect(host)
    client.fps_den = 0
    with pytest.raises(OBSTelemetryUnavailable):
        host.poll()


def test_nonlocal_host_cannot_be_selected_by_caller():
    host, client, clock, seen = build()
    connect(host)
    assert seen["host"] == "127.0.0.1"
    assert "host" not in host.status()


def test_sample_does_not_copy_unallowlisted_obs_fields():
    host, client, clock, seen = build()
    connect(host)
    sample = host.poll()
    assert not hasattr(sample, "secret")
    assert not hasattr(sample, "sourceName")
    assert not hasattr(sample, "width")


def test_connection_requires_explicit_disconnect_before_reconnect():
    host, client, clock, seen = build()
    connect(host)
    with pytest.raises(RuntimeError, match="already connected"):
        connect(host)


def test_minimum_poll_interval_and_skew_configuration_are_bounded():
    with pytest.raises(ValueError):
        OBSWebSocketHost(min_poll_interval_ms=100)
    with pytest.raises(ValueError):
        OBSWebSocketHost(max_sample_skew_ms=10)


def test_host_observation_uses_oldest_measurement_timestamp():
    host, client, clock, seen = build()
    connect(host)
    sample = host.poll()
    assert sample.captured_ms == sample.sampled_ms - sample.sampling_skew_ms
    assert sample.sampling_skew_ms >= 0


def test_disconnect_and_reconnect_during_inflight_poll_do_not_clear_new_session():
    entered = threading.Event()
    release = threading.Event()

    class BlockingClient(FakeClient):
        def get_stream_status(self):
            entered.set()
            assert release.wait(2.0)
            return super().get_stream_status()

    old_client = BlockingClient()
    new_client = FakeClient()
    clients = iter([old_client, new_client])
    clock = Clock()
    host = OBSWebSocketHost(client_factory=lambda **kwargs: next(clients), clock_ms=clock)
    connect(host)
    errors = []

    def run_poll():
        try:
            host.poll()
        except Exception as exc:  # expected: disconnect invalidates the in-flight generation
            errors.append(exc)

    worker = threading.Thread(target=run_poll)
    worker.start()
    assert entered.wait(2.0)
    host.disconnect(confirm=True, owner_approved=True)
    connect(host)
    release.set()
    worker.join(2.0)
    assert not worker.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], OBSTelemetryUnavailable)
    assert host.status()["connected"] is True
    assert host.status()["polling"] is False
    assert host.poll().output_active is True


def test_obsws_python_attrs_snake_case_responses_are_normalized():
    class AttrsResponse:
        def __init__(self, **fields):
            self._fields = fields

        def attrs(self):
            return dict(self._fields)

    class AttrsClient(FakeClient):
        def get_stream_status(self):
            self.calls.append("stream")
            return AttrsResponse(
                output_active=self.active,
                output_reconnecting=self.reconnecting,
                output_bytes=self.bytes,
                output_skipped_frames=self.stream_skipped,
                output_total_frames=self.stream_total,
                output_congestion=self.congestion,
            )

        def get_stats(self):
            self.calls.append("stats")
            return AttrsResponse(
                active_fps=59.8,
                average_frame_render_time=5.0,
                render_skipped_frames=self.render_skipped,
                render_total_frames=self.render_total,
                output_skipped_frames=self.output_skipped,
                output_total_frames=self.output_total,
            )

        def get_video_settings(self):
            self.calls.append("video")
            return AttrsResponse(fps_numerator=60_000, fps_denominator=1_001)

    client = AttrsClient()
    host = OBSWebSocketHost(client_factory=lambda **kwargs: client, clock_ms=Clock())
    connect(host)
    sample = host.poll()
    assert sample.active_fps == pytest.approx(59.8)
    assert sample.target_fps == pytest.approx(60_000 / 1_001)


def test_stream_state_change_inside_one_poll_invalidates_sample():
    class FlippingClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.status_calls = 0

        def get_stream_status(self):
            self.status_calls += 1
            self.active = self.status_calls == 1
            return super().get_stream_status()

    client = FlippingClient()
    host = OBSWebSocketHost(client_factory=lambda **kwargs: client, clock_ms=Clock())
    connect(host)
    with pytest.raises(OBSTelemetryUnavailable, match="state changed"):
        host.poll()
    assert host.snapshot() is None
    assert host.status()["connected"] is True


def test_network_congestion_is_not_mislabeled_as_frame_drops():
    host, client, clock, seen = build()
    connect(host)
    host.poll()
    clock.advance(600)
    client.congestion = 0.95
    client.render_total += 60
    client.output_total += 60
    client.stream_total += 60
    client.bytes += 50_000
    sample = host.poll()
    assert sample.output_congestion == pytest.approx(0.95)
    assert sample.obs_dropped_pct == 0.0


def test_hidden_stream_restart_counter_rollback_rebaselines_stats():
    host, client, clock, seen = build()
    connect(host)
    first = host.poll()
    clock.advance(600)
    client.bytes = 10
    client.stream_skipped = 0
    client.stream_total = 10
    client.render_total += 60
    client.output_total += 60
    second = host.poll()
    assert second.stream_interval_status == "counter_reset"
    assert second.obs_dropped_pct is None

    clock.advance(600)
    client.bytes += 50_000
    client.stream_total += 60
    client.render_total += 60
    client.output_total += 60
    third = host.poll()
    assert third.stream_epoch != second.stream_epoch
    assert third.stream_interval_status == "epoch_changed"
    assert third.stats_interval_status == "baseline"
    assert third.obs_dropped_pct is None

    clock.advance(600)
    client.bytes += 50_000
    client.stream_total += 60
    client.render_total += 60
    client.output_total += 60
    fourth = host.poll()
    assert fourth.stream_interval_status == "ok"
    assert fourth.stats_interval_status == "ok"
    assert fourth.obs_dropped_pct == 0.0


def test_obs_stats_counter_rollback_creates_new_process_epoch():
    host, client, clock, seen = build()
    connect(host)
    initial = host.poll()
    clock.advance(600)
    client.render_skipped = 0
    client.render_total = 10
    client.output_skipped = 0
    client.output_total = 10
    client.bytes += 50_000
    client.stream_total += 60
    reset = host.poll()
    assert reset.stats_interval_status == "counter_reset"
    assert reset.obs_dropped_pct is None

    clock.advance(600)
    client.render_total += 60
    client.output_total += 60
    client.stream_total += 60
    client.bytes += 50_000
    baseline = host.poll()
    assert baseline.obs_epoch != reset.obs_epoch
    assert baseline.stats_interval_status == "baseline"
    assert baseline.obs_dropped_pct is None

    clock.advance(600)
    client.render_total += 60
    client.output_total += 60
    client.stream_total += 60
    client.bytes += 50_000
    recovered = host.poll()
    assert recovered.stats_interval_status == "ok"
    assert recovered.stream_interval_status == "ok"
    assert recovered.obs_dropped_pct == 0.0
