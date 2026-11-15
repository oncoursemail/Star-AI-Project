"""Defensive security lab: explicit owner-chosen scope, read-only by default.

Only a local directory the owner listed in ``allowed_roots`` can be a target.
URLs, missing paths, and anything that resolves outside the target are refused.
Writing needs the owner's approval. Nothing here scans or contacts anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MODE_READ_ONLY = "read_only_audit"
MODE_WRITE = "write"
_MODES = (MODE_READ_ONLY, MODE_WRITE)


class ScopeError(ValueError):
    """The requested target or mode is outside what the owner allowed."""


@dataclass(frozen=True)
class SecurityLabScope:
    root: Path
    mode: str = MODE_READ_ONLY

    @property
    def allows_write(self) -> bool:
        return self.mode == MODE_WRITE

    def contains(self, path: str | Path) -> bool:
        """True only if the fully resolved path stays inside the target."""
        try:
            Path(path).resolve().relative_to(self.root)
        except (ValueError, OSError):
            return False
        return True


def resolve_scope(
    target: str,
    *,
    allowed_roots: list[Path] | tuple[Path, ...],
    mode: str = MODE_READ_ONLY,
    owner_approved: bool = False,
) -> SecurityLabScope:
    if mode not in _MODES:
        raise ScopeError(f"unknown mode: {mode!r}")
    text = (target or "").strip()
    if not text:
        raise ScopeError("no target chosen: the owner must pick one project")
    if "://" in text:
        raise ScopeError("network targets are not allowed; choose a local project")
    root = Path(text).resolve()
    if not root.is_dir():
        raise ScopeError("target is not an existing directory")
    if not any(root == r.resolve() or r.resolve() in root.parents for r in allowed_roots):
        raise ScopeError("target is outside the owner's allowed projects")
    if mode == MODE_WRITE and not owner_approved:
        raise ScopeError("writing needs the owner's approval")
    return SecurityLabScope(root=root, mode=mode)


_SECRET_RULES = (
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
)
_MAX_FILE_BYTES = 1_000_000


@dataclass(frozen=True)
class Finding:
    """One pattern match. ``verified`` stays False: a match is not a proven leak."""

    rule: str
    path: str
    line: int
    evidence: str
    verified: bool = False


def scan_secrets(scope: SecurityLabScope) -> list[Finding]:
    """Read-only pattern scan of files inside the scope; secrets are redacted."""
    findings: list[Finding] = []
    for path in sorted(scope.root.rglob("*")):
        try:
            if not path.is_file() or not scope.contains(path):
                continue
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.resolve().relative_to(scope.root).as_posix()
        for number, line in enumerate(text.splitlines(), start=1):
            for rule, pattern in _SECRET_RULES:
                match = pattern.search(line)
                if match:
                    shown = line.replace(match.group(0), "[REDACTED]").strip()
                    findings.append(Finding(rule, rel, number, shown))
    return findings
