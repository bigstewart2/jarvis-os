# Jarvis OS Milestone 7: Dashboard Widgets — Design

**Process note:** Stephen asked me to keep working continuously through this milestone without pausing for the usual per-section approval, since he stepped away from the computer. This spec was authored in one pass using judgment grounded in the existing codebase and the master architecture doc's roadmap line ("Dashboard widgets — configurable layout, persisted widget config"), rather than through interactive brainstorming. Scoping decisions are called out explicitly below with their rationale so they can be revisited if Stephen disagrees later.

## Purpose

Replace the current flat, single-column `App.tsx` (a bare list of skill forms plus a voice button) with a real dashboard: a small set of independent widget cards, each surfacing a different subsystem built in Milestones 1-6, arranged in a layout the user can customize (show/hide, reorder) and which persists across app restarts.

This is the first milestone where the desktop app aggregates activity across subsystems (skills, voice, Claude Code tasks, automations) into one view, rather than each subsystem living behind its own single-purpose screen.

## Non-Goals

- **Drag-and-drop reordering.** Simple up/down move controls in a lightweight "Customize" panel satisfy "configurable layout" without a drag-and-drop library dependency. Revisit if the up/down UX proves annoying in daily use.
- **WebSocket-driven live widget updates.** The backend event bus (`events_ws`, built in Milestone 1) already carries task/automation progress events, but no frontend WS client exists yet in this codebase (checked: `apps/desktop/src/api/client.ts` has none). Wiring one up is a real chunk of new frontend infrastructure. This milestone's widgets poll their REST endpoints on an interval instead. Live WS updates are a natural Milestone 9 (notifications/polish) improvement.
- **Per-widget settings beyond show/hide + order.** No widget-specific configuration (e.g. "only show failed runs") this milestone.
- **Multi-user or multi-profile dashboard config.** This is a single-user desktop app; one global config row is sufficient.
- **New skills or new subsystem functionality.** All data the widgets show already exists via Milestone 1-6 endpoints (`/skills`, `/tasks`, `/automations`, `/automations/runs`). This milestone is purely presentation + persisted layout.

## Widgets (4)

1. **Skills widget** — wraps the existing skill-list-and-invoke UI (currently `SkillForm` rendered directly in `App.tsx`) into a card.
2. **Voice widget** — wraps the existing `VoiceButton` into a card.
3. **Automation Runs widget** — lists automations (`GET /automations`) with their enabled/scheduled/invalid status and last-run outcome, plus the 10 most recent runs across all automations (`GET /automations/runs?limit=10`) with status badges (running/completed/failed/interrupted). Polls every 5s while the dashboard is mounted.
4. **Claude Code Tasks widget** — lists the 10 most recent Claude Code tasks (`GET /tasks?limit=10` — note: `limit` param does not currently exist on this endpoint and must be added, see Task list) with status badges. Polls every 5s while mounted.

Each widget is a self-contained component: `apps/desktop/src/widgets/<Name>Widget.tsx`, each exporting a component with no props beyond an optional `className`, each independently responsible for its own data fetching, loading, and error states (no shared "dashboard data" god-context — keeps widgets independently testable, matching the existing per-component test convention in this repo, e.g. `SkillForm.test.tsx`).

## Layout & Persistence

**Data model (new):** a single-row `DashboardConfig` table (SQLite, via the existing SQLAlchemy `Base` in `core/db/models.py`):

```python
class DashboardConfig(Base):
    __tablename__ = "dashboard_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    widget_order: Mapped[list] = mapped_column(JSON, nullable=False)   # e.g. ["skills", "voice", "automations", "tasks"]
    hidden_widgets: Mapped[list] = mapped_column(JSON, nullable=False) # e.g. ["voice"]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=...)
```

Single-row semantics: the backend always operates on the row with the lowest `id` (creating a default one on first read if none exists), matching the "one global config" non-goal above. No need for a "current user" concept.

**Endpoints (new, in `apps/core/core/app.py`):**
- `GET /dashboard/config` → `{"widget_order": [...], "hidden_widgets": [...]}`. If no row exists yet, creates and persists a default row (`widget_order: ["skills", "voice", "automations", "tasks"]`, `hidden_widgets: []`) and returns it — so the endpoint never 404s and the frontend never needs to hardcode the default widget list.
- `PUT /dashboard/config` — body `{"widget_order": [...], "hidden_widgets": [...]}`. Validates that `widget_order` is exactly a permutation of the 4 known widget IDs (`skills`, `voice`, `automations`, `tasks`) and `hidden_widgets` is a subset of those same 4 IDs — 400 on violation (this is the one input-validation surface in this milestone, since it's user-editable state that gets echoed back into the render list; a malformed list must not silently break the dashboard).

**Frontend:**
- `apps/desktop/src/api/client.ts` gains `fetchDashboardConfig()` and `saveDashboardConfig(config)`.
- `App.tsx` becomes the dashboard shell: on mount, fetches config, renders visible widgets (filtering `hidden_widgets`, in `widget_order` order) via a `WIDGET_REGISTRY: Record<WidgetId, {label: string; component: React.ComponentType}>` map (`apps/desktop/src/widgets/registry.ts`) — adding a future widget later means one entry in this map plus a new file, not touching layout logic.
- A "Customize" toggle button reveals a small panel listing all 4 widgets with a show/hide checkbox and up/down move buttons per visible widget; a "Save" button calls `saveDashboardConfig` and closes the panel. No live-preview-while-editing complexity — edits apply to the visible dashboard only after Save (simplest correct behavior; avoids a whole class of "is this the saved or draft state" bugs for a 4-widget list).

## Error Handling

- `GET /dashboard/config`: cannot practically fail once the default-row-creation path exists (no user input on this path) — no special frontend error UI beyond the existing app-level error banner pattern already in `App.tsx`.
- `PUT /dashboard/config`: 400 on invalid payload (see validation above) — frontend surfaces this as an inline error in the Customize panel and does NOT close the panel, so the user's in-progress edits aren't lost.
- Each widget's own polling fetch failure is caught and shown as an inline "couldn't load" message within that widget's card only — one widget's backend hiccup must never blank out the other three (this mirrors the existing per-skill error isolation pattern, not a new invariant).

## Testing Strategy

- Backend: `test_dashboard_config.py` — default-row creation on first `GET`, round-trip via `PUT` then `GET`, validation rejection (400) for a `widget_order` missing a widget / containing an unknown id / containing a duplicate, and for a `hidden_widgets` containing an unknown id. Update `test_task_endpoints.py` (or add a case) proving the new `limit` query param on `GET /tasks` defaults to 50 (preserving current behavior) and is respected when given a smaller value.
- Frontend: one test file per widget (`SkillsWidget.test.tsx` — likely a thin wrapper reusing existing `SkillForm` tests' mocking approach, `VoiceWidget.test.tsx`, `AutomationsWidget.test.tsx`, `TasksWidget.test.tsx`) mocking `fetch` the same way `client.test.ts` / `SkillForm.test.tsx` already do; plus `App.test.tsx` updated to prove config-driven ordering/visibility (mock `fetchDashboardConfig` to return a config hiding one widget and reordering the rest, assert the DOM reflects it) and the Customize panel's show/hide + reorder + save flow.
- No new Python dependencies. No new frontend dependencies (plain CSS grid/flex for layout, no drag-and-drop library).

## Open Questions Deferred

- WebSocket-driven live widget updates (front-end WS client) — Milestone 9 candidate.
- Drag-and-drop reordering — revisit only if up/down controls prove painful in real use.
