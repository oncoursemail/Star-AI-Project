"""Optional pinned adapters for diagnostic compaction (#411): a pure policy check, nothing is run or installed."""
from __future__ import annotations

import pytest

from star import diag_adapters as da


def test_known_adapters_are_exactly_the_three_optional_ones():
    assert set(da.ADAPTERS) == {"rtk-oss", "ripgrep", "ast-grep"}


def test_default_is_off_and_nothing_is_installed_automatically():
    r = da.check("ripgrep", "14.1.0", "MIT", pins={})
    assert not r["allowed"] and "not pinned" in r["reason"]
    assert da.AUTO_INSTALL is False and da.CLOUD_UPLOAD is False


def test_pinned_version_with_approved_license_is_allowed():
    assert da.check("ripgrep", "14.1.0", "MIT", pins={"ripgrep": "14.1.0"})["allowed"]
    assert da.check("ast-grep", "0.30.0", "MIT", pins={"ast-grep": "0.30.0"})["allowed"]


def test_version_other_than_the_pin_is_refused():
    r = da.check("ripgrep", "14.1.1", "MIT", pins={"ripgrep": "14.1.0"})
    assert not r["allowed"] and "pin" in r["reason"]


def test_rtk_requires_the_apache_oss_edition():
    pins = {"rtk-oss": "1.0.0"}
    assert da.check("rtk-oss", "1.0.0", "Apache-2.0", pins=pins)["allowed"]
    assert not da.check("rtk-oss", "1.0.0", "ELv2", pins=pins)["allowed"]
    assert not da.check("rtk-oss", "1.0.0", "Proprietary", pins=pins)["allowed"]


@pytest.mark.parametrize("name", ["rtk", "context-mode", "bash", "", "RIPGREP"])
def test_unknown_adapter_is_refused_not_guessed(name):
    with pytest.raises(ValueError):
        da.check(name, "1", "MIT", pins={name: "1"})
