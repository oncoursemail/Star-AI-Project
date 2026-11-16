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


def test_statuses_do_not_exaggerate_capabilities():
    sources = {s.id: s for s in SOURCES}
    assert sources["decomp-wtf"].status == "archived"
    assert sources["medal"].status == "research_only"
    assert sources["steelseries"].status == "pilot_in_pr"
    assert sources["obs"].status == "pilot_in_pr"
    assert "No general" in sources["outplayed"].warning


def test_search_category_and_bounded_results():
    assert catalog()["total"] == len(SOURCES)
    assert not catalog()["truncated"]
    assert len(catalog()["sources"]) == len(SOURCES)
    assert catalog("Xbox")["total"] >= 3
    assert {s["category"] for s in catalog(category="recomp")["sources"]} == {"recomp"}
    assert catalog(limit=2)["truncated"]
    assert len(catalog(limit=2)["sources"]) == 2
    assert not catalog("THIS_DOES_NOT_EXIST")["sources"]
    assert catalog("MiXeD")["checked_on"] == "2026-11-16"


def test_run64_research_sources_are_discoverable_and_caveated():
    sources = {s.id: s for s in SOURCES}
    expected = {
        "opengameeval", "gameworld", "agentodyssey", "cua-recovery",
        "interactionbench", "eot-bench", "dualdecoder", "flashoffloading",
        "llama-speed-bench", "gamedevbench", "vtube-studio-api",
    }
    assert expected <= set(sources)
    assert all(sources[source_id].status == "research_only" for source_id in expected)
    assert all(sources[source_id].url.startswith("https://") for source_id in expected)
    assert catalog(category="gaming")["total"] >= 2
    assert catalog("CUA-Recovery")["total"] == 1
    assert catalog("NeurIPS 2026")["total"] == 1
    assert "not a drop-in" in sources["dualdecoder"].warning
    assert "Ascend 910C" in sources["flashoffloading"].warning
    assert "viewer chat" in sources["vtube-studio-api"].warning


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
