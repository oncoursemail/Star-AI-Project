"""Version-pinned Ghidra and JDK preflight for approved REA work.

Reads version files from owner-installed folders only. It never executes
Ghidra or Java, never downloads anything and never touches a target binary.
"""
from __future__ import annotations

import re
from pathlib import Path

PINNED_GHIDRA_VERSIONS = frozenset({"11.3.2"})
REQUIRED_JDK_MAJOR = 21


def _props(path: Path) -> dict:
    out: dict = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                out[key.strip()] = value.strip().strip('"')
    except OSError:
        pass
    return out


def _ghidra(root) -> dict:
    if not root:
        return {"found": False, "version": None}
    root = Path(root)
    version = _props(root / "Ghidra" / "application.properties").get("application.version")
    launcher = any((root / "support" / n).is_file() for n in ("analyzeHeadless", "analyzeHeadless.bat"))
    return {"found": bool(version and launcher), "version": version}


def _jdk(root) -> dict:
    if not root:
        return {"found": False, "version": None, "major": None}
    version = _props(Path(root) / "release").get("JAVA_VERSION") or ""
    m = re.match(r"1\.(\d+)", version) or re.match(r"(\d+)", version)
    return {"found": bool(m), "version": version or None, "major": int(m.group(1)) if m else None}


def preflight(ghidra_dir, jdk_dir) -> dict:
    ghidra, jdk = _ghidra(ghidra_dir), _jdk(jdk_dir)
    advisories: list[str] = []
    if not ghidra["found"]:
        advisories.append("Ghidra install not found; install a pinned release yourself and set its folder.")
    elif ghidra["version"] not in PINNED_GHIDRA_VERSIONS:
        advisories.append(f"Ghidra {ghidra['version']} is not a pinned version "
                          f"({', '.join(sorted(PINNED_GHIDRA_VERSIONS))}); check its security advisories.")
    if not jdk["found"]:
        advisories.append(f"JDK not found; install JDK {REQUIRED_JDK_MAJOR} yourself and set its folder.")
    elif jdk["major"] != REQUIRED_JDK_MAJOR:
        advisories.append(f"JDK {jdk['major']} found but JDK {REQUIRED_JDK_MAJOR} is required.")
    return {"ready": not advisories, "ghidra": ghidra, "jdk": jdk, "advisories": advisories,
            "executed": False, "downloaded": False}
