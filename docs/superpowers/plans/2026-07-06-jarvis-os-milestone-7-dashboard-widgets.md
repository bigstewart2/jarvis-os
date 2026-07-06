# Jarvis OS Milestone 7: Dashboard Widgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `App.tsx` skill list with a configurable, persisted, widget-based dashboard surfacing skills, voice, automations, and Claude Code tasks.

**Architecture:** A new `DashboardConfig` SQLAlchemy row (single global row, auto-created on first read) persists widget order and hidden-widget set via two new FastAPI endpoints. The frontend gains 4 widget components (`SkillsWidget`, `VoiceWidget` — thin wrappers around existing components — and two new polling widgets, `AutomationsWidget` and `TasksWidget`), a `WIDGET_REGISTRY` map keyed by widget id, and `App.tsx` becomes a dashboard shell that fetches config, renders visible widgets in order, and exposes a Customize panel to edit and save that config.

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy 2.0 (backend, `apps/core/`), React + TypeScript + Vite + Vitest + Testing Library (frontend, `apps/desktop/`). No new dependencies on either side.

## Global Constraints

- The 4 known widget ids are exactly: `"skills"`, `"voice"`, `"automations"`, `"tasks"` — used verbatim in `widget_order`/`hidden_widgets` and in the `WIDGET_REGISTRY` keys. No other widget ids exist this milestone.
- Default config on first read (no row yet): `widget_order: ["skills", "voice", "automations", "tasks"]`, `hidden_widgets: []`.
- `PUT /dashboard/config` validates: `widget_order` must be exactly a permutation of the 4 known ids (no missing, no duplicate, no unknown id) → 400 otherwise; `hidden_widgets` must be a subset of the 4 known ids → 400 otherwise.
- `GET /tasks` gains an optional `limit: int = 50` query param (preserves current default behavior of 50).
- `AutomationsWidget` and `TasksWidget` poll their REST endpoints every 5000ms while mounted, using `limit=10`.
- No drag-and-drop, no WebSocket wiring on the frontend, no per-widget settings beyond show/hide + order — these are explicit non-goals in the design spec (`docs/superpowers/specs/2026-07-06-jarvis-os-milestone-7-dashboard-widgets-design.md`).
- Backend tests use the existing `_client(tmp_path, monkeypatch)` pattern (fresh SQLite DB per test via `JARVIS_DATABASE_URL` env var, `TestClient(create_app())`) already established in `apps/core/tests/test_task_endpoints.py` and `test_automation_endpoints.py`.
- Frontend tests mock `fetch`/component-level API functions the same way `apps/desktop/src/api/client.test.ts` and `apps/desktop/src/components/SkillForm.test.tsx` already do (`vi.spyOn(client, "fnName")` for component tests, `globalThis.fetch = vi.fn()...` for `client.ts` tests itself). `App.test.tsx` already stubs a fake `WebSocket` global (required because `VoiceButton` opens one on mount) — every test that renders `App` or any widget that (transitively) renders `VoiceButton` must keep doing this.

---

### Task 1: `DashboardConfig` model

**Files:**
- Modify: `apps/core/core/db/models.py` (append new class at end of file)
- Test: `apps/core/tests/test_db.py` (append new test function at end of file)

**Interfaces:**
- Produces: `DashboardConfig` class with columns `id: int` (PK, autoincrement), `widget_order: list` (JSON), `hidden_widgets: list` (JSON), `updated_at: datetime` (timezone-aware, defaults to now).

- [ ] **Step 1: Write the failing test**

Append to `apps/core/tests/test_db.py`:

```python
def test_dashboard_config_can_be_created_and_queried():
    from core.db.models import DashboardConfig

    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        row = DashboardConfig(
            widget_order=["skills", "voice", "automations", "tasks"],
            hidden_widgets=[],
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        assert row.id is not None

    with session_factory() as session:
        fetched = session.query(DashboardConfig).one()
        assert fetched.widget_order == ["skills", "voice", "automations", "tasks"]
        assert fetched.hidden_widgets == []
        assert fetched.updated_at is not None
```

Check the top of `apps/core/tests/test_db.py` for the existing `make_engine`/`init_db`/`make_session_factory` imports — this test follows the exact same pattern as `test_skill_invocation_can_be_created_and_queried` and `test_route_decision_can_be_created_and_queried` already in that file, so no new imports should be needed at module level (the `from core.db.models import DashboardConfig` import is local to the test function, matching how `test_route_decision_can_be_created_and_queried` locally imports `RouteDecision`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_db.py::test_dashboard_config_can_be_created_and_queried -v`
Expected: FAIL with `ImportError: cannot import name 'DashboardConfig'`

- [ ] **Step 3: Write minimal implementation**

Append to `apps/core/core/db/models.py`:

```python
class DashboardConfig(Base):
    __tablename__ = "dashboard_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    widget_order: Mapped[list] = mapped_column(JSON, nullable=False)
    hidden_widgets: Mapped[list] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
```

(The `Base`, `Integer`, `JSON`, `DateTime`, `Mapped`, `mapped_column`, `datetime`, `timezone` names are already imported at the top of `models.py` — reused from the existing `SkillInvocation`/`ClaudeCodeTask`/`AutomationRun` classes in the same file. No new imports needed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_db.py::test_dashboard_config_can_be_created_and_queried -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/db/models.py apps/core/tests/test_db.py
git commit -m "feat(core): add DashboardConfig model"
```

---

### Task 2: `GET`/`PUT /dashboard/config` endpoints

**Files:**
- Modify: `apps/core/core/app.py` (add imports, add two new routes after the `/automations/runs/{run_id}` route and before the `/ws` websocket route)
- Test: `apps/core/tests/test_dashboard_config.py` (new file)

**Interfaces:**
- Consumes: `DashboardConfig` from Task 1 (`core.db.models`).
- Produces: `GET /dashboard/config` → 200 `{"widget_order": [...], "hidden_widgets": [...]}`. `PUT /dashboard/config` with body `{"widget_order": [...], "hidden_widgets": [...]}` → 200 with the saved config, or 400 with a `detail` string on validation failure.

- [ ] **Step 1: Write the failing test**

Create `apps/core/tests/test_dashboard_config.py`:

```python
from fastapi.testclient import TestClient

from core.app import create_app
from core.db.models import DashboardConfig

KNOWN_WIDGETS = ["skills", "voice", "automations", "tasks"]


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    app = create_app()
    return TestClient(app), app


def test_get_dashboard_config_creates_default_row_on_first_read(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)

    response = client.get("/dashboard/config")

    assert response.status_code == 200
    body = response.json()
    assert body["widget_order"] == KNOWN_WIDGETS
    assert body["hidden_widgets"] == []

    with app.state.session_factory() as session:
        assert session.query(DashboardConfig).count() == 1


def test_get_dashboard_config_returns_existing_row_without_creating_another(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        session.add(DashboardConfig(widget_order=["voice", "skills", "tasks", "automations"], hidden_widgets=["tasks"]))
        session.commit()

    response = client.get("/dashboard/config")

    assert response.status_code == 200
    body = response.json()
    assert body["widget_order"] == ["voice", "skills", "tasks", "automations"]
    assert body["hidden_widgets"] == ["tasks"]
    with app.state.session_factory() as session:
        assert session.query(DashboardConfig).count() == 1


def test_put_dashboard_config_saves_and_round_trips(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.put(
        "/dashboard/config",
        json={"widget_order": ["tasks", "automations", "voice", "skills"], "hidden_widgets": ["voice"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "widget_order": ["tasks", "automations", "voice", "skills"],
        "hidden_widgets": ["voice"],
    }

    follow_up = client.get("/dashboard/config")
    assert follow_up.json() == {
        "widget_order": ["tasks", "automations", "voice", "skills"],
        "hidden_widgets": ["voice"],
    }


def test_put_dashboard_config_rejects_missing_widget(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.put(
        "/dashboard/config",
        json={"widget_order": ["skills", "voice", "automations"], "hidden_widgets": []},
    )

    assert response.status_code == 400


def test_put_dashboard_config_rejects_duplicate_widget(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.put(
        "/dashboard/config",
        json={"widget_order": ["skills", "skills", "voice", "tasks"], "hidden_widgets": []},
    )

    assert response.status_code == 400


def test_put_dashboard_config_rejects_unknown_widget_id(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.put(
        "/dashboard/config",
        json={"widget_order": ["skills", "voice", "automations", "bogus"], "hidden_widgets": []},
    )

    assert response.status_code == 400


def test_put_dashboard_config_rejects_hidden_widget_not_in_known_set(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.put(
        "/dashboard/config",
        json={"widget_order": KNOWN_WIDGETS, "hidden_widgets": ["bogus"]},
    )

    assert response.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_dashboard_config.py -v`
Expected: FAIL — all tests error with 404 (routes don't exist yet).

- [ ] **Step 3: Write minimal implementation**

In `apps/core/core/app.py`, change the import on line 15 from:

```python
from core.db.models import AutomationRun, ClaudeCodeTask
```

to:

```python
from core.db.models import AutomationRun, ClaudeCodeTask, DashboardConfig
```

Add this near the top of the file, after the `InvokeRequest` class definition (around line 31):

```python
KNOWN_WIDGET_IDS = {"skills", "voice", "automations", "tasks"}
DEFAULT_WIDGET_ORDER = ["skills", "voice", "automations", "tasks"]


class DashboardConfigRequest(BaseModel):
    widget_order: list[str]
    hidden_widgets: list[str]
```

Add these two routes in `apps/core/core/app.py` immediately after the `/automations/runs/{run_id}` route (after the closing of `get_automation_run`, before the `@app.websocket("/ws")` line):

```python
    @app.get("/dashboard/config")
    def get_dashboard_config():
        with app.state.session_factory() as session:
            row = session.query(DashboardConfig).first()
            if row is None:
                row = DashboardConfig(widget_order=DEFAULT_WIDGET_ORDER, hidden_widgets=[])
                session.add(row)
                session.commit()
            return {"widget_order": row.widget_order, "hidden_widgets": row.hidden_widgets}

    @app.put("/dashboard/config")
    def put_dashboard_config(request: DashboardConfigRequest):
        if set(request.widget_order) != KNOWN_WIDGET_IDS or len(request.widget_order) != len(KNOWN_WIDGET_IDS):
            raise HTTPException(
                status_code=400,
                detail=f"widget_order must be exactly a permutation of {sorted(KNOWN_WIDGET_IDS)}",
            )
        if not set(request.hidden_widgets).issubset(KNOWN_WIDGET_IDS):
            raise HTTPException(
                status_code=400,
                detail=f"hidden_widgets must be a subset of {sorted(KNOWN_WIDGET_IDS)}",
            )
        with app.state.session_factory() as session:
            row = session.query(DashboardConfig).first()
            if row is None:
                row = DashboardConfig(widget_order=request.widget_order, hidden_widgets=request.hidden_widgets)
                session.add(row)
            else:
                row.widget_order = request.widget_order
                row.hidden_widgets = request.hidden_widgets
            session.commit()
            return {"widget_order": row.widget_order, "hidden_widgets": row.hidden_widgets}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_dashboard_config.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/app.py apps/core/tests/test_dashboard_config.py
git commit -m "feat(core): add GET/PUT /dashboard/config endpoints"
```

---

### Task 3: `limit` query param on `GET /tasks`

**Files:**
- Modify: `apps/core/core/app.py:148-166` (the `list_tasks` route)
- Test: `apps/core/tests/test_task_endpoints.py` (append new test function)

**Interfaces:**
- Produces: `GET /tasks?limit=N` returns at most `N` tasks (newest first); `GET /tasks` (no param) still defaults to 50.

- [ ] **Step 1: Write the failing test**

Append to `apps/core/tests/test_task_endpoints.py`:

```python
def test_list_tasks_respects_limit_query_param(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        for i in range(5):
            session.add(ClaudeCodeTask(
                task_id=f"task-{i}", prompt="p", working_dir="/tmp", status="completed",
                created_at=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
            ))
        session.commit()

    response = client.get("/tasks?limit=2")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert [t["task_id"] for t in body] == ["task-4", "task-3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_task_endpoints.py::test_list_tasks_respects_limit_query_param -v`
Expected: FAIL with `TypeError: list_tasks() got an unexpected keyword argument 'limit'` (FastAPI will actually return a 422 since the extra query param is silently ignored by default — actual failure mode: the assertion `len(body) == 2` fails because all 5 rows are returned. Either way, it does not pass as written before Step 3.)

- [ ] **Step 3: Write minimal implementation**

In `apps/core/core/app.py`, replace the existing `list_tasks` route (currently at lines 148-166):

```python
    @app.get("/tasks")
    def list_tasks():
        with app.state.session_factory() as session:
            rows = (
                session.query(ClaudeCodeTask)
                .order_by(ClaudeCodeTask.created_at.desc())
                .limit(50)
                .all()
            )
            return [
                {
                    "task_id": row.task_id,
                    "status": row.status,
                    "prompt": row.prompt,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                }
                for row in rows
            ]
```

with:

```python
    @app.get("/tasks")
    def list_tasks(limit: int = 50):
        with app.state.session_factory() as session:
            rows = (
                session.query(ClaudeCodeTask)
                .order_by(ClaudeCodeTask.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "task_id": row.task_id,
                    "status": row.status,
                    "prompt": row.prompt,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                }
                for row in rows
            ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_task_endpoints.py -v`
Expected: PASS (all tests in file, including the existing 3 plus the new one — confirms the default-50 behavior is unbroken)

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/app.py apps/core/tests/test_task_endpoints.py
git commit -m "feat(core): add limit query param to GET /tasks"
```

---

### Task 4: `client.ts` dashboard config functions

**Files:**
- Modify: `apps/desktop/src/api/client.ts` (append new interface + functions at end of file)
- Test: `apps/desktop/src/api/client.test.ts` (append new describe blocks at end of file)

**Interfaces:**
- Produces:
  - `interface DashboardConfig { widget_order: string[]; hidden_widgets: string[]; }`
  - `async function fetchDashboardConfig(): Promise<DashboardConfig>`
  - `async function saveDashboardConfig(config: DashboardConfig): Promise<DashboardConfig>`

- [ ] **Step 1: Write the failing test**

Append to `apps/desktop/src/api/client.test.ts`:

```typescript
describe("fetchDashboardConfig", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns the parsed dashboard config on success", async () => {
    const mockConfig = { widget_order: ["skills", "voice", "automations", "tasks"], hidden_widgets: [] };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockConfig,
    } as Response);

    const result = await fetchDashboardConfig();

    expect(result).toEqual(mockConfig);
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8420/dashboard/config");
  });

  it("throws when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    } as Response);

    await expect(fetchDashboardConfig()).rejects.toThrow("Failed to fetch dashboard config: 500");
  });
});

describe("saveDashboardConfig", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("PUTs the config and returns the parsed response on success", async () => {
    const mockConfig = { widget_order: ["voice", "skills", "tasks", "automations"], hidden_widgets: ["tasks"] };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockConfig,
    } as Response);

    const result = await saveDashboardConfig(mockConfig);

    expect(result).toEqual(mockConfig);
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8420/dashboard/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(mockConfig),
    });
  });

  it("throws with status and body when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "widget_order must be exactly a permutation of [...]" }),
    } as Response);

    await expect(
      saveDashboardConfig({ widget_order: ["skills"], hidden_widgets: [] })
    ).rejects.toThrow(/Failed to save dashboard config: 400/);
  });
});
```

Also update the import line at the top of `apps/desktop/src/api/client.test.ts` from:

```typescript
import { fetchSkills, invokeSkill, invokeVoice, voiceAudioUrl } from "./client";
```

to:

```typescript
import { fetchSkills, invokeSkill, invokeVoice, voiceAudioUrl, fetchDashboardConfig, saveDashboardConfig } from "./client";
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/api/client.test.ts`
Expected: FAIL with `does not provide an export named 'fetchDashboardConfig'`

- [ ] **Step 3: Write minimal implementation**

Append to `apps/desktop/src/api/client.ts`:

```typescript
export interface DashboardConfig {
  widget_order: string[];
  hidden_widgets: string[];
}

export async function fetchDashboardConfig(): Promise<DashboardConfig> {
  const response = await fetch(`${BASE_URL}/dashboard/config`);
  if (!response.ok) {
    throw new Error(`Failed to fetch dashboard config: ${response.status}`);
  }
  return response.json();
}

export async function saveDashboardConfig(config: DashboardConfig): Promise<DashboardConfig> {
  const response = await fetch(`${BASE_URL}/dashboard/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(`Failed to save dashboard config: ${response.status} ${JSON.stringify(body)}`);
  }
  return response.json();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/api/client.test.ts`
Expected: PASS (all tests in file)

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/api/client.ts apps/desktop/src/api/client.test.ts
git commit -m "feat(desktop): add fetchDashboardConfig/saveDashboardConfig to client"
```

---

### Task 5: `SkillsWidget` and `VoiceWidget`

**Files:**
- Create: `apps/desktop/src/widgets/SkillsWidget.tsx`
- Create: `apps/desktop/src/widgets/VoiceWidget.tsx`
- Test: `apps/desktop/src/widgets/SkillsWidget.test.tsx`
- Test: `apps/desktop/src/widgets/VoiceWidget.test.tsx`

**Interfaces:**
- Consumes: `SkillForm` from `../components/SkillForm`, `VoiceButton` from `../components/VoiceButton`, `SkillManifest`/`fetchSkills` from `../api/client`.
- Produces: `SkillsWidget` (no props) — fetches skills itself and renders one `SkillForm` per skill inside a card, with its own loading/error state (moved here from `App.tsx`, which will stop doing this fetch itself in Task 8). `VoiceWidget` (no props) — renders `VoiceButton` inside a card with a heading.

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/src/widgets/SkillsWidget.test.tsx`:

```typescript
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { SkillsWidget } from "./SkillsWidget";
import * as client from "../api/client";
import type { SkillManifest } from "../api/client";

const echoManifest: SkillManifest = {
  id: "echo",
  name: "Echo",
  description: "Repeats back text.",
  input_schema: { type: "object", properties: { text: { type: "string" } }, required: ["text"] },
  output_schema: { type: "object", properties: { text: { type: "string" } } },
  voice_invokable: true,
  ui_component: null,
};

describe("SkillsWidget", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("renders a SkillForm for each fetched skill", async () => {
    vi.spyOn(client, "fetchSkills").mockResolvedValue([echoManifest]);

    render(<SkillsWidget />);

    await waitFor(() => {
      expect(screen.getByText("Echo")).toBeInTheDocument();
    });
  });

  it("shows an error if fetching skills fails", async () => {
    vi.spyOn(client, "fetchSkills").mockRejectedValue(new Error("network down"));

    render(<SkillsWidget />);

    await waitFor(() => {
      expect(screen.getByTestId("skills-widget-error")).toHaveTextContent("network down");
    });
  });
});
```

Create `apps/desktop/src/widgets/VoiceWidget.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { VoiceWidget } from "./VoiceWidget";

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  constructor(_url: string) {}
  close() {}
}

describe("VoiceWidget", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("renders the voice button", () => {
    render(<VoiceWidget />);

    expect(screen.getByTestId("voice-button")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/widgets/SkillsWidget.test.tsx src/widgets/VoiceWidget.test.tsx`
Expected: FAIL — `Failed to resolve import "./SkillsWidget"` / `"./VoiceWidget"` (files don't exist yet)

- [ ] **Step 3: Write minimal implementation**

Create `apps/desktop/src/widgets/SkillsWidget.tsx`:

```typescript
import { useEffect, useState } from "react";
import type { SkillManifest } from "../api/client";
import { fetchSkills } from "../api/client";
import { SkillForm } from "../components/SkillForm";

export function SkillsWidget() {
  const [skills, setSkills] = useState<SkillManifest[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSkills()
      .then(setSkills)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  return (
    <div className="rounded-lg border border-gray-300 p-4">
      <h2 className="text-lg font-semibold mb-2">Skills</h2>
      {error && (
        <p data-testid="skills-widget-error" className="text-sm text-red-600 mb-2">
          {error}
        </p>
      )}
      {skills.map((skill) => (
        <SkillForm key={skill.id} skill={skill} />
      ))}
    </div>
  );
}
```

Create `apps/desktop/src/widgets/VoiceWidget.tsx`:

```typescript
import { VoiceButton } from "../components/VoiceButton";

export function VoiceWidget() {
  return (
    <div className="rounded-lg border border-gray-300 p-4">
      <h2 className="text-lg font-semibold mb-2">Voice</h2>
      <VoiceButton />
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/widgets/SkillsWidget.test.tsx src/widgets/VoiceWidget.test.tsx`
Expected: PASS (3 tests total)

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/widgets/SkillsWidget.tsx apps/desktop/src/widgets/VoiceWidget.tsx apps/desktop/src/widgets/SkillsWidget.test.tsx apps/desktop/src/widgets/VoiceWidget.test.tsx
git commit -m "feat(desktop): add SkillsWidget and VoiceWidget"
```

---

### Task 6: `AutomationsWidget`

**Files:**
- Create: `apps/desktop/src/widgets/AutomationsWidget.tsx`
- Modify: `apps/desktop/src/api/client.ts` (append `Automation`/`AutomationRun` types + `fetchAutomations`/`fetchAutomationRuns`)
- Test: `apps/desktop/src/api/client.test.ts` (append tests for the two new fetch functions)
- Test: `apps/desktop/src/widgets/AutomationsWidget.test.tsx` (new file)

**Interfaces:**
- Consumes: nothing from earlier frontend tasks besides the existing `BASE_URL` constant in `client.ts`.
- Produces:
  - `interface Automation { id: string; name: string | null; enabled: boolean | null; status: string; last_run: { run_id: string; status: string; finished_at: string | null } | null; }`
  - `interface AutomationRunSummary { run_id: string; automation_id: string; status: string; started_at: string | null; finished_at: string | null; }`
  - `async function fetchAutomations(): Promise<Automation[]>`
  - `async function fetchAutomationRuns(limit: number): Promise<AutomationRunSummary[]>`
  - `AutomationsWidget` (no props) — on mount and every 5000ms thereafter, fetches both and renders them; cleans up its interval on unmount.

- [ ] **Step 1: Write the failing test**

Append to `apps/desktop/src/api/client.test.ts`:

```typescript
describe("fetchAutomations", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed automations on success", async () => {
    const mockAutomations = [
      {
        id: "ask_digest",
        name: "Daily Ask Digest",
        enabled: true,
        status: "scheduled",
        last_run: { run_id: "run-1", status: "completed", finished_at: "2026-07-06T09:00:00Z" },
      },
    ];
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockAutomations,
    } as Response);

    const result = await fetchAutomations();

    expect(result).toEqual(mockAutomations);
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8420/automations");
  });

  it("throws when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 } as Response);

    await expect(fetchAutomations()).rejects.toThrow("Failed to fetch automations: 500");
  });
});

describe("fetchAutomationRuns", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed runs with the limit query param", async () => {
    const mockRuns = [
      { run_id: "run-1", automation_id: "ask_digest", status: "completed", started_at: "2026-07-06T09:00:00Z", finished_at: "2026-07-06T09:00:05Z" },
    ];
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockRuns,
    } as Response);

    const result = await fetchAutomationRuns(10);

    expect(result).toEqual(mockRuns);
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8420/automations/runs?limit=10");
  });

  it("throws when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 } as Response);

    await expect(fetchAutomationRuns(10)).rejects.toThrow("Failed to fetch automation runs: 500");
  });
});
```

Update the import line at the top of `apps/desktop/src/api/client.test.ts` to add `fetchAutomations, fetchAutomationRuns`.

Create `apps/desktop/src/widgets/AutomationsWidget.test.tsx`:

```typescript
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { AutomationsWidget } from "./AutomationsWidget";
import * as client from "../api/client";

describe("AutomationsWidget", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("renders automations and recent runs", async () => {
    vi.spyOn(client, "fetchAutomations").mockResolvedValue([
      { id: "ask_digest", name: "Daily Ask Digest", enabled: true, status: "scheduled", last_run: null },
    ]);
    vi.spyOn(client, "fetchAutomationRuns").mockResolvedValue([
      { run_id: "run-1", automation_id: "ask_digest", status: "completed", started_at: "2026-07-06T09:00:00Z", finished_at: "2026-07-06T09:00:05Z" },
    ]);

    render(<AutomationsWidget />);

    await waitFor(() => {
      expect(screen.getByText("Daily Ask Digest")).toBeInTheDocument();
      expect(screen.getByText(/run-1/)).toBeInTheDocument();
    });
  });

  it("shows an error if fetching automations fails", async () => {
    vi.spyOn(client, "fetchAutomations").mockRejectedValue(new Error("boom"));
    vi.spyOn(client, "fetchAutomationRuns").mockResolvedValue([]);

    render(<AutomationsWidget />);

    await waitFor(() => {
      expect(screen.getByTestId("automations-widget-error")).toHaveTextContent("boom");
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/api/client.test.ts src/widgets/AutomationsWidget.test.tsx`
Expected: FAIL — missing exports `fetchAutomations`/`fetchAutomationRuns`, missing module `./AutomationsWidget`

- [ ] **Step 3: Write minimal implementation**

Append to `apps/desktop/src/api/client.ts`:

```typescript
export interface Automation {
  id: string;
  name: string | null;
  enabled: boolean | null;
  status: string;
  last_run: { run_id: string; status: string; finished_at: string | null } | null;
}

export interface AutomationRunSummary {
  run_id: string;
  automation_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
}

export async function fetchAutomations(): Promise<Automation[]> {
  const response = await fetch(`${BASE_URL}/automations`);
  if (!response.ok) {
    throw new Error(`Failed to fetch automations: ${response.status}`);
  }
  return response.json();
}

export async function fetchAutomationRuns(limit: number): Promise<AutomationRunSummary[]> {
  const response = await fetch(`${BASE_URL}/automations/runs?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch automation runs: ${response.status}`);
  }
  return response.json();
}
```

Create `apps/desktop/src/widgets/AutomationsWidget.tsx`:

```typescript
import { useEffect, useState } from "react";
import type { Automation, AutomationRunSummary } from "../api/client";
import { fetchAutomationRuns, fetchAutomations } from "../api/client";

const POLL_INTERVAL_MS = 5000;

export function AutomationsWidget() {
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [runs, setRuns] = useState<AutomationRunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = () => {
      Promise.all([fetchAutomations(), fetchAutomationRuns(10)])
        .then(([nextAutomations, nextRuns]) => {
          if (cancelled) return;
          setAutomations(nextAutomations);
          setRuns(nextRuns);
          setError(null);
        })
        .catch((err) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : String(err));
        });
    };

    load();
    const intervalId = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, []);

  return (
    <div className="rounded-lg border border-gray-300 p-4">
      <h2 className="text-lg font-semibold mb-2">Automations</h2>
      {error && (
        <p data-testid="automations-widget-error" className="text-sm text-red-600 mb-2">
          {error}
        </p>
      )}
      <ul className="mb-3">
        {automations.map((automation) => (
          <li key={automation.id} className="text-sm mb-1">
            {automation.name ?? automation.id} — {automation.status}
          </li>
        ))}
      </ul>
      <h3 className="text-sm font-semibold mb-1">Recent runs</h3>
      <ul>
        {runs.map((run) => (
          <li key={run.run_id} className="text-sm text-gray-600 mb-1">
            {run.run_id} ({run.automation_id}) — {run.status}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/api/client.test.ts src/widgets/AutomationsWidget.test.tsx`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/api/client.ts apps/desktop/src/api/client.test.ts apps/desktop/src/widgets/AutomationsWidget.tsx apps/desktop/src/widgets/AutomationsWidget.test.tsx
git commit -m "feat(desktop): add AutomationsWidget with polling"
```

---

### Task 7: `TasksWidget`

**Files:**
- Create: `apps/desktop/src/widgets/TasksWidget.tsx`
- Modify: `apps/desktop/src/api/client.ts` (append `Task` type + `fetchTasks`)
- Test: `apps/desktop/src/api/client.test.ts` (append tests for `fetchTasks`)
- Test: `apps/desktop/src/widgets/TasksWidget.test.tsx` (new file)

**Interfaces:**
- Produces:
  - `interface Task { task_id: string; status: string; prompt: string; created_at: string | null; finished_at: string | null; }`
  - `async function fetchTasks(limit: number): Promise<Task[]>`
  - `TasksWidget` (no props) — polls every 5000ms with `limit=10`, same lifecycle pattern as `AutomationsWidget`.

- [ ] **Step 1: Write the failing test**

Append to `apps/desktop/src/api/client.test.ts`:

```typescript
describe("fetchTasks", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed tasks with the limit query param", async () => {
    const mockTasks = [
      { task_id: "task-1", status: "completed", prompt: "do X", created_at: "2026-07-06T09:00:00Z", finished_at: "2026-07-06T09:00:05Z" },
    ];
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockTasks,
    } as Response);

    const result = await fetchTasks(10);

    expect(result).toEqual(mockTasks);
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8420/tasks?limit=10");
  });

  it("throws when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 } as Response);

    await expect(fetchTasks(10)).rejects.toThrow("Failed to fetch tasks: 500");
  });
});
```

Update the import line at the top of `apps/desktop/src/api/client.test.ts` to add `fetchTasks`.

Create `apps/desktop/src/widgets/TasksWidget.test.tsx`:

```typescript
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { TasksWidget } from "./TasksWidget";
import * as client from "../api/client";

describe("TasksWidget", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("renders recent tasks", async () => {
    vi.spyOn(client, "fetchTasks").mockResolvedValue([
      { task_id: "task-1", status: "completed", prompt: "do X", created_at: "2026-07-06T09:00:00Z", finished_at: "2026-07-06T09:00:05Z" },
    ]);

    render(<TasksWidget />);

    await waitFor(() => {
      expect(screen.getByText(/task-1/)).toBeInTheDocument();
    });
  });

  it("shows an error if fetching tasks fails", async () => {
    vi.spyOn(client, "fetchTasks").mockRejectedValue(new Error("boom"));

    render(<TasksWidget />);

    await waitFor(() => {
      expect(screen.getByTestId("tasks-widget-error")).toHaveTextContent("boom");
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/api/client.test.ts src/widgets/TasksWidget.test.tsx`
Expected: FAIL — missing export `fetchTasks`, missing module `./TasksWidget`

- [ ] **Step 3: Write minimal implementation**

Append to `apps/desktop/src/api/client.ts`:

```typescript
export interface Task {
  task_id: string;
  status: string;
  prompt: string;
  created_at: string | null;
  finished_at: string | null;
}

export async function fetchTasks(limit: number): Promise<Task[]> {
  const response = await fetch(`${BASE_URL}/tasks?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch tasks: ${response.status}`);
  }
  return response.json();
}
```

Create `apps/desktop/src/widgets/TasksWidget.tsx`:

```typescript
import { useEffect, useState } from "react";
import type { Task } from "../api/client";
import { fetchTasks } from "../api/client";

const POLL_INTERVAL_MS = 5000;

export function TasksWidget() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = () => {
      fetchTasks(10)
        .then((nextTasks) => {
          if (cancelled) return;
          setTasks(nextTasks);
          setError(null);
        })
        .catch((err) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : String(err));
        });
    };

    load();
    const intervalId = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, []);

  return (
    <div className="rounded-lg border border-gray-300 p-4">
      <h2 className="text-lg font-semibold mb-2">Claude Code Tasks</h2>
      {error && (
        <p data-testid="tasks-widget-error" className="text-sm text-red-600 mb-2">
          {error}
        </p>
      )}
      <ul>
        {tasks.map((task) => (
          <li key={task.task_id} className="text-sm mb-1">
            {task.task_id} — {task.status} — {task.prompt}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/api/client.test.ts src/widgets/TasksWidget.test.tsx`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/api/client.ts apps/desktop/src/api/client.test.ts apps/desktop/src/widgets/TasksWidget.tsx apps/desktop/src/widgets/TasksWidget.test.tsx
git commit -m "feat(desktop): add TasksWidget with polling"
```

---

### Task 8: Widget registry + `App.tsx` dashboard shell with Customize panel

**Files:**
- Create: `apps/desktop/src/widgets/registry.ts`
- Modify: `apps/desktop/src/App.tsx` (full rewrite)
- Modify: `apps/desktop/src/App.test.tsx` (full rewrite)

**Interfaces:**
- Consumes: `SkillsWidget`, `VoiceWidget`, `AutomationsWidget`, `TasksWidget` (Tasks 5-7), `fetchDashboardConfig`/`saveDashboardConfig`/`DashboardConfig` (Task 4).
- Produces: `WIDGET_REGISTRY: Record<string, { label: string; component: React.ComponentType }>` keyed by `"skills" | "voice" | "automations" | "tasks"`. `App` — the dashboard shell component (default export, unchanged contract from the app's entry point in `main.tsx`, which imports `App` as the default export and does not need modification).

- [ ] **Step 1: Write the failing test**

Replace the full contents of `apps/desktop/src/App.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup, within } from "@testing-library/react";
import App from "./App";
import * as client from "./api/client";

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  constructor(_url: string) {}
  close() {}
}

const defaultConfig = { widget_order: ["skills", "voice", "automations", "tasks"], hidden_widgets: [] };

function mockBaseFetches() {
  vi.spyOn(client, "fetchDashboardConfig").mockResolvedValue(defaultConfig);
  vi.spyOn(client, "fetchSkills").mockResolvedValue([]);
  vi.spyOn(client, "fetchAutomations").mockResolvedValue([]);
  vi.spyOn(client, "fetchAutomationRuns").mockResolvedValue([]);
  vi.spyOn(client, "fetchTasks").mockResolvedValue([]);
}

describe("App", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    cleanup();
  });

  it("renders all 4 widgets in the configured order by default", async () => {
    mockBaseFetches();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });
    expect(screen.getByText("Voice")).toBeInTheDocument();
    expect(screen.getByText("Automations")).toBeInTheDocument();
    expect(screen.getByText("Claude Code Tasks")).toBeInTheDocument();
  });

  it("hides a widget listed in hidden_widgets", async () => {
    vi.spyOn(client, "fetchDashboardConfig").mockResolvedValue({
      widget_order: ["skills", "voice", "automations", "tasks"],
      hidden_widgets: ["voice"],
    });
    vi.spyOn(client, "fetchSkills").mockResolvedValue([]);
    vi.spyOn(client, "fetchAutomations").mockResolvedValue([]);
    vi.spyOn(client, "fetchAutomationRuns").mockResolvedValue([]);
    vi.spyOn(client, "fetchTasks").mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });
    expect(screen.queryByText("Voice")).not.toBeInTheDocument();
  });

  it("shows an error if fetching the dashboard config fails", async () => {
    vi.spyOn(client, "fetchDashboardConfig").mockRejectedValue(new Error("network down"));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("app-error")).toHaveTextContent("network down");
    });
  });

  it("opens the Customize panel, hides a widget, and saves", async () => {
    mockBaseFetches();
    vi.spyOn(client, "saveDashboardConfig").mockResolvedValue({
      widget_order: ["skills", "voice", "automations", "tasks"],
      hidden_widgets: ["voice"],
    });

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Customize" }));
    const panel = screen.getByTestId("customize-panel");
    fireEvent.click(within(panel).getByLabelText("Voice"));
    fireEvent.click(within(panel).getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(client.saveDashboardConfig).toHaveBeenCalledWith({
        widget_order: ["skills", "voice", "automations", "tasks"],
        hidden_widgets: ["voice"],
      });
    });
    expect(screen.queryByTestId("customize-panel")).not.toBeInTheDocument();
  });

  it("shows an inline error and keeps the panel open when saving fails", async () => {
    mockBaseFetches();
    vi.spyOn(client, "saveDashboardConfig").mockRejectedValue(new Error("widget_order must be exactly a permutation"));

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Customize" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(screen.getByTestId("customize-error")).toHaveTextContent("widget_order must be exactly a permutation");
    });
    expect(screen.getByTestId("customize-panel")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/App.test.tsx`
Expected: FAIL — `App` still renders the old flat layout; `fetchDashboardConfig`/`fetchAutomations`/etc. spies exist (from earlier tasks) but `App.tsx` doesn't call them yet, so none of the new assertions (widget headings, Customize button, panel) find matching elements.

- [ ] **Step 3: Write minimal implementation**

Create `apps/desktop/src/widgets/registry.ts`:

```typescript
import type { ComponentType } from "react";
import { AutomationsWidget } from "./AutomationsWidget";
import { SkillsWidget } from "./SkillsWidget";
import { TasksWidget } from "./TasksWidget";
import { VoiceWidget } from "./VoiceWidget";

export type WidgetId = "skills" | "voice" | "automations" | "tasks";

export const WIDGET_REGISTRY: Record<WidgetId, { label: string; component: ComponentType }> = {
  skills: { label: "Skills", component: SkillsWidget },
  voice: { label: "Voice", component: VoiceWidget },
  automations: { label: "Automations", component: AutomationsWidget },
  tasks: { label: "Claude Code Tasks", component: TasksWidget },
};

export const ALL_WIDGET_IDS: WidgetId[] = ["skills", "voice", "automations", "tasks"];
```

Replace the full contents of `apps/desktop/src/App.tsx`:

```typescript
import { useEffect, useState } from "react";
import type { DashboardConfig } from "./api/client";
import { fetchDashboardConfig, saveDashboardConfig } from "./api/client";
import { ALL_WIDGET_IDS, WIDGET_REGISTRY } from "./widgets/registry";
import type { WidgetId } from "./widgets/registry";

function CustomizePanel({
  config,
  onSave,
  onCancel,
}: {
  config: DashboardConfig;
  onSave: (config: DashboardConfig) => void;
  onCancel: () => void;
}) {
  const [order, setOrder] = useState<WidgetId[]>(config.widget_order as WidgetId[]);
  const [hidden, setHidden] = useState<Set<WidgetId>>(new Set(config.hidden_widgets as WidgetId[]));
  const [error, setError] = useState<string | null>(null);

  const toggleHidden = (id: WidgetId) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const move = (id: WidgetId, direction: -1 | 1) => {
    setOrder((prev) => {
      const index = prev.indexOf(id);
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
      return next;
    });
  };

  const handleSave = async () => {
    setError(null);
    try {
      const saved = await saveDashboardConfig({ widget_order: order, hidden_widgets: [...hidden] });
      onSave(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div data-testid="customize-panel" className="rounded-lg border border-gray-300 p-4 mb-4">
      <h2 className="text-lg font-semibold mb-2">Customize dashboard</h2>
      {order.map((id, index) => (
        <div key={id} className="flex items-center gap-2 mb-1">
          <input
            type="checkbox"
            aria-label={WIDGET_REGISTRY[id].label}
            checked={!hidden.has(id)}
            onChange={() => toggleHidden(id)}
          />
          <span>{WIDGET_REGISTRY[id].label}</span>
          <button onClick={() => move(id, -1)} disabled={index === 0} aria-label={`Move ${WIDGET_REGISTRY[id].label} up`}>
            ↑
          </button>
          <button
            onClick={() => move(id, 1)}
            disabled={index === order.length - 1}
            aria-label={`Move ${WIDGET_REGISTRY[id].label} down`}
          >
            ↓
          </button>
        </div>
      ))}
      {error && (
        <p data-testid="customize-error" className="text-sm text-red-600 mt-2">
          {error}
        </p>
      )}
      <div className="mt-2">
        <button onClick={handleSave} className="bg-blue-600 text-white rounded px-3 py-1 mr-2">
          Save
        </button>
        <button onClick={onCancel} className="rounded px-3 py-1 border border-gray-300">
          Cancel
        </button>
      </div>
    </div>
  );
}

function App() {
  const [config, setConfig] = useState<DashboardConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [customizing, setCustomizing] = useState(false);

  useEffect(() => {
    fetchDashboardConfig()
      .then(setConfig)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  const visibleOrderedWidgets: WidgetId[] = config
    ? (config.widget_order as WidgetId[]).filter((id) => !config.hidden_widgets.includes(id))
    : [];

  return (
    <main className="p-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Jarvis OS</h1>
        <button
          onClick={() => setCustomizing((prev) => !prev)}
          className="rounded px-3 py-1 border border-gray-300"
        >
          Customize
        </button>
      </div>
      {error && (
        <p data-testid="app-error" className="text-red-600 mb-4">
          {error}
        </p>
      )}
      {customizing && config && (
        <CustomizePanel
          config={config}
          onSave={(saved) => {
            setConfig(saved);
            setCustomizing(false);
          }}
          onCancel={() => setCustomizing(false)}
        />
      )}
      <div className="flex flex-col gap-4">
        {visibleOrderedWidgets.map((id) => {
          const Widget = WIDGET_REGISTRY[id].component;
          return <Widget key={id} />;
        })}
      </div>
    </main>
  );
}

export default App;
```

Note: `ALL_WIDGET_IDS` is exported from `registry.ts` for completeness/future use (e.g. a later milestone resetting to defaults) but is not consumed by `App.tsx` itself this milestone — `App.tsx` derives its rendering order from the fetched `config.widget_order`, not from `ALL_WIDGET_IDS`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/App.test.tsx`
Expected: PASS (6 tests)

Then run the full frontend suite to confirm nothing else broke:

Run: `cd apps/desktop && npx vitest run`
Expected: PASS (all files, including `SkillForm.test.tsx` and `VoiceButton.test.tsx` unaffected by this change since those components themselves were not modified)

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/widgets/registry.ts apps/desktop/src/App.tsx apps/desktop/src/App.test.tsx
git commit -m "feat(desktop): turn App into a config-driven dashboard shell with Customize panel"
```

---

### Task 9: Full-suite verification and manual smoke check

**Files:** None created or modified — verification only, mirrors Milestone 6's Task 11 manual smoke test in spirit but scoped to what can be checked without a running Tauri shell (backend + frontend test suites, plus a live backend manual check via curl).

**Interfaces:** None — this task consumes everything from Tasks 1-8 and asserts the whole system holds together.

- [ ] **Step 1: Run the full backend suite**

Run: `cd apps/core && .venv/bin/python -m pytest -q`
Expected: all tests pass, 0 failed (includes every existing Milestone 1-6 test plus this milestone's new `test_dashboard_config.py`, the `test_db.py` addition, and the `test_task_endpoints.py` addition)

- [ ] **Step 2: Run the full frontend suite**

Run: `cd apps/desktop && npx vitest run`
Expected: all tests pass, 0 failed (includes every existing Milestone 1-2/4 component test plus this milestone's widget tests and the rewritten `App.test.tsx`)

- [ ] **Step 3: Manual smoke check of the new endpoints against a live backend**

Start the backend from `apps/core`: `.venv/bin/uvicorn core.app:create_app --factory --port 8420 &` and wait ~2s for startup, then:

```bash
curl -s http://127.0.0.1:8420/dashboard/config
```

Expected: `{"widget_order":["skills","voice","automations","tasks"],"hidden_widgets":[]}` (first-ever call against a fresh dev DB creates the default row — if the dev DB already has automations/tasks from Milestone 5/6 manual testing, this is still the first `DashboardConfig` row specifically, since the table is new this milestone).

```bash
curl -s -X PUT http://127.0.0.1:8420/dashboard/config -H "Content-Type: application/json" -d '{"widget_order": ["voice", "skills", "automations", "tasks"], "hidden_widgets": ["tasks"]}'
```

Expected: `{"widget_order":["voice","skills","automations","tasks"],"hidden_widgets":["tasks"]}`

```bash
curl -s http://127.0.0.1:8420/dashboard/config
```

Expected: same body as the PUT response above, proving persistence.

```bash
curl -s "http://127.0.0.1:8420/tasks?limit=1"
```

Expected: a JSON array with at most 1 element (proves the new `limit` param works against the real running app, not just the test DB).

Stop the backend: `kill %1` (or find and kill the uvicorn process by port if job control isn't available in the shell).

**Do not** attempt to launch the full Tauri desktop shell in this task — that requires a display and is out of scope for a headless verification pass; the frontend test suite (Step 2) is the verification for the UI layer.

- [ ] **Step 4: Update the progress ledger**

Append to `.superpowers/sdd/progress.md` (create the file if it doesn't exist yet in this worktree, matching the format used in Milestones 5 and 6):

```
Task 9: complete (verification only, no commit; full backend suite green, full frontend suite green, /dashboard/config GET/PUT manually verified against a live backend including persistence round-trip, GET /tasks?limit=1 manually verified)
```

No commit for this task (verification-only, matching the pattern from Milestone 6's Task 11).
