"""Reviewed, read-only references for STAR Game Lab; not installed integrations.

No network, package installation, binary execution, ROM access, or automatic
tool permissions. The links and capability statuses are deliberately explicit.
The owner can use STAR's existing Agent Skills library with locally reviewed
SKILL.md files rather than having this catalog execute remote instructions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    url: str
    category: str
    scope: str
    kind: str = "reference"
    status: str = "research_only"
    warning: str = ""


SOURCES = (
    Source("gamedev-skills","Awesome GameDev Agent Skills",
           "https://github.com/gamedev-skills/awesome-gamedev-agent-skills",
           "skills","74 skill documents + engine/task router; reviewed local import only"),
    Source("gamedev-org","GameDev Skills organization","https://github.com/gamedev-skills",
           "skills","Project and version overview"),
    Source("universal-modder","Universal Modder","https://github.com/rehan-remade/universal-modder",
           "modding","Engine-aware modding skills, evidence, local test pipelines",
           warning="Its CLI executes operations; never auto-install or run agent-submitted commands."),
    Source("decomp-games","Awesome Decomp Games","https://github.com/SubmitGame/awesome-decomp-games",
           "catalog","Structured directory of source ports, recomp projects and reimplementations"),
    Source("fortnite-rust","Fortnite-Rust","https://github.com/omonkeyz/Fortnite-Rust",
           "modding","Rust parsing and inspection for older Fortnite UE4 content",
           warning="Asset tooling, not a proven full playable game or an anti-cheat bypass."),
    Source("recompiledgames","Recompiled Games","https://recompiledgames.com/",
           "catalog","Browser/native port index; validate each link and asset rights"),
    Source("ps3recomp","PS3Recomp","https://github.com/sp00nznet/ps3recomp",
           "recomp","Cell PPU/SPU recompilation and replacement runtime; per-title native verification"),
    Source("xboxrecomp","XboxRecomp","https://github.com/sp00nznet/xboxrecomp",
           "recomp","Original Xbox XBE-to-C pipeline + Windows runtime; game-specific shims"),
    Source("rexdex-recompiler","ReXDeX Recompiler","https://github.com/rexdex/recompiler",
           "recomp","Legacy Xbox 360 XEX recompiler research prototype",
           warning="Old prototype, not a general game-running solution."),
    Source("decomp-dev","decomp.dev","https://decomp.dev/",
           "catalog","Community progress reports, GitHub bot and project metadata"),
    Source("decomp-archive","decomp.dev October 2026 Archive",
           "https://web.archive.org/web/20261013045303/https://decomp.dev/",
           "catalog","Historical snapshot; availability cannot be guaranteed"),
    Source("shibbo","shibbo repositories","https://github.com/shibbo?tab=repositories",
           "modding","GameCube/Wii/Switch editors, tools and community decompilation"),
    Source("decomp-me","decomp.me","https://decomp.me/",
           "recomp","Per-function matching compiler scratchpad and collaboration"),
    Source("decomp-wtf","decomp.wtf","https://github.com/i12bp8/decomp.wtf",
           "recomp","Local multi-agent function matching via original compiler / objdiff",
           status="archived",warning="Maintainer discontinued the project; respect community opt-outs."),
    Source("osgameclones","Open Source Game Clones","https://osgameclones.com/",
           "catalog","Catalog of source-available and open-source game reimplementations"),
    Source("xb-live","xb.live","https://xb.live/",
           "community","Community original Xbox stats, sessions, events and public APIs",
           warning="Use documented APIs with appropriate account permissions; no token scraping."),
    Source("xrevive","xrevive","https://github.com/Teraflopping/xrevive",
           "community","Windows launcher for original Xbox static recomp builds and online revival",
           warning="Requires user's own legitimate game data."),
    Source("replays","RePlays","https://github.com/lulzsun/RePlays",
           "clipping","Open recorder/reference for libobs-based capture and clip libraries"),
    Source("obs","OBS Studio","https://obsproject.com/",
           "clipping","Replay buffer; opt-in STAR Clips controller implemented in separate draft",
           kind="separate_desktop_application",status="pilot_in_pr"),
    Source("medal","Medal","https://medal.tv/developer/auto-clipping",
           "clipping","Approved developer-owned game events and external recorder import",
           kind="external_app_api",warning="Claim/approval and a developer API key are required for events."),
    Source("steelseries","SteelSeries Moments",
           "https://github.com/SteelSeries/gamesense-sdk/blob/master/doc/api/sending-moments-events.md",
           "clipping","Local GameSense event registration for games you develop",
           kind="local_api",status="pilot_in_pr",
           warning="Accepted event is not proof that a video was recorded."),
    Source("outplayed","Outplayed","https://support.overwolf.com/support/solutions/articles/9000284659-how-to-use-outplayed",
           "clipping","Overwolf-powered game events; importing local video files",
           kind="external_app",warning="No general external-app control API verified."),
    Source("ghidra","Ghidra","https://github.com/NationalSecurityAgency/ghidra",
           "analysis","Read-only static binary analysis, existing STAR bounded adapter"),
    Source("objdiff","objdiff","https://github.com/encounter/objdiff",
           "analysis","Assembly/object binary diff for matching decompilation"),
    Source("n64recomp","N64Recomp","https://github.com/N64Recomp/N64Recomp",
           "recomp","MIPS static recompilation and owned-asset native ports"),
    Source("unreal-remote","Unreal Remote Control",
           "https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-quick-start-for-unreal-engine",
           "engines","Editor remote control via HTTP/WebSocket, disabled by default"),
    Source("unity-test","Unity Test Framework",
           "https://docs.unity.com/en-us/engine/6000.7/manual/programming-environment/test-framework-introduction/reference-command-line",
           "engines","Batchmode edit/play tests with NUnit XML results"),
    Source("nuclear","Nuclear Music Player","https://nuclearplayer.com/",
           "music","Open-source desktop music player with an optional MCP server",
           warning="AGPL licensing review before embedding sources."),
    Source("opengameeval","Roblox OpenGameEval",
           "https://github.com/Roblox/open-game-eval",
           "gaming","Roblox Studio benchmark; 84 stateful tasks; observation/edit separation; scene and simulated-play checks",
           warning="Benchmark harness, not a live STAR integration or guarantee of Roblox Studio acceptance."),
    Source("gameworld","GameWorld multimodal game benchmark",
           "https://gameworld-project.github.io/",
           "gaming","34 games and 170 tasks; state-verifiable progress/success; separate real-time track",
           warning="Paused and real-time tracks are distinct; no STAR score or live gameplay result is implied."),
    Source("agentodyssey","AgentOdyssey",
           "https://agentodyssey.github.io/",
           "learning","NeurIPS 2026 generated text-game framework for exploration, episodic memory, world knowledge, skill learning, planning and cost",
           warning="Research benchmark; text-game performance does not prove visual or real-time game mastery."),
    Source("cua-recovery","CUA-Recovery",
           "https://github.com/xu-hu-2002/CUA-Recovery",
           "computer_use","2,250 verified erroneous states across 100 tasks and 8.6K recovery trajectories across 377 tasks",
           warning="Published fine-tuning results are model-specific; STAR has not been trained on this dataset."),
    Source("interactionbench","InteractionBench",
           "https://arxiv.org/abs/2611.02430",
           "voice","Voice evaluation for timing, spoken-task accuracy, whisper/volume and long-conversation grounding; client-heard timing",
           warning="Protocol differences limit direct cross-system rankings; benchmark is not a production voice engine."),
    Source("adaptduplex","AdaptDuplex",
           "https://arxiv.org/abs/2609.29217",
           "voice","Adaptive full-duplex dialogue with variable response windows and non-blocking reasoning/consolidation",
           warning="Published benchmark scores are not STAR results; no local RTX 4060 compatibility or speedup is established."),
    Source("video-interactionbench","Video InteractionBench",
           "https://arxiv.org/abs/2610.05775",
           "streaming","Event-triggered streaming-video evaluation for content accuracy, timing, and silence compliance with negative streams and near-miss events",
           warning="Offline video benchmark; not evidence of live capture latency or STAR gameplay commentary quality."),
    Source("eot-bench","LiveKit End-of-Turn Benchmark",
           "https://github.com/livekit/eot-bench",
           "voice","Fourteen-language real human-to-agent turns with pause annotations for hesitation versus true turn end",
           warning="Evaluator and dataset, not a production turn detector or voice runtime."),
    Source("dualdecoder","DualDecoder predictive KV prefetch",
           "https://arxiv.org/abs/2607.26475",
           "inference","Predictive prefetch for sparse host-memory KV retrieval; up to 2.62x decode throughput in the paper's evaluated system",
           warning="Research result is serving-stack-specific; not a drop-in llama.cpp or RTX 4060 optimization."),
    Source("flashoffloading","FlashOffloading KV cache research",
           "https://arxiv.org/abs/2611.07542",
           "inference","Host-DRAM KV offload and compute/load overlap evaluated on Ascend 910C",
           warning="Ascend 910C results do not transfer to STAR's NVIDIA GPU; backend compatibility is not established."),
    Source("llama-speed-bench","llama.cpp SPEED-Bench",
           "https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench",
           "inference","Server benchmark harness for matched prefill, decode, latency and throughput experiments",
           warning="Results depend on backend, model, quantization, context, server slots and hardware; measure STAR directly."),
    Source("gamedevbench","GameDevBench",
           "https://github.com/waynchi/gamedevbench",
           "engines","333 Godot game-development tasks covering graphics, animation, UI and gameplay with visual feedback",
           warning="External benchmark results are not proof of STAR game quality or a successful project build."),
    Source("vtube-studio-api","VTube Studio API",
           "https://github.com/DenchiSoft/VTubeStudio",
           "vtuber","Local WebSocket API for authorized parameter injection, expression/hotkey control and event subscriptions",
           warning="Requires explicit user authorization and a revocable secret token; avoid 60+ FPS full-parameter polling and keep one writer per overridden parameter."),
    Source("cegame-bench","CEGame-Bench — long-horizon complete-game creation",
           "https://arxiv.org/abs/2610.26098",
           "game_creation","Five production engines (Defold, Godot, Roblox Studio, Unity, Unreal); contract-driven builds and hidden real-input play evaluation; reports a major artifact-to-play gap",
           warning="Paper results are benchmark-specific, not STAR results. Review task assets, engine versions and license terms before reproducing; do not import its skill without code and safety review."),
    Source("full-duplex-bench-v3","Full-Duplex-Bench v3",
           "https://arxiv.org/abs/2604.04847",
           "voice","Real human audio with five disfluency classes and chained mock-API tasks; evaluates task accuracy, latency, tool use and turn-taking",
           warning="Published comparisons are configuration- and protocol-specific. Review dataset terms and consent before reuse; do not treat benchmark scores as STAR performance."),
    Source("windowsworld","WindowsWorld cross-application computer-use benchmark",
           "https://aclanthology.org/2026.findings-acl.750/",
           "computer_use","181 tasks across 17 desktop applications with intermediate process checkpoints; most tasks require multiple apps",
           warning="A benchmark environment is not proof of native Windows reliability. Reproduce only in disposable, resettable environments with explicit app and file scopes."),
    Source("obs-websocket","OBS Studio obs-websocket 5.x protocol",
           "https://github.com/obsproject/obs-websocket",
           "streaming","Official local RPC and event protocol for scene, source and stream automation; supports request/response and event subscriptions",
           kind="local_api",
           warning="Require password authentication and loopback binding; keep credentials in the OS secret store, redact logs, and separately approve scene/recording/stream mutations.")

)


def catalog(query: str = "", category: str = "", limit: int = 60) -> dict:
    if not isinstance(query, str) or not isinstance(category, str):
        raise ValueError("Search and category must be text.")
    if len(query) > 120 or len(category) > 24:
        raise ValueError("Narrow the search text or category.")
    if type(limit) is not int or not 1 <= limit <= 60:
        raise ValueError("Results limit must be between 1 and 60.")
    category = category.strip().lower()
    categories = sorted({s.category for s in SOURCES})
    if category and category not in categories:
        raise ValueError("Unknown STAR Game Lab category.")
    search = query.strip().casefold()
    selected = [s for s in SOURCES if (not category or s.category == category)
                and (not search or search in (
                    s.name + " " + s.scope + " " + s.category + " " + s.id).casefold())]
    return {"checked_on": "2026-11-16", "categories": categories,
            "total": len(selected), "sources": [asdict(s) for s in selected[:limit]],
            "truncated": len(selected) > limit,
            "note": "Research index only. No third-party software was installed or authorized."}
