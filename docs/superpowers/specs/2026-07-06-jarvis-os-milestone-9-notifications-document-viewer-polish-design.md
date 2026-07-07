# Jarvis OS Milestone 9: Notifications, Document Viewer, Polish — Design

**Process note:** Authored in one pass, continuing Stephen's standing "keep working non-stop" instruction. Scoping decisions below are explicit for later review.

## Scope Decision

The master roadmap's Milestone 9 line — "Notifications, document viewer, polish pass" — is vaguer than any prior milestone's line, and there's no display available in this environment to visually verify a running Tauri desktop shell. That constrains what "notifications" can responsibly mean here:

- **OS-level native notifications** (via Tauri's notification plugin) would require touching the Rust/Tauri shell for the first time in this project and can only really be verified by looking at a real notification popping up on a real desktop — not something I can prove happened from here. Deferring this specific piece.
- **In-app WebSocket-driven notifications** (a toast/banner UI reacting to backend events) are fully within reach: they're plain React state driven by the WebSocket connection the backend has exposed since Milestone 1 (`/ws`) but that the frontend has never actually consumed (every prior milestone's widgets poll REST instead — this was flagged as a known gap in both the Milestone 7 and Milestone 6 designs). This milestone finally wires up that WS client and uses it for exactly one thing: a toast notification when an automation run or Claude Code task finishes (success or failure). This is genuinely testable in `jsdom`/vitest the same way `VoiceButton`'s existing WS handling already is (that component already opens a WebSocket and reacts to messages — this milestone's toast component follows the identical, already-proven pattern).

**Decision: "Notifications" this milestone means an in-app toast system wired to the existing WS event bus (automation runs + Claude Code tasks), not OS-level native notifications.** OS notifications are a reasonable follow-up whenever Stephen is at the machine to visually confirm them.

**"Document viewer"** becomes concrete once paired with Milestone 8's `search_notes` skill: right now, `search_notes` returns excerpts, but there's no way to see a note's full content, and no UI surfaces search at all yet (M8 only built the skill, not a widget). This milestone adds (a) a `get_note` capability on `KnowledgeSource` (read a note's full content by its relative path) exposed as a new skill, `read_note`, and (b) a `NotesWidget` — a fifth dashboard widget with a search box (calling `search_notes`) and a click-to-expand view of the full note content (calling `read_note`). This is the first genuinely new dashboard widget since Milestone 7, added to the same `WIDGET_REGISTRY` pattern.

**"Polish pass"** folds in the specific, already-identified minor findings deferred from Milestone 7's and Milestone 8's final reviews (see below) rather than an open-ended cleanup sweep — each one is small, already-diagnosed, and already has a recommended fix.

## Non-Goals

- OS-level native notifications (Tauri notification plugin) — needs a live desktop to verify, deferred.
- Note editing/writing (still read-only, per Milestone 8's non-goals — unchanged).
- Reconnection/backoff logic for the WS client beyond what `VoiceButton` already does (open on mount, close on unmount) — this milestone's toast component follows the exact same lifecycle, no new reconnection strategy invented.
- Retiring `AutomationsWidget`/`TasksWidget`'s existing polling in favor of WS (flagged as a good idea in Milestone 7's review, but polling and a new toast-only WS consumer can coexist without conflict — replacing polling wholesale is a separate, riskier refactor of already-shipped, tested code, better done as its own deliberate step later, not folded into this milestone's already-broad scope).

## Part 1: WS-Driven Toast Notifications

**Backend:** no changes — confirmed by reading `core/tasks/manager.py` and `core/automation/runner.py` directly: `automation_run` events (Milestone 6, stages including `completed`/`failed`) and `claude_code_task` events (Milestone 5, stages `started`/`completed`/`failed`) already publish over the existing `/ws` event bus. No backend addition needed for this part.

**Frontend — `apps/desktop/src/notifications/`:**
- `useEventToasts()` — a hook (not a component) that opens one WebSocket connection (mirroring `VoiceButton`'s `WS_URL`/`onmessage` pattern exactly), listens for `{"type": "automation_run", "stage": "completed" | "failed", ...}` and `{"type": "claude_code_task", "stage": "completed" | "failed", ...}` messages, and appends a toast entry `{id, message, kind: "success" | "error"}` to a list. Each toast auto-dismisses after 6 seconds (a `setTimeout` per toast, cleared on unmount).
- `ToastContainer` — a small fixed-position component rendering the current toast list, used once at the top of `App.tsx` (outside the widget list, so it doesn't compete for dashboard layout space).
- `App.tsx` calls `useEventToasts()` once at the top level and renders `<ToastContainer toasts={toasts} />`.

## Part 2: Document Viewer (`read_note` skill + `NotesWidget`)

**Backend:**
- `KnowledgeSource` protocol (`core/providers/knowledge/base.py`) gains a second method: `def read(self, path: str) -> str | None` — returns a note's full raw content, or `None` if the path doesn't exist or resolves outside the vault (same path-traversal guard as `search`, reused).
- `ObsidianVaultSource.read(path)` implements this: joins `path` onto the vault root, resolves, checks `is_relative_to`, reads and returns the content, or `None` on any failure (missing file, traversal attempt, decode error) — deliberately returning `None` rather than raising, mirroring `search`'s "never raise for expected failure modes" contract.
- New skill `read_note`: `input_schema: {"path": "string"}`, `output_schema: {"content": "string | null"}`, `voice_invokable: false` (reading a full note aloud via TTS for an arbitrary-length document is a bad voice UX — this is a UI-only, click-driven action, unlike `search_notes` which returns short excerpts appropriate for voice).

**Frontend:**
- `client.ts` gains `fetchNoteContent(path: string): Promise<string | null>` (`POST /skills/read_note/invoke`) and `searchNotes(query: string): Promise<NoteMatch[]>` (`POST /skills/search_notes/invoke`) — both go through the existing generic `invokeSkill` HTTP path already used by every other skill invocation, no new endpoint needed.
- `NotesWidget.tsx` — a search input + button (calls `searchNotes`, renders each match's title/excerpt/path), where clicking a match calls `fetchNoteContent` and expands an inline `<pre>` block showing the full note text. Same error-isolation pattern as every other widget (its own loading/error state, no shared dashboard context).
- Added to `WIDGET_REGISTRY` as `"notes"`, extending `KNOWN_WIDGET_IDS` on the backend (`GET`/`PUT /dashboard/config`'s permutation set grows from 4 to 5 known ids) and `ALL_WIDGET_IDS` on the frontend. Existing saved `DashboardConfig` rows from before this milestone won't include `"notes"` in their `widget_order` — the `PUT` validation would reject re-saving an old config as-is, but a `GET` of an old row returns it unchanged (no automatic migration needed for a single-developer, pre-release local app; the Customize panel naturally offers "notes" once its own default widget_order is regenerated, and there is no production user data to migrate for this personal project at this stage).

## Part 3: Polish (deferred M7/M8 findings)

From Milestone 7's final review:
1. `DashboardConfig.updated_at` never updates on `PUT` — add `row.updated_at = datetime.now(timezone.utc)` in the `PUT /dashboard/config` handler.
2. `App.tsx`'s `visibleOrderedWidgets` trusts DB-stored widget ids against `WIDGET_REGISTRY` with no runtime guard — add `.filter((id) => id in WIDGET_REGISTRY)` before rendering.

From Milestone 8's final review:
3. `test_knowledge_obsidian.py`'s awkward `FIXTURE_VAULT = None` placeholder followed by a mid-file import — move the `from pathlib import Path` import to the top of the file and delete the placeholder line.

Not included (explicitly still deferred, lower value relative to effort right now):
- `GET /tasks`/`GET /automations/runs`'s unbounded `limit` query param — cosmetic hardening on a localhost-only single-user API, no real exposure.
- The lazy-create race in `GET /dashboard/config` — practically unreachable (one desktop app, one frontend, sequential requests).
- `knowledge_vault_dir`'s fixture-pointing default — worth revisiting once Stephen actually points this at a real vault, not before.

## Testing Strategy

- Backend: `test_knowledge_obsidian.py` gains `read()` test cases (found note, missing note → `None`, traversal attempt → `None`) in the same file as the existing `search()` tests. `test_read_note_skill.py` (new, mirrors `test_search_notes_skill.py`'s pattern exactly). `test_dashboard_config.py` gains an `updated_at` assertion and the 5-widget-id permutation update.
- Frontend: `useEventToasts.test.ts` — this codebase has no existing hook-test convention and no `@testing-library/react-hooks` dependency, but the installed `@testing-library/react@16` ships `renderHook` built in (no new dependency needed), which is the standard way to test a hook in isolation; test via `renderHook(() => useEventToasts())` with the same `FakeWebSocket` stub `App.test.tsx`/`VoiceButton.test.tsx` already use, asserting the returned toast list updates when a fake `onmessage` fires. `NotesWidget.test.tsx` (search + expand flow, mocking `searchNotes`/`fetchNoteContent`). `App.test.tsx` updated for the 5th widget and the toast container's presence.
- Manual proof step: live backend + live frontend test suite, same pattern as every prior milestone. No Tauri shell launch (still no display available).

## Open Questions Deferred

- OS-level native notifications via Tauri — needs Stephen present to verify visually.
- Retiring polling in favor of WS across `AutomationsWidget`/`TasksWidget` — a deliberate future refactor, not bundled here.
- Migrating pre-Milestone-9 `DashboardConfig` rows to include the new `"notes"` widget id automatically — not needed for a single local install with no real users yet.
