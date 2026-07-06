# Jarvis OS Milestone 6 — Automation Engine Design

Status: Approved
Date: 2026-07-06

## Purpose

Milestones 1–5 built a skill system with three invocation surfaces — UI button, voice, and HTTP — all of which share one property: a human initiates every run. Milestone 6 adds the fourth surface the master architecture promised: **programmatic invocation on a schedule**. An automation is a named, cron-scheduled, ordered pipeline of skill calls with output→input wiring, executed by the backend with no human in the loop, observable live over the existing WebSocket bus and after the fact via a durable run history.

The milestone is proven by one real automation: an **"ask digest"** that fires on a cron schedule, invokes the existing `ask` skill with a fixed prompt, and speaks the answer through a new skill wrapping the M4 TTS provider — a genuine two-step pipeline (`ask` → `speak`) that exercises scheduling, sequencing, and wiring with zero special cases.

The design principle throughout: **the automation engine is a caller of the skill system, not an extension of it.** Every pipeline step goes through the same `invoke_and_record_skill` path the UI and voice pipeline already use. The engine adds scheduling, sequencing, wiring, and run-tracking around that call — nothing inside it changes.

## Non-Goals (for this milestone)

- **No event-based triggers.** Cron only. `AutomationTrigger` as an abstraction with an event-based implementation waits for Milestone 8, when there are integrations producing events worth reacting to. (The definition format reserves room for this — see Automation Definition Format — but no code path exists.)
- **No branching, conditionals, or parallel steps.** An ordered sequence, executed front to back. This matches the master doc's explicit YAGNI position; DAG expressiveness is a named open question for a future milestone, decided when a real automation needs it.
- **No automation CRUD API or UI editor.** Automations are YAML files edited in a text editor, loaded at startup — exactly how skills work today. An enable/disable or edit endpoint implies writing YAML back to disk from the API; deferred until file-editing proves annoying in practice.
- **No retry policy.** A failed step fails the run, once. Retries/backoff are a real-workflow-engine feature with no consumer yet.
- **No per-run timeout or cancellation.** Steps are in-process threadpool calls — there is no process to kill, and abandoning a threadpool thread mid-skill doesn't actually stop it. The existing skills are seconds-scale; a runaway-skill guard is deferred until a slow skill exists.
- **No catch-up of missed runs.** If the app was closed when the cron time passed, that run simply didn't happen (`misfire_grace_time` covers brief startup races only, and `coalesce=True` collapses pile-ups). Jarvis is a desktop app, not a server; "runs while the app is running" is the honest contract, stated in the UI rather than papered over.
- **No automation-composed prompts from external content.** The M5 security review flagged Milestone 6 as the re-review point for prompt injection *if* automations compose prompts from email/calendar content. This milestone's prompts are static strings authored by Stephen in YAML — the injection channel does not open yet. It opens at Milestone 8 and must be reviewed there.
- **No backend-side audio playback.** The `speak` step synthesizes audio and publishes its URL; the desktop UI plays it if connected. The backend never touches the speaker directly (see The Ask Digest Automation).

## Components

| Component | Responsibility |
|---|---|
| `apps/core/automations/*.yaml` | Automation definitions, one file per automation (see Automation Definition Format). Sibling of `apps/core/skills/`, same "config-on-disk, scanned at startup" pattern. |
| `apps/core/core/automation/definition.py` | `AutomationDefinition` Pydantic model + `load_definition(path)` — mirrors `manifest.py`/`load_manifest` exactly, including a typed `DefinitionError`. |
| `apps/core/core/automation/registry.py` | `AutomationRegistry.load_from_directory(dir)` — scans `*.yaml`, validates each definition (cron parses, every `skill` id exists in the `SkillRegistry`, step templates reference only earlier steps). **Invalid files are registered with a load error, not skipped and not fatal** — see Loading & Validation. `get(id)` / `list()` mirror `SkillRegistry`. |
| `apps/core/core/automation/template.py` | Pure function `render_inputs(template: dict, step_outputs: list[dict]) -> dict` — the one wiring mechanism (see Output→Input Wiring). No engine, no filters; trivially unit-testable. |
| `apps/core/core/automation/runner.py` | `AutomationRunner` — owns a pipeline run's lifecycle: creates the `AutomationRun` row, renders each step's inputs, calls `invoke_and_record_skill` per step, publishes WS events, writes exactly one terminal state (via `finally`, per the M5 pattern). `start(automation_id, trigger)` returns a `run_id` immediately; the run proceeds as an asyncio task. |
| `apps/core/core/automation/scheduler.py` | Thin APScheduler wrapper: builds an `AsyncIOScheduler`, registers one cron job per enabled+valid automation whose job body is `runner.start(automation_id, trigger="cron")`, started/stopped from the app lifecycle hooks. |
| `apps/core/core/db/models.py` (extended) | New `AutomationRun` table (see Run State Model). |
| `apps/core/core/app.py` (extended) | Automation endpoints (see API Surface); startup: load registry, mark orphaned `running` runs `interrupted` (same sweep as `ClaudeCodeTask`), start scheduler; shutdown: stop scheduler. |
| `apps/core/core/config.py` (extended) | `automations_dir: str = "automations"`. That's the only new setting — schedules and prompts live in the YAML where they belong, not in env config. |
| `apps/core/skills/speak/` | **New skill**: `speak(text) -> {audio_url, text}` — wraps the existing `TTSProvider` exactly the way `ask` wraps `LLMProvider` (see The Ask Digest Automation). |
| `apps/desktop/src/components/AutomationsPanel.tsx` | Lists automations (schedule, enabled, next run, last run status), a "Run now" button per automation, live run feed filtered from `/ws`, and audio playback when a completed run's outputs contain an `audio_url`. |

## Automation Definition Format

**Decision: one YAML file per automation, in a new `apps/core/automations/` directory, loaded at startup by an `AutomationRegistry` that mirrors `SkillRegistry.load_from_directory`.**

Why files, not DB rows: automations are *authored configuration*, like skill manifests — they benefit from version control, text-editor editing, and diff review, and there is no CRUD UI to feed a DB-backed store this milestone. DB rows would force building create/edit endpoints just to get one automation defined. Run *history* is state and goes in the DB (see Run State Model); this split — definitions on disk, execution records in SQLite — is exactly the split the skill system already made (`manifest.yaml` on disk, `SkillInvocation` in DB).

Why a flat file per automation rather than a directory per automation: skills need a directory because they carry code (`skill.py`). An automation is pure data. A directory-per-automation layout buys nothing today; if automations ever grow attached assets, moving `foo.yaml` to `foo/automation.yaml` is a trivial loader change.

The schema — deliberately five concepts, nothing more:

```yaml
# apps/core/automations/ask_digest.yaml
id: ask_digest
name: Daily Ask Digest
description: Every morning, ask the LLM for an interesting fact about today's date and speak it.
enabled: true
trigger:
  type: cron
  cron: "0 9 * * *"          # 9:00 every day, local time
steps:
  - skill: ask
    inputs:
      prompt: "In two sentences, tell me one genuinely interesting historical fact about today's date."
  - skill: speak
    inputs:
      text: "{{steps.0.response}}"
```

Field notes:

- `id` — must match the filename stem (same convention a reviewer expects from skills; validated at load).
- `trigger` — a one-key-today object rather than a bare `cron: "..."` string. This is the single piece of deliberate forward-room in the schema: Milestone 8's event triggers become `type: event` without a format migration. It costs one level of nesting now; a flat `cron` field would cost every automation file an edit later. Everything else in the schema is strictly needed today.
- `steps[].inputs` — a template dict validated at load time against nothing (skill input schemas contain runtime-substituted values, so schema validation happens naturally when the skill runs); what *is* validated at load is that every `{{steps.N...}}` reference points to an earlier step (see Loading & Validation).
- **What is deliberately absent**: no `on_failure`, no `retries`, no `timeout`, no `condition`, no step names/ids (steps are addressed by index — with ≤3-step pipelines, names are ceremony). Each absence is a YAGNI decision; any of them can be added additively without breaking existing files.

The corresponding Pydantic model (`AutomationDefinition`) mirrors `SkillManifest` in shape and strictness.

### Loading & Validation

`AutomationRegistry.load_from_directory` scans `automations_dir` for `*.yaml` at startup and validates each:

1. YAML parses and satisfies `AutomationDefinition`.
2. `trigger.cron` parses via `CronTrigger.from_crontab`.
3. Every `steps[].skill` exists in the `SkillRegistry` (the automation registry takes the skill registry as a constructor argument — load order in `create_app` is skills first, automations second).
4. Every `{{steps.N.path}}` token in step *i*'s inputs has `N < i` (no forward or self references — statically checkable, so checked statically).

**One deliberate divergence from `SkillRegistry`: an invalid file does not crash startup and is not silently skipped.** It is registered with `status: invalid` and the error message, excluded from scheduling and from manual triggering, and surfaced in `GET /automations`. Rationale: skill packages are code, edited rarely, where failing loud at startup is right; automation YAML is user-edited config expected to change often — a cron typo bricking the entire backend (voice, skills, everything) is the wrong blast radius, and a silently-skipped file is the M4 "evidence trail" lesson violated. Visible-but-inert is the correct failure mode for config.

No hot-reload: like skills, edits take effect on app restart. Same known limitation, same milestone-deferred fix, no new inconsistency.

## Output→Input Wiring

**Decision: one mechanism — `{{steps.N.path}}` token substitution, applied to string values in the step's input template, resolved against the accumulated outputs of prior steps.**

Rules, exhaustively (this is the whole spec of the mechanism):

- A token has the form `{{steps.N.dotted.path}}`. `N` is a zero-based step index; the dotted path traverses that step's `outputs` dict (e.g. `steps.0.response` reaches into `ask`'s `{"response": ...}`).
- If a template string is **exactly one token** (`"{{steps.0.response}}"`), it is replaced by the referenced value with its type preserved (a dict output field can flow into a dict input field intact).
- If a token is **embedded in a longer string** (`"Summarize this: {{steps.0.response}}"`), the value is stringified and interpolated. Both cases fall out of one implementation; both are needed for real prompt composition.
- Substitution is applied recursively through nested dicts/lists in the template, so structured inputs work without special cases.
- A path that resolves to nothing (missing key, non-dict traversal) is a **render error**, which fails the step before the skill is invoked — never a silent empty-string substitution. Feeding a skill `""` where it expected the previous answer is a bug you want loud.
- That is all. No filters, no expressions, no conditionals, no environment variables, no Jinja. `render_inputs` is a ~40-line pure function with a regex and a dict walk.

Why this shape and not Jinja2: Jinja would work, but it imports a full template *language* — loops, conditionals, filters — into a system whose fixed constraint is "no branching." The moment the wiring mechanism is more expressive than the pipeline model, automations start encoding logic in templates that the execution model can't see, track, or report on. The mechanism should be exactly as expressive as the pipeline: reference an earlier output, optionally inside a string. If Milestone 8+ genuinely needs transformations (date formatting, truncation), that decision gets made then — most likely as a transformation *step* (a skill), not template syntax.

Why `steps.N` and not named steps: with sequences capped by YAGNI at a handful of steps, index addressing is unambiguous and needs no uniqueness validation. Named steps are an additive change if pipelines grow.

## Scheduler Integration

**Decision: APScheduler's `AsyncIOScheduler`, attached to the FastAPI process's running event loop, started in the startup hook and shut down in the shutdown hook.**

Why `AsyncIOScheduler` and not `BackgroundScheduler`: `BackgroundScheduler` runs jobs on its own thread pool, in threads that have no event loop — every job would immediately need `run_coroutine_threadsafe` to reach the `EventBus` and the runner coroutine, recreating the M5 `bind_loop` thread-marshaling dance for no benefit, plus a whole scheduler thread that exists only to bounce work back to the loop. `AsyncIOScheduler` schedules coroutines natively on the loop where the `EventBus`, the runner, and FastAPI already live: a cron firing is just a coroutine call, zero cross-thread hops. The M5 lesson applies directly — threadpools are for short opaque blocking calls, the event loop is for orchestration — and a scheduler is pure orchestration. (The blocking parts of a run — the skill bodies — still go through `run_in_threadpool` inside `invoke_and_record_skill`, unchanged, so the loop never blocks.)

Lifecycle wiring in `create_app` / startup:

```
create_app():
    automation_registry = AutomationRegistry(skill_registry)
    automation_registry.load_from_directory(BASE_DIR / settings.automations_dir)
    runner = AutomationRunner(automation_registry, app)   # needs app for invoke_and_record_skill
    scheduler = build_scheduler(automation_registry, runner)   # jobs registered, not started

@app.on_event("startup"):
    # existing: bind task manager loop, mark orphaned ClaudeCodeTask rows
    mark_orphaned_automation_runs_interrupted()
    scheduler.start()          # must be inside startup — AsyncIOScheduler needs the running loop

@app.on_event("shutdown"):
    scheduler.shutdown(wait=False)
```

Job configuration per automation: `CronTrigger.from_crontab(defn.trigger.cron)`, `id=automation_id`, `coalesce=True` (a pile of missed firings collapses to one), `misfire_grace_time=60` (a firing missed by less than a minute — e.g. during startup — still runs; older misses are dropped, per the no-catch-up non-goal), `max_instances=1` (a cron firing while the previous cron run of the *same* automation is still going is skipped and logged, not stacked — the digest at 9:00 tomorrow should not queue behind a wedged run from today).

The job body is one line: `runner.start(automation_id, trigger="cron")`. All lifecycle, tracking, and error handling live in the runner — the scheduler knows nothing about pipelines, which is what makes the manual-trigger endpoint (below) share 100% of the execution path with cron firings.

## Pipeline Execution Model

**Decision: a new, small `AutomationRunner` that reuses TaskManager's *patterns* — DB-row-as-source-of-truth, exactly-one-terminal-state-via-`finally`, `{type, correlation_id, stage, detail}` WS event shape, startup orphan sweep — but none of its *code*.**

The reasoning, against the specific differences rather than by vibes:

| Concern | TaskManager (M5) | Automation run (M6) | Consequence |
|---|---|---|---|
| Unit of work | External subprocess emitting NDJSON | In-process `invoke_and_record_skill` calls | No spawn, no stream parsing, no stderr handling — the majority of TaskManager's body is inapplicable |
| Termination | Process-group SIGTERM/SIGKILL, timeout via `wait_for` | Nothing to kill; a threadpool skill call can't be safely abandoned | No kill machinery, no timeout this milestone (Non-Goals) |
| Thread entry | `start()` called from a threadpool skill `run()` → `run_coroutine_threadsafe` + `bind_loop` | `start()` called from the event loop (scheduler job or endpoint handler) → plain `asyncio.create_task` | No loop-binding dance at all — the M5 complexity existed because the *skill contract* was the entry point; here the engine is the entry point |
| Progress semantics | Opaque agent, progress = parsed stream | Structured pipeline, progress = step boundaries | Events are step_started/step_completed, known in advance from the definition |
| Terminal-state guarantee | `finally` writes exactly one terminal DB state | Identical requirement | **Pattern reused verbatim** |
| Durable record + orphan sweep | `ClaudeCodeTask` table; startup flips `running`→`interrupted` | `AutomationRun` table; same sweep, same startup hook | **Pattern reused verbatim** |
| WS schema | `{"type": "claude_code_task", "task_id", "stage", "detail"}` | `{"type": "automation_run", "run_id", "automation_id", "stage", "detail"}` | **Shape reused verbatim** — the frontend's event-filtering pattern from TaskPanel transfers directly |

Attempting to literally share code (a generalized "BackgroundJobManager" superclass) was considered and rejected: the shared surface is the *shape* of ~4 decisions, not implementable logic — a base class would be mostly abstract methods and would couple M5's subprocess machinery to M6's release cycle for zero deduplication. Two small classes with the same well-documented conventions beat one framework with two clients. If a third background-thing appears, that's the moment to extract.

**Each step is a first-class skill invocation.** The runner calls the existing `invoke_and_record_skill(app, skill_id, rendered_inputs)` — meaning every step lands its own `SkillInvocation` row and fires its own `skill_invoked` event, indistinguishable from a button press or voice command. This is the milestone's core requirement ("the automation engine invokes skills exactly the way the API/voice pipeline already do") satisfied structurally: there is no second invocation path for the skill system to diverge from. The `AutomationRun` row is the *pipeline-level* record layered above the per-step records, exactly as a voice invocation's `RouteDecision` layers above its `SkillInvocation`.

The run loop, in full:

```
async def _run(run_id, defn, trigger):
    step_outputs = []
    try:
        publish(started)
        for i, step in enumerate(defn.steps):
            publish(step_started, {index: i, skill: step.skill})
            inputs = render_inputs(step.inputs, step_outputs)        # render error → fail run at step i
            status, outputs = await invoke_and_record_skill(app, step.skill, inputs)
            if status == "failed":                                    # fail-fast, see Error Handling
                record step result; terminal(failed, failed_step=i); return
            step_outputs.append(outputs)
            publish(step_completed, {index: i, skill: step.skill})
        terminal(completed)
    except Exception:                                                 # incl. render errors, SkillNotFound
        terminal(failed)          # finally-guaranteed single terminal write, M5 pattern
```

Concurrency posture: `max_instances=1` prevents same-automation cron stacking; a *manual* trigger while a run is active is allowed (each run is independent, and blocking "Run now" on scheduler state adds coordination for a single-user testing affordance). Different automations run concurrently without restriction — they are independent by construction.

## Error Handling

**Decision: fail-fast. The first failed step terminates the run; no subsequent step executes; the run's terminal status is `failed` with the failing step index recorded.**

Justification against continue-on-error: with no branching, a later step cannot route around a failure — its only relationship to earlier steps is *consuming their outputs*. If step 2 of 3 fails, step 3 either references step 2's outputs (render fails anyway — garbage in) or it doesn't (in which case, why is it sequenced after step 2? Independent steps in a strictly-sequential model are a definition smell, not a feature to support). "Partial success" would also make the terminal status ambiguous — the M5 invariant "every run reaches exactly one *meaningful* terminal state" is worth more than salvaging a tail step. If genuinely-independent step groups ever matter, that's the branching/DAG conversation, deferred by name in the master doc.

What "failed" captures — the run row stores enough to debug without replaying:

| Failure point | Behavior |
|---|---|
| Automation id unknown / definition invalid (manual trigger) | No run created; endpoint returns 404 / 409 respectively. Cron can't hit this (invalid automations are never scheduled). |
| Template render error (bad path, missing key) at step *i* | Run `failed`, `failed_step=i`, `error="render_error: ..."`. The skill is never invoked — a mis-wired pipeline fails loudly at the wire, not with a confusing downstream skill error. |
| Skill returns `status="failed"` at step *i* (skill exceptions are already caught and converted by `invoke_and_record_skill`) | Run `failed`, `failed_step=i`, `error` = the skill's error string. The step's `SkillInvocation` row exists independently with full detail. |
| Skill id vanishes between load-validation and run (theoretical single-process race, per the M4 pipeline's same note) | Caught by the runner's top-level guard → `failed`. |
| Runner itself raises unexpectedly | `finally` guarantees one terminal `failed` write + WS event — a run can never be stuck `running` while nothing is executing (M5 invariant, verbatim). |
| Backend restarts mid-run | Startup sweep marks `running` rows `interrupted` — honest record, no resumption (M5 pattern, verbatim). |
| Cron fires while same automation's previous cron run is active | Skipped by `max_instances=1`, logged. Not a run, not a failure — nothing enters the history, which is correct: nothing was attempted. |

Per-step results are stored in the run row's `steps` JSON as the run progresses (`[{skill, status, error?}, ...]` — outputs live in `SkillInvocation`, not duplicated), so `GET /automations/runs/{id}` shows exactly how far the pipeline got and why it stopped.

## Run State Model

```
AutomationRun:
  run_id: str (uuid4, PK)
  automation_id: str
  trigger: "cron" | "manual"
  status: running | completed | failed | interrupted
  steps: JSON            # [{skill_id, status, error?}] appended as steps finish
  failed_step: int | None
  error: str | None
  started_at, finished_at
```

Same two-writes-plus-step-appends cost profile as `ClaudeCodeTask`; same justification (M5's "anything worth doing is worth a queryable record" — doubly true for runs that fire when nobody is watching, which is this milestone's entire premise).

### WebSocket events

```json
{"type": "automation_run", "run_id": "<uuid>", "automation_id": "ask_digest", "stage": "<stage>", "detail": {...}}
```

| `stage` | `detail` |
|---|---|
| `started` | `{"trigger": "cron", "num_steps": 2}` |
| `step_started` | `{"index": 0, "skill_id": "ask"}` |
| `step_completed` | `{"index": 0, "skill_id": "ask"}` |
| `completed` | `{"result_excerpt": "≤500 chars of the last step's primary text output", "audio_url": "...or null"}` |
| `failed` | `{"failed_step": 1, "error": "..."}` |

Per-step `skill_invoked` events (with full outputs) also fire from the unchanged invocation path; the `automation_run` stream is the pipeline-level narrative. Missed events reconcile via `GET /automations/runs/{run_id}` — the DB-not-wire recovery rule from M5.

## API Surface

Mirrors the M5 `/tasks` pattern:

| Endpoint | Behavior |
|---|---|
| `GET /automations` | All loaded automations: `{id, name, description, enabled, cron, status: "scheduled"\|"disabled"\|"invalid", load_error, next_run_time, last_run: {run_id, status, finished_at} \| null}`. Invalid files appear here with their error — the observability half of the visible-but-inert loading decision. |
| `POST /automations/{id}/run` | **Manual trigger — yes, it exists, and it is the primary testing/debugging affordance.** Calls the same `runner.start(id, trigger="manual")` the scheduler calls — literally the same function, so a manual run exercises 100% of the real path except the cron firing itself. Returns `202 {"run_id": ...}` immediately; progress streams over `/ws`. Works on `enabled: false` automations by design (disabled means "don't schedule", not "can't test" — this is what makes iterating on a new automation's YAML tolerable). 404 unknown id; 409 for `invalid` definitions. |
| `GET /automations/runs?automation_id=&limit=` | Run history, newest first, default limit 50 (M5 list conventions). |
| `GET /automations/runs/{run_id}` | Full run record incl. per-step statuses, `failed_step`, `error`, timestamps. 404 unknown. |

No `POST/PUT/DELETE` on definitions and no enable/disable endpoint (Non-Goals): both imply API-driven writes to YAML on disk, which is a real design decision (who wins when the file and the API disagree?) that should be made when file-editing demonstrably hurts, not preemptively.

## The Ask Digest Automation

**Decision: "speak the result" is IN scope, implemented as a new `speak` skill wrapping the existing `TTSProvider` — the digest is the two-step pipeline `ask` → `speak` shown in the definition example above.**

The reasoning, since this determines what the implementation plan builds:

1. **A single-skill pipeline proves nothing this milestone claims.** Scheduling + one skill call is a cron job. The deliverable is a *pipeline engine* with output→input wiring; the proving automation must have a step 2 that consumes step 1's output, or the wiring code ships untested by the milestone's own acceptance demo.
2. **A skill, not a runner special-case.** The alternative — the runner calling `tts_provider.synthesize` directly as a post-run action — would give the engine a hardcoded side-channel that bypasses the skill system on day one, corrupting the "engine is only a caller of skills" invariant for one convenience. Wrapping TTS as a skill instead follows the *established, documented* M3/M5 pattern precisely: `ask` imports `get_llm_provider`; `claude_code_task` imports `get_task_manager`; `speak` imports `get_tts_provider`. STT/TTS remain core providers (M4's decision stands — the voice *pipeline* doesn't change); `speak` is merely a ~12-line skill-shaped adapter over one of them, and it's independently useful (UI button: type text, hear it; voice-composable later).
3. **Clean reuse is real here.** `speak` calls `tts_provider.synthesize(text, tts_path(voice_dir))` and returns `{"audio_url": "/voice/audio/<id>", "text": ...}` — the M4 synthesis call, file convention, pruning (`prune_tts_files`), and serving endpoint, all unchanged. Nothing is forked.
4. **Playback is the UI's job, honestly scoped.** The backend synthesizes and records; the desktop app, on receiving the run's `completed` event carrying `audio_url`, fetches and plays it. If the UI is closed when the cron fires, the digest is not heard aloud — but the run record and the text survive in the DB, and the audio file survives until pruned. Making the headless backend drive the speaker (e.g. shelling to `afplay`) was considered and rejected: it adds an OS-audio surface to the sidecar for a case (app closed) where the runs mostly aren't happening anyway (see the no-catch-up non-goal — the backend only runs while the app runs, so "UI closed but backend firing crons" is a narrow window, not a mode).

`speak` manifest: `voice_invokable: false` (routing a voice command *to* a text-to-speech skill is a pointless loop for the intent router to fall into), `input_schema: {text: string, required}`, `output_schema: {audio_url, text}`.

## Data Flow

```
[APScheduler on the event loop]              [FastAPI core]                      [Existing M1–M4 machinery]

 CronTrigger fires (or POST /automations/ask_digest/run)
        │
        ▼
 runner.start("ask_digest", trigger)
        │ DB: AutomationRun(status=running)
        │ asyncio.create_task(_run)          ──▶ 202 {run_id}  (manual path only)
        ▼
 ws: automation_run {stage: started, num_steps: 2}
        │
        │  step 0: render_inputs({prompt: "...static..."}, [])
        ├──▶ invoke_and_record_skill(app, "ask", inputs) ───▶ threadpool: ask.run()
        │      │ DB: SkillInvocation(ask)                        └─▶ LLMProvider.complete()
        │      │ ws: skill_invoked
        │      ▼ outputs: {response: "On this day in..."}
        │  step_outputs[0] captured
 ws: automation_run {stage: step_completed, index: 0}
        │
        │  step 1: render_inputs({text: "{{steps.0.response}}"}, step_outputs)
        │           └─ resolves to {text: "On this day in..."}
        ├──▶ invoke_and_record_skill(app, "speak", inputs) ──▶ threadpool: speak.run()
        │      │ DB: SkillInvocation(speak)                      └─▶ TTSProvider.synthesize()
        │      ▼ outputs: {audio_url: "/voice/audio/<id>", text}      → data/voice/tts/<id>.wav
 ws: automation_run {stage: step_completed, index: 1}
        │
        ▼ terminal (exactly one, finally-guaranteed):
        │   all steps ok        → completed
        │   step failed/render  → failed (failed_step=i, later steps never run)
        │   backend restart     → interrupted (at next startup)
        │ DB: AutomationRun terminal write
        ▼
 ws: automation_run {stage: completed, result_excerpt, audio_url}
        │
        ▼
 [Desktop UI] plays GET /voice/audio/<id>; run browsable via GET /automations/runs/{run_id}
```

## Testing Strategy

Same layering as M4/M5:

- **`render_inputs` unit tests** (pure, offline — the highest-value suite): whole-string token preserves type; embedded token stringifies; nested dict/list recursion; dotted-path traversal; missing key / non-dict traversal / out-of-range index each raise the render error; multiple tokens in one string; token-free templates pass through untouched.
- **Definition/registry tests**: valid file loads; bad YAML, bad cron, unknown skill id, forward reference (`{{steps.1...}}` in step 0), self reference, id/filename mismatch each produce `status: invalid` with the message **without raising** — and the registry's other automations still load.
- **Runner tests with stub skills** (register throwaway skills in a test `SkillRegistry`, per the M1 pattern): happy two-step run — wiring delivers step 0's output into step 1's input, WS event sequence exact, DB transitions `running→completed`, per-step `SkillInvocation` rows exist; step-1-fails → step 2 never invoked, `failed_step=1`, terminal `failed`; render error → skill not invoked, terminal `failed`; runner-exception path still lands exactly one terminal write.
- **Scheduler tests**: enabled+valid automations get jobs, disabled/invalid don't; job ids match automation ids; `max_instances=1` skip behavior with a stub long run. (Don't test that APScheduler's cron math works — test our registration of it.)
- **Endpoint tests** via `TestClient`: `GET /automations` shape incl. an invalid definition's surfaced error; `POST .../run` returns 202+run_id, 404 unknown, 409 invalid, works on disabled; run history ordering/limit; run detail 404; startup sweep flips a seeded `running` run to `interrupted`.
- **`speak` skill tests**: mocked `TTSProvider` (M4's technique) — returns `audio_url`/`text`, file lands under the voice dir, pruning respected.
- **Manual smoke closes the milestone**: set the digest cron to `* * * * *`, restart, watch it fire — `started`/`step_completed×2`/`completed` on the WS feed, hear the fact spoken, confirm the run in `GET /automations/runs`; then break the template path on purpose, `POST .../run`, and confirm a loud `failed` at step 1 with `render_error`.

## Open Questions Deferred to Later Milestones

- **Event-based triggers** (`trigger.type: event`) — Milestone 8, when integrations produce events. The trigger object in the schema is the reserved seam.
- **Automation-composed prompts from external content** — the M5 security review's named re-review point. The moment a template can wire email/calendar text into an `ask` prompt or (worse) a `claude_code_task` prompt, prompt injection becomes a real channel. **Mandatory security review at Milestone 8.**
- **Branching/conditional/parallel steps** — per the master doc, its own milestone decision if a real automation demands it; fail-fast and index-addressed steps are both revisited then.
- **Per-run timeout / cancellation** — becomes necessary the first time a slow or wedged skill exists; note that cancelling in-process threadpool work is genuinely hard and may motivate re-examining execution isolation then.
- **Definition CRUD / enable-disable API and hot-reload** — when file-edit-and-restart demonstrably hurts.
- **Missed-run catch-up / run-on-wake semantics** — if "the 9am digest never fires because the laptop was asleep" becomes a real complaint, options range from `misfire_grace_time` tuning to an on-startup "should have run" check.
- **Retry policy per step** — with retryable failures (network-flaky integrations) as the trigger, Milestone 8 territory.
- **Run-history retention** — the table grows one row per firing; a pruning policy (or the M7 dashboard exposing it) decided when it matters.
