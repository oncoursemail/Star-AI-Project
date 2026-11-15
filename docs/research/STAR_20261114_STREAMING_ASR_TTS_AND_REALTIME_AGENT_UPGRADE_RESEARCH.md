# STAR streaming ASR, expressive TTS, and real-time agent upgrade research

**Research date:** 2026-11-14  
**Target branch:** `feat/resource-admission-20261113-run21` (draft PR #1178)  
**Scope:** local-first speech recognition, full-stream speech generation, conversational timing, inference efficiency, game-agent control, VTuber presence, and verified skill transfer.

## Executive decision

The next high-value upgrade for STAR is not another large language model. It is replacing repeated, whole-utterance work in the live voice path with event-driven streaming components, while preserving the existing host-side turn director and the single resource-admission authority.

Three candidates stand out:

1. **Moonshine Voice** is the strongest first ASR experiment for STAR's local hardware profile. It exposes incremental transcript events, supports on-device Windows/Linux/Python deployment, offers small English streaming models, and includes optional speaker identification. Its event model maps much better to STAR's existing live microphone path than repeatedly re-running Whisper over an ever-growing audio buffer.
2. **VoXtream2.5** is a promising full-stream TTS candidate. Its project reports 30 ms first-packet latency and 0.103 real-time factor on an RTX 3090, plus a single-CPU-core GGUF/int8 streaming path. These are upstream measurements, not STAR measurements. The model's training-data licensing requires review before any public or commercial distribution.
3. **GameWorld + OpenGameEval** provide a much stronger evaluation basis for STAR's gamer and creator abilities than screenshot-only demos or code-compilation checks. They emphasize state-verifiable outcomes, exploration before edits, and real-time control.

Keep the existing Faster-Whisper + Kokoro path as the known-good fallback until paired tests show a better end-to-end result. No model, package, model weight, credential, stream provider, or production default is enabled by this research document.

## 1. Repository audit: what STAR actually does today

The current branch already has useful foundations:

- `star/voice/call.py` owns VAD, end-of-turn decisions, speculative/partial transcript jobs, cancellation, streamed model text, sentence chunking, and playback.
- `star/voice/engines.py` exposes a small ASR/TTS registry and currently implements Faster-Whisper plus Kokoro.
- `star/voice/settings.py` currently registers Faster-Whisper as the only ASR engine and Kokoro as the only TTS engine.
- `star/voice/devices.py` captures 16 kHz mono microphone frames, bounds the input queue to 16 x 32 ms frames, and exposes aggregate device diagnostics.
- `star/voice/room.py`, `room_host.py`, and the room queue/payload store separate trusted floor-control decisions from untrusted audio/chat/game content.
- `star/voice/persona.py` keeps a stable, cache-friendly character prompt and explicitly leaves permission to speak with the room director.
- The branch has turn-level latency instrumentation and generation-bound cancellation.

The key remaining ASR inefficiency is visible in the implementation: Faster-Whisper's public adapter is one-shot `transcribe(pcm)`. Partial transcription periodically reprocesses the accumulated utterance, while final transcription processes the utterance again. The `_asr_lock` correctly prevents preview work from blocking the final pass, but it cannot make repeated full-context encoding incremental.

The current TTS path waits for a complete speakable sentence before calling Kokoro. This is a robust baseline, but it imposes a sentence-formation boundary before the first audio can be generated.

These are the highest-leverage areas for a measured streaming upgrade.

## 2. Moonshine Voice: first streaming-ASR candidate

Primary sources:

- Moonshine Voice project: https://github.com/moonshine-ai/moonshine-v2
- Moonshine v2 paper: https://arxiv.org/abs/2602.12241
- Current model matrix and license notes: https://github.com/moonshine-ai/moonshine/blob/main/docs/models/available-models.md

### 2.1 Why it fits STAR

Moonshine Voice is an on-device speech toolkit with Python bindings and Windows, Linux, macOS, iOS, and Android support. Its documented pipeline combines microphone input, VAD/segmentation, ASR, optional speaker identification, and command recognition.

Its streaming API is event-based:

- `LineStarted`: a speech segment begins.
- `LineTextChanged`: provisional text changes.
- `LineUpdated`: line metadata/audio/text changes.
- `LineCompleted`: the segment is final and will not be revised.

The same line ID persists while that segment is updated. A completed line includes its speaker ID when speaker identification is enabled. The API supports feeding mono float32 audio chunks at the source sample rate and performs its own resampling. It also supports multiple input streams while sharing one loaded model.

This is a much cleaner fit for live captions than repeatedly invoking a one-shot recognizer over the entire growing utterance.

### 2.2 Model-size shortlist

The upstream current model table lists these English streaming models:

| Model | Parameters | Upstream WER | License |
|---|---:|---:|---|
| Tiny Streaming | 34M | 12.00% | MIT |
| Small Streaming | 123M | 7.84% | MIT |
| Medium Streaming | 245M | 6.65% | MIT |

The WER values are the project's floating-point Open ASR Leaderboard averages across eight datasets. They are not STAR's expected WER, are not measured on STAR's microphone, and should not be compared with a STAR test set unless the exact audio and scoring protocol match. Quantized model results can differ.

**Recommended experiment order:** Tiny Streaming as the lowest-resource baseline, then Small Streaming as the likely quality/compute balance, then Medium Streaming only if it remains comfortably within the CPU and memory budget during simultaneous gameplay and inference.

For STAR's 8 GB VRAM target, run the first experiment on CPU so the main language model, game renderer, OBS, and avatar are not forced to compete for VRAM. Compare CPU and GPU only after measuring the complete mixed workload. Do not assume a small parameter count means zero runtime overhead.

### 2.3 License and language constraints

The current upstream model table says English streaming models are MIT-licensed. Some non-English streaming models are also MIT, while Korean and Ukrainian currently fall back to Community-licensed non-streaming models. The Moonshine Community License is non-commercial.

Do not bundle a non-commercial model in a public/commercial STAR distribution. Record the exact model architecture, checkpoint, license file, and checksum for every tested model. Re-check the license at the exact checkpoint before shipping.

### 2.4 Integration design: one microphone, one event stream

Do not use Moonshine's `MicTranscriber` alongside STAR's existing `Microphone`; that would open a second microphone capture path and complicate device selection, echo behavior, timestamps, and consent.

Instead, add an optional adapter that receives the existing 16 kHz mono frames:

1. Convert PCM16 to mono float32 once at the adapter boundary.
2. Feed each frame into one long-lived Moonshine `Transcriber` session.
3. Attach a listener that maps upstream line events into STAR's typed ASR events.
4. Keep a stable `session_id`, utterance/line ID, monotonic timestamp, and revision number.
5. Treat `LineTextChanged` as provisional UI text only.
6. Treat `LineCompleted` as committed ASR text, but not as permission for STAR to speak.
7. Let the existing `TurnDetector` and room director continue to own end-of-turn, addressee, respond/ignore, interrupt, stop, and queue decisions.
8. At the host-confirmed turn boundary, reconcile the completed line IDs with the current STAR turn and preserve the exact transcript in conversation history.
9. On call cancellation, stop the transcriber and invalidate all late callbacks using a generation/session token.

The first implementation should be a provider adapter behind an opt-in setting, not a replacement for the current ASR path.

### 2.5 Important speaker-ID boundary

Moonshine exposes speaker IDs as identifiers for transcript lines. STAR should treat these as **session-scoped pseudonyms** by default. Do not infer a viewer's real identity from a voice, do not persist raw voice/audio for recognition, and do not link a speaker across separate streams or sessions without an explicit, consented product requirement and privacy review.

Speaker attribution is evidence about which acoustic speaker produced a segment. It does not establish who that person is or whether they addressed STAR.

## 3. VoXtream2.5: full-stream TTS candidate

Primary sources:

- Official implementation: https://github.com/herimor/voxtream
- Project page: https://herimor.github.io/voxtream2/
- VoXtream2 paper: https://arxiv.org/abs/2603.13518

The upstream repository's November 2026 README identifies VoXtream2.5 as a full-stream, zero-shot TTS model with dynamic speaking-rate control. Its current claims include:

- 30 ms first-packet latency and 0.103 real-time factor on an RTX 3090.
- A reported real-time streaming path on one CPU core using GGUF/int8 with llama.cpp.
- GPU inference requiring about 3 GB VRAM; optional prompt enhancement adds about 2 GB.
- A 3–10 second reference audio prompt.
- Streaming text input, with words sent incrementally to the server.
- A maximum generated audio duration of five minutes for the 2.5 configuration.

These numbers are from the upstream project's own benchmark and hardware. They are not measured on STAR's RTX 4060, CPU, or mixed stream workload. The one-CPU-core claim is promising for a CPU/RAM-first design, but the exact CPU real-time factor and quality must be measured locally.

### 3.1 Why it matters

STAR currently starts Kokoro after a complete speakable sentence is available. A full-stream synthesizer can begin producing audio while the model is still generating the rest of a sentence. Dynamic speaking-rate control may also allow a response to slow down for a careful explanation or speed up slightly for a brief, low-stakes interjection.

Do not equate faster speech with more natural speech. The objective is low first-audio latency while preserving intelligibility, stable voice identity, and conversational pacing.

### 3.2 Voice identity and licensing gate

Use only an owner-authorized reference recording or a reference generated from STAR's own currently licensed synthetic voice. Do not imitate a real person without their consent.

The upstream repository says its code is MIT, but also notes that its training data includes Emilia under CC BY-NC 4.0 and HiFiTTS2 under CC BY 4.0. The repository's current README does not establish a simple blanket commercial redistribution license for every released weight. Obtain a clear model-weight/license determination before bundling it or using it in a public/commercial product.

Keep Kokoro as the default until:
- weight licensing is cleared;
- the exact target checkpoint is pinned and checksummed;
- the same authorized voice prompt is used for paired auditions;
- pronunciation, long-form stability, interruption, and CPU/GPU load tests pass.

### 3.3 TTS adapter contract

A STAR TTS provider should expose:

- incremental text input;
- incremental PCM output with explicit sample rate and channel count;
- a response-generation ID on every chunk;
- cancellation that prevents stale chunks from entering the speaker queue;
- first-packet and real-time-factor metrics;
- optional speaking-rate control that can change without restarting the stream;
- explicit warm-up and unload methods;
- no implicit microphone access or network access.

The avatar, captions, and room director must follow the audio actually played, not the text merely generated or audio merely synthesized.

## 4. Full-duplex behavior: measure the client-heard interaction

Full-Duplex-Bench v3: https://www.full-duplex.ai/benchmarks/fdb-v3  
Official benchmark code: https://github.com/DanielLin94144/Full-Duplex-Bench

The v3 protocol adds real-time streaming evaluation with disfluent speech, self-corrections, chained tool calls, task accuracy, latency, and turn-taking. Its published suite contains 100 human-recorded spoken requests across 79 scenarios and 12 speakers.

STAR should add a private, consented benchmark that covers:

- a viewer changing their mind mid-sentence;
- a viewer correcting a name or game command;
- a second person interrupting;
- a question explicitly directed to STAR;
- a side conversation not directed to STAR;
- another human resolving the question before STAR finishes;
- a viewer speaking while STAR is talking;
- a game event occurring during a spoken question;
- a tool result arriving after the original request has become stale.

Measure at the client output, not only at the server:
- speech endpoint to first audible packet;
- partial transcript delay;
- final transcript delay;
- response-intent precision/recall;
- interruption success and time to silence;
- false-interruption rate;
- repeated-answer rate after human resolution;
- task/tool correctness;
- groundedness over long conversations.

A response is not successful just because it is fast. A fast wrong-speaker answer is a failure.

## 5. Faster reasoning without blindly increasing model size

### 5.1 Automatic prefix caching

Official vLLM documentation: https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/

Automatic Prefix Caching reuses KV state for identical prompt prefixes. It reduces repeated **prefill** work when requests share a prefix. It does not make token-by-token **decode** intrinsically faster, and it provides little benefit when prompts do not share a prefix.

STAR already keeps a stable persona/system prefix and trims history in larger blocks. Preserve this property. Keep per-turn data after the stable prefix and avoid inserting timestamps, random IDs, or changing metadata into the cacheable prefix.

Measure cache hit rate, prefill time, decode time, and end-to-end latency separately.

### 5.2 Session-aware cache retention

SGLang session-aware radix cache: https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/session_radix_cache.mdx  
SGLang radix eviction policies: https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/radix_eviction_policy.mdx

SGLang documents session-aware references that can prefer active-session KV during eviction. These are soft references, not memory pins. The application still has to send the intended prompt/context; a cache session ID does not reconstruct conversation history.

STAR should treat this as a backend-specific experiment, not a portable assumption. Keep the existing resource-admission controller as the single authority for resource leases and scheduling.

### 5.3 Speculative decoding

llama.cpp speculative decoding documentation: https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md

llama.cpp supports draft-model and n-gram-based speculative methods, among others. Speculation only helps when the draft path is cheap enough and the target model accepts enough proposed tokens.

For STAR, compare:
- baseline decode tokens/second;
- draft generation cost;
- accepted tokens per draft;
- net tokens/second;
- first-token latency;
- peak VRAM and RAM;
- answer quality and exactness.

Do not enable a draft model that competes with the main model for scarce 8 GB VRAM unless the paired benchmark demonstrates a net win. A lightweight n-gram method may be a lower-memory experiment, but it must still be measured on STAR's actual prompts.

### 5.4 Workload routing

Use the smallest sufficient component for each job:
- VAD and audio framing: small deterministic/local components;
- incremental ASR: small streaming model;
- speaker/addressee and response-intent signals: bounded classifiers plus trusted host context;
- routine tool formatting: quick model;
- hard reasoning, architecture, and unfamiliar research: stronger model;
- verification: independent tests, state inspection, or a second model where appropriate.

The resource supervisor should protect the foreground stream and game renderer. Background research, training, indexing, and asset generation should checkpoint and yield under pressure. Do not create a competing scheduler.

## 6. Gamer Brain: separate strategic reasoning from reactive control

Primary benchmarks:

- GameWorld: https://gameworld-project.github.io/
- GameWorld paper: https://arxiv.org/abs/2604.07429
- Roblox OpenGameEval: https://github.com/Roblox/open-game-eval
- MineDojo: https://github.com/MineDojo/MineDojo
- Voyager: https://github.com/caixianzhou/voyager

GameWorld evaluates 34 browser games and 170 tasks across runner, arcade, platformer, puzzle, and simulation genres. Its outcome metrics read serialized game state rather than asking a vision model to judge whether a screenshot looks successful. It also distinguishes a paused benchmark from a real-time variant where the environment continues while the agent is reasoning.

OpenGameEval evaluates agents inside reproducible Roblox Studio sessions. Its 84-task evaluation emphasizes scene/script inspection and executable checks in both edit and simulated play sessions. The research reports that inspecting relevant objects before acting correlates with higher task success.

### 6.1 Two-timescale controller

Build two cooperating loops:

**Reactive controller**
- bounded input/action primitives;
- movement, camera, aim, dodge, interaction, and cooldown handling;
- short observation-to-action cycle;
- explicit action validity and timeout;
- no large-model call for every frame.

**Strategic planner**
- objective selection;
- map exploration;
- inventory/resource planning;
- enemy/boss strategy;
- route planning;
- post-failure analysis;
- skill selection and adaptation.

The strategic planner sends a compact plan to the reactive controller. The controller reports state changes and failures. The planner is re-invoked on meaningful events rather than every render frame.

### 6.2 Learn skills that transfer

A promoted skill record should contain:
- skill ID and version;
- game/engine and compatible version;
- preconditions and required observations;
- action sequence or controller policy;
- expected state transition;
- timeout and recovery path;
- safety boundaries;
- verifier and evidence;
- known failure modes;
- held-out maps/variants tested;
- rollback target.

Use a curriculum: simple mechanics first, then combinations, then unseen maps and adversarial variants. Do not promote a strategy based only on a single successful attempt or the same model grading itself.

### 6.3 Creator Brain

Use the same inspect-first loop for game creation:

**Inspect project → map dependencies → plan a small patch → edit → run → capture state/screens → verify behavior → repair → save checkpoint**

For Roblox, use the supported Studio MCP/API surface and multiple Studio instances only through explicit instance routing. Use Studio's actual playtest and scene/script state for verification. A script compiling is not evidence that a multiplayer feature works.

## 7. Natural VTuber presence: one event spine

The stream runtime should correlate four sources on one monotonic timeline:

1. microphone/ASR events;
2. moderated chat and room events;
3. game observations and trusted game-state events;
4. speaker playback and avatar/OBS events.

Each event should have:
- session/stream epoch;
- opaque event ID and optional causal parent;
- source and event class;
- monotonic observation time and expiry;
- confidence and evidence reference;
- response-generation ID when one exists;
- source/consent policy outcome.

Do not put raw audio, full transcripts, viewer identity, or video frames into the metadata queue. Keep content in the existing bounded short-lived payload boundary.

### 7.1 Social Director

The Social Director should decide whether to speak before STAR generates a response. Candidate signals:
- explicit address to STAR;
- whether a question has already been resolved;
- novelty and relevance;
- urgency;
- who currently has the floor;
- whether another human is speaking;
- current speech backlog;
- whether the observation is stale;
- resource pressure.

The action set should include `RESPOND`, `QUEUE`, `WAIT`, `IGNORE`, `INTERRUPT`, and `STOP`. Silence is a valid positive outcome.

### 7.2 Avatar and audio synchronization

Avatar states should be derived from actual runtime state:
- idle;
- listening;
- thinking;
- speaking;
- reacting;
- interrupted;
- muted/disconnected.

Bind captions, mouth movement, gestures, and expression changes to the same response-generation ID and played-audio cursor. On cancellation, invalidate pending chunks and stale animation callbacks. Do not move the mouth because text was generated if no audio was played.

Expressive delivery should come from context-appropriate pacing, wording, gaze/attention, and permitted avatar controls—not forced filler, fake laughter, fabricated memories, or a false human biography. STAR remains transparently an AI character.

## 8. General intelligence and memory

Use a task-oriented evidence packet instead of dumping the entire memory store into every prompt.

For each task, retrieve only:
- relevant episodic examples;
- verified procedural skills;
- current project facts;
- causal explanations and failure history;
- authoritative external sources with dates;
- unresolved uncertainties and contradictions.

Every durable fact should retain provenance, timestamp, confidence, scope, and expiry/revalidation policy. Separate:
- working context;
- episodic memory;
- semantic knowledge;
- procedural skills;
- project state;
- user-approved persistent preferences.

When STAR learns a skill, preserve the verified procedure and the conditions under which it worked—not merely the final answer or code blob.

For general knowledge, evaluate research quality, factual accuracy, source freshness, contradiction handling, uncertainty calibration, and whether STAR can apply the knowledge to a new task.

## 9. Evaluation matrix and acceptance gates

Run the following tests on the target Windows machine and the actual streaming configuration. Record CPU, RAM, VRAM, GPU utilization, OBS frame drops, and game frame time in every mixed-load run.

| Area | Required measurements | Promotion gate |
|---|---|---|
| Streaming ASR | partial latency, final latency, WER, real-time factor, CPU/RAM, dropped frames | beats Faster-Whisper on end-to-end latency without unacceptable WER regression |
| Speaker tracking | speaker attribution accuracy, overlap handling, false merges/splits | no persistent identity assumptions; errors fail safely |
| TTS | first packet, RTF, intelligibility, voice similarity, cancellation | no stale audio after cancellation; no stream/OBS starvation |
| Turn-taking | direct-address precision/recall, false interruption, silence correctness | no increase in wrong-person replies or duplicate answers |
| Avatar | audio-to-mouth offset, stale animation rate, caption alignment | playback-authoritative synchronization |
| Gameplay | task success, normalized progress, action validity, recovery, held-out transfer | repeatable improvement on unseen variants |
| Game creation | scene/script checks, playtest pass rate, multiplayer correctness, regression count | no promotion on compile-only evidence |
| Reasoning | correctness, verifier pass rate, calibration, cost, latency | quality gain must justify additional compute |
| Memory | retrieval precision, stale-fact rate, contradiction resolution, token cost | useful transfer without uncontrolled context growth |
| Mixed workload | p50/p95 response latency, game FPS/frame time, OBS drops, memory headroom | foreground stream remains within its declared budget |

### Paired experiment protocol

1. Pin the STAR branch, model versions, engine versions, prompt, and audio/game fixtures.
2. Warm up each provider before timing.
3. Run baseline and candidate with the same utterances/tasks.
4. Randomize run order to reduce thermal/cache bias.
5. Test single-task and mixed workloads.
6. Repeat enough times to report median and p95, not only the best run.
7. Preserve failed runs and error logs.
8. Keep a sealed holdout set for skill/strategy promotion.
9. Record license, model checksum, memory footprint, and rollback procedure.
10. Promote only when quality and latency both improve or a clearly documented trade-off is accepted.

## 10. Prioritized implementation plan

### P0 — Instrument and establish baselines
- Freeze a consented local voice test set and game test set.
- Capture end-to-end client-heard latency, not only server timings.
- Add per-provider CPU/RAM/VRAM and audio-drop attribution.
- Record current Faster-Whisper + Kokoro mixed-load baselines.

### P1 — Moonshine streaming-ASR prototype
- Add an optional provider adapter and typed partial/committed events.
- Reuse the existing microphone capture; do not open a second device.
- Test Tiny Streaming and Small Streaming on CPU first.
- Keep partial text out of tools and durable memory.
- Preserve Faster-Whisper fallback and an opt-out setting.
- Add event-order, cancellation, stale-callback, and long-utterance tests.

### P2 — Full-stream TTS evaluation
- Audit VoXtream2.5 checkpoint licensing and provenance.
- Evaluate the CPU GGUF path first, then GPU only if VRAM headroom remains.
- Compare against Kokoro using the same authorized STAR voice reference.
- Add response-generation IDs, cancellation, and played-audio acknowledgements before any provider switch.

### P3 — Gamer/Creator benchmark harness
- Build a small owner-authored suite with state-verifiable outcomes.
- Add a reactive controller and event-triggered strategic planner.
- Add inspect-first Roblox Studio tasks and automated playtests.
- Test held-out maps, failures, and recovery.

### P4 — Social/avatar integration
- Connect moderated chat, game events, ASR, playback, OBS, and VTube Studio through one event timeline.
- Keep floor control in the host, not in a system prompt.
- Tie expression and lip-sync to actual playback.

### P5 — Transferable learning
- Store verified skill procedures with preconditions and test evidence.
- Run cross-map and cross-project holdouts.
- Promote, version, and roll back skills independently from model weights.

## 11. Explicit non-goals and safety boundaries

- Do not claim that STAR is human, conscious, or has lived experiences.
- Do not fabricate perception, viewer identity, emotions, or personal memories.
- Do not train on benchmark audio unless its license and consent explicitly allow it.
- Do not retain raw viewer audio/video by default.
- Do not persist voice IDs across sessions by default.
- Do not enable public chat posting, purchases, account actions, or irreversible game/server operations without the existing owner-approval policy.
- Do not use game automation to bypass anti-cheat, evade platform rules, or interfere with other players.
- Do not change production model routes, resource budgets, permissions, installer behavior, or release channels as part of a research-only provider evaluation.

## Sources checked for this research

- Moonshine Voice API, streaming events, Python usage, and model licenses: https://github.com/moonshine-ai/moonshine-v2
- Moonshine v2 paper: https://arxiv.org/abs/2602.12241
- Moonshine current streaming model table: https://github.com/moonshine-ai/moonshine/blob/main/docs/models/available-models.md
- VoXtream2.5 implementation and current benchmark: https://github.com/herimor/voxtream
- VoXtream2 project page: https://herimor.github.io/voxtream2/
- VoXtream2 paper: https://arxiv.org/abs/2603.13518
- sherpa-onnx online transducer model catalog: https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-transducer/index.html
- Full-Duplex-Bench v3: https://www.full-duplex.ai/benchmarks/fdb-v3
- Full-Duplex-Bench code: https://github.com/DanielLin94144/Full-Duplex-Bench
- GameWorld: https://gameworld-project.github.io/
- GameWorld paper: https://arxiv.org/abs/2604.07429
- OpenGameEval: https://github.com/Roblox/open-game-eval
- vLLM Automatic Prefix Caching: https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/
- SGLang session-aware radix cache: https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/session_radix_cache.mdx
- SGLang radix eviction policies: https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/radix_eviction_policy.mdx
- llama.cpp speculative decoding: https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md

**Status:** research and implementation handoff only. No candidate provider, checkpoint, dependency, or model default is installed or enabled by this document.
