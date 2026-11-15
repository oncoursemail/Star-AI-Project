"""Policy for the optional diagnostic adapters (#411): pinned version and approved license only.

Pure checks: nothing is run, downloaded or installed here, and nothing is uploaded. An adapter is usable only when
the owner pinned its exact version and the installed edition carries an approved license (rtk must be the
Apache-only ``rtk-oss`` edition).
"""
from __future__ import annotations

AUTO_INSTALL = False
CLOUD_UPLOAD = False

ADAPTERS: dict[str, frozenset[str]] = {
    "rtk-oss": frozenset({"Apache-2.0"}),
    "ripgrep": frozenset({"MIT", "Unlicense", "MIT OR Unlicense", "Unlicense OR MIT"}),
    "ast-grep": frozenset({"MIT"}),
}


def check(name: str, version: str, license_id: str, *, pins: dict[str, str]) -> dict:
    """Is this installed adapter allowed? Unknown names raise; everything else returns a reason when refused."""
    if name not in ADAPTERS:
        raise ValueError(f"not an allowlisted adapter: {name!r}")
    pinned = pins.get(name)
    if not pinned:
        return {"allowed": False, "reason": f"{name} is not pinned"}
    if version != pinned:
        return {"allowed": False, "reason": f"{name} version {version!r} differs from the pin {pinned!r}"}
    if license_id not in ADAPTERS[name]:
        return {"allowed": False, "reason": f"{name} license {license_id!r} is not approved"}
    return {"allowed": True, "reason": ""}
