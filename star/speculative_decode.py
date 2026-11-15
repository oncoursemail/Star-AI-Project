"""Capability-gated, opt-in llama.cpp speculative-decoding argument planner.

This module does not launch a server, download models, alter runtime defaults,
or select a profile automatically. It builds a small argv fragment only after
checking the selected llama-server's own --help output. The initial supported
profiles deliberately avoid auxiliary draft models and cross-slot shared n-gram
pools; they are intended for a measured local canary, not assumed speedups.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


_MODES = frozenset({"none", "ngram-simple", "ngram-map-k"})
_FLAG_RE = re.compile(r"(?<![A-Za-z0-9_-])(--[a-z0-9][a-z0-9-]*)")
_MODE_RE = re.compile(r"\b(none|ngram-simple|ngram-map-k)\b")
_MAX_HELP_CHARS = 256_000


class UnsupportedRuntimeError(RuntimeError):
    """The selected llama-server does not advertise the required options."""


@dataclass(frozen=True)
class SpeculativeConfig:
    """A bounded speculative profile; mode='none' preserves ordinary decoding."""

    mode: str = "none"
    draft_max: int = 8
    draft_min: int = 0
    ngram_size_n: int = 12
    ngram_size_m: int = 24
    min_hits: int = 2

    def __post_init__(self) -> None:
        if type(self.mode) is not str or self.mode not in _MODES:
            raise ValueError("mode must be none, ngram-simple, or ngram-map-k")
        if type(self.draft_max) is not int or not 1 <= self.draft_max <= 64:
            raise ValueError("draft_max must be an integer in 1..64")
        if type(self.draft_min) is not int or not 0 <= self.draft_min <= self.draft_max:
            raise ValueError("draft_min must be an integer in 0..draft_max")
        if type(self.ngram_size_n) is not int or not 2 <= self.ngram_size_n <= 64:
            raise ValueError("ngram_size_n must be an integer in 2..64")
        if type(self.ngram_size_m) is not int or not 1 <= self.ngram_size_m <= 128:
            raise ValueError("ngram_size_m must be an integer in 1..128")
        if type(self.min_hits) is not int or not 1 <= self.min_hits <= 32:
            raise ValueError("min_hits must be an integer in 1..32")


@dataclass(frozen=True)
class LlamaHelpCapabilities:
    """Only flags and modes explicitly advertised by a local executable."""

    flags: frozenset[str]
    modes: frozenset[str]

    @classmethod
    def parse(cls, help_text: str) -> "LlamaHelpCapabilities":
        if type(help_text) is not str or len(help_text) > _MAX_HELP_CHARS:
            raise ValueError("llama-server help must be bounded text")
        flags = frozenset(_FLAG_RE.findall(help_text))
        modes = frozenset(_MODE_RE.findall(help_text))
        return cls(flags=flags, modes=modes)


def _flag(capabilities: LlamaHelpCapabilities, *choices: str) -> str:
    for choice in choices:
        if choice in capabilities.flags:
            return choice
    raise UnsupportedRuntimeError(
        "llama-server does not advertise a required speculative-decoding option: "
        + " or ".join(choices)
    )


def build_speculative_args(
    config: SpeculativeConfig,
    *,
    help_text: str,
) -> tuple[str, ...]:
    """Return a shell-free argv fragment, or refuse an unsupported runtime.

    'none' intentionally returns no flags and does not require a particular
    llama.cpp version. For speculative modes, all required flags must appear in
    the selected executable's help text. The function never guesses based on a
    version string because downstream builds can backport or omit options.
    """
    if not isinstance(config, SpeculativeConfig):
        raise TypeError("config must be SpeculativeConfig")
    if config.mode == "none":
        return ()

    caps = LlamaHelpCapabilities.parse(help_text)
    if config.mode not in caps.modes:
        raise UnsupportedRuntimeError(
            f"llama-server does not advertise speculative mode {config.mode!r}"
        )

    args: list[str] = [
        _flag(caps, "--spec-type"), config.mode,
        _flag(caps, "--spec-draft-n-max", "--draft-max"), str(config.draft_max),
    ]
    if config.draft_min:
        args.extend((
            _flag(caps, "--spec-draft-n-min", "--draft-min"),
            str(config.draft_min),
        ))

    if config.mode == "ngram-simple":
        n_flag = _flag(caps, "--spec-ngram-simple-size-n", "--spec-ngram-size-n")
        m_flag = _flag(caps, "--spec-ngram-simple-size-m", "--spec-ngram-size-m")
        args.extend((n_flag, str(config.ngram_size_n), m_flag, str(config.ngram_size_m)))
    elif config.mode == "ngram-map-k":
        n_flag = _flag(caps, "--spec-ngram-map-k-size-n", "--spec-ngram-size-n")
        m_flag = _flag(caps, "--spec-ngram-map-k-size-m", "--spec-ngram-size-m")
        hits_flag = _flag(caps, "--spec-ngram-map-k-min-hits", "--spec-ngram-min-hits")
        args.extend((
            n_flag, str(config.ngram_size_n),
            m_flag, str(config.ngram_size_m),
            hits_flag, str(config.min_hits),
        ))

    return tuple(args)
