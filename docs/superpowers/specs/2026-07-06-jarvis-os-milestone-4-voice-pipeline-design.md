# Jarvis OS Milestone 4 — Voice Pipeline Design

Status: Approved
Date: 2026-07-06

## Purpose

Milestones 1–3 proved the skill contract, the desktop shell, and config-swappable LLM providers. Milestone 4 delivers the master architecture's signature interaction: push-to-talk voice that invokes a skill end-to-end. Hold a button, speak, release — the backend transcribes locally (faster-whisper), routes the transcript to a skill via the existing `LLMProvider`, invokes it, speaks the result locally (Piper), and streams stage-by-stage progress to the UI over the existing WebSocket bus. This milestone adds two new provider protocols (`STTProvider`, `TTSProvider`) following the M3 pattern, an LLM-based intent router, one new REST pipeline endpoint plus an audio-serving endpoint, and a push-to-talk component in the desktop shell.

## Non-Goals (for this milestone)

- No streaming STT. The full clip is recorded, then transcribed once.
- No wake word, no always-on listening, no barge-in (interrupting playback by speaking).
- No native audio capture. Recording uses the browser's Web Audio API inside the Tauri webview; Rust-side audio is out of scope.
- No second STT or TTS implementation. One implementation per protocol; the protocol + factory exist so a swap is config-only later — no speculative Kokoro/whisper-alternative code.
- No voice-quality tuning. Model size, quantization, and Piper voice selection get sensible defaults exposed via `Settings`; optimizing them is deferred (see STT Model Decision).
- No multi-turn conversation. Each push-to-talk utterance is independent, matching M3's single-prompt `complete()`.
- No global OS-level hotkey. Push-to-talk is an in-window button.
- No independent LLM provider selection for the router vs. skill execution. The router uses the same `get_llm_provider(settings)` factory as every other LLM consumer — no separate "cheap model for routing" config axis this milestone (see Router Cost, below, for why this was deliberately deferred rather than built now).

## STT Model Decision

The master architecture states a preference for "large-v3 class... best local transcription quality." Applied literally here, that preference would sabotage this milestone's actual goal. On a CPU-only Mac, faster-whisper `large-v3` commonly takes 5–15+ seconds to transcribe a short clip — turning "press button, speak, release, get an answer" into a multi-second silent gap that makes a correctly-working pipeline feel broken.

**Decision: default to `small` with `compute_type="int8"`, exposed as `Settings` fields so upgrading to `large-v3` is a config change, not a code change.**

The quality priority is honored structurally, not abandoned: `stt_model` is a config knob, so once the pipeline is proven, `JARVIS_STT_MODEL=large-v3` + restart delivers maximum accuracy with zero code changes — the same "swap via config" promise the whole architecture is built on. `small` int8 on Apple Silicon CPU transcribes short clips in roughly real-time (~1–2s for a 5s clip); its accuracy on clean, close-mic, single-speaker command audio is more than sufficient to prove routing works. `int8` is CTranslate2's intended CPU quantization (float16 is a GPU-path optimization, out of scope here).

## Components

| Component | Responsibility |
|---|---|
| `apps/core/core/providers/stt/base.py` | `STTProvider` Protocol: `transcribe(audio_path: Path) -> str` — returns the stripped transcript, `""` for silence |
| `apps/core/core/providers/stt/faster_whisper_provider.py` | `FasterWhisperProvider` — wraps `faster_whisper.WhisperModel(settings.stt_model, compute_type=settings.stt_compute_type)`; loads the model lazily on first `transcribe()` and keeps it in memory for the process's lifetime (model load takes seconds — must happen once, not per request) |
| `apps/core/core/providers/tts/base.py` | `TTSProvider` Protocol: `synthesize(text: str, output_path: Path) -> None` — writes a WAV to the caller-chosen path. The pipeline (not the provider) owns file naming/lifecycle, since it needs the UUID for the `/voice/audio/{id}` URL before synthesis runs |
| `apps/core/core/providers/tts/piper_provider.py` | `PiperProvider` — runs the `piper` CLI as a subprocess: text on stdin, `--model <settings.piper_voice>`, `--output_file <output_path>`; raises on non-zero exit |
| `apps/core/core/providers/stt/factory.py`, `.../tts/factory.py` | `get_stt_provider(settings)` / `get_tts_provider(settings)` — mirror `get_llm_provider`. The STT provider instance is created once at startup and stored on `app.state` (it owns an expensive in-memory model); the TTS provider is stateless but stored alongside for symmetry |
| `apps/core/core/routing/intent_router.py` | `route(transcript, manifests, llm) -> RouteResult` — builds the routing prompt from voice-invokable manifests, calls `llm.complete(..., system=...)` (the first real consumer of M3's `system` param), parses/validates the JSON, and returns either the routed skill or the ask-fallback. Pure function of its arguments — trivially unit-testable with a fake LLM. **Always logs its decision** (see Router Logging, below) regardless of outcome |
| `apps/core/core/voice/pipeline.py` | `run_voice_pipeline(...)` — orchestrates upload → STT → route → invoke → TTS, publishes `voice_status` events between stages, implements the always-respond error policy |
| `apps/core/core/voice/files.py` | Voice file lifecycle: allocates UUID-named files under `voice_dir`, opportunistic pruning (see Temp File Lifecycle) |
| `apps/core/core/app.py` (extended) | `POST /voice/invoke` (multipart audio upload → full pipeline → JSON response) and `GET /voice/audio/{audio_id}` (serves the WAV; validates `audio_id` parses as a UUID to prevent path traversal). Skill invocation inside the pipeline reuses the same record-to-SQLite + publish-`skill_invoked` path as `POST /skills/{id}/invoke`, refactored into a shared internal helper so the two endpoints cannot drift |
| `apps/core/core/config.py` (extended) | `stt_provider: Literal["faster_whisper"] = "faster_whisper"`, `stt_model: str = "small"`, `stt_compute_type: str = "int8"`, `tts_provider: Literal["piper"] = "piper"`, `piper_voice: str = "en_US-lessac-medium"`, `voice_dir: str = "data/voice"` |
| `apps/desktop/src/components/VoiceButton.tsx` | Push-to-talk button + live status line + last-result panel |
| `apps/desktop/src/api/client.ts` (extended) | `invokeVoice(audio: Blob): Promise<VoiceInvokeResponse>` — multipart POST |
| New dependencies | `faster-whisper`, `piper-tts`, `jsonschema` (input validation in the router), `python-multipart` (FastAPI file upload) |

### Protocol shape rationale

- `transcribe(audio_path: Path) -> str`: the upload already lands in a temp file, and faster-whisper's native input is a path. Returning a bare `str` (not segments/timestamps) is deliberate — nothing in this milestone consumes anything but the text; widening the return type later is a normal protocol evolution, same as M3 adding `system` when a consumer appeared.
- `synthesize(text: str, output_path: Path) -> None`: keeps file-lifecycle policy in exactly one module (the pipeline), not leaked into every TTS implementation.
- No `language`/`voice`/`speed` parameters on the protocols. Both implementations read configuration from `Settings` at construction, matching `AnthropicProvider`. Per-call options get added when a caller needs them, not before.

## Intent Router Design

### Prompt

System prompt (fixed):

> You route a user's spoken request to one skill. You will receive the transcript and a list of available skills with their input schemas. Respond with ONLY a JSON object, no markdown, no explanation: `{"skill_id": "<id>", "inputs": {<inputs matching that skill's input_schema>}}`. If no skill clearly matches the request, or you are not confident, choose `{"skill_id": "ask", "inputs": {"prompt": "<the transcript, verbatim>"}}`.

User prompt: the transcript, followed by a JSON array of voice-invokable skills — for each, `id`, `description`, `input_schema` straight from `SkillManifest` (only manifests with `voice_invokable: true` are included).

### How "not confident" is represented

There is no numeric confidence field. **The `ask` skill is itself one of the routable choices, and the system prompt instructs the model to choose it whenever unsure.** A self-reported confidence score would require picking an arbitrary threshold over a number LLMs calibrate poorly; making the fallback a first-class choice collapses "confidence" into the same decision the model is already making.

### Validation, and the exact fallback triggers

`route()` falls back to `RouteResult(skill_id="ask", inputs={"prompt": transcript}, fallback_reason=...)` on any of:

1. **JSON parse failure** — the reply doesn't parse as JSON (one leniency: strip a surrounding ```` ```json ```` fence if present).
2. **Wrong shape** — parsed JSON isn't an object with a string `skill_id` and a dict `inputs`.
3. **Unknown skill_id** — not in the registry, or not `voice_invokable`.
4. **Schema validation failure** — `jsonschema.validate(inputs, manifest.input_schema)` raises.
5. **Model chose ask itself** — not a failure; recorded as the fallback so the UI can label it.

No retry on any of these — a second LLM round-trip adds latency for marginal accuracy gain, and the fallback already guarantees a useful response. The only way `route()` itself raises is if `llm.complete()` raises (provider down/no network) — that case cannot fall back to ask (same provider) and is handled by the pipeline's error policy.

### Router Logging (added after design review)

Both Fable's architecture review and a subsequent multi-perspective pressure-test (an LLM council session; see Design Review below) converged on the same gap: combining "no confidence threshold, no retry" with "every failure still returns 200 with a spoken response" means a genuine misroute — the LLM confidently picking the wrong real skill, not falling back to `ask` — produces a fluent, successful-looking spoken answer with no signal anywhere that anything went wrong. That is a real debugging blind spot for a solo builder with no one else to notice a silently-wrong result.

**The fix is logging, not a redesign.** `route()` records, for every call regardless of outcome: the raw LLM routing response (before validation), the chosen `skill_id`, whether it was a fallback, and which of the five trigger conditions (if any) caused the fallback. This is written to the same `SkillInvocation`-adjacent record the pipeline already creates for the invoked skill (or a sibling `RouteDecision` row — implementation detail for the plan), so a misroute is diagnosable after the fact from logs even though the user-facing experience stays "always responds smoothly." This does not change the architecture, the response schema, or the always-200 policy — it only ensures the information needed to notice a bad route actually exists somewhere.

### Router Cost (deliberately deferred)

The same review also flagged that the router's own LLM call is a real, if small, per-utterance cost — every voice invocation pays for at least one LLM call to route, on top of whatever the target skill itself costs (for `ask`, that's two LLM calls per fallback utterance: one to route, one to answer). A cheaper option — route via the free local Ollama provider from M3 regardless of which provider skills use — was considered and explicitly **not** adopted this milestone: it would require a second, independent provider-selection axis (routing vs. skill execution), which is real added architecture surface beyond what this design and its reviews covered, for an as-yet-unmeasured cost problem. Accept the cost as-is for now; revisit with real usage data if it proves to matter (see Open Questions).

## Data Flow

```
[Desktop UI]                         [FastAPI core]
 hold VoiceButton
   → MediaRecorder records webm/opus
 release
   → POST /voice/invoke (multipart) ──▶ save upload → voice_dir/uploads/{uuid}.webm
                                        │  ws: voice_status stage=transcribing
                                        ▼
                                       STTProvider.transcribe(path) → transcript
                                        │  ws: voice_status stage=routing (transcript)
                                        ▼
                                       intent_router.route(transcript, manifests, LLMProvider)
                                        │  (logs routing decision regardless of outcome)
                                        │  ws: voice_status stage=invoking_skill (skill_id)
                                        ▼
                                       skill.run(inputs)  ── recorded to SQLite +
                                        │                    ws: skill_invoked (existing event)
                                        ▼
                                       response_text derived from outputs
                                        │  ws: voice_status stage=synthesizing
                                        ▼
                                       TTSProvider.synthesize(text, voice_dir/tts/{uuid}.wav)
                                        │  ws: voice_status stage=done
                                        ▼
 ◀── JSON response {transcript, skill_id, outputs, response_text, audio_url, ...}
 <audio> element plays GET /voice/audio/{uuid}
```

The blocking stages (STT, LLM call, skill run, Piper subprocess) run via `run_in_threadpool`, same as the M3 fix to `POST /skills/{id}/invoke`, so the event loop — and the WebSocket publishing progress events — stays live during the multi-second pipeline.

**Response text derivation** (what gets spoken): if `outputs` contains a string field named `response`, speak it (covers `ask`); otherwise speak the first string value in `outputs`; otherwise speak "Done — {skill name} completed." Documented heuristic, not a new manifest field — a `spoken_output` manifest hint is deferred until a real skill needs it.

### `POST /voice/invoke` response

```json
{
  "invocation_id": "uuid",
  "transcript": "what's 2 plus 2",
  "skill_id": "ask",
  "fallback_used": false,
  "fallback_reason": null,
  "outputs": {"response": "4."},
  "response_text": "4.",
  "audio_url": "/voice/audio/3f2a...-....wav-id",
  "error": null
}
```

## Error Handling — "always respond"

Governing rule: every stage failure still produces a spoken response if at all possible; if speech itself fails, it degrades to a text response; the endpoint returns HTTP 200 with `error` populated for every failure past upload validation. A hard HTTP error only occurs when there is nothing sensible to respond about.

| Stage | Failure | Behavior |
|---|---|---|
| Upload | missing/empty file part | HTTP 400. Only hard-error case. |
| STT | empty/whitespace transcript (silence, mic glitch) | Skip routing/skill entirely. `response_text = "I didn't catch that."`, TTS it, return 200 with `transcript: ""`, `skill_id: null`, `error: "empty_transcript"`. |
| STT | `transcribe()` raises | `response_text = "I couldn't process that audio."`, TTS it, return 200 with `error` set. |
| Routing | LLM call raises (provider unreachable) | Cannot fall back to ask (same provider). `response_text = "I couldn't reach the language model."`, TTS it, return 200 with `error` set. |
| Routing | malformed JSON / unknown skill / schema failure / model unsure | Not an error — router falls back to ask (logged per Router Logging above); `fallback_used: true`. |
| Skill | `run()` raises | Recorded as a failed `SkillInvocation` (existing M1 path + `skill_invoked` event, `status: "failed"`). `response_text = "The {skill name} skill failed."`, TTS it, return 200 with `error` carrying the exception string. |
| TTS | Piper fails / voice model missing | Return 200 with the full result and `audio_url: null`, `error` noting TTS failure. The UI shows `response_text` as text — the one stage whose failure cannot itself be spoken. |

`voice_status stage: "error"` is published whenever the pipeline takes a degraded path, so the UI can show the failure live even before the HTTP response lands.

## WebSocket Event Schema

One new event type on the existing bus, delivered over the existing `/ws` endpoint alongside `skill_invoked`:

```json
{"type": "voice_status", "invocation_id": "<uuid>", "stage": "<stage>", "detail": {...}}
```

| `stage` | `detail` |
|---|---|
| `transcribing` | `{}` |
| `routing` | `{"transcript": "..."}` |
| `invoking_skill` | `{"skill_id": "...", "fallback_used": bool}` |
| `synthesizing` | `{"skill_id": "..."}` |
| `done` | `{}` |
| `error` | `{"message": "..."}` |

`invocation_id` (also in the REST response) lets the UI correlate events with the request it made — necessary even single-user, since the WS stream and the HTTP response race. The existing `skill_invoked` event still fires unchanged during the skill stage. Deliberately not a general progress-event framework: one type, one enum, flat payloads.

## Temp File Lifecycle

- All voice files live under `voice_dir` (default `apps/core/data/voice/`, resolved relative to `BASE_DIR` like `skills_dir`): `uploads/{uuid}.webm` and `tts/{uuid}.wav`. UUID4 filenames; `GET /voice/audio/{audio_id}` rejects anything that doesn't parse as a UUID (no path traversal).
- **Uploads**: deleted immediately after transcription completes (success or failure) — the transcript is the only artifact anyone needs.
- **TTS WAVs**: must outlive the request (the frontend fetches the URL after the response), pruned opportunistically: at the start of each `/voice/invoke`, delete TTS files older than 1 hour, keeping at most the 20 newest regardless of age. No background reaper — one directory scan per invocation is free at this scale.
- On backend startup, `voice_dir` contents are cleared entirely.

## Desktop UI

A new `VoiceButton` component rendered in `App.tsx` above the existing skill list — voice is a peer entry point to the forms, not a modifier of them.

- **States**: `idle` → (press+hold) `recording` → (release) `processing` (sub-labeled live from `voice_status`: "Transcribing…", "Routing…", "Running ask…", "Speaking…") → `playing` (while `<audio>` plays) → `idle`. An `error` state shows the message, returns to `idle` on next press. Button disabled during `processing` — one in-flight invocation at a time, sidestepping backend concurrency questions this milestone.
- **Mechanics**: `onMouseDown` requests mic access (`getUserMedia`) and starts a `MediaRecorder`; `onMouseUp`/`onMouseLeave` stops it, assembles the Blob, calls `invokeVoice()`. The component opens its own WebSocket to `/ws` (first frontend consumer of the M1 bus) and filters for `voice_status` events matching its `invocation_id`.
- **Result panel**: below the button, the last invocation renders as plain text — transcript, chosen skill (tagged "fell back to ask" when `fallback_used`), and `response_text` — plus a hidden `<audio>` auto-playing `audio_url`.
- **No SkillForm integration.** Voice does not populate or highlight the M2 forms — that coupling would serve no one this milestone, consistent with M2's "no polish" precedent. The result panel already tells the user which skill ran.

## Testing Strategy

Same two-layer philosophy as M3:

- **Router unit tests** (offline, fake `LLMProvider`): happy path; fenced-JSON leniency; each of the four fallback triggers individually; model-chose-ask; LLM exception propagates; **logging occurs for every case, including the happy path**.
- **Provider unit tests**: `FasterWhisperProvider` with `WhisperModel` mocked (model/compute_type args, lazy single load, segment-joining/stripping); `PiperProvider` with `subprocess` mocked (CLI args, stdin text, non-zero-exit raises).
- **Pipeline unit tests** with all three providers faked: assert the `voice_status` event sequence for the happy path, and every error-table row (empty transcript, STT raise, LLM raise, skill raise, TTS raise → correct `response_text`/`error`/`audio_url`, HTTP 200).
- **Endpoint tests** via `TestClient`: multipart upload plumbing, 400 on missing file, `GET /voice/audio/{id}` serves a file and rejects non-UUID ids.
- **Contract tests** (mirroring `test_llm_provider_contract.py`): real `FasterWhisperProvider` transcribes a tiny checked-in WAV, skipped if the model isn't downloaded; real `PiperProvider` produces a non-empty WAV, skipped if the voice model is absent.
- **Manual smoke** closes the milestone: hold the button, say "what is two plus two," confirm live stage updates, `ask` runs, answer plays audibly; then say something matching no skill and confirm the fallback tag appears **and a logged route decision exists for both cases**.

## Design Review

This design went through two review passes before implementation planning: a Fable (deep-reasoning model) architecture synthesis, and a 5-advisor LLM council pressure-test (contrarian/first-principles/expansionist/outsider/executor personas, with anonymized peer review). The council's core finding — the always-respond + no-retry-fallback combination can mask a genuine misroute — is addressed via Router Logging above; its secondary finding (per-utterance router cost, unaddressed by any single advisor) is addressed via Router Cost above, deliberately deferred rather than acted on.

## Open Questions Deferred to Later Milestones

- **STT quality tuning** — flipping `stt_model` to `distil-large-v3` or `large-v3` (and whether Metal/GPU acceleration is worth pursuing) once the pipeline is proven and real transcription failures are observed.
- Piper voice selection/quality, and speech rate control.
- Global push-to-talk hotkey via Tauri and wake-word activation.
- Router accuracy measurement and whether a retry/self-correction step earns its latency — revisit once there are enough voice-invokable skills for misrouting to actually occur, using the Router Logging data as evidence.
- **Router LLM cost** — whether to route via the free local Ollama provider (independent of the skill-execution provider) once real usage shows the current per-utterance cost actually matters. Deliberately not built this milestone (see Router Cost above).
- Multi-turn voice conversation (needs chat-history support already deferred from M3).
- A `spoken_output` manifest hint if the response-text heuristic proves inadequate for a future skill.
