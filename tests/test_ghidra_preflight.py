"""Ghidra/JDK preflight reads version files only; it never runs or downloads anything."""
import subprocess

from star import ghidra_preflight as gp


def _ghidra(root, version="11.3.2"):
    (root / "Ghidra").mkdir(parents=True)
    (root / "support").mkdir()
    (root / "Ghidra" / "application.properties").write_text(
        "application.name=Ghidra\napplication.version=" + version + "\napplication.release.name=PUBLIC\n")
    (root / "support" / "analyzeHeadless.bat").write_text("")
    return root


def _jdk(root, version="21.0.5"):
    root.mkdir()
    (root / "release").write_text('IMPLEMENTOR="x"\nJAVA_VERSION="' + version + '"\n')
    return root


def test_pinned_versions_are_ready(tmp_path):
    r = gp.preflight(_ghidra(tmp_path / "g"), _jdk(tmp_path / "j"))
    assert r["ready"] and r["ghidra"]["version"] == "11.3.2" and r["jdk"]["major"] == 21
    assert not r["executed"] and not r["downloaded"] and r["advisories"] == []


def test_unpinned_ghidra_and_old_jdk_not_ready(tmp_path):
    r = gp.preflight(_ghidra(tmp_path / "g", "10.0"), _jdk(tmp_path / "j", "17.0.1"))
    assert not r["ready"]
    text = " ".join(r["advisories"])
    assert "10.0" in text and "17" in text


def test_missing_install_is_not_ready_and_never_executes(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not execute")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    r = gp.preflight(tmp_path / "nope", None)
    assert not r["ready"] and r["ghidra"]["found"] is False and r["jdk"]["found"] is False
