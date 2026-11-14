"""PortAudio callback health and freshness policy without physical audio hardware."""
import queue
import threading
from collections import deque
from types import SimpleNamespace

from star.voice.devices import MICROPHONE_QUEUE_FRAMES, Microphone, SoundSpeaker
from star.voice.pcm import FRAME_SAMPLES, SAMPLE_RATE


def make_microphone(maxsize=1):
    mic = object.__new__(Microphone)
    mic._frames = queue.Queue(maxsize=maxsize)
    mic._stats_lock = threading.Lock()
    mic._input_overflows = 0
    mic._input_underflows = 0
    mic.dropped = 0
    return mic


def test_microphone_reports_driver_status_and_keeps_newest_frame_on_overload():
    mic = make_microphone(maxsize=1)
    mic._callback(b"\x01\x00", 1, None, SimpleNamespace(input_overflow=True, input_underflow=False))
    mic._callback(b"\x02\x00", 1, None, SimpleNamespace(input_overflow=False, input_underflow=True))

    assert mic.diagnostics() == {
        "input_overflows": 1,
        "input_underflows": 1,
        "queue_drops": 1,
        "queued_frames": 1,
        "queue_capacity_frames": 1,
        "queue_capacity_seconds": FRAME_SAMPLES / SAMPLE_RATE,
    }
    assert mic._frames.get_nowait() == b"\x02\x00"


def test_microphone_overload_discards_oldest_and_preserves_newest_order():
    mic = make_microphone(maxsize=2)
    mic._callback(b"\x01\x00", 1, None, None)
    mic._callback(b"\x02\x00", 1, None, None)
    mic._callback(b"\x03\x00", 1, None, None)

    assert [mic._frames.get_nowait(), mic._frames.get_nowait()] == [b"\x02\x00", b"\x03\x00"]
    assert mic.diagnostics()["queue_drops"] == 1


def test_default_microphone_backlog_is_bounded_to_about_half_a_second():
    mic = make_microphone(maxsize=MICROPHONE_QUEUE_FRAMES)
    diagnostics = mic.diagnostics()
    assert MICROPHONE_QUEUE_FRAMES == 16
    assert diagnostics["queue_capacity_frames"] == 16
    assert diagnostics["queue_capacity_seconds"] == 16 * FRAME_SAMPLES / SAMPLE_RATE


def test_speaker_reports_portaudio_underflow_without_recording_audio():
    speaker = object.__new__(SoundSpeaker)
    speaker.sample_rate = 24000
    speaker._lock = threading.Lock()
    speaker._buffer = bytearray()
    speaker._played = 0
    speaker._output_underflows = 0
    speaker._output_overflows = 0
    speaker._levels = deque(maxlen=64)

    output = bytearray(4)
    speaker._callback(
        output, 2, None,
        SimpleNamespace(output_underflow=True, output_overflow=True),
    )

    assert output == b"\x00" * 4
    diagnostics = speaker.diagnostics()
    assert diagnostics == {
        "output_underflows": 1,
        "output_overflows": 1,
        "queued_seconds": 0.0,
        "played_seconds": 0.0,
        "sample_rate": 24000,
    }
    assert not {"audio", "transcript", "device_name"} & diagnostics.keys()


def test_callbacks_tolerate_missing_portaudio_status():
    mic = make_microphone(maxsize=1)
    mic._callback(b"\x00\x00", 1, None, None)
    assert mic.diagnostics()["input_overflows"] == 0
    assert mic.diagnostics()["queue_drops"] == 0

    speaker = object.__new__(SoundSpeaker)
    speaker.sample_rate = 24000
    speaker._lock = threading.Lock()
    speaker._buffer = bytearray()
    speaker._played = 0
    speaker._output_underflows = 0
    speaker._output_overflows = 0
    speaker._levels = deque(maxlen=64)
    output = bytearray(4)
    speaker._callback(output, 2, None, None)
    assert output == b"\x00" * 4
    assert speaker.diagnostics()["output_underflows"] == 0
