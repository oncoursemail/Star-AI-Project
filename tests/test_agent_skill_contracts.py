"""Optional versioned contract discovery for the existing Agent Skills loader."""
from __future__ import annotations

import json

import pytest

from star.agent_skills import SkillLibrary
from star.skill_contract import parse_skill_contract


def contract(skill_id: str = "demo-skill") -> dict:
    return {
        "schema_version": 1,
        "skill_id": skill_id,
        "version": "1.0.0",
        "domain": "general",
        "summary": "A small test skill with independently verifiable behavior.",
        "preconditions": [],
        "steps": [
            {"step_id": "observe", "operation": "observe", "intent": "Inspect the current state."}
        ],
        "behavior_constraints": [
            {
                "constraint_id": "verify-result",
                "condition": {"kind": "state_exists", "subject": "result"},
                "expected_behavior": "Verify the actual result before reporting completion.",
                "severity": "critical",
            }
        ],
        "postconditions": [{"path": "result", "operator": "exists"}],
        "resource_budget": {
            "max_elapsed_ms": 1000,
            "max_steps": 1,
            "max_tool_calls": 0,
            "max_tokens": 100,
            "max_retries": 0,
            "max_ram_mib": 64,
        },
        "provenance": [{"kind": "owner_note", "locator": "unit-test"}],
    }


def make_library(tmp_path):
    workspace = tmp_path / "workspace"
    skill_dir = workspace / ".agents" / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: A test skill\n---\n# Demo\nInspect, act, and verify.\n",
        encoding="utf-8",
    )
    library = SkillLibrary(workspace=workspace, home=tmp_path / "home")
    return library, skill_dir


def test_legacy_skill_without_sidecar_keeps_loading(tmp_path):
    library, _ = make_library(tmp_path)

    listed = library.list()["skills"]
    assert listed == [{"name": "demo-skill", "description": "A test skill", "source": "project"}]

    loaded = library.load("demo-skill")
    assert loaded["instructions"].startswith("# Demo")
    assert loaded["contract_status"] == "absent"
    assert "contract" not in loaded


def test_valid_contract_is_loaded_only_when_skill_is_activated(tmp_path):
    library, skill_dir = make_library(tmp_path)
    raw = contract()
    sidecar = skill_dir / "SKILL.contract.json"
    sidecar.write_text(json.dumps(raw), encoding="utf-8")

    # Discovery remains metadata-only; the structured sidecar is read by load().
    assert "contract_status" not in library.list()["skills"][0]

    loaded = library.load("demo-skill")
    parsed = parse_skill_contract(raw)
    assert loaded["contract_status"] == "parsed"
    assert loaded["contract"] == parsed.to_dict()
    assert loaded["contract_sha256"] == parsed.digest()
    assert "not a permission grant" in loaded["contract_notice"]


def test_invalid_json_does_not_disable_the_legacy_skill(tmp_path):
    library, skill_dir = make_library(tmp_path)
    (skill_dir / "SKILL.contract.json").write_text("{not-json", encoding="utf-8")

    loaded = library.load("demo-skill")
    assert loaded["instructions"].startswith("# Demo")
    assert loaded["contract_status"] == "invalid"
    assert "contract" not in loaded
    assert "valid JSON" in loaded["contract_error"]


def test_contract_identity_must_match_skill_directory(tmp_path):
    library, skill_dir = make_library(tmp_path)
    (skill_dir / "SKILL.contract.json").write_text(json.dumps(contract("other-skill")), encoding="utf-8")

    loaded = library.load("demo-skill")
    assert loaded["contract_status"] == "invalid"
    assert "must match" in loaded["contract_error"]
    assert "contract" not in loaded


def test_oversized_contract_is_rejected_without_hiding_skill(tmp_path):
    library, skill_dir = make_library(tmp_path)
    (skill_dir / "SKILL.contract.json").write_text(" " * 64_001, encoding="utf-8")

    loaded = library.load("demo-skill")
    assert loaded["contract_status"] == "invalid"
    assert "64000-byte limit" in loaded["contract_error"]
    assert loaded["instructions"].startswith("# Demo")


def test_symlinked_contract_is_rejected(tmp_path):
    library, skill_dir = make_library(tmp_path)
    external = tmp_path / "external.contract.json"
    external.write_text(json.dumps(contract()), encoding="utf-8")
    sidecar = skill_dir / "SKILL.contract.json"
    try:
        sidecar.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this test environment")

    loaded = library.load("demo-skill")
    assert loaded["contract_status"] == "invalid"
    assert "non-symlink" in loaded["contract_error"]
    assert "contract" not in loaded
