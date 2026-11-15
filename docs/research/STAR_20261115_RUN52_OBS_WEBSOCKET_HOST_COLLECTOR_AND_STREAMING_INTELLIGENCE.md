# STAR Run 52 — Local OBS telemetry transport, streaming observability, and capability integration

**Date:** 2026-11-15  
**Repository:** oncoursemail/Star-AI-Project  
**Development branch:** feat/obs-local-readonly-host-20261115-run52  
**Base:** fix/stream-host-sampling-coherence-20261112-auto11 (stacked on the OBS parser / stream-host-sampler review chain)

## Executive summary

STAR already has substantial streaming, voice, avatar, gaming, game-creation, memory, and local-inference work. The important gap found in this audit was not another model or another scheduler: the current OBS work had **pure parsers and a fail-closed host-sample contract, but no actual authenticated local OBS WebSocket collector**.

This run adds that missing transport edge in star/obs_websocket_host.py.

The collector:

- Connects only to 127.0.0.1:4455 using the optional obsws-python desktop dependency already declared in requirements-desktop.txt.
- Requires explicit owner approval to connect and disconnect.
- Calls only GetVersion, GetStreamStatus, GetStats, and GetVideoSettings.
- Brackets the stats/video reads with two GetStreamStatus reads and rejects a poll if output-active/reconnecting state changes inside the window.
- Polls at a default 500 ms minimum interval from a background host worker.
- Preserves the existing epoch-safe OBS parsers and StreamHostSampler contract.
- Exposes render drops, output-thread drops, stream-output counters, network congestion, reconnecting state, active FPS, target FPS, and frame-render budget as separate measurements.
- Exports streaming and a conservative obs_dropped_pct observation to the existing StreamHostSampler interface.
- Fails closed on stale, incoherent, reset, missing, or malformed telemetry.

It does not start/stop a stream, change scenes, record, capture media, connect to VTube Studio, or control a game.

## 1. Repository audit: build on the systems that already exist

The current star/next architecture already contains meaningful foundations. This run deliberately avoids creating a duplicate speech scheduler, resource scheduler, avatar host, or game agent.

### Streaming and social intelligence

Existing areas include:

- star/stream_persona.py, star/stream_stage.py, star/stream_turntaking.py, and the stream director/context modules for persona, reactions, timing, and context.
- star/stream_hardware_telemetry.py for trusted local hardware/game/audio observations.
- star/vtube_local_host.py, star/vtube_live2d_bridge.py, and star/vtuber/ for the local avatar host, Live2D/VMC paths, camera output, and playback-linked motion.
- The open review chain around playback timing, multiparty room decisions, turn-taking, session context, persona, replay evaluation, and latest-wins avatar frame transport.

The next real milestone is not another simulated persona. It is a measured Windows rehearsal where voice, avatar, OBS, gameplay, and chat operate together without stale queues or dropped output.

### Gamer Brain

The repository already has screen-to-action gating, game loops, game experience/skill memory, skill promotion, transfer evaluation, mechanic probing, Roblox/Minecraft adapters, and game-stream hooks. The current open work also includes causal mechanic-probe evaluation and an OpenGameEval adapter.

The next intelligence milestone is verified transfer: a skill learned in one game or level must improve performance on a held-out variant, with the same start state and a no-skill baseline. A memorized button sequence is not proof of general game understanding.

### Creator Brain

The project already has Roblox Studio/MCP and Luau development workflows, plus asset and game-development pipelines. OpenGameEval is the right evaluation direction because it separates observation from editing and scores both scene changes and simulated play behavior.

The next milestone is actual Studio-host integration and held-out tasks, not more generated scripts that have never been run.

### Memory and general knowledge

STAR has project knowledge, lessons, session/event memory, and new long-horizon streaming-memory work. These should remain distinct:

- factual knowledge: source, date, confidence, contradictions, and freshness;
- episodic memory: what happened and when;
- procedural skill: how to perform a task, preconditions, evidence, and version;
- causal memory: why an action appeared to produce an outcome and what experiment supports that explanation.

A retrieved memory is evidence to inspect, not automatic truth or permission.

### Inference and performance

The repository already has local runtime routing, resource-aware admission, stream load/QoS policy, and separate open work for KV-residency planning and paired mixed-load evaluation. This run does not add another scheduler. It supplies one missing real-world signal to the existing host-sampling path.

## 2. OBS WebSocket research: what must be measured separately

OBS WebSocket v5 exposes different signals for the renderer, output thread, and active stream output. They must not be collapsed into one ambiguous "dropped frames" counter.

### GetStats

The collector reads:

- activeFps;
- averageFrameRenderTime;
- renderSkippedFrames and renderTotalFrames;
- outputSkippedFrames and outputTotalFrames.

The existing ObsStatsWindow establishes a baseline within one OBS connection epoch and one stream epoch. It computes interval deltas only when timestamps and counters are coherent. Render-thread and output-thread skip rates remain separate.

### GetStreamStatus

The collector reads:

- outputActive;
- outputReconnecting;
- outputCongestion (nullable; ratio 0..1);
- outputBytes;
- outputSkippedFrames and outputTotalFrames.

The existing ObsStreamStatusWindow uses the host monotonic clock for byte throughput. It does not divide by OBS-reported outputDuration or trust outputTimecode as a wall-clock denominator.

The collector keeps the per-stream output counters separate from the GetStats output-thread counters. It does not assume that per-stream skipped frames are bounded by the delivered-frame counter, and therefore does not manufacture a percentage from those fields.

### GetVideoSettings

Target FPS is computed from the rational pair fpsNumerator / fpsDenominator. For example, 60000/1001 is not rounded to 60. This matters when comparing active FPS and render time against the actual configured frame budget.

### Important protocol edge cases

- outputCongestion: null means unknown/unavailable, not zero congestion.
- OBS users have reported Enhanced Broadcasting duration/timecode behavior that can overstate elapsed time. Use the host monotonic clock for interval calculations.
- Cumulative frame counters need a fresh baseline after stream starts, reconnect transitions, OBS reconnects, and counter resets.
- A missing or invalid active-stream measurement must remain unknown. Do not report a healthy zero.

## 3. New implementation

### star/obs_websocket_host.py

OBSWebSocketHost is the transport adapter above the existing parsers.

**Connection contract**

- Fixed loopback endpoint: 127.0.0.1:4455.
- No caller-selected host, port, URL, or remote address.
- connect() and disconnect() require both confirm=True and owner_approved=True.
- Password is passed to the in-memory client constructor only; no file, settings, log, telemetry field, or status response stores it.
- Raw third-party exception text is not returned because it can contain authentication or connection details.

**Read-only request allowlist**

- GetVersion validates the connection.
- GetStreamStatus reads output state and network/output counters.
- GetStats reads renderer and output-thread counters.
- GetVideoSettings reads the rational target frame rate.

No OBS write request is present in this module. Disconnecting STAR drops its client reference; it never stops an existing OBS stream or recording.

**Sampling contract**

- Default minimum poll interval: 500 ms; allowed configuration: 250–5000 ms.
- Maximum RPC sampling skew: 500 ms by default; bounded configuration: 50–2000 ms.
- snapshot() is in-memory only and rejects samples older than 1500 ms by default.
- poll() is a blocking local RPC and must run on a low-priority host worker, never on the game, render, or audio callback.
- Stream-active and reconnecting transitions create a new stream epoch and reset both interval windows.
- A hidden stop/start detected by stream-output counter rollback creates a new stream epoch and re-baselines the stats window; a GetStats counter rollback creates a new OBS/process epoch.
- Invalid/coherency-failed samples reset interval windows. The next accepted sample must establish a new baseline.
- A generation token prevents an in-flight poll from an old connection from clearing a newly reconnected session.

**Host-sampler bridge**

OBSHostSample.host_observations(clock_epoch=...) returns:

- streaming: an explicit Boolean MetricObservation;
- obs_dropped_pct: the worst of the measured GetStats render-thread and output-thread skip percentages, but only when both interval statuses are ok, both rates are valid, and output is active and not reconnecting.

If either denominator is missing, the output is reconnecting, or the sample is only a baseline, the drop observation is None. The existing StreamHostSampler then rejects an active-stream sample rather than assuming zero drops.

Network congestion and reconnecting state remain separate fields on OBSHostSample; they are not mislabeled as dropped-frame percentages. The next host-sampler revision should add explicit obs_congestion_ratio and obs_reconnecting observations rather than folding them into obs_dropped_pct.

## 4. Why this improves STAR's streaming quality

This collector gives STAR a way to distinguish several failure modes:

| Signal | Likely pressure source | Correct response to evaluate |
|---|---|---|
| Render-thread skips | Scene composition/GPU render pressure | Reduce optional visual/background load; inspect scene complexity |
| Output-thread skips | Encoder/output pipeline pressure | Reduce encoder contention or noncritical GPU/CPU work |
| Output congestion | Network/output congestion | Avoid interpreting it as GPU pressure; inspect network/output path |
| Reconnecting | Stream output instability | Mark stream telemetry incomplete and defer noncritical experiments |
| Active FPS below target | Render pipeline not meeting configured cadence | Compare with frame-render budget and game/OBS load |
| High render-time utilization | Render thread consuming most frame budget | Reduce competing work and inspect scene/render cost |

These are diagnostic signals, not automatic OBS setting changes. A future policy may recommend changes, but should not silently change stream settings or scenes.

## 5. Human-like VTuber research and engineering direction

A believable AI streamer is not produced by making her speak continuously or adding random expressions. Naturalness is a coordinated behavior across conversation, attention, speech timing, memory, gameplay, and avatar motion.

### Conversation and social attention

Use the existing multiparty room/turn director and evaluate:

- correct addressee identification;
- whether a question is already answered;
- whether STAR should speak, backchannel, wait, or remain silent;
- interruption and end-of-turn timing;
- topic continuity and callbacks;
- separate private, room, and broadcast permissions.

MP-Bench and Full-Duplex-Bench v3 are useful for group turn-taking and real-time interaction. EoT-Bench is useful for calibrating when a person has actually finished speaking. A stream should also have an explicit silence policy: silence is often the right action while concentrating on gameplay or listening to a viewer.

### Avatar and voice

Keep the existing audible-playback clock authoritative. TTS queue submission is not the same as audio reaching the device, and device DAC scheduling is not the same as a remote viewer hearing the audio.

The VTube Studio API is permissioned: a plugin must request user approval, and custom parameter injection can control the model. Keep plugin identity explicit, request only required permissions, and preserve the latest-wins frame pump for animation samples. Do not let avatar updates queue behind old frames or race the audio playback epoch.

### AI transparency and personality

STAR can have a consistent character voice, preferences, humor, and expressive reactions while remaining honest that she is an AI when sincerely asked out of character. Human-like interaction should mean good timing, contextual understanding, and agency—not deceiving viewers into believing she is a human operator.

## 6. Gamer Brain and Creator Brain research direction

### Game-playing intelligence

SIMA and SIMA 2 show why a generalist game agent should separate visual understanding, goal reasoning, action execution, and experience-based improvement. STAR's low-latency action loop should not call a large reasoning model for every frame.

Recommended learning loop:

1. Observe the current game state using a trusted game/window observer.
2. Infer a bounded set of available actions and current objectives.
3. Choose a strategic subgoal with the slow brain.
4. Execute short low-latency actions with the fast controller.
5. Verify the actual game-state change.
6. Record the episode, including failure and uncertainty.
7. Propose a procedural skill only after repeated evidence.
8. Test the skill on a held-out level, seed, or game variant.
9. Compare with a no-skill baseline and check for negative transfer.

### Roblox/game creation

OpenGameEval is especially relevant because it measures both exploration and final correctness in a stateful Roblox Studio environment. STAR should inspect the relevant objects before editing, then validate both the edited scene and simulated play behavior.

Recommended creator loop:

Plan → Inspect → Build → Static-check → Run → Playtest → Observe → Repair → Replay → Verify.

Do not count generated code, a successful API response, or a plausible screenshot as a passing game. Use executable checks and actual play sessions.

### General knowledge

For general-knowledge answers, preserve source, date, confidence, and contradictions. For time-sensitive claims, attach a freshness horizon and re-check before reuse. Keep factual knowledge separate from procedural skills and from inferred user preferences. A model-written note should not silently become a verified fact.

## 7. Speed and intelligence: measure end-to-end goodput

Do not optimize tokens/second in isolation. STAR is simultaneously an AI, voice system, game player, avatar renderer, and stream producer.

The integrated benchmark should record:

- model time-to-first-token and time-per-output-token;
- first-audible latency and end-of-turn delay;
- audio underruns and playback queue p95/p99;
- game FPS p10 and frame-time p95/p99;
- OBS render/output skip percentages, congestion, reconnects, and active FPS;
- VRAM/RAM/CPU and model/KV residency;
- verified task success and quality on a held-out workload.

Use paired baseline/candidate runs with the same game build, scene, chat/audio trace, model, hardware, and duration. Report task-quality regressions alongside speed improvements. Keep the existing fast/deep/background routing and single resource-admission authority; do not add a competing scheduler.

OpenTelemetry's GenAI semantic conventions provide useful names for inference operation duration, server request duration, time-to-first-token, and time-per-output-token. STAR can keep its local, privacy-preserving metric store while using consistent terminology.

## 8. Next integration phases

| Phase | Work | Acceptance evidence |
|---|---|---|
| A | Complete the parent OBS parser/stream-status/host-sampler review chain and this transport PR on exact heads | Full offline CI and Windows package checks |
| B | Wire OBSWebSocketHost.poll() into the Windows host supervisor at 0.5–1 Hz on a background worker | Fresh MetricObservation values with a shared monotonic clock epoch |
| C | Extend StreamHostInputs/StreamSample with separate congestion and reconnecting fields | Missing/stale values fail closed; no conflation with drop percentage |
| D | Run a private Windows OBS canary: connect, stream start/stop, reconnect, counter reset, null congestion, OBS restart | Host logs show epoch changes and no cross-session rates |
| E | Combine OBS with game FPS, VRAM, voice p95, audio underruns, and avatar playback timing | Coherent sample accepted by StreamHostSampler |
| F | Run a 60-minute mixed-load rehearsal with local inference, game, voice, avatar, and OBS | p50/p95/p99 latency, dropped frames, underruns, and verified task quality |
| G | Run held-out game-learning and Roblox Studio creator tasks during the same resource budget | Transfer and creation success, not self-reported competence |

## 9. Verification boundary for this run

- Isolated local harness: **32 tests passed** against compatible parser/window fixtures and fake OBS clients.
- Python compilation: passed.
- The repository's actual parser/window implementations are supplied by the stacked parent branch; exact-head GitHub Actions remains the authoritative integration check.
- No OBS installation or live WebSocket connection was available in this run.
- No Windows microphone, WASAPI loopback, VTube Studio, OBS broadcast, RTX hardware, Roblox Studio, or live gameplay test was performed.
- No model speedup, intelligence gain, stream-quality improvement, or game mastery is claimed.
- No OBS settings, stream state, recording, scenes, avatar parameters, model weights, routing defaults, production permissions, or production main were changed.

## 10. Research sources

### OBS and local streaming telemetry

- OBS WebSocket v5 protocol: https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md
- OBS WebSocket generated protocol fields: https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.json
- OBS output reference: https://docs.obsproject.com/reference-outputs
- OBS nullable congestion report: https://github.com/obsproject/obs-websocket/issues/1176
- OBS Enhanced Broadcasting duration/timecode report: https://github.com/obsproject/obs-websocket/issues/1234
- obsws-python request client: https://github.com/aatikturk/obsws-python

### VTuber and real-time interaction

- VTube Studio API: https://github.com/DenchiSoft/VTubeStudio
- VTube Studio plugin permission model: https://github.com/DenchiSoft/VTubeStudio/wiki/Plugins
- MP-Bench: https://www.fullduplex.ai/benchmarks/mp-bench
- Full-Duplex-Bench v3: https://arxiv.org/abs/2604.04847
- EoT-Bench: https://github.com/livekit/eot-bench

### Gaming, creation, and intelligence

- SIMA 2: https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/
- OpenGameEval: https://github.com/Roblox/open-game-eval
- OpenGameEval paper: https://arxiv.org/abs/2610.02563

### Inference observability

- OpenTelemetry GenAI metrics: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md
- OpenTelemetry inference metrics: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/client-inference.md
