"""Per-turn latency records for voice calls and the table that prints them."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import ceil, isfinite


@dataclass
class TurnMetrics:
    """Clock times (seconds, same clock) of each stage in one user turn and the reply to it."""
    turn: int = 0
    user_text: str = ""
    reply_text: str = ""            # what was actually spoken (cut short if interrupted)
    speech_end: float | None = None      # last voiced microphone frame
    turn_end: float | None = None        # end-of-turn decision
    transcript_at: float | None = None   # transcript ready
    first_token_at: float | None = None  # first text from the brain
    first_sentence_at: float | None = None   # first chunk handed to text-to-speech
    first_audio_at: float | None = None  # first audio handed to the speaker
    first_ack_at: float | None = None    # acknowledgement clip handed to the speaker (star/voice/acks.py)
    ack_text: str = ""
    last_token_at: float | None = None
    done_at: float | None = None
    end_reason: str = ""
    asr_seconds: float = 0.0
    asr_speculative: bool = False
    tokens: int = 0
    audio_seconds: float = 0.0
    tts_seconds: float = 0.0
    interrupted: bool = False
    interrupt_reason: str = ""
    heard_seconds: float = 0.0
    error: str = ""

    @staticmethod
    def _gap(a: float | None, b: float | None) -> float | None:
        return None if a is None or b is None else max(0.0, b - a)

    def stages(self) -> dict:
        """The latency breakdown in seconds. 'total' ends when reply audio is submitted."""
        generation = self._gap(self.first_token_at, self.last_token_at)
        return {
            "endpoint": self._gap(self.speech_end, self.turn_end),
            "asr": self._gap(self.turn_end, self.transcript_at),
            "speech_end_to_transcript": self._gap(self.speech_end, self.transcript_at),
            "transcript_to_first_token": self._gap(self.transcript_at, self.first_token_at),
            "first_token_to_first_audio": self._gap(self.first_token_at, self.first_audio_at),
            "total": self._gap(self.speech_end, self.first_audio_at),
            # An acknowledgement may be the first audible response, before generated speech.
            "perceived": self._gap(self.speech_end, min((t for t in (self.first_ack_at, self.first_audio_at)
                                                         if t is not None), default=None)),
            "tokens_per_second": ((self.tokens - 1) / generation) if generation and self.tokens > 2 else None,
        }

    def to_dict(self) -> dict:
        data = asdict(self)
        data["stages"] = {k: (None if v is None else round(v, 3)) for k, v in self.stages().items()}
        return data


def latency_summary(turns: list[TurnMetrics]) -> dict:
    """Summarize stage and tail latency without returning transcripts or reply text.

    Audio timestamps mean a PCM chunk was submitted to the speaker, not that it
    reached a physical listener. Errors are excluded. Incomplete turns may still
    contribute to stages whose two timestamps exist. p95/p99 readiness flags
    describe sample volume only; they are not deployment or quality gates.
    """
    if len(turns) > 10000 or any(not isinstance(t, TurnMetrics) for t in turns):
        raise ValueError("Expected at most 10000 voice turns")

    pairs = {
        "speech_end_to_audio_submitted": ("speech_end", "first_audio_at"),
        "speech_end_to_ack_submitted": ("speech_end", "first_ack_at"),
        "endpointer": ("speech_end", "turn_end"),
        "transcription": ("turn_end", "transcript_at"),
        "speech_end_to_transcript": ("speech_end", "transcript_at"),
        "brain_first_token": ("transcript_at", "first_token_at"),
        "token_to_first_sentence": ("first_token_at", "first_sentence_at"),
        "first_sentence_to_audio": ("first_sentence_at", "first_audio_at"),
        "tts_and_queue": ("first_token_at", "first_audio_at"),
    }
    samples: dict[str, list[float]] = {key: [] for key in pairs}
    samples["speech_end_to_first_response_submitted"] = []
    failed = invalid = incomplete = 0
    timestamp_fields = (
        "speech_end", "turn_end", "transcript_at", "first_token_at",
        "first_sentence_at", "first_audio_at", "first_ack_at",
        "last_token_at", "done_at",
    )

    def valid(value) -> bool:
        return type(value) in (float, int) and isfinite(value)

    for turn in turns:
        if turn.error:
            failed += 1
            continue

        present = [getattr(turn, field) for field in timestamp_fields
                   if getattr(turn, field) is not None]
        if any(not valid(value) for value in present):
            invalid += 1
            continue

        # A generated token cannot arrive after the first generated audio chunk.
        if (turn.speech_end is not None and turn.first_audio_at is not None
                and turn.first_audio_at < turn.speech_end):
            invalid += 1
            continue
        if (turn.first_token_at is not None and turn.first_audio_at is not None
                and turn.first_token_at > turn.first_audio_at):
            invalid += 1
            continue
        if (turn.first_token_at is not None and turn.first_sentence_at is not None
                and turn.first_sentence_at < turn.first_token_at):
            invalid += 1
            continue
        if (turn.first_sentence_at is not None and turn.first_audio_at is not None
                and turn.first_audio_at < turn.first_sentence_at):
            invalid += 1
            continue

        # Keep valid partial-stage samples even when a later pipeline stage is missing.
        for key, (begin, end) in pairs.items():
            x, y = getattr(turn, begin), getattr(turn, end)
            if x is not None and y is not None and y >= x:
                samples[key].append((y - x) * 1000)

        response_stamps = [stamp for stamp in (turn.first_ack_at, turn.first_audio_at)
                           if stamp is not None]
        if turn.speech_end is not None and response_stamps:
            first_response = min(response_stamps)
            if first_response >= turn.speech_end:
                samples["speech_end_to_first_response_submitted"].append(
                    (first_response - turn.speech_end) * 1000
                )

        if turn.speech_end is None or turn.first_audio_at is None:
            incomplete += 1

    def quantiles(values: list[float]) -> dict:
        if not values:
            return {
                "n": 0, "mean_ms": None, "p50_ms": None, "p95_ms": None,
                "p99_ms": None, "max_ms": None,
                "p95_sample_ready": False, "p99_sample_ready": False,
            }
        ordered = sorted(values)
        n = len(ordered)
        index = lambda percentile: ordered[ceil(percentile * n) - 1]
        p95_ready = n >= 20
        p99_ready = n >= 100
        return {
            "n": n,
            "mean_ms": round(sum(ordered) / n, 1),
            "p50_ms": round(index(0.50), 1),
            "p95_ms": round(index(0.95), 1),
            "p99_ms": round(index(0.99), 1) if p99_ready else None,
            "max_ms": round(ordered[-1], 1),
            "p95_sample_ready": p95_ready,
            "p99_sample_ready": p99_ready,
        }

    return {
        "total_turns": len(turns),
        "errored_turns": failed,
        "incomplete_turns": incomplete,
        "invalid_clock_turns": invalid,
        "interrupted_turns": sum(t.interrupted for t in turns),
        "sample_guidance": {"p95_min_samples": 20, "p99_min_samples": 100},
        "latency": {key: quantiles(values) for key, values in samples.items()},
    }


def _cell(value: float | None, width: int, digits: int = 2) -> str:
    return ("-" if value is None else f"{value:.{digits}f}").rjust(width)


def latency_table(turns: list[TurnMetrics]) -> str:
    """Plain-text table, one row per turn, times in seconds."""
    head = (f"{'turn':>4}  {'end-of-turn':>11}  {'transcribe':>10}  {'speech end ->':>13}  {'transcript ->':>13}  "
            f"{'first token ->':>14}  {'TOTAL':>6}  {'tok/s':>5}  note")
    sub = (f"{'':>4}  {'wait':>11}  {'':>10}  {'transcript':>13}  {'first token':>13}  "
           f"{'first audio':>14}  {'':>6}  {'':>5}")
    rows = [head, sub, "-" * len(head)]
    for m in turns:
        s = m.stages()
        notes = []
        if m.end_reason:
            notes.append(f"end={m.end_reason}")
        if m.asr_speculative:
            notes.append("early transcript")
        if m.interrupted:
            notes.append(f"interrupted after {m.heard_seconds:.1f}s ({m.interrupt_reason})")
        if m.error:
            notes.append("ERROR " + m.error[:60])
        rows.append(f"{m.turn:>4}  {_cell(s['endpoint'], 11)}  {_cell(s['asr'], 10)}  "
                    f"{_cell(s['speech_end_to_transcript'], 13)}  {_cell(s['transcript_to_first_token'], 13)}  "
                    f"{_cell(s['first_token_to_first_audio'], 14)}  {_cell(s['total'], 6)}  "
                    f"{_cell(s['tokens_per_second'], 5, 1)}  {', '.join(notes)}")
    complete = [m.stages() for m in turns if m.stages()["total"] is not None]
    if len(complete) > 1:
        def mean(key: str) -> float | None:
            values = [s[key] for s in complete if s[key] is not None]
            return sum(values) / len(values) if values else None
        rows.append("-" * len(head))
        rows.append(f"{'mean':>4}  {_cell(mean('endpoint'), 11)}  {_cell(mean('asr'), 10)}  "
                    f"{_cell(mean('speech_end_to_transcript'), 13)}  {_cell(mean('transcript_to_first_token'), 13)}  "
                    f"{_cell(mean('first_token_to_first_audio'), 14)}  {_cell(mean('total'), 6)}  "
                    f"{_cell(mean('tokens_per_second'), 5, 1)}")
    return "\n".join(rows)
