# STAR Run 28 — Realtime Audio Callback Isolation and Streaming Capability Plan

**Research date:** 2026-11-14  
**Repository:** `oncoursemail/Star-AI-Project`  
**Branch:** `fix/voice-meter-off-callback-20261114`  
**Parent:** draft PR #1178, head `0fb5d5e75c41be8e509c924d4f75863fcf8351d4`  
**Scope:** real-time audio callback workload, bounded telemetry, streaming ASR evaluation, and the next mixed-load acceptance gates.

---

## Executive decision

The highest-value code change in this pass is small but concrete: move speaker RMS/level analysis out of STAR's PortAudio output callback and into a bounded worker.

The current #1178 implementation preloads NumPy before opening the stream, which avoids a first-callback import, but still performs NumPy conversion, allocation, vector arithmetic, and RMS reduction inside the high-priority callback. Those operations are not required to deliver PCM. The meter is used for echo/floor awareness and can be delayed slightly without delaying the audio itself.

Run 28 therefore:

1. Preserves the existing PCM output queue and PortAudio status counters.
2. Removes NumPy from the speaker callback path.
3. Sends best-effort meter samples to a bounded worker queue.
4. Drops stale meter samples rather than blocking or delaying PCM.
5. Treats pending, dropped, or failed meter data as conservatively audible rather than falsely silent.
6. Adds deterministic hardware-free tests for callback independence, overflow, failure, and shutdown.

This is a reduction in callback work, **not a claim of hard real-time safety**. The Python callback still takes the existing PCM-buffer lock and allocates a bytes copy and a small queue record. A preallocated native ring buffer would be a separate, more invasive future step.

No ASR provider, model, prompt, device, buffer size, scheduler, permission, OBS/VTube Studio connection, or production default is changed.

---

## 1. Primary-source findings

### 1.1 PortAudio callback rules

PortAudio's callback guidance says callbacks run at high priority and should avoid memory allocation, I/O, language-boundary calls, OS services, and locks that may be held by lower-priority threads. Callback execution must stay below the duration represented by the requested audio frames; otherwise glitches and missed deadlines become possible.

Sources:

- PortAudio callback tips: https://github.com/PortAudio/portaudio/wiki/Tips_Callbacks
- PortAudio callback-writing guide: https://portaudio.com/docs/v19-doxydocs/writing_a_callback.html
- PortAudio API overview: https://portaudio.com/docs/v19-doxydocs-dev/api_overview.html

### 1.2 python-sounddevice raw streams

The python-sounddevice documentation distinguishes array-based streams from raw buffer streams. RawInputStream and RawOutputStream use Python buffer objects and do not require NumPy for the stream interface. The documentation also requires the output callback to fill the entire output buffer, including when an error occurs.

Sources:

- API overview: https://python-sounddevice.readthedocs.io/en/0.3.12/api.html
- Raw streams: https://python-sounddevice.readthedocs.io/en/0.4.4/api/raw-streams.html

**STAR implication:** NumPy is not necessary for PCM delivery. A small PCM16 RMS function can run on a normal worker thread, while the callback focuses on copying queued PCM and filling any underrun remainder with silence.

### 1.3 On-device streaming ASR candidate: Moonshine Voice

The current Moonshine repository describes an on-device toolkit for streaming speech-to-text, intent recognition, text-to-speech, and voice-agent workflows. It lists Windows support and streaming-oriented examples. Its public repository also documents model and license details, including exceptions for some legacy non-English models.

Sources:

- Official repository: https://github.com/moonshine-ai/moonshine
- Official live demos: https://www.moonshine.ai/
- Documentation: https://moonshine-voice.readthedocs.io/

**STAR decision:** benchmark Moonshine as an optional ASR adapter against the existing Faster-Whisper path. Do not replace the current provider based on vendor-reported latency or leaderboard results. Measure the exact model, version, Windows machine, microphone, noise profile, and mixed STAR workload.

### 1.4 Inference serving is a separate bottleneck

The llama.cpp server documents continuous batching, parallel decoding, speculative decoding, and monitoring endpoints. These are relevant to STAR's foreground/background model scheduling, but they do not solve audio callback deadlines.

Source:

- llama.cpp server documentation: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md

**STAR decision:** keep inference optimization in the existing telemetry/evaluation train (#1131, #1167, #1166, #1140/#1142). Do not move model work into the audio callback or introduce another scheduler.

---

## 2. Repository audit and exact integration gap

The code review compared:

- #1178, `feat/resource-admission-20261113-run21`
- #1151, `feat/voice-playback-clock-and-validation-fix-20261112`

In #1178, `SoundSpeaker._callback` still computes output RMS using NumPy after copying PCM to the PortAudio output buffer. Preloading NumPy prevents an import on the first callback, but it does not remove the per-callback conversion and RMS work.

The separate #1151 branch already contains a bounded asynchronous meter-worker design. Its full branch cannot be blindly merged because it has a different base and also changes playback timing, voice metrics, acknowledgements, and related tests.

**Run 28 ports only the isolated meter-worker responsibility** onto a child branch of #1178. It intentionally does not copy the separate playback-clock implementation or overwrite #1178's room/voice changes.

---

## 3. Implementation contract

### Callback path

The output callback now:

1. Reads the existing PCM buffer under the existing speaker lock.
2. Updates PortAudio underflow/overflow counters.
3. Copies the available PCM into the output buffer.
4. Fills the remainder with zero-valued silence.
5. Enqueues the already-created PCM chunk as best-effort meter input.
6. Returns without NumPy conversion or RMS calculation.

### Meter worker

A dedicated daemon worker:

- consumes a bounded queue;
- computes native-endian PCM16 RMS;
- stores only a short bounded level history;
- detects sequence gaps caused by telemetry eviction;
- counts dropped meter blocks;
- stops after the stream is closed and queued telemetry is drained.

### Conservative echo-gate behavior

If meter data is pending, dropped, or failed, `level()` returns a conservative non-silent value for the short echo window. This prevents a telemetry failure from being interpreted as proof that STAR is not speaking.

### Data minimization

The worker retains only short-lived PCM blocks already emitted by the speaker and aggregate meter values. It does not write audio to disk, persist transcripts, expose device names, or send media to a service. The bounded queue and history cap memory use.

### Queue overflow policy

The meter queue is intentionally lossy; the PCM path is not. When the worker cannot keep up, old meter samples may be evicted and the echo gate becomes conservative. Audio chunks already copied to the device are never removed to make room for telemetry.

---

## 4. Tests added

The hardware-free tests cover:

- PCM16 RMS correctness for known amplitudes and malformed/empty input.
- A deliberately blocked RMS worker while the output callback still returns promptly.
- Byte-for-byte preservation of the PCM output.
- Pending meter data being treated as unknown/non-silent.
- Meter queue overflow while all PCM callbacks still emit their full audio blocks.
- Sequence-gap detection and dropped-meter accounting.
- Worker exceptions remaining conservative.
- Idempotent close and worker termination.

These tests establish the queue/worker contract under synthetic conditions. They do not establish physical Windows device stability or listener-heard latency.

---

## 5. Performance validation plan

Do not claim a speedup from code inspection alone. Compare the parent #1178 head with this candidate on the same machine, device, driver, sample rate, block size, and audio content.

Record at minimum:

| Metric | Why it matters |
|---|---|
| Callback duration p50/p95/p99/max | Measures callback work and tail spikes |
| PortAudio output underflows | Detects missed output deadlines |
| Meter queue high-water mark | Detects worker lag |
| Dropped meter blocks | Shows telemetry pressure |
| PCM byte equality in synthetic tests | Proves telemetry cannot alter output |
| Speaker queue depth | Separates TTS backlog from device callback delay |
| First audio submitted | Measures the application-side start |
| First callback with audio | Measures local output scheduling, not acoustic arrival |
| CPU usage by process/thread | Detects contention during gameplay and inference |

Run three paired conditions:

1. **Idle:** voice call only.
2. **Broadcast:** voice plus OBS and avatar animation.
3. **Full mixed load:** voice, OBS, VTube Studio, game, ASR, LLM generation, TTS, chat, and bounded background learning.

Use repeated trials and report median, p95, p99, sample count, dropped/invalid samples, and exact hardware/software versions. Keep the same test utterances and playback samples between baseline and candidate.

The callback worker is acceptable only if it preserves PCM, does not increase underflows, remains bounded under stress, and does not create a measurable regression in end-to-end speech quality or avatar timing.

---

## 6. Broader capability roadmap — avoid duplicating active trains

STAR already has substantial draft work for multiparty room decisions, task coordination, resource admission, incremental thinking, Live2D frame transport, streamed inference measurement, and paired rehearsal evaluation.

The next useful integration sequence is:

1. Land and verify the single resource-admission chain (#1140/#1142) before introducing more background workers.
2. Keep partial ASR hypotheses ephemeral; only stable/final transcripts enter canonical conversation state.
3. Benchmark Moonshine Voice and sherpa-onnx as optional adapters against Faster-Whisper on the target Windows hardware.
4. Keep speech playback acknowledgements distinct from TTS queue submission and from actual listener-heard output.
5. Connect gameplay perception to a low-frequency strategic planner and a separately bounded real-time controller.
6. Promote game skills only after held-out map/task transfer and independent environment checks.
7. Use Creator's inspect → edit → run → observe → repair → verify loop for Roblox, Godot, and Unity; keep each engine's acceptance tests separate.
8. Preserve claim-level source provenance and freshness for general-knowledge retrieval.
9. Keep long-running research and learning work in the background lane so it cannot starve live speech, game control, or avatar deadlines.

---

## 7. Explicit limitations

- This child branch is based on the #1178 draft head; it is not based directly on production `main`.
- The change moves RMS analysis off the callback but does not make Python/PortAudio callback execution formally hard real-time.
- The existing PCM-buffer lock and bytes copy remain.
- No NumPy package removal from the overall project is proposed; other STAR components may still require it.
- No ASR model is installed, selected, or enabled.
- No measured latency or CPU improvement is claimed.
- No Windows microphone/speaker, RTX 4060, OBS, VTube Studio, Roblox Studio, gameplay, or public livestream test was performed.
- GitHub Actions on the exact child PR head must pass before repository-level validation is claimed.
- Parent PR #1178 and its stacked dependencies remain draft and unmerged; production `main` is unchanged.

---

## Source register

1. PortAudio callback tips — https://github.com/PortAudio/portaudio/wiki/Tips_Callbacks
2. PortAudio callback guide — https://portaudio.com/docs/v19-doxydocs/writing_a_callback.html
3. PortAudio API overview — https://portaudio.com/docs/v19-doxydocs-dev/api_overview.html
4. python-sounddevice API — https://python-sounddevice.readthedocs.io/en/0.3.12/api.html
5. python-sounddevice raw streams — https://python-sounddevice.readthedocs.io/en/0.4.4/api/raw-streams.html
6. Moonshine Voice — https://github.com/moonshine-ai/moonshine
7. Moonshine live demos — https://www.moonshine.ai/
8. llama.cpp server — https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
