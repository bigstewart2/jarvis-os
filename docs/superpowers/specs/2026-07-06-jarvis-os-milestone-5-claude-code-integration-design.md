# Jarvis OS Milestone 5 — Claude Code Integration Skill Design

Status: Approved
Date: 2026-07-06

## Purpose

Milestones 1–4 built the skill contract, desktop shell, provider abstraction, and voice pipeline — all around skills that finish in seconds and return their result in the HTTP response. Milestone 5 delivers the master architecture's `claude_code_task` skill: headless invocation of the Claude Code CLI against the Jarvis OS repo itself, with genuine incremental progress streamed to the UI over the existing WebSocket bus. It is the first skill whose work outlives its HTTP request — invoking it returns a `task_id` immediately, the CLI runs for up to a configurable maximum (default 10 minutes) as a background subprocess, progress events stream live, and a status endpoint answers "what happened to task X" at any time.

One correction to the master architecture is baked in: the master doc's example (`claude -p "<prompt>" --output-format json`) emits a single final blob only. This design uses `--output-format stream-json`, which emits newline-delimited JSON events (tool calls, assistant text, final result) as the agent works — the only mode that makes streamed progress real rather than cosmetic.

## Non-Goals (for this milestone)

- **No arbitrary working directory.** The task's `cwd` is fixed to the Jarvis OS repo (or a configured subpath within it) — a deliberate security scoping decision, not a technical limitation.
- **No voice invocation.** `voice_invokable: false`; a skill with real file/git side effects stays out of the intent router's reach.
- **No manual cancellation.** No kill-task endpoint this milestone; the timeout is the only way a running task ends early. Explicitly deferred.
- **No review-before-apply gate.** The agent's file edits land directly in the working tree (uncommitted — see Security Considerations). A diff-review/approve step before changes touch disk is a future milestone, named here so its absence is a decision, not an omission.
- **No concurrent-task orchestration.** Multiple tasks may technically run at once (each is an independent subprocess), but no queueing, no serialization, no per-task resource limits. One-at-a-time discipline is the user's job this milestone.
- **No full agentic-progress visualization.** The UI gets a minimal stage/event stream, not a transcript viewer, diff viewer, or tool-call tree.
- **No task survival across backend restart.** A restart kills the subprocess; the DB records the interruption honestly (see Task State Model), but nothing resumes.

## The Central Tension: Does This Fit the Existing Skill Contract?

Every existing skill is a pure synchronous `run(inputs) -> outputs` function, executed via `run_in_threadpool` inside `invoke_and_record_skill`, with the outputs recorded to `SkillInvocation` and returned in the HTTP response. A multi-minute task cannot be that — but it doesn't have to break the contract either.

**Decision: keep the existing contract untouched. The skill's `run()` *starts* the task and returns `{"task_id": ..., "status": "running"}` synchronously; the long-running work is owned by a new core service (`TaskManager`), not by the skill.**

"Start a background task" is itself a fast, synchronous operation — it validates inputs, resolves and checks the working directory, asks the `TaskManager` to spawn the subprocess, and returns the id in well under a second. That return value is a perfectly valid `outputs` dict: it conforms to a declared `output_schema`, gets recorded as a `SkillInvocation`, fires the existing `skill_invoked` event, and flows through `POST /skills/{id}/invoke` completely unchanged. **No new skill "kind", no `execution_mode` branch in `invoke_and_record_skill`, no second invocation path in the registry.** The alternative — teaching the registry/invocation layer about async skills — was considered and rejected: it adds a second execution contract to core infrastructure to serve exactly one skill, when the one skill can instead conform by making its synchronous answer *be* the task handle. If a second long-running skill ever appears, `TaskManager` is already the shared machinery; generalizing the manifest then is a one-milestone decision with two real consumers.

Two honest consequences, stated rather than hidden:

1. **This is the first skill that needs a core service.** `run(inputs)` receives only its inputs — no `app` handle. The skill obtains the `TaskManager` through a module-level accessor (`core.tasks.get_task_manager()`), initialized in `create_app()`. This is a documented pattern ("skills may import core service accessors"), the same way `ask` already imports `get_llm_provider`. And because `run()` executes on a threadpool thread while `TaskManager` lives on the event loop, `TaskManager.start()` is explicitly thread-safe: it captures the running loop at app startup (FastAPI startup hook) and schedules the task coroutine via `asyncio.run_coroutine_threadsafe`.
2. **One additive manifest field:** `background: bool = false` on `SkillManifest`. Purely informational metadata so the UI knows the returned `outputs` are a task handle, not a final result (render "task started" + subscribe to events, instead of a result card). Non-breaking default; no core code branches on it.

### Manifest

```yaml
id: claude_code_task
name: Claude Code Task
description: Run a coding/agentic task headlessly against the Jarvis OS repo via the Claude Code CLI. Returns a task_id immediately; progress streams over the event bus.
voice_invokable: false
background: true
input_schema:
  type: object
  properties:
    prompt:
      type: string
      minLength: 1
      description: The task for Claude Code to perform.
    subpath:
      type: string
      description: Optional path relative to the repo root to use as the working directory. Must resolve inside the repo.
  required: [prompt]
  additionalProperties: false
output_schema:
  type: object
  properties:
    task_id: {type: string}
    status: {type: string, enum: [running, failed]}
    error: {type: [string, "null"]}
  required: [task_id, status]
```

`status: failed` in the *immediate* output covers exactly one case: the preflight check (CLI not found, invalid subpath) fails before a task is ever created — see Error Handling.

## Components

| Component | Responsibility |
|---|---|
| `apps/core/skills/claude_code_task/manifest.yaml` + `skill.py` | The skill package. `run(inputs)`: preflight (`shutil.which` on the CLI binary, subpath resolution + containment check), then `get_task_manager().start(prompt, working_dir)` → `{"task_id", "status"}`. Returns in <1s always. |
| `apps/core/core/tasks/manager.py` | `TaskManager` — owns the full task lifecycle: spawns `asyncio.create_subprocess_exec`, runs the NDJSON reader coroutine, enforces the timeout, kills the process group, writes DB state transitions, publishes WS events. Holds live handles (`dict[task_id, RunningTask]`) in memory; the DB is the durable record. Thread-safe `start()` via `run_coroutine_threadsafe`. |
| `apps/core/core/tasks/stream.py` | Pure NDJSON-line → internal-event translation: `parse_stream_line(line) -> TaskEvent \| None`. Maps Claude Code `stream-json` event types to the minimal UI event set; returns `None` for lines to skip. Pure function — trivially unit-testable with canned NDJSON. |
| `apps/core/core/db/models.py` (extended) | New `ClaudeCodeTask` table (see Task State Model). |
| `apps/core/core/app.py` (extended) | `GET /tasks/{task_id}` (status/result lookup) and `GET /tasks` (recent tasks, newest first, limit 50). Startup: bind `TaskManager` to the loop; mark any DB rows still `running` as `interrupted` (orphans from a previous process). |
| `apps/core/core/config.py` (extended) | `claude_code_binary: str = "claude"`, `claude_code_subpath: str = ""` (default = repo root), `claude_code_timeout_seconds: int = 600`, `claude_code_allowed_tools: str = "Read,Glob,Grep,Edit,Write,Bash(git status:*),Bash(git diff:*),Bash(git log:*)"`, `claude_code_max_turns: int = 50`. |
| `apps/desktop/src/components/TaskPanel.tsx` | Renders the running task's live event feed (filtered from `/ws` by `task_id`) and terminal state; on reconnect/mount, reconciles via `GET /tasks/{id}`. |

### Repo root resolution

The repo root is derived the same way `BASE_DIR` already is (`Path(__file__).resolve()` ancestors), not from config — the constraint "the working directory is this repo" is enforced in code, with only the *subpath within it* configurable. `working_dir = (REPO_ROOT / settings.claude_code_subpath / inputs.get("subpath", "")).resolve()`; if `not working_dir.is_relative_to(REPO_ROOT)` (post-`resolve()`, so `..` and symlink escapes are both caught) or it doesn't exist, the invocation fails preflight. No caller-supplied absolute paths, ever.

## Subprocess Invocation

```python
process = await asyncio.create_subprocess_exec(
    settings.claude_code_binary,
    "-p", prompt,
    "--output-format", "stream-json",
    "--verbose",                       # required by the CLI for stream-json in print mode
    "--allowedTools", settings.claude_code_allowed_tools,
    "--max-turns", str(settings.claude_code_max_turns),
    cwd=working_dir,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    start_new_session=True,            # own process group — see Error Handling
)
```

**Why `asyncio.create_subprocess_exec`, not `run_in_threadpool`.** M4 used `run_in_threadpool` correctly: STT/TTS/LLM calls are opaque blocking calls of a few seconds with no intermediate output — a threadpool thread parks, returns one value, done. This task is the opposite shape: minutes long, with output that must be consumed *incrementally* as it appears. `run_in_threadpool` would pin a threadpool slot (default pool is small) for the full duration and would still need a second mechanism to marshal each parsed line back onto the event loop where the `EventBus` lives. `asyncio.create_subprocess_exec` gives non-blocking `await process.stdout.readline()` natively on the event loop — each NDJSON line is parsed and published to the bus with zero cross-thread hops, and the event loop stays fully live throughout. This is the architecturally correct tool for a streaming subprocess; the threadpool remains the correct tool for short opaque calls. (One asymmetry to preserve: DB writes still use the sync SQLAlchemy session factory, so state-transition writes go through `run_in_threadpool` — they're rare: one at start, one at terminal.)

**Why exec, not shell.** The prompt is passed as a single argv element — there is no shell, so no quoting/injection surface no matter what the prompt contains. `--allowedTools` and the absence of `--dangerously-skip-permissions` mean tools outside the allowlist simply fail inside the agent in headless mode (no interactive prompt to hang on). The default allowlist deliberately excludes unrestricted `Bash` — see Security Considerations.

**cwd enforcement, honestly stated.** `cwd=` plus argv-only invocation guarantees the *CLI* starts scoped to the repo and no caller input can smuggle extra CLI flags (`--add-dir`, an absolute path, etc. — the argv is fixed by our code; only the prompt string and validated subpath vary). What `cwd` cannot do is jail the *agent*: prompt content saying "edit /Users/stephen/.zshrc" is an instruction to the model, and `Edit`/`Write` accept absolute paths. The real containment layers are (a) no unrestricted Bash in the allowlist and (b) the CLI's own permission system denying out-of-scope file writes in headless mode. Residual risk is assessed in Security Considerations rather than papered over.

### NDJSON stream parsing

The reader loop: `readline()` → decode → `parse_stream_line()`. Per line:

- **Parses, recognized type** → translated to a `TaskEvent`, published on the bus.
- **Parses, unrecognized/uninteresting type** → skipped silently (the stream-json format includes event types the UI has no use for; forward-compatibility means ignoring unknowns, not erroring).
- **Fails to parse** → log a warning with the first ~200 chars, skip, continue. A progress line is never load-bearing: the task's outcome is determined solely by the final `result` event and the process exit code. A malformed line must never kill a healthy task.

Type mapping (kept minimal):

| stream-json event | Surfaced as |
|---|---|
| `system` (subtype `init`) | `started` |
| `assistant` message containing `tool_use` blocks | `tool_use` (tool name + a one-line summary, e.g. the `file_path` or command) |
| `assistant` message containing `text` blocks | `assistant_text` (truncated to ~500 chars) |
| `result` | captured as the task's final result; drives `completed`/`failed` |
| `user` (tool results), anything else | skipped |

## Data Flow

```
[Desktop UI]                    [FastAPI core]                      [Subprocess]
 POST /skills/claude_code_task/invoke
   {inputs: {prompt}}
        │
        ▼
 invoke_and_record_skill ──▶ skill.run(inputs)          (threadpool, <1s)
   (unchanged M1/M4 path)      │ preflight: which(claude), subpath check
                               │ TaskManager.start(...)  (run_coroutine_threadsafe)
                               │     │ DB: ClaudeCodeTask(status=running)
                               ▼     ▼
 ◀── 200 {"outputs":       returns {task_id,          asyncio.create_subprocess_exec(
      {task_id, status:      status: "running"}         claude -p ... stream-json,
       "running"}}             │                         cwd=repo, own process group)
   + ws: skill_invoked         │                              │
                               ▼                              │ NDJSON on stdout
 ws: claude_code_task ◀── reader coroutine  ◀────────────────┘
   started / tool_use /      │ (asyncio.wait_for wraps the whole
   assistant_text ...        │  read-to-exit in the timeout)
                             ▼
                        terminal transition (exactly one, always):
                          exit 0 + result event → completed
                          non-zero exit         → failed
                          timeout               → kill process group → timed_out
                             │ DB: status/result/finished_at
                             ▼
 ws: claude_code_task {completed|failed|timed_out}
 GET /tasks/{task_id} ──▶ full record any time (poll fallback / reconnect reconcile)
```

## Task State Model

**Decision: a new `ClaudeCodeTask` DB table is the source of truth for status/result; the in-memory `TaskManager` dict holds only live runtime handles (process, reader task).**

Pure in-memory was considered — single user, app restarts as a unit — and rejected for two reasons that cost almost nothing to fix: (1) precedent and diagnosability — `SkillInvocation` and `RouteDecision` established that anything worth doing is worth a queryable record, and a task that ran 9 minutes and then the app crashed is *exactly* the case where you want the record to survive; (2) the M4 Router Logging lesson generalizes — a solo builder needs the evidence trail to exist even when the live UI missed it. The table is written twice per task (start, terminal) — negligible cost.

```
ClaudeCodeTask:
  task_id: str (uuid4, PK)
  prompt: str
  working_dir: str
  status: running | completed | failed | timed_out | interrupted
  result_text: str | None      # the CLI's final result event text
  error: str | None            # stderr tail / failure classification
  num_turns, duration_ms, cost_usd: from the result event, when present
  created_at, finished_at
```

**States and transitions.** `running` is the only initial state (preflight failures never create a row). Exactly one terminal transition per task, structurally guaranteed by a `finally` block in the reader coroutine:

- `running → completed` — process exited 0 and a `result` event with `subtype: success` was seen.
- `running → failed` — non-zero exit, error-subtype result, or an unexpected exception in the reader itself.
- `running → timed_out` — `claude_code_timeout_seconds` exceeded; process group killed.
- `running → interrupted` — set *at next startup* for rows orphaned by a backend restart/crash (the one transition the dying process can't write itself).

No `queued` (tasks start immediately), no `cancelled` (deferred with manual cancellation).

### `GET /tasks/{task_id}` response

```json
{
  "task_id": "3f2a...",
  "status": "completed",
  "prompt": "add a docstring to bus.py",
  "working_dir": "/Users/.../jarvis-os",
  "result_text": "Added the docstring...",
  "error": null,
  "num_turns": 6,
  "duration_ms": 48210,
  "cost_usd": 0.31,
  "changed_files": ["apps/core/core/events/bus.py"],
  "created_at": "...",
  "finished_at": "..."
}
```

404 for unknown ids. `changed_files` comes from a post-completion `git status --porcelain` (see Security Considerations).

## WebSocket Event Schema

One new event type on the existing bus, exactly mirroring `voice_status`'s shape (`type` + correlation id + stage enum + flat detail):

```json
{"type": "claude_code_task", "task_id": "<uuid>", "stage": "<stage>", "detail": {...}}
```

| `stage` | `detail` |
|---|---|
| `started` | `{"prompt_excerpt": "first 120 chars", "working_dir": "..."}` |
| `tool_use` | `{"tool": "Edit", "summary": "apps/core/core/events/bus.py"}` |
| `assistant_text` | `{"text": "≤500-char excerpt"}` |
| `completed` | `{"result_excerpt": "...", "duration_ms": 48210, "cost_usd": 0.31, "changed_files": [...]}` |
| `failed` | `{"error": "..."}` |
| `timed_out` | `{"timeout_seconds": 600}` |

`task_id` correlates the stream with the invoke response, same as `invocation_id` in M4 — necessary because WS delivery and UI subscription race. The existing `skill_invoked` event still fires once at invocation time, unchanged. Deliberately not a general task-progress framework: one type, one enum, flat payloads, excerpts not transcripts. Missed events (UI closed, reconnect) are recovered via `GET /tasks/{task_id}`, which is why the terminal state lives in the DB and not only on the wire.

## Error Handling

The M4 philosophy — "always respond, never silently fail" — translates to the async model as a different invariant: **the invoke call always returns something actionable, and every created task always reaches exactly one terminal state, observably (WS event + DB row).** There is no single HTTP response to attach degradation to, so the guarantees split across the two phases:

| Failure point | Phase | Behavior |
|---|---|---|
| `claude` binary not on PATH | preflight, in `run()` | No task created. `run()` returns `{"task_id": null, "status": "failed", "error": "claude_cli_not_found: install Claude Code or set JARVIS_CLAUDE_CODE_BINARY"}` — a *successful* skill invocation whose output reports the problem (HTTP 200, matching M4's degrade-gracefully posture), recorded in `SkillInvocation` as usual. |
| Invalid `subpath` (escapes repo, nonexistent) | preflight, in `run()` | Same shape: no task, `status: failed`, `error: "invalid_subpath"`. |
| Spawn itself raises (race: binary deleted after preflight; fork failure) | task start | Row created then immediately transitioned to `failed`; `failed` WS event. One code path handles it — the reader's `finally`. |
| Subprocess exits non-zero | during run | `failed`; `error` = last ~1000 chars of stderr plus exit code. stderr is read concurrently (`asyncio.gather` on both pipes) to avoid pipe-buffer deadlock on chatty stderr. |
| stdout line fails to parse | during run | Skip line, log warning, continue. Never terminal on its own. |
| Timeout exceeded | during run | `timed_out`. Kill sequence below. |
| Reader coroutine itself raises unexpectedly | during run | `finally` guarantees: kill process group if still alive, write `failed` with the exception, publish `failed` event. A task can never be silently stuck in `running` while the process is gone. |
| Backend restarts mid-task | across restart | Subprocess dies with the parent (process group is not detached from the session leader's lifetime in practice, but see below); at next startup, `running` rows are marked `interrupted`. Honest record, no resurrection. |

**Orphan/zombie processes — a real concern, mitigated by process-group kill.** Claude Code's tools spawn child processes (any `Bash` tool call, git subprocesses). Killing only the direct child leaves those orphaned and still writing to the working tree after the task is "dead" — the worst kind of ghost for a tool that edits files. Mitigation: `start_new_session=True` puts the CLI in its own process group; the kill sequence is `os.killpg(pgid, SIGTERM)` → wait up to 5s → `os.killpg(pgid, SIGKILL)` → `await process.wait()` (reaps the zombie entry). This kills the entire tree in one shot. The same sequence runs on timeout and in the reader's exception `finally`. One accepted gap: if the *backend itself* is SIGKILLed, nothing runs the killpg — the orphaned CLI tree is possible in that one case, and the `interrupted` status at next startup at least tells you to look.

## Security Considerations

Scoping to the repo shrinks the blast radius; it does not eliminate it. What can still go wrong, and what this milestone does about each:

1. **Prompt injection / malicious prompt content → security-sensitive files inside the repo.** The repo contains `.env`-style secrets (e.g. `JARVIS_ANTHROPIC_API_KEY` if placed in a project `.env`), the `skills/` directory (Python that the registry `exec_module`s at next startup — writing here is deferred arbitrary code execution in the backend), and `.claude/` CLI settings. Mitigations this milestone: the tool allowlist excludes unrestricted `Bash` (only read-only git subcommands), so exfiltration via `curl` or `cat .env | ...` isn't available; no `--dangerously-skip-permissions`, so the CLI's own headless permission denials remain active; `max_turns` and the timeout bound how long a hijacked agent can operate. **Explicitly deferred, not omitted:** a protected-path denylist (refuse tasks whose edits touch `.env*`, `skills/`, `.claude/`, CI workflows) belongs with the review-before-apply milestone — enforcing it robustly requires inspecting the diff, which is that milestone's core machinery.
2. **Escaping the repo scope.** Covered in layers above: argv-only invocation (no flag smuggling), `resolve()` + `is_relative_to` on subpath (no traversal/symlink escape), `cwd` pinning, no `--add-dir`. Residual: `Edit`/`Write` with absolute paths as instructed by a hostile prompt, bounded by the CLI's permission behavior in headless mode. Accepted and documented for a single-user local app whose prompts come from the owner; revisit before any automation (Milestone 6) can compose prompts from external content (email, calendar) — **that composition is the moment this residual risk becomes a real injection channel, and it must be re-reviewed then.**
3. **Uncommitted destructive changes.** **Decision: completed tasks leave all changes uncommitted, and never auto-commit.** Auto-commit would launder agent output into history without human eyes and make a destructive edit look finished; leaving the working tree dirty makes `git diff` the natural, zero-new-infrastructure review step, and `git checkout .` the undo. To make the dirty state visible rather than discoverable, the terminal `completed` event and the `/tasks/{id}` record include `changed_files` from `git status --porcelain`. A structured review-before-apply flow (run in a worktree, present diff, approve to merge) is the natural next hardening milestone and is deferred by name.
4. **The prompt is a spend trigger.** Each task costs real API money for up to 10 minutes of agentic work. `cost_usd` from the result event is surfaced in the terminal event and stored per task, so spend is visible per-run — consistent with the M4 precedent of surfacing rather than silently accruing. Voice invocation being off also means no accidental spoken-misroute into a 10-minute task.

## Testing Strategy

Same layering as M4:

- **`parse_stream_line` unit tests** (pure, offline): each recognized event type maps correctly; unknown types return `None`; malformed JSON returns `None` (skip semantics live in the caller); truncation limits hold.
- **`TaskManager` tests with a stub CLI** — a tiny checked-in Python script that emits scripted NDJSON (the same technique as M4's mocked Piper subprocess, upgraded to streaming): happy path publishes the exact event sequence and lands `completed` with result fields; non-zero exit → `failed` with stderr tail; a script that sleeps past a 1-second test timeout → `timed_out` and, critically, **its child process is also dead** (the stub spawns a child and writes both PIDs; the test asserts neither survives); a garbage line mid-stream doesn't affect the outcome; DB row transitions match at each step.
- **Skill tests**: `run()` returns `{task_id, status}` in bounded time; preflight failures (missing binary via patched `shutil.which`, subpath with `..`, absolute subpath, symlink escape) return the no-task failure shape and create no DB row.
- **Endpoint tests** via `TestClient`: `GET /tasks/{id}` shape, 404, list ordering/limit; startup orphan-marking flips a seeded `running` row to `interrupted`.
- **Contract test** (skipped when the real CLI is absent, mirroring the model-download skips): real `claude -p "say ok" --output-format stream-json` against a scratch subdir, asserting NDJSON parses and a result event arrives — this is the canary for CLI stream-format drift, which is a real external dependency risk this design takes on.
- **Manual smoke** closes the milestone: invoke with "add a comment to README", watch `started`/`tool_use`/`assistant_text` stream live, confirm `completed` with `changed_files`, confirm the file changed and is uncommitted, confirm `GET /tasks/{id}` agrees; then repeat with the timeout set to 10 seconds and confirm `timed_out` plus no surviving processes (`ps` check).

## Open Questions Deferred to Later Milestones

- **Review-before-apply**: run tasks in an isolated worktree, present the diff in the UI, approve-to-merge — plus the protected-path denylist that belongs with it.
- **Manual cancellation endpoint** (kill before timeout) — the process-group kill machinery built here makes it a small addition when wanted.
- **Task queueing/concurrency policy** if overlapping tasks prove to be a real usage pattern rather than a mistake.
- **Arbitrary (allowlisted) working directories** beyond this repo, once the review gate exists to make broader scope safe.
- **Session continuation** (`--resume`/`--continue`) for multi-turn task refinement.
- **Automation-composed prompts** (Milestone 6): the mandatory security re-review point for injection risk, per Security Considerations #2.
- **stream-json format drift**: the contract test detects it; pinning a CLI version or vendoring a schema is deferred until drift is actually observed.
