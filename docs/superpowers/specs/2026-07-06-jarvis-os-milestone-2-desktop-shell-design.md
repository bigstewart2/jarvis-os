# Jarvis OS Milestone 2 — Desktop Shell Design

Status: Approved
Date: 2026-07-06

## Purpose

Milestone 1 proved the skill contract end-to-end at the backend layer (HTTP + WebSocket, SQLite-logged, one working "echo" skill). Milestone 2 proves the other half of that contract: that a real desktop UI can discover skills from the running backend, render an input form for one from its manifest, invoke it, and show the result — without any UI polish yet. This is the smallest possible slice that makes the skill system usable by a human instead of only by tests and curl.

## Non-Goals (for this milestone)

- No sidecar-managed backend process. The desktop app assumes the Milestone 1 backend is already running at `http://127.0.0.1:8420` (started manually via `python3 orchestrator.py`). Auto-starting/stopping the backend as a Tauri sidecar is deferred to a later milestone, once both the backend and the app shell are individually stable.
- No WebSocket-driven live status in the UI. Invocation results are shown via the plain REST response (`POST /skills/{id}/invoke`'s JSON body), not via `/ws`. Live status becomes relevant once a skill exists that takes long enough to need it (the dashboard/widget milestone, M7, or the Claude Code integration skill, M5).
- No general JSON-Schema-to-form renderer. Every input-schema property is rendered as a plain text input. Richer field types (numbers, booleans, enums) are deferred until a skill actually needs one.
- No app polish/theming beyond a working Tailwind setup. "Premium, Raycast-like" visual design is explicitly a later milestone's job, not this one's.

## Tech Stack

Scaffolded via `npm create tauri-app@latest` (React + TypeScript + Vite template), with Tailwind CSS added on top. Test stack: Vitest + React Testing Library + jsdom, matching the Vite-native tooling with no extra config layers.

## Components

| Component | Responsibility |
|---|---|
| `apps/desktop/src/api/client.ts` | Thin typed wrapper around `fetch` against `http://127.0.0.1:8420`: `fetchSkills(): Promise<SkillManifest[]>`, `invokeSkill(id: string, inputs: Record<string, string>): Promise<{ outputs: Record<string, unknown> }>` |
| `apps/desktop/src/components/SkillForm.tsx` | Renders one skill: its name + description, one text `<input>` per key in `input_schema.properties`, an "Invoke" button, and the result (or an error message) below |
| `apps/desktop/src/App.tsx` | Fetches the skill list on mount via `fetchSkills()`, renders a `SkillForm` per returned manifest |

This matches the master architecture's "skill exposed as a UI button auto-rendered from the manifest's input schema" principle at the smallest scope that principle needs right now — one skill, one field type, no generalized schema renderer.

## Backend Change Required

Milestone 1's FastAPI app (`apps/core/core/app.py`) has no CORS policy. The Tauri dev server (Vite, default `http://localhost:1420`) calling `http://127.0.0.1:8420` cross-origin will be blocked by the browser's CORS enforcement without one. This milestone adds `fastapi.middleware.cors.CORSMiddleware` to `create_app()`, allowing the Tauri dev origin(s). This is a backend change, but it belongs to this milestone since nothing in Milestone 1 needed it — the first cross-origin caller is this desktop shell.

## Data Flow

```
App mounts → GET /skills → render one SkillForm per manifest
User fills in the "text" field on the echo SkillForm → clicks Invoke
   → POST /skills/echo/invoke {"inputs": {"text": "..."}}
   → success: {"outputs": {"text": "..."}} → rendered in the SkillForm
   → failure (network error, 404, 500): error message rendered in the SkillForm instead of a result
```

## Testing Strategy

- `client.ts`: unit tests with a mocked global `fetch`, covering both the success and error paths of `fetchSkills` and `invokeSkill`.
- `SkillForm.tsx` / `App.tsx`: rendered with React Testing Library, `fetchSkills`/`invokeSkill` mocked at the module level — no real backend process or Tauri runtime required to run the suite.
- A manual smoke test closes out the milestone: run the Milestone 1 backend, run the Tauri app in dev mode, invoke the echo skill through the actual UI, confirm the result renders.

## Open Questions Deferred to Later Milestones

- Sidecar-managed backend lifecycle (bundling the Python venv/interpreter with the packaged app) — deferred, not designed here.
- WebSocket-driven live invocation status in the UI — deferred to M7 (dashboard/widgets) or M5 (Claude Code integration skill), whichever needs it first.
- General JSON-Schema-to-form rendering (numbers, booleans, enums, nested objects) — deferred until a skill with a non-string input field exists.
- Visual/theming polish ("premium, Raycast-like" feel) — explicitly out of scope for this milestone, tracked as a distinct future milestone in the master roadmap.
