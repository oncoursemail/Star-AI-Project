"""Real microphone and loudspeaker through the optional `sounddevice` package (PortAudio).

Physical device streams are not opened in automated tests; callback accounting is tested with synthetic
PortAudio status flags. The speaker follows the same interface as the virtual device in filecall.py, so the
call logic above it is identical.
"""
from __future__ import annotations

import collections
import logging
import math
import queue
import threading
import time

from .pcm import FRAME_SAMPLES, SAMPLE_RATE
from .playback import PlaybackSnapshot, PlaybackTelemetry, estimate_output_time

log = logging.getLogger(__name__)

# Sixteen 32 ms frames cap stale microphone backlog at roughly half a second.
MICROPHONE_QUEUE_FRAMES = 16

# Speaker metering is diagnostic/echo-gate telemetry, never part of PCM delivery.
# Keep its queue bounded: losing an old meter sample is safer than delaying audio.
_LEVEL_QUEUE_CAPACITY = 64
_LEVEL_HISTORY_CAPACITY = 64
_LEVEL_WINDOW_S = 0.4
_LEVEL_WORKER_POLL_S = 0.01


def _pcm_rms(pcm: bytes) -> float:
    """RMS of native-endian PCM16; deliberately runs on the meter worker, not PortAudio."""
    if len(pcm) < 2 or len(pcm) % 2:
        return 0.0
    samples = memoryview(pcm).cast("h")
    if not samples:
        return 0.0
    mean_square = sum(sample * sample for sample in samples) / len(samples)
    return math.sqrt(mean_square) / 32768.0


def _sounddevice():
    try:
        import sounddevice
    except (ImportError, OSError) as exc:
        log.warning("Audio devices unavailable (%s); install with: pip install -r requirements-voice.txt", exc)
        raise RuntimeError("Voice features are not set up on this computer yet.") from exc
    return sounddevice


def _device(value):
    if value in (None, ""):
        return None
    return int(value) if str(value).isdigit() else str(value)


def list_devices() -> list[dict]:
    """Microphones and speakers as plain dicts (for the settings screen)."""
    sd = _sounddevice()
    default_in, default_out = sd.default.device
    # Windows lists every device once per audio API (MME, DirectSound, WASAPI, ...). Show only the default
    # API's copies: that is the one the call opens, and it converts sample rates by itself.
    try:
        host_api = sd.query_devices(default_in if default_in >= 0 else default_out)["hostapi"]
    except Exception:
        host_api = None
    found = []
    for index, info in enumerate(sd.query_devices()):
        if host_api is not None and info["hostapi"] != host_api:
            continue
        if info["max_input_channels"] > 0:
            found.append({"index": index, "kind": "input", "name": info["name"], "default": index == default_in})
        if info["max_output_channels"] > 0:
            found.append({"index": index, "kind": "output", "name": info["name"], "default": index == default_out})
    return found


class Microphone:
    """Default (or chosen) microphone as an iterator of 32 ms, 16 kHz, mono PCM16 frames."""

    def __init__(self, device=None) -> None:
        sd = _sounddevice()
        self._frames: queue.Queue = queue.Queue(maxsize=MICROPHONE_QUEUE_FRAMES)
        self._closed = threading.Event()
        self.dropped = 0
        self._stats_lock = threading.Lock()
        self._input_overflows = 0
        self._input_underflows = 0
        self._stream = sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=FRAME_SAMPLES, channels=1, dtype="int16",
                                         device=_device(device), callback=self._callback)

    def _callback(self, data, _frames, _time, status) -> None:
        # PortAudio reports device-level loss separately from our bounded Python queue.
        # Count both, but never log or retain microphone samples in diagnostics.
        with self._stats_lock:
            if getattr(status, "input_overflow", False):
                self._input_overflows += 1
            if getattr(status, "input_underflow", False):
                self._input_underflows += 1
        frame = bytes(data)
        try:
            self._frames.put_nowait(frame)
            return
        except queue.Full:
            # This is a live conversation, not an archival recorder. Preserve freshness:
            # evict the oldest stale frame and enqueue the newest audio instead of letting
            # the consumer fall seconds behind the person speaking.
            pass
        try:
            self._frames.get_nowait()
        except queue.Empty:
            # The consumer may have freed a slot between Full and get_nowait.
            pass
        else:
            with self._stats_lock:
                self.dropped += 1
        try:
            self._frames.put_nowait(frame)
        except queue.Full:
            # Defensive fallback for an unexpected competing producer.
            with self._stats_lock:
                self.dropped += 1

    def diagnostics(self) -> dict:
        """Aggregate device health only; no audio, transcript, or device identity is returned."""
        with self._stats_lock:
            return {
                "input_overflows": self._input_overflows,
                "input_underflows": self._input_underflows,
                "queue_drops": self.dropped,
                "queued_frames": self._frames.qsize(),
                "queue_capacity_frames": self._frames.maxsize,
                "queue_capacity_seconds": self._frames.maxsize * FRAME_SAMPLES / SAMPLE_RATE,
            }

    def __enter__(self) -> "Microphone":
        self._stream.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        self._closed.set()
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass

    def __iter__(self):
        while not self._closed.is_set():
            try:
                yield self._frames.get(timeout=0.2)
            except queue.Empty:
                continue


class SoundSpeaker:
    """Interruptible PortAudio speaker with bounded asynchronous output-level metering."""

    def __init__(self, sample_rate: int = 24000, device=None) -> None:
        sd = _sounddevice()
        self.sample_rate = sample_rate
        self._lock = threading.Lock()
        self._buffer = bytearray()
        self._played = 0
        self._output_underflows = 0
        self._output_overflows = 0
        self._playback = PlaybackTelemetry()

        self._levels: collections.deque[tuple[float, float]] = collections.deque(
            maxlen=_LEVEL_HISTORY_CAPACITY
        )
        self._levels_lock = threading.Lock()
        # PortAudio is the sole producer. deque append/popleft are bounded, non-waiting
        # handoffs on the supported CPython runtime; maxlen drops stale telemetry only.
        self._level_queue: collections.deque[tuple[int, float, bytes]] = collections.deque(
            maxlen=_LEVEL_QUEUE_CAPACITY
        )
        self._level_submitted_seq = 0
        self._level_processed_seq = 0
        self._level_last_processed_seq = 0
        self._level_overflow_until = float("-inf")
        self.dropped_level_blocks = 0
        self._level_stop = threading.Event()
        self._closed = threading.Event()

        self._stream = sd.RawOutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=_device(device),
            callback=self._callback,
        )
        self._level_worker = threading.Thread(
            target=self._process_levels,
            name="star-speaker-levels",
            daemon=True,
        )
        self._level_worker.start()

    def _process_levels(self) -> None:
        """Compute RMS away from PortAudio's high-priority callback thread."""
        while True:
            try:
                sequence, at, chunk = self._level_queue.popleft()
            except IndexError:
                if self._level_stop.is_set():
                    return
                self._level_stop.wait(_LEVEL_WORKER_POLL_S)
                continue

            try:
                value = _pcm_rms(chunk)
            except Exception:
                # Unknown meter data must never be mistaken for silence by the echo gate.
                value = 1.0
                self._level_overflow_until = max(
                    self._level_overflow_until,
                    time.monotonic() + _LEVEL_WINDOW_S,
                )

            # Sequence gaps identify samples evicted by deque(maxlen) while the worker
            # was busy. Count them here, outside the audio callback.
            missing = max(0, sequence - self._level_last_processed_seq - 1)
            if missing:
                self.dropped_level_blocks += missing
                self._level_overflow_until = max(
                    self._level_overflow_until,
                    at + _LEVEL_WINDOW_S,
                )
            self._level_last_processed_seq = sequence
            with self._levels_lock:
                self._levels.append((at, value))
                self._level_processed_seq = sequence

    def _callback(self, out, frames, time_info, status) -> None:
        # PortAudio's DAC timestamp is the best available estimate of when this block
        # becomes audible. Invalid/missing driver times fall back to callback time.
        callback_at = time.monotonic()
        output_at = estimate_output_time(
            callback_at,
            current_time=getattr(time_info, "currentTime", None),
            output_buffer_dac_time=getattr(time_info, "outputBufferDacTime", None),
        )
        wanted = frames * 2
        underflow = bool(getattr(status, "output_underflow", False))
        with self._lock:
            if underflow:
                self._output_underflows += 1
            if getattr(status, "output_overflow", False):
                self._output_overflows += 1
            chunk = bytes(self._buffer[:wanted])
            del self._buffer[:wanted]
            emitted_frames = len(chunk) // 2
            self._played += emitted_frames

            # Keep playback accounting under the same speaker lock as reset() and
            # snapshots. This makes the per-reply evidence window atomic without
            # introducing a competing reader/writer lock order.
            try:
                self._playback.record_callback(
                    frames=frames,
                    emitted_frames=emitted_frames,
                    output_underflow=underflow,
                    at=output_at,
                )
            except Exception:
                pass  # diagnostics must never break the audio callback

        # Always fill the complete output buffer, including underrun silence.
        out[:len(chunk)] = chunk
        if len(chunk) < wanted:
            out[len(chunk):] = b"\x00" * (wanted - len(chunk))

        if chunk:
            # Metering is best-effort and bounded. A full queue drops old meter
            # samples, never the PCM that has already been copied to the device.
            try:
                sequence = self._level_submitted_seq + 1
                self._level_queue.append((sequence, output_at, chunk))
                self._level_submitted_seq = sequence
            except Exception:
                self.dropped_level_blocks += 1
                self._level_overflow_until = max(
                    self._level_overflow_until,
                    callback_at + _LEVEL_WINDOW_S,
                )

    def __enter__(self) -> "SoundSpeaker":
        self._stream.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        """Stop callbacks, drain bounded meter work, and stop the worker idempotently."""
        if self._closed.is_set():
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        self._closed.set()
        self._level_stop.set()
        worker = self._level_worker
        if worker is not threading.current_thread():
            worker.join(timeout=1.0)

    def diagnostics(self) -> dict:
        """Aggregate PortAudio/playback health without exposing audio samples."""
        with self._lock:
            playback = self._playback.snapshot()
            return {
                "output_underflows": self._output_underflows,
                "output_overflows": self._output_overflows,
                "queued_seconds": len(self._buffer) / 2 / self.sample_rate,
                "played_seconds": self._played / self.sample_rate,
                "sample_rate": self.sample_rate,
                "first_playback_at": playback.first_playback_at,
                "output_callbacks_with_audio": playback.output_callbacks_with_audio,
                "playback_output_underflows": playback.output_underflows,
            }

    # -- Speaker interface --------------------------------------------------------------------
    def play(self, pcm: bytes, sample_rate: int) -> None:
        if sample_rate != self.sample_rate:
            from .engines import float_to_pcm16, pcm16_to_float, resample
            pcm = float_to_pcm16(resample(pcm16_to_float(pcm), sample_rate, self.sample_rate))
        with self._lock:
            self._buffer.extend(pcm)

    def stop(self) -> None:
        with self._lock:
            self._buffer.clear()

    def reset(self) -> None:
        with self._lock:
            self._played = 0
            self._playback.reset()

    def playback_snapshot(self) -> PlaybackSnapshot:
        """Return aggregate DAC-time playback evidence for the current reply."""
        with self._lock:
            return self._playback.snapshot()

    def pending_seconds(self) -> float:
        with self._lock:
            return len(self._buffer) / 2 / self.sample_rate

    def played_seconds(self) -> float:
        with self._lock:
            return self._played / self.sample_rate

    def level(self) -> float:
        """Peak-held output level; pending/dropped telemetry is conservatively audible."""
        now = time.monotonic()
        with self._levels_lock:
            levels = tuple(self._levels)
            processed = self._level_processed_seq
        if self._level_submitted_seq > processed or now < self._level_overflow_until:
            return 1.0
        cutoff = now - _LEVEL_WINDOW_S
        return max((value for at, value in levels if at >= cutoff), default=0.0)
