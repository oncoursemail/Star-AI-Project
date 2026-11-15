"""Security lab secret check: deterministic, inside scope only, never echoes the secret."""

import pytest

from star.security_lab import Finding, resolve_scope, scan_secrets


def _scope(root):
    return resolve_scope(str(root), allowed_roots=[root])


def test_finds_planted_secret_with_exact_location_and_redacts(tmp_path):
    fake = "AKIA" + "ABCDEFGHIJKLMNOP"  # synthetic, built at runtime
    (tmp_path / "app.py").write_text(f"x = 1\nKEY = '{fake}'\n", encoding="utf-8")
    findings = scan_secrets(_scope(tmp_path))
    assert len(findings) == 1
    f = findings[0]
    assert isinstance(f, Finding)
    assert (f.path, f.line, f.rule) == ("app.py", 2, "aws_access_key_id")
    assert fake not in f.evidence
    assert f.verified is False


def test_clean_project_has_no_findings(tmp_path):
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    assert scan_secrets(_scope(tmp_path)) == []


def test_symlink_outside_scope_is_not_read(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("k = '" + "AKIA" + "ABCDEFGHIJKLMNOP'\n", encoding="utf-8")
    try:
        (proj / "link.txt").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert scan_secrets(resolve_scope(str(proj), allowed_roots=[tmp_path])) == []
