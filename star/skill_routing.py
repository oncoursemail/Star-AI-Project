"""Opt-in skill-pack routing by embedding similarity (setting `skill_pack_embeddings`).

The keyword router (`star.skill_packs.select`) needs the prompt to name a pack's topic in its trigger words. When
it finds nothing, this router embeds the prompt with STAR's own embedding model (star-embed-ft1 on STAR Server) and
picks the pack whose name and description are closest, above a similarity floor. The same context rules apply (a
Roblox, Godot or named-engine prompt, only enabled packs), so unrelated prompts stay unchanged. Pack vectors are
cached on disk per model and pack text. Any problem (server unreachable, slow, odd reply) gives the keyword answer.

Why keyword first: on the 197 held-out routing cases of the pack tests the embedding router alone was right 171
times at this floor and the keyword router 197; on 36 requests that describe a topic without its trigger words the
keyword router was right 16 times and keyword-then-embedding 25 (benchmarks/skill_pack_routing.py). MIN_SIMILARITY
was set before that measurement and not tuned on it.
Idea from jcode's embedding-matched skills (github.com/1jehuang/jcode, MIT); no code was copied.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from pathlib import Path

from . import skill_packs
from .skill_packs import ENGINE_CONTEXTS, GODOT_PACKS, MAX_PACKS_PER_TURN, Pack

EMBED_MODEL = "star-embed-ft1"
QUERY_PREFIX = "task: search result | query: "      # EmbeddingGemma's retrieval-query prompt (as in starkb)
CACHE_FILE = "skill_pack_embeddings.json"
MIN_SIMILARITY = 0.45
QUERY_TIMEOUT = 3.0          # seconds for the prompt's vector, every turn
PACKS_TIMEOUT = 15.0         # seconds for pack vectors not cached yet (once per pack text and model)
MAX_QUERY_CHARS = 2000


def pack_document(pack: Pack) -> str:
    """What a pack is embedded as: its name and description (EmbeddingGemma's document prompt)."""
    return f"title: {pack.name.replace('-', ' ')} | text: {pack.description}"


def candidates(prompt: str, allowed) -> list[Pack]:
    """Packs the context rules allow for this prompt (the keyword router's gates, without its trigger words)."""
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
        return []
    roblox = bool(skill_packs._ROBLOX_CONTEXT.search(prompt))
    godot = bool(skill_packs._GODOT_CONTEXT.search(prompt))
    engines = {name for name, context in ENGINE_CONTEXTS.items() if context.search(prompt)} & set(allowed)
    if engines:
        # A named engine outranks Roblox packs, as in the keyword router.
        return [p for p in skill_packs.available() if p.name in engines]
    science = bool(skill_packs.SCIENCE_CONTEXT.search(prompt))
    return [p for p in skill_packs.available() if p.name in allowed and p.name not in ENGINE_CONTEXTS
            and ((p.name in skill_packs.SCIENCE_TOPICS and science)
                 or (p.name not in skill_packs.SCIENCE_TOPICS
                     and ((p.name in GODOT_PACKS and godot and not roblox)
                          or (p.name not in GODOT_PACKS and roblox and not godot))))]


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _key(document: str) -> str:
    return hashlib.sha256((EMBED_MODEL + "\n" + document).encode("utf-8")).hexdigest()


def _read_cache(path: Path | None) -> dict:
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cache(path: Path | None, cache: dict) -> None:
    if path is None:
        return
    try:
        from .atomic_io import atomic_write_text
        atomic_write_text(path, json.dumps(cache))
    except (OSError, ValueError):
        pass       # a cache that cannot be written only costs the vectors again next time


def _vectors(reply, count: int) -> list[list[float]]:
    if not isinstance(reply, list) or len(reply) != count:
        raise ValueError("unexpected embedding reply")
    out = []
    for vector in reply:
        if not isinstance(vector, list) or not vector or not all(isinstance(x, (int, float)) for x in vector):
            raise ValueError("unexpected embedding vector")
        out.append([float(x) for x in vector])
    return out


async def rank(prompt: str, embed, *, allowed, cache_dir: Path | None = None) -> list[tuple[float, Pack]]:
    """(similarity, pack) for every candidate, best first. `embed(texts)` is async and returns one vector per text.
    Raises on any embedding problem; `select` turns that into the keyword fallback."""
    packs = candidates(prompt, allowed)
    if not packs:
        return []
    path = Path(cache_dir) / CACHE_FILE if cache_dir is not None else None
    cache = _read_cache(path)
    documents = {p.name: pack_document(p) for p in packs}
    missing = [p.name for p in packs if not isinstance(cache.get(_key(documents[p.name])), list)]
    if missing:
        texts = [documents[name] for name in missing]
        fresh = _vectors(await asyncio.wait_for(embed(texts), PACKS_TIMEOUT), len(texts))
        cache.update({_key(documents[name]): vector for name, vector in zip(missing, fresh)})
        _write_cache(path, cache)
    query = _vectors(await asyncio.wait_for(embed([QUERY_PREFIX + prompt[:MAX_QUERY_CHARS]]), QUERY_TIMEOUT), 1)[0]
    scored = [(_cosine(query, cache[_key(documents[p.name])]), p) for p in packs]
    return sorted(scored, key=lambda item: -item[0])


async def select(prompt: str, embed, *, enabled=None, limit: int = MAX_PACKS_PER_TURN, home=None,
                 min_similarity: float = MIN_SIMILARITY, on_fallback=None) -> list[Pack]:
    """The keyword router's packs; when it has none, the closest packs by embedding similarity."""
    allowed = skill_packs.enabled_names(home=home) if enabled is None else frozenset(enabled)
    if not allowed:
        return []
    keyword = skill_packs.select(prompt, enabled=allowed, limit=limit, home=home)
    if keyword:
        return keyword
    try:
        ranked = await rank(prompt, embed, allowed=allowed, cache_dir=home)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if on_fallback is not None:
            on_fallback(type(exc).__name__)
        return []           # the keyword router already said: no pack
    return [pack for score, pack in ranked if score >= min_similarity][:max(0, limit)]
