import pytest

from star.speculative_decode import (
    SpeculativeConfig,
    UnsupportedRuntimeError,
    build_speculative_args,
)


LATEST_HELP = """
--spec-type [none|draft-simple|ngram-simple|ngram-map-k]
--spec-draft-n-max N
--spec-draft-n-min N
--spec-ngram-simple-size-n N
--spec-ngram-simple-size-m M
--spec-ngram-map-k-size-n N
--spec-ngram-map-k-size-m M
--spec-ngram-map-k-min-hits H
"""

LEGACY_HELP = """
--spec-type [none|ngram-simple|ngram-map-k]
--draft-max N
--draft-min N
--spec-ngram-size-n N
--spec-ngram-size-m M
--spec-ngram-min-hits H
"""


def test_none_is_a_noop_even_for_unknown_or_empty_runtime_help():
    assert build_speculative_args(SpeculativeConfig(), help_text="") == ()


def test_latest_ngram_simple_flags_are_capability_gated_and_bounded():
    got = build_speculative_args(
        SpeculativeConfig(mode="ngram-simple", draft_max=8, ngram_size_n=12, ngram_size_m=24),
        help_text=LATEST_HELP,
    )
    assert got == (
        "--spec-type", "ngram-simple",
        "--spec-draft-n-max", "8",
        "--spec-ngram-simple-size-n", "12",
        "--spec-ngram-simple-size-m", "24",
    )


def test_legacy_ngram_simple_aliases_are_supported_only_when_advertised():
    got = build_speculative_args(
        SpeculativeConfig(mode="ngram-simple", draft_max=6, draft_min=2),
        help_text=LEGACY_HELP,
    )
    assert got == (
        "--spec-type", "ngram-simple", "--draft-max", "6", "--draft-min", "2",
        "--spec-ngram-size-n", "12", "--spec-ngram-size-m", "24",
    )


def test_latest_ngram_map_k_includes_minimum_hits():
    got = build_speculative_args(
        SpeculativeConfig(mode="ngram-map-k", draft_max=10, min_hits=3),
        help_text=LATEST_HELP,
    )
    assert got == (
        "--spec-type", "ngram-map-k", "--spec-draft-n-max", "10",
        "--spec-ngram-map-k-size-n", "12",
        "--spec-ngram-map-k-size-m", "24",
        "--spec-ngram-map-k-min-hits", "3",
    )


def test_legacy_ngram_map_k_aliases_are_supported():
    got = build_speculative_args(
        SpeculativeConfig(mode="ngram-map-k", min_hits=4), help_text=LEGACY_HELP
    )
    assert got[-6:] == (
        "--spec-ngram-size-n", "12", "--spec-ngram-size-m", "24",
        "--spec-ngram-min-hits", "4",
    )


def test_missing_mode_is_rejected():
    with pytest.raises(UnsupportedRuntimeError, match="does not advertise"):
        build_speculative_args(
            SpeculativeConfig(mode="ngram-simple"),
            help_text="--spec-type [none|ngram-map-k] --spec-draft-n-max N",
        )


def test_missing_required_flag_is_rejected_not_guessed():
    with pytest.raises(UnsupportedRuntimeError, match="--spec-draft-n-max or --draft-max"):
        build_speculative_args(
            SpeculativeConfig(mode="ngram-simple"),
            help_text="--spec-type [none|ngram-simple] --spec-ngram-simple-size-n N "
                      "--spec-ngram-simple-size-m M",
        )


def test_missing_ngram_parameters_are_rejected():
    with pytest.raises(UnsupportedRuntimeError, match="ngram-simple-size-n"):
        build_speculative_args(
            SpeculativeConfig(mode="ngram-simple"),
            help_text="--spec-type [none|ngram-simple] --spec-draft-n-max N",
        )


def test_nonzero_draft_min_requires_an_advertised_min_flag():
    help_without_min = LATEST_HELP.replace("--spec-draft-n-min N", "")
    with pytest.raises(UnsupportedRuntimeError, match="--spec-draft-n-min or --draft-min"):
        build_speculative_args(
            SpeculativeConfig(mode="ngram-simple", draft_min=1),
            help_text=help_without_min,
        )


@pytest.mark.parametrize("kwargs", [
    {"mode": "ngram-mod"},
    {"mode": "ngram-cache"},
    {"mode": "draft-simple"},
    {"draft_max": True},
    {"draft_max": 0},
    {"draft_max": 65},
    {"draft_min": -1},
    {"draft_min": 9, "draft_max": 8},
    {"ngram_size_n": 1},
    {"ngram_size_n": 65},
    {"ngram_size_m": 0},
    {"ngram_size_m": 129},
    {"min_hits": 0},
    {"min_hits": 33},
])
def test_invalid_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        SpeculativeConfig(**kwargs)


def test_help_input_is_bounded_and_typed():
    with pytest.raises(ValueError):
        build_speculative_args(SpeculativeConfig(mode="ngram-simple"), help_text=object())
    with pytest.raises(ValueError):
        build_speculative_args(SpeculativeConfig(mode="ngram-simple"), help_text="x" * 256_001)


def test_result_is_an_argv_tuple_not_a_shell_command():
    got = build_speculative_args(SpeculativeConfig(mode="ngram-simple"), help_text=LATEST_HELP)
    assert isinstance(got, tuple)
    assert all(isinstance(part, str) and not any(c in part for c in ";&|`\n\r") for part in got)
    assert "--model-draft" not in got
    assert "--spec-type" in got
