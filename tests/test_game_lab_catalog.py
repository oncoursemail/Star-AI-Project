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
            "robloxstudio-mcp", "mp-bench", "mem2actbench", "memagent",
            "harness-memory", "vllm-disagg-prefill", "streamarena", "eventmemagent", "onlinewm", "ma-wam", "sima2", "vjepa2", "osworld-v2", "androidworld", "openhands-index",
            "skillret", "polyskill", "skilllearnbench", "skillhorizon", "skill2bench",
            "agentspec", "asymspec", "omniagent", "tact", "turboquant", "express-streamer",
            "memento-skills", "lumi-nox", "llama-speed-bench", "nvidia-aiperf",
            "sentinelbench", "full-duplex-v3", "interactionbench", "llama-server-docs",
            "vtubestudio-api", "roblox-agentic-workflow", "agentcl", "agenticrag-r1", "duplex-mpe", "aituber-onair", "agentif"}.issubset(ids)


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
    assert sources["mp-bench"].status == "research_only"
    assert sources["mem2actbench"].status == "research_only"
    assert sources["memagent"].status == "research_only"
    assert sources["harness-memory"].status == "research_only"
    assert sources["vllm-disagg-prefill"].status == "research_only"
    assert "not a STAR score" in sources["mp-bench"].warning
    assert "existing task ledger" in sources["memagent"].warning
    assert "local 8 GB GPU" in sources["vllm-disagg-prefill"].warning
    assert sources["streamarena"].status == "research_only"
    assert sources["eventmemagent"].status == "research_only"
    assert sources["onlinewm"].status == "research_only"
    assert sources["ma-wam"].status == "research_only"
    assert sources["sima2"].status == "research_only"
    assert sources["vjepa2"].status == "research_only"
    assert sources["osworld-v2"].status == "research_only"
    assert sources["androidworld"].status == "research_only"
    assert sources["openhands-index"].status == "research_only"
    assert sources["skillret"].status == "research_only"
    assert sources["polyskill"].status == "research_only"
    assert sources["skilllearnbench"].status == "research_only"
    assert sources["skillhorizon"].status == "research_only"
    assert sources["skill2bench"].status == "research_only"
    assert all(sources[key].status == "research_only" for key in
               ("agentspec", "asymspec", "omniagent", "tact", "turboquant", "express-streamer"))
    assert "never execute side effects" in sources["agentspec"].warning
    assert "critical evidence" in sources["asymspec"].warning
    assert "8 GB GPU" in sources["omniagent"].warning
    assert "not STAR results" in sources["tact"].warning
    assert "H100-specific" in sources["turboquant"].warning
    assert "UX hypothesis" in sources["express-streamer"].warning
    assert "Pin the dataset revision" in sources["skillret"].warning
    assert "web-agent-specific" in sources["polyskill"].warning
    assert "self-feedback drift" in sources["skilllearnbench"].warning
    assert "not a game benchmark" in sources["skillhorizon"].warning
    assert "local 8 GB GPU" in sources["skill2bench"].warning
    assert "not a STAR speedup" in sources["streamarena"].warning
    assert "no implementation installed" in sources["eventmemagent"].warning
    assert "Do not online-train" in sources["onlinewm"].warning
    assert "Offline MARL results only" in sources["ma-wam"].warning
    assert "not a generally downloadable local model" in sources["sima2"].warning
    assert "not a desktop/game action controller" in sources["vjepa2"].warning
    assert "pinned osworld-v2.1" in sources["osworld-v2"].warning
    assert "production phone-control permission" in sources["androidworld"].warning
    assert "not STAR scores" in sources["openhands-index"].warning
    assert "read-only mode first" in sources["robloxstudio-mcp"].warning
    assert sources["memento-skills"].status == "research_only"
    assert "protected holdouts" in sources["memento-skills"].warning
    assert sources["lumi-nox"].status == "research_only"
    assert "does not automatically wire" in sources["lumi-nox"].warning
    assert sources["llama-speed-bench"].status == "research_only"
    assert "parallel slots" in sources["llama-speed-bench"].warning
    assert sources["nvidia-aiperf"].status == "research_only"
    assert "Metric definitions" in sources["nvidia-aiperf"].warning
    assert all(sources[key].status == "research_only" for key in
               ("sentinelbench", "full-duplex-v3", "interactionbench",
                "llama-server-docs", "vtubestudio-api", "roblox-agentic-workflow",
                "agentcl", "agenticrag-r1", "duplex-mpe", "aituber-onair", "agentif")))
    assert "no-op" in sources["sentinelbench"].warning
    assert "do not measure STAR" in sources["full-duplex-v3"].warning
    assert "four dimensions" in sources["interactionbench"].warning
    assert "Pin the exact llama.cpp commit" in sources["llama-server-docs"].warning
    assert "once per second" in sources["vtubestudio-api"].warning
    assert "no automatic publishing" in sources["roblox-agentic-workflow"].warning
    assert "held-out compositions" in sources["agentcl"].warning
    assert "anonymous code" in sources["agenticrag-r1"].warning
    assert "session-scoped replay labels" in sources["duplex-mpe"].warning
    assert "competing stage or playback authorities" in sources["aituber-onair"].warning
    assert "judge version" in sources["agentif"].warning
    assert "memory-margin-based LRU unloading" in sources["llama-server-docs"].scope
    assert "never a serving model" in sources["llama-server-docs"].warning


def test_search_category_and_bounded_results():
    assert catalog("Xbox")["total"] >= 3
    assert {s["category"] for s in catalog(category="recomp")["sources"]} == {"recomp"}
    assert catalog(limit=2)["truncated"]
    assert len(catalog(limit=2)["sources"]) == 2
    assert not catalog("THIS_DOES_NOT_EXIST")["sources"]
    assert catalog("MiXeD")["checked_on"] == "2026-11-15"
    assert catalog("GameWorld")["total"] == 1
    assert catalog(category="benchmarks")["total"] >= 6
    assert catalog(category="input")["total"] == 2
    assert catalog(category="inference")["total"] >= 4
    assert catalog(category="vtuber")["total"] >= 2
    assert catalog("Memento-Skills")["total"] == 1
    assert catalog("SPEED-Bench")["total"] == 1
    default_catalog = catalog()
    assert len(default_catalog["sources"]) == 83
    assert default_catalog["total"] == 83
    assert not default_catalog["truncated"]
    assert len(catalog(limit=80)["sources"]) == 80
    assert catalog(limit=80)["truncated"]
    assert len(catalog(limit=90)["sources"]) == 83
    with pytest.raises(ValueError, match="between 1 and 90"):
        catalog(limit=91)


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
