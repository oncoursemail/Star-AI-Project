"""Every shipped example must satisfy the same strict contract parser."""
from __future__ import annotations

import json
from pathlib import Path

from star.skill_contract import parse_skill_contract


EXAMPLES = Path(__file__).parents[1] / "examples" / "skills"


def test_all_checked_in_skill_contract_examples_parse():
    paths = sorted(EXAMPLES.glob("*.contract.json"))
    assert paths, "at least one example contract must be present"
    for path in paths:
        parse_skill_contract(json.loads(path.read_text(encoding="utf-8")))


def test_examples_cover_game_streaming_research_and_roblox():
    domains = {
        parse_skill_contract(json.loads(path.read_text(encoding="utf-8"))).domain
        for path in EXAMPLES.glob("*.contract.json")
    }
    assert {"game", "streaming", "research", "roblox"} <= domains
