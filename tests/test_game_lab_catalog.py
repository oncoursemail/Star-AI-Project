import pytest
from star.game_lab_catalog import SOURCES, catalog


def test_sources_are_https_unique_and_research_only():
    ids = [s.id for s in SOURCES]
    assert len(ids) == len(set(ids))
    assert all(s.url.startswith("https://") for s in SOURCES)
    assert all(s.status in ("research_only", "pilot_in_pr", "archived") for s in SOURCES)
    assert all(s.kind in ("reference", "external_app_api", "external_app", "local_api",
                          "separate_desktop_application") for s in SOURCES)
    assert "decomp-wtf" in ids and "gamedev-skills" in ids and "medal" in ids
    assert "xrevive" in ids and "ps3recomp" in ids and "xboxrecomp" in ids
    assert {"gameworld", "gym-anything-rt", "keel", "continual-arc",
            "windows-dxgi", "windows-sendinput", "microsoft-gameinput",
            "javis", "realtime-venus", "hithink-turn", "joi-bench-task",
            "model-interruption-bench", "subternary", "gamedevbench",
            "robloxstudio-mcp"}.issubset(ids)


def test_statuses_do_not_exaggerate_capabilities():
    sources = {s.id: s for s in SOURCES}
    assert sources["decomp-wtf"].status == "archived"
    assert sources["medal"].status == "research_only"
    assert sources["steelseries"].status == "pilot_in_pr"
    assert sources["obs"].status == "pilot_in_pr"
    assert "No general" in sources["outplayed"].warning
    assert "not a blanket synthetic-input" in sources["microsoft-gameinput"].warning
    assert "never an anti-cheat bypass" in sources["windows-sendinput"].warning
    assert sources["gameworld"].status == "research_only"
    assert sources["hithink-turn"].status == "research_only"
    assert sources["subternary"].status == "research_only"
    assert "read-only mode first" in sources["robloxstudio-mcp"].warning


def test_search_category_and_bounded_results():
    assert catalog("Xbox")["total"] >= 3
    assert {s["category"] for s in catalog(category="recomp")["sources"]} == {"recomp"}
    assert catalog(limit=2)["truncated"]
    assert len(catalog(limit=2)["sources"]) == 2
    assert not catalog("THIS_DOES_NOT_EXIST")["sources"]
    assert catalog("MiXeD")["checked_on"] == "2026-11-14"
    assert catalog("GameWorld")["total"] == 1
    assert catalog(category="benchmarks")["total"] >= 6
    assert catalog(category="input")["total"] == 2
    assert len(catalog()["sources"]) <= 50


@pytest.mark.parametrize("kwargs",[
    {"category":"not-category"},
    {"query":"x"*121},
    {"limit":0},
    {"limit":1000},
    {"query":None},
])
def test_bad_filters_refused(kwargs):
    with pytest.raises(ValueError):
        catalog(**kwargs)
