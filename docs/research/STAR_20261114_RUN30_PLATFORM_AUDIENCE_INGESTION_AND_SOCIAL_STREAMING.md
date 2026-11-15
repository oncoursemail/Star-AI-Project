# STAR Run 30 — Platform Audience Ingestion, Social Presence, and Safe Live Interaction

**Research date:** 2026-11-14  
**Repository:** oncoursemail/Star-AI-Project  
**Branch:** research/star-run24-integration-blueprint-20261114  
**Parent:** draft PR #1180, based on production main  
**Related implementation:** draft PR #1178 (provider-neutral room host and turn director)  
**Related acceptance:** issue #584 — STAR Creator Studio: production VTuber, games, live chat, multistream and auto-editing  
**Scope:** Twitch and YouTube live-chat ingestion, provider lifecycle, audience-event normalization, natural conversational participation, privacy, moderation, and acceptance testing.

---

## Executive decision

STAR's next major VTuber integration gap is not another persona prompt or another queue. The repository already has a provider-neutral room policy and host boundary. What it does not yet have is a production platform adapter that authenticates to a live service, receives real chat events, maps them into trusted metadata, and safely hands the short-lived message payload to the existing room host.

Build the platform layer as two narrow, opt-in adapters:

1. **Twitch EventSub WebSocket** for chat messages and selected channel events.
2. **YouTube Live Chat streamList** for low-latency chat ingestion and resumable catch-up.

Both adapters must feed the existing RoomStreamHost / RoomTurnDirector / RoomPayloadStore path. Do not create a second social director, a second queue, a second task ledger, or a second resource scheduler.

The first release should be **read-only intake**. Chat output, polls, moderator actions, channel changes, and public-stream start/stop remain separate capabilities with separate authorization and confirmation. A viewer message is untrusted content, never an instruction to operate the PC, edit a game, reveal secrets, or invoke a tool.

The target is a natural, expressive AI streamer who notices the right people and events, responds at the right moment, and is comfortable being quiet. The target is not to deceive viewers into believing STAR is biologically human.

## 1. Repository audit: the host boundary already exists

The current development line has these responsibilities:

| Existing component | Current responsibility | Run 30 decision |
|---|---|---|
| star/voice/room.py | Metadata-only RoomCue and deterministic speak / queue / continue / ignore / interrupt / stop policy | Reuse as the single floor-control authority |
| star/voice/room_host.py | Trusted ingress, source allowlist, bounded per-source/per-speaker rate limits, deduplication, final-cue validation, and required chat moderation callback | Reuse; do not duplicate it |
| star/voice/room_payloads.py | Bounded short-lived message payload storage separate from metadata | Keep raw text out of RoomCue and long-term memory |
| star/voice/call.py | Room messages become untrusted user content for the voice brain; this path does not invoke tools | Preserve this hard boundary |
| star/voice/bridge.py | Host-only submit_room_message; not registered as a frontend/IPC action | Keep provider ingress outside the renderer |
| star/voice/persona.py | Stable AI-character voice and streaming-naturalness rules | Keep character behavior separate from floor permission |
| PR #1177 | Durable task and communication ledger | Use only for actual long-running work, not every chat line |
| PRs #1140 / #1142 | Existing resource-admission and stream-pressure path | All optional classifier/model work must use this one authority |
| PR #1159 | Playback-aware, latest-wins Live2D frame transport | Keep avatar transport independent of platform chat |
| PR #1165 / #1166 / #1167 | Rehearsal quality, paired comparison, and streamed inference measurements | Reuse for acceptance and performance comparisons |

The RoomStreamHost module explicitly states that Twitch, YouTube, Discord, ASR/diarization, and game observers are outside the host. A trusted adapter must authenticate, obtain consent, moderate, classify, and construct a RoomCue before submission. The current host already requires a moderation callback when chat is enabled.

This is the concrete integration gap Run 30 addresses.

**Do not change the existing room policy to make it platform-aware.** Platform-specific details belong in adapters. The host should continue receiving a normalized cue plus a separate, short-lived text payload.

## 2. Proposed platform-neutral event contract

Each provider adapter should normalize its events into an immutable envelope. The envelope is metadata only; raw message text remains in the existing bounded payload store.

Recommended fields:

| Field | Meaning |
|---|---|
| stream_session_id | Opaque ID for the current STAR broadcast session |
| platform | twitch or youtube |
| platform_event_id | Provider event/message ID used for dedupe |
| event_kind | Chat text, reply, cheer, subscription, membership, poll, deletion, moderation hold, raid, or connection state |
| source | Existing CueSource.CHAT or a separately approved event source |
| speaker_ref | Session-scoped opaque pseudonym; not a global viewer identity |
| reply_to_event_id | Existing platform message ID, when the event is a reply |
| observed_wall_time | Provider timestamp for diagnostics and ordering |
| received_monotonic | Host monotonic arrival time used for freshness and deadlines |
| expires_monotonic | Hard expiry after which the event cannot trigger speech |
| intent | Existing CueIntent after trusted classification |
| addressed_to_star | True only when supported by strong evidence |
| confidence | Classifier confidence, calibrated on held-out stream sessions |
| urgency | Bounded event urgency; money must not automatically override direct questions |
| moderation_state | Normal, held, deleted, cleared, suspicious, or unknown |
| payload_ref | Opaque handle to a bounded ephemeral text payload |
| consent_scope | Which owner-approved source and capabilities are active |
| correlation_id | Links the platform event to the response generation and playback acknowledgement |

Do not put raw chat text, profile URLs, profile images, email addresses, access tokens, refresh tokens, or permanent viewer identifiers into the metadata envelope.

### Identity rules

- Platform account IDs are not interchangeable across Twitch and YouTube.
- Never assume two accounts on different platforms belong to the same person.
- Derive a per-session pseudonym from the platform namespace and provider ID using a session-specific secret; discard the mapping at stream end.
- Keep the provider message ID only as long as needed for deduplication, deletion handling, and reply threading.
- Do not infer real-world identity, age, location, health, personality, or relationships from a username, profile image, voice, or chat behavior.
- Do not build a durable viewer dossier by default.
- If an owner-approved returning-viewer feature is considered later, it needs a separate purpose, explicit retention policy, deletion path, and privacy review.

## 3. Twitch: EventSub WebSocket adapter

### 3.1 Preferred transport

Use the official Twitch EventSub WebSocket transport for a local STAR desktop or owner-controlled server. It avoids exposing a public inbound webhook endpoint and supports near-real-time channel events.

Official sources:

- EventSub overview: https://dev.twitch.tv/docs/eventsub
- WebSocket handling: https://dev.twitch.tv/docs/eventsub/handling-websocket-events
- WebSocket message reference: https://dev.twitch.tv/docs/eventsub/websocket-reference/
- Chat event reference: https://dev.twitch.tv/docs/eventsub/reference/chat
- OAuth scopes: https://dev.twitch.tv/docs/authentication/scopes
- Sending and receiving chat: https://dev.twitch.tv/docs/chat/send-receive-messages

### 3.2 Connection lifecycle

Implement an explicit state machine:

**DISABLED → CONNECTING → WELCOMED → SUBSCRIBING → ACTIVE → RECONNECTING**

Terminal or fail-closed states:

**AUTH_REVOKED, SUBSCRIPTION_REVOKED, STOPPING, STOPPED, ERROR.**

Required behavior:

1. Connect to Twitch's documented EventSub WebSocket endpoint.
2. Validate the first session_welcome message and retain its session ID.
3. Create only the subscriptions selected in the owner's configuration.
4. Subscribe within the welcome window; Twitch currently documents a 10-second window.
5. Track the keepalive timeout from the welcome message.
6. Respond to WebSocket Ping frames with Pong; do not send arbitrary application messages to the EventSub socket.
7. On session_reconnect, use the supplied reconnect URL exactly as provided.
8. Keep the old connection alive until the new connection receives its welcome message, then close the old connection.
9. If the connection is lost without a reconnect handoff, reconnect and recreate subscriptions. Mark the event interval as a gap because Twitch does not replay notifications missed during an ordinary disconnect.
10. Treat token revocation, subscription revocation, and permission loss as an explicit disconnected state; never silently switch to another account or request broader scopes.

Twitch recommends maintaining one WebSocket connection until there is a reason to create another. The current documented limits include a maximum of three enabled WebSocket connections per user-token pair and up to 300 subscriptions per connection, with subscription-cost limits. STAR needs only one connection for a single channel.

### 3.3 Delivery semantics and deduplication

Twitch notifications are at-least-once. A notification may be delivered more than once, and a resend uses the same metadata.message_id.

The adapter must:

- Deduplicate before any classifier or speech generation.
- Use the provider message ID, not display text, as the primary idempotency key.
- Reject messages with a provider timestamp older than the replay window.
- Keep a bounded recent-ID cache, scoped to the current stream session.
- Preserve event ordering where possible, but do not delay fresh direct messages waiting for old low-priority events.
- Emit a content-free gap marker when the connection was unexpectedly lost.
- Never speak a delayed backlog as if it were live.

Twitch documents a 10-minute age check as one replay-attack guard. STAR should use a much shorter speech-freshness TTL for live conversation; the 10-minute check is a provider replay/security check, not permission to read a message aloud ten minutes late.

### 3.4 Minimal subscriptions for the first pilot

Start with only:

- channel.chat.message — viewer chat text.
- channel.chat.message_delete — invalidate a message removed by a moderator.
- channel.chat.user_message_hold and channel.chat.user_message_update — respect AutoMod holds and subsequent status changes.
- channel.chat.notification — optional subscription/gift and chat-visible event notifications, if the owner enables acknowledgements.

Potential later subscriptions, only when actually needed:

- channel.follow — requires the appropriate follower-read authorization.
- channel.subscribe and related subscription events — require subscription-read authorization.
- channel.cheer — requires Bits-read authorization.
- Channel Point redemption events — require the specific redemption permissions.
- Raid events — use the documented channel event type and its required authorization.

Do not request every available scope. Twitch explicitly instructs applications to request only the scopes needed for their functionality.

For a WebSocket chat subscription, use a user access token with user:read:chat. The EventSub chat reference also documents app-token authorization paths with prior user/bot and channel/bot grants for applicable transports. Do not assume an app token is interchangeable with a user token for WebSocket subscriptions.

### 3.5 Chat write must remain separate

The official Send Chat Message API uses a separate user:write:chat scope. It is not needed for read-only ingestion.

If STAR eventually sends chat messages:

- Add a separate, visibly disabled-by-default “STAR may send chat” capability.
- Request the write scope only when the owner enables that capability.
- Show the exact outgoing message before first-time use and provide an immediate stop switch.
- Apply a per-session message budget, cooldown, duplicate suppression, and reply-to-message binding.
- Never allow chat output to run commands, grant permissions, publish a game, change account settings, or start/stop a public stream.
- Treat a platform response indicating that AutoMod held or dropped the message as a failed send; do not retry blindly.

No write scope is needed for Run 30.

## 4. YouTube: Live Chat streamList adapter

### 4.1 Prefer server-streaming over tight polling

Use the official YouTube Live Streaming API method liveChatMessages.streamList.

Official sources:

- streamList: https://developers.google.com/youtube/data/live/reference/rest/v3/liveChatMessages/streamList
- LiveChatMessages resource: https://developers.google.com/youtube/data/live/reference/rest/v3/liveChatMessages
- Authorization: https://developers.google.com/youtube/data/live/authentication
- LiveBroadcasts list: https://developers.google.com/youtube/data/live/reference/rest/v3/liveBroadcasts/list

The official documentation describes streamList as a low-latency server-streaming connection that pushes new messages as they become available. It is more efficient than repeatedly polling for updates.

### 4.2 Resume behavior

Each response includes a nextPageToken. Persist the most recent token only for the active broadcast session, and use it as pageToken when reconnecting.

Required behavior:

- Process messages in provider order (oldest to newest within each response).
- Deduplicate by YouTube liveChatMessage ID.
- Resume from the last successfully committed page token.
- Treat an invalid or expired page token as a recoverable gap; do not replay the entire stream history into the voice queue.
- The first connection may include recent history. Summarize or skip that history according to the selected session mode; never read hundreds of old messages aloud.
- Stop the stream when the broadcast ends or chat becomes disabled.
- Record provider gap/reconnect state without persisting message contents.

The current documentation lists a quota cost of 5 units for streamList. The list method also costs 5 units and exposes pollingIntervalMillis; if a fallback poller is ever necessary, respect the returned interval instead of polling on a fixed aggressive timer.

### 4.3 Broadcast discovery and authorization

A liveBroadcast resource exposes snippet.liveChatId.

For a user-selected public broadcast, a restricted API key may be sufficient to read public live chat data. If STAR discovers the owner's private or own broadcast automatically through liveBroadcasts.list with mine=true, use the documented OAuth flow and the narrow read-only scope needed for that account operation.

Keep API keys restricted to the YouTube Data API and the intended application. Keep OAuth access and refresh tokens in the operating-system credential store, never in settings JSON, chat, logs, telemetry, or GitHub.

### 4.4 Message and event types

The YouTube liveChatMessage resource can represent more than ordinary text:

- Text message events.
- Super Chats and Super Stickers.
- Membership milestones.
- New sponsorship events.
- Membership gifts and received gifts.
- Poll events.
- User-banned and message-deleted event records.

Normalize these into event classes rather than flattening everything into a text string.

A Super Chat amount or membership tier may justify a short acknowledgement if the owner enables it, but monetary value must not automatically outrank a direct question, a safety issue, or an ongoing conversation. STAR should not imply that viewers can buy a guaranteed response or privileged personal relationship.

### 4.5 Chat write is a separate capability

YouTube's liveChatMessages.insert method requires write authorization and has a documented quota cost of 20 units. Its documented scopes include youtube and youtube.force-ssl.

Do not request those scopes for read-only ingestion. Do not enable message insertion, poll creation, message deletion, bans, or moderation operations in the first pilot.

## 5. Natural social participation: what STAR should actually do

The existing RoomTurnDirector should remain the authority that decides whether STAR responds, queues, continues, interrupts, stops, or stays silent.

A platform adapter should not decide to speak merely because a message arrived.

### 5.1 Four-stage selection

**Stage A — Evidence**

- Is this a real platform event?
- Is the provider event ID valid and not duplicated?
- Is the event still fresh?
- Is it visible and not held/deleted?
- Is the current broadcast/session still active?

**Stage B — Addressing and intent**

Strong evidence that a message is directed to STAR includes:

- An explicit mention of STAR's configured channel handle.
- A reply to a recent message that STAR actually sent.
- An explicit, documented command such as a bounded poll vote.
- A direct question with clear context in the current conversation.

Weak evidence includes:

- Any sentence containing a question mark.
- A viewer saying “Star” while talking to another viewer.
- A general comment about the game.
- A donation message with no request.
- A message that merely resembles a command.

When addressing is uncertain, classify it as UNKNOWN or SIDE_CONVERSATION. Do not invent confidence.

**Stage C — Opportunity**

Before speaking, check:

- Is another human speaking?
- Is STAR already answering?
- Has the question already been resolved?
- Is the game in a high-focus moment?
- Is the voice output queue backed up?
- Is the event still fresh?
- Is there a cooldown for this event or speaker?
- Is the current stream mode mention-only, question-queue, co-host, or quiet-focus?

**Stage D — Smallest useful response**

Prefer, in order:

- Silence when no response is needed.
- A short acknowledgement.
- One useful answer.
- A concise follow-up question.
- A brief game-coaching cue when requested.
- A queued response when another person has the floor.

Do not narrate every chat line or game frame.

### 5.2 Session modes

Expose explicit modes instead of relying on one prompt to guess the desired social behavior:

| Mode | Behavior |
|---|---|
| Quiet focus | Monitor chat, speak only for direct high-confidence questions or urgent owner-approved events |
| Mention only | Respond only to explicit STAR mentions or replies to STAR |
| Question queue | Collect direct questions and answer one at a time during natural pauses |
| Co-host | Participate in group discussion when invited; silence is scored as a valid action |
| Game coach | Prioritize requested coaching and game-critical events; suppress unrelated chatter |
| Celebration | Acknowledge follows, memberships, raids, and milestones briefly, subject to owner-enabled event types |
| Rehearsal | Use fixture events and simulated viewers; never connect to a public channel |

Each mode must be visible in the stream control panel and reset to the owner's configured default when the session ends.

### 5.3 Conversation quality

Evaluate more than response latency:

- Correct addressee detection.
- Multi-party comprehension.
- Turn-taking appropriateness.
- Duplicate-answer rate.
- Unnecessary interruption rate.
- Appropriate silence rate.
- Relevance to the active game.
- Groundedness to supplied evidence.
- Voice and avatar timing.
- Viewer message-to-response delay.
- Long-session repetition and topic drift.

The existing Full-Duplex-Bench v3 and MP-Bench research should be reused. Their benchmark audio/tasks are evaluation assets, not a default training corpus. Build separate consented rehearsal data for any adaptation.

## 6. Bounded event selection and backpressure

A busy chat can generate more events than STAR can answer. Do not push every message into the LLM context.

Use a two-stage pipeline:

1. **Ingest and account:** validate, deduplicate, classify provider event type, apply moderation state, and update aggregate counters.
2. **Select for attention:** choose only a small number of fresh, relevant events for the room host.

Recommended policies:

- Direct mention/reply: high priority when confidence is high.
- Direct question: high priority when clearly addressed to STAR.
- Correction to STAR's active answer: high priority if it is relevant and credible.
- Viewer-to-viewer discussion: retain only short-lived context; normally do not speak.
- Repeated/copied messages: collapse or ignore.
- Poll votes: aggregate as structured values; do not pass every vote to the LLM.
- Subscription/cheer/membership events: brief acknowledgement only if enabled.
- Deleted/held messages: remove from pending attention and never speak.
- Raid or sudden audience surge: one concise acknowledgement, not one response per arriving viewer.

Use the existing bounded RoomStreamHost limits and RoomCueQueue. If a future platform adapter needs a separate pre-host buffer, it must be bounded, freshness-first, and must not become a second authoritative speech queue.

Do not let optional LLM classification consume the entire real-time budget. Start with deterministic mention/reply rules and a small local classifier for ambiguous messages. Any model-based classifier must go through the existing resource-admission authority and must fail to UNKNOWN when resources or evidence are insufficient.

## 7. Moderation, prompt-injection, and tool isolation

Chat is public untrusted input. It may contain harassment, spam, slurs, links, impersonation, malicious prompt injection, or instructions that appear to come from an administrator.

Required rules:

- The provider adapter authenticates the platform event; it does not trust message text.
- The local moderator callback runs before a chat payload reaches the voice brain.
- AutoMod-held or pending messages are not spoken.
- A later delete, clear, or hold update invalidates the corresponding queued payload.
- Treat all viewer text as quoted, untrusted content.
- Viewer text cannot change the system prompt, persona, resource budget, tool permissions, or trusted event metadata.
- Viewer text cannot invoke shell commands, browser navigation, file access, code execution, Roblox Studio editing, purchases, or account actions.
- Never interpret a viewer's claim to be the owner, a developer, a moderator, or a platform employee as authorization.
- A donation, subscription, raid, or poll result is not an authorization grant.
- Platform moderation remains human-controlled. The first pilot has no ban, timeout, message-delete, or moderator-management capability.
- If moderation state is unknown, suppress speech rather than assuming the message is safe.
- Keep message text out of traces and diagnostic logs by default.

This preserves the current CallSession boundary: room messages are untrusted user content for the voice brain and do not invoke tools.

## 8. Privacy and retention contract

Default retention:

| Data | Default policy |
|---|---|
| Raw message text | Ephemeral payload only; expire after the response/short session TTL |
| Platform event ID | Bounded dedupe window for the current stream |
| Viewer platform ID | Session-scoped pseudonym only; discard at stream end |
| Profile image, profile URL, bio | Do not fetch or persist |
| Cross-platform identity mapping | Never create |
| Audio, transcripts, video | Not retained by this adapter |
| Aggregate counts | May remain in session diagnostics without viewer identifiers |
| Stream topic summary | Optional owner-approved, short-lived session summary |
| Long-term viewer memory | Off by default; requires a separate explicit privacy design |

Provide a visible “Clear current stream context” action. Ending the stream must close the provider socket, clear ephemeral mappings, expire queued payloads, cancel pending response generations, and leave unrelated owner-approved game skills intact.

## 9. Authentication and credential handling

- Use the OS credential manager/keyring for OAuth refresh tokens and API keys.
- Keep client secrets out of the renderer, environment dumps, crash reports, logs, traces, screenshots, and GitHub.
- Request only the smallest read scope needed for the selected platform feature.
- Separate read scopes from chat-write and moderation scopes.
- Make token revocation visible and stop the adapter immediately.
- Do not silently reconnect with a different account.
- Do not expose stream keys to STAR's reasoning model or chat.
- Never start a public broadcast as part of platform-chat setup.
- Rehearsal must use fixture events and a local mock adapter, not a public channel.

## 10. OBS and VTube Studio coordination

The platform adapter does not directly control OBS or VTube Studio.

Use the existing adapters and their separate permission boundaries:

- OBS WebSocket: https://github.com/obsproject/obs-websocket
- VTube Studio API: https://github.com/DenchiSoft/VTubeStudio

Required behavior:

- Local OBS WebSocket stays password-authenticated.
- STAR receives an allowlist of permitted scene/source operations.
- No public network exposure of OBS WebSocket.
- VTube Studio must show its normal plugin authorization prompt.
- Store the VTube Studio token securely and handle revocation.
- Use the existing playback-authoritative avatar path for lip-sync.
- A chat event may request a small expression/emote from an allowlist, but cannot load arbitrary files, images, models, plugins, or scripts.
- Avatar reactions must not delay audio playback or game control.
- A platform disconnect must not freeze the avatar or block the stream.

## 11. Feature roadmap unlocked by this integration

Once read-only ingestion passes acceptance, STAR can support:

1. Viewer question queue with natural answer timing.
2. Mention/reply awareness.
3. Viewer-to-viewer conversation awareness.
4. Contextual greeting for returning viewers within the current session only.
5. Brief follow/subscription/raid acknowledgements.
6. Super Chat / Bits / membership acknowledgement with no paid-response guarantee.
7. Structured polls and safe viewer votes.
8. Game challenge voting through a constrained allowlist.
9. Chat-driven emote/expression triggers.
10. Live captions and translated captions.
11. Chat topic summary for STAR's own context.
12. Post-stream audience question summary.
13. Highlight candidates linked to game events and playback timestamps.
14. Stream health and chat-pressure dashboard.
15. Cross-platform chat normalization without identity merging.
16. Private rehearsal with synthetic viewers.
17. Owner-reviewed highlight/clip candidates.
18. A read-only analytics view of aggregate event counts.

TikTok Live should be a later provider only through an account-eligible, documented official integration. Do not scrape web chat, reverse engineer private endpoints, or automate a browser login to bypass platform APIs.

## 12. Acceptance test plan

### Provider fixture tests

For Twitch and YouTube separately:

- Valid chat message.
- Duplicate delivery.
- Out-of-order delivery.
- Old timestamp.
- Future timestamp.
- Malformed payload.
- Unknown event type.
- Unicode, emotes, links, and unusually long message.
- Message deletion.
- AutoMod hold and release.
- Channel clear.
- Provider reconnect.
- Provider token revocation.
- Subscription failure.
- Stream ended.
- API quota/rate limit.
- Large message burst.
- Invalid continuation token / page token.
- Shutdown while a message is queued.

### Room integration tests

- Direct mention is recognized.
- Reply to STAR's known message is recognized.
- Viewer-to-viewer conversation is not answered.
- Ambiguous question is not confidently treated as addressed to STAR.
- Resolved question stops the exact active response.
- Duplicate message never causes duplicate speech.
- Deleted/held message is removed before response.
- Stale message expires.
- Chat burst cannot starve microphone, game control, TTS, avatar, or OBS.
- Chat text cannot invoke a tool or alter permissions.
- Stop/mute and owner takeover always win.
- Stream end clears ephemeral viewer/session state.

### Suggested acceptance thresholds

These are proposed STAR targets, not measured results:

| Metric | Initial target |
|---|---|
| Duplicate spoken events | 0 |
| Held/deleted messages spoken | 0 |
| Cross-platform identity merges | 0 |
| Stale chat responses | 0 after configured TTL |
| Chat-triggered tool invocations | 0 |
| Provider reconnect | Recover or show disconnected state; never silently lose state |
| Queue memory | Fixed, configured upper bound |
| Direct mention recognition | Report precision and recall separately on held-out sessions |
| Unnecessary interruption | Report per-session rate; do not hide behind average latency |
| Appropriate silence | Score as a positive outcome when STAR should not speak |
| Foreground audio/game control regressions | 0 accepted regressions versus paired baseline |

Do not promote a classifier based on aggregate accuracy alone. Report precision, recall, calibration, false-positive direct-address rate, false-negative direct-address rate, and session-clustered uncertainty.

### Mixed-load acceptance

Run paired baseline/candidate rehearsals with:

1. Chat only.
2. Chat + voice call.
3. Chat + OBS + VTube Studio.
4. Chat + game + local ASR + LLM + TTS.
5. Full mixed load with bounded background learning.

Measure p50/p95/p99 for event-to-decision, decision-to-first-audio, actual playback acknowledgement, avatar synchronization, queue age, CPU/RAM/VRAM, game frame time, audio underruns, and dropped telemetry.

A faster response is not a win if it speaks over people, answers the wrong viewer, repeats deleted content, harms game control, or degrades the stream.

## 13. Implementation sequence

1. Add typed provider-neutral event fixtures and contract tests.
2. Implement Twitch EventSub WebSocket read-only adapter behind a new explicit opt-in.
3. Map Twitch events into the existing RoomStreamHost without changing RoomTurnDirector.
4. Implement YouTube streamList read-only adapter with page-token resume.
5. Add platform-specific message tombstones and moderation-state handling.
6. Add the four session modes: quiet focus, mention only, question queue, and co-host.
7. Add privacy-safe aggregate metrics to the existing trace/diagnostic path.
8. Rehearse with synthetic chat fixtures and consented private sessions.
9. Compare against the current room host using paired, held-out multi-party sessions.
10. Only then consider a separate, owner-approved chat-write capability.

Do not bundle platform OAuth, public stream start, moderation actions, game-control permissions, and chat reading into one broad “streamer” permission.

## 14. Research and repository handoff

This work aligns with existing issue #584, which already calls for owner-authorized Twitch EventSub and YouTube chat intake as moderated read-only pilots. It does not bypass the issue's legal, account-authorization, playtest, or public-stream acceptance requirements.

Related development:

- PR #1178: provider-neutral room host, room turn director, natural streamer persona, and exact response stopping.
- PR #1180: research and integration blueprint.
- PR #1159: Live2D frame transport.
- PR #1140 / #1142: resource admission and stream pressure.
- PR #1165 / #1166 / #1167: rehearsal quality, paired evaluation, and inference timing.
- Issue #584: end-to-end Creator Studio and VTuber acceptance.

### Scope boundary for this document

- Research and integration design only.
- No Twitch/YouTube OAuth app, client secret, API key, or refresh token created.
- No platform connection or public chat read performed.
- No message was sent.
- No moderation action was enabled.
- No OBS/VTube Studio permission was granted.
- No public stream was started.
- No model, voice, scheduler, or production default changed.
- No benchmark data was copied into training.
- No live-stream performance or human-equivalence claim is made.

---

## Primary sources

1. Twitch EventSub overview — https://dev.twitch.tv/docs/eventsub
2. Twitch WebSocket handling — https://dev.twitch.tv/docs/eventsub/handling-websocket-events
3. Twitch WebSocket reference — https://dev.twitch.tv/docs/eventsub/websocket-reference/
4. Twitch Chat EventSub reference — https://dev.twitch.tv/docs/eventsub/reference/chat
5. Twitch OAuth scopes — https://dev.twitch.tv/docs/authentication/scopes
6. Twitch sending and receiving chat — https://dev.twitch.tv/docs/chat/send-receive-messages
7. YouTube LiveChatMessages streamList — https://developers.google.com/youtube/data/live/reference/rest/v3/liveChatMessages/streamList
8. YouTube LiveChatMessages resource — https://developers.google.com/youtube/data/live/reference/rest/v3/liveChatMessages
9. YouTube Live Streaming API authorization — https://developers.google.com/youtube/data/live/authentication
10. YouTube LiveBroadcasts list — https://developers.google.com/youtube/data/live/reference/rest/v3/liveBroadcasts/list
11. Full-Duplex-Bench v3 — https://www.fullduplex.ai/benchmarks/fdb-v3
12. MP-Bench — https://www.fullduplex.ai/benchmarks/mp-bench
13. OBS WebSocket — https://github.com/obsproject/obs-websocket
14. VTube Studio API — https://github.com/DenchiSoft/VTubeStudio
