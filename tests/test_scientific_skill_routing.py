"""Scientific method guides are routed by the existing keyword/embedding routers, opt-in and within the one-pack budget."""
import asyncio

import pytest

from star import skill_packs, skill_routing

NAMES = (
    "sci-experiment-design",
    "sci-source-grading",
    "sci-reproducibility",
    "sci-statistical-confidence",
    "sci-benchmarking",
    "sci-ux-study",
    "sci-uncertainty",
)
FIXTURES = (
    ("Help me design an experiment with a control group and a clear hypothesis.", "sci-experiment-design"),
    ("Grade the sources for this claim: which are independent and which are primary sources?", "sci-source-grading"),
    ("How do I make this analysis reproducible, with a fixed random seed and pinned versions?", "sci-reproducibility"),
    ("Is the difference significant? Give me a confidence interval and the p-value.", "sci-statistical-confidence"),
    ("Benchmark these two models on a held-out set and compare latency.", "sci-benchmarking"),
    ("Plan a usability study with five participants and a task success rate.", "sci-ux-study"),
    ("State the uncertainty of this estimate and what is unknown.", "sci-uncertainty"),
)
NOT_SCIENCE = (
    "How do I bake bread?",
    "Roblox: how do I validate RemoteEvent arguments on the server against exploiters?",
    "Fix the failing test in my python script.",
)


def test_the_guides_have_contexts_and_are_never_enabled_by_default():
    assert set(skill_packs.SCIENCE_TOPICS) == set(NAMES) <= set(skill_packs.TRIGGERS)
    assert set(NAMES).isdisjoint(skill_packs.DEFAULT_ENABLED)
    assert set(NAMES) <= {p.name for p in skill_packs.available()}
    assert set(NAMES).isdisjoint(skill_packs.enabled_names({}))


@pytest.mark.parametrize("prompt,name", FIXTURES)
def test_fixed_selection_fixtures_pick_one_guide_when_enabled(prompt, name):
    chosen = skill_packs.select(prompt, enabled=set(NAMES))
    assert [p.name for p in chosen] == [name]
    assert len(skill_packs.render(chosen)) <= skill_packs.MAX_BLOCK_CHARS


@pytest.mark.parametrize("prompt,name", FIXTURES)
def test_nothing_is_selected_when_the_guides_are_not_enabled(prompt, name):
    assert skill_packs.select(prompt, enabled=set()) == []
    assert skill_packs.select(prompt) == []


@pytest.mark.parametrize("prompt", NOT_SCIENCE)
def test_ordinary_prompts_never_select_a_guide(prompt):
    assert all(p.name not in NAMES for p in skill_packs.select(prompt, enabled=set(NAMES)))
    assert all(p.name not in NAMES for p in skill_routing.candidates(prompt, set(NAMES)))


def test_the_embedding_router_only_considers_guides_for_science_prompts(tmp_path):
    prompt = "Given the evidence in this study, how sure are we?"
    assert skill_packs.select(prompt, enabled=set(NAMES)) == []                  # no trigger word
    assert {p.name for p in skill_routing.candidates(prompt, set(NAMES))} == set(NAMES)

    class Embed:
        async def __call__(self, texts):
            return [[1.0, 0.0] if t.startswith(skill_routing.QUERY_PREFIX) or "uncertainty" in t else [0.0, 1.0]
                    for t in texts]

    got = asyncio.run(skill_routing.select(prompt, Embed(),
                                           enabled=set(NAMES), home=tmp_path))
    assert [p.name for p in got] == ["sci-uncertainty"]
