# Jarvis OS Milestone 9: Notifications, Document Viewer, Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add in-app WebSocket-driven toast notifications, a document viewer (`read_note` skill + `NotesWidget`), and fold in specific deferred polish items from Milestones 7 and 8.

**Architecture:** Toasts are a new `useEventToasts()` hook opening the existing `/ws` connection (mirroring `VoiceButton`'s proven WS pattern) and a `ToastContainer` rendering them, wired once into `App.tsx`. The document viewer extends the `KnowledgeSource` protocol with a `read(path)` method, implemented by `ObsidianVaultSource`, exposed as a new `read_note` skill, and surfaced as a 5th dashboard widget (`NotesWidget`) added to the existing `WIDGET_REGISTRY` pattern. Polish items are small, targeted fixes to already-shipped code.

**Tech Stack:** No new dependencies on either side. `@testing-library/react@16` (already installed) ships `renderHook`/`act` for hook testing — no `@testing-library/react-hooks` needed.

## Global Constraints

- `KnowledgeSource.read(path: str) -> str | None` — returns `None` for a missing file, a path resolving outside the vault root, or any read/decode failure. Never raises.
- `read_note` skill: `voice_invokable: false` (reading an arbitrary-length note aloud is bad voice UX, unlike `search_notes`'s short excerpts), `input_schema: {"path": "string"}`, `output_schema: {"content": "string"}` (documented as nullable at runtime even though the schema's declared type is `string`, matching this project's existing convention of not encoding nullability in manifest schemas).
- The 5 known widget ids become: `"skills"`, `"voice"`, `"automations"`, `"tasks"`, `"notes"` — `KNOWN_WIDGET_IDS`/`DEFAULT_WIDGET_ORDER` (backend) and `WidgetId`/`WIDGET_REGISTRY`/`ALL_WIDGET_IDS` (frontend) all grow from 4 to 5.
- `PUT /dashboard/config` must set `updated_at = datetime.now(timezone.utc)` on every save (Polish item 1 — it currently never updates).
- Both `App.tsx`'s dashboard render list AND `CustomizePanel`'s initial order must filter out any widget id not present in `WIDGET_REGISTRY` before use (Polish item 2 — protects against a stale saved config referencing a widget id that no longer exists).
- Toast notifications: triggered by `{"type": "automation_run", "stage": "completed" | "failed", ...}` and `{"type": "claude_code_task", "stage": "completed" | "failed", ...}` WebSocket messages (confirmed these exact type/stage values already exist in `core/automation/runner.py` and `core/tasks/manager.py` — no backend changes needed for this part). Each toast auto-dismisses after 6000ms.
- No new Python or npm dependencies.

---

### Task 1: `KnowledgeSource.read()` + `ObsidianVaultSource.read()`

**Files:**
- Modify: `apps/core/core/providers/knowledge/base.py`
- Modify: `apps/core/core/providers/knowledge/obsidian.py`
- Modify: `apps/core/tests/test_knowledge_obsidian.py` (fix the awkward import placeholder — Polish item 3 — and append new tests)

**Interfaces:**
- Produces: `KnowledgeSource.read(path: str) -> str | None`, `ObsidianVaultSource.read(path: str) -> str | None`.

- [ ] **Step 1: Write the failing test**

First, fix the existing awkward import block at the top of `apps/core/tests/test_knowledge_obsidian.py`. Find this (near the top of the file):

```python
import shutil

from core.providers.knowledge.obsidian import ObsidianVaultSource

FIXTURE_VAULT = None  # set below after Path import to keep this block copy-pasteable


from pathlib import Path  # noqa: E402

FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"
```

Replace it with:

```python
import shutil
from pathlib import Path

from core.providers.knowledge.obsidian import ObsidianVaultSource

FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"
```

Then append these tests to the end of the file:

```python
def test_read_returns_content_for_existing_note():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    content = source.read("project-ideas.md")

    assert content is not None
    assert "Jarvis OS should eventually search my notes." in content


def test_read_returns_content_for_nested_note():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    content = source.read("subdir/nested-note.md")

    assert content is not None
    assert "Quarterly Review" in content


def test_read_returns_none_for_missing_note():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    content = source.read("does-not-exist.md")

    assert content is None


def test_read_returns_none_for_relative_path_traversal_attempt():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    content = source.read("../../../../etc/passwd")

    assert content is None


def test_read_returns_none_for_absolute_path_outside_vault(tmp_path):
    outside_file = tmp_path / "secret.md"
    outside_file.write_text("top secret content")
    source = ObsidianVaultSource(FIXTURE_VAULT)

    content = source.read(str(outside_file))

    assert content is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_knowledge_obsidian.py -v`
Expected: the 5 new tests FAIL with `AttributeError: 'ObsidianVaultSource' object has no attribute 'read'`; the pre-existing 7 tests still pass (proving the import cleanup didn't break anything).

- [ ] **Step 3: Write minimal implementation**

In `apps/core/core/providers/knowledge/base.py`, add a `read` method to the `KnowledgeSource` Protocol. The full file becomes:

```python
from typing import Protocol, TypedDict, runtime_checkable


class NoteMatch(TypedDict):
    path: str
    title: str
    excerpt: str
    line_number: int


@runtime_checkable
class KnowledgeSource(Protocol):
    def search(self, query: str, limit: int = 10) -> list[NoteMatch]: ...
    def read(self, path: str) -> str | None: ...
```

In `apps/core/core/providers/knowledge/obsidian.py`, add a `read` method to `ObsidianVaultSource` (append after `search`, keeping everything else in the file unchanged):

```python
    def read(self, path: str) -> str | None:
        candidate = self.vault_root / path
        resolved_root = self.vault_root.resolve()
        resolved_candidate = candidate.resolve()

        if not resolved_candidate.is_relative_to(resolved_root):
            return None
        if not candidate.is_file():
            return None

        try:
            return candidate.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_knowledge_obsidian.py -v`
Expected: PASS (12 tests: 7 existing + 5 new)

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/providers/knowledge/base.py apps/core/core/providers/knowledge/obsidian.py apps/core/tests/test_knowledge_obsidian.py
git commit -m "feat(core): add KnowledgeSource.read() and fix test import cleanup"
```

---

### Task 2: `read_note` skill

**Files:**
- Create: `apps/core/skills/read_note/manifest.yaml`
- Create: `apps/core/skills/read_note/skill.py`
- Test: `apps/core/tests/test_read_note_skill.py`

**Interfaces:**
- Consumes: `ObsidianVaultSource.read` from Task 1.
- Produces: the `read_note` skill, `run({"path": str}) -> {"content": str | None}`.

- [ ] **Step 1: Write the failing test**

Create `apps/core/tests/test_read_note_skill.py`:

```python
from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"


def test_manifest_is_not_voice_invokable():
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)

    loaded = registry.get("read_note")

    assert loaded is not None
    assert loaded.manifest.voice_invokable is False


def test_run_returns_content_for_existing_note(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("read_note")

    class FakeSettings:
        knowledge_vault_dir = str(FIXTURE_VAULT)

    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: FakeSettings())

    result = loaded.run({"path": "project-ideas.md"})

    assert result["content"] is not None
    assert "Jarvis OS should eventually search my notes." in result["content"]


def test_run_returns_none_content_for_missing_note(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("read_note")

    class FakeSettings:
        knowledge_vault_dir = str(FIXTURE_VAULT)

    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: FakeSettings())

    result = loaded.run({"path": "does-not-exist.md"})

    assert result["content"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_read_note_skill.py -v`
Expected: FAIL — `loaded is None` (skill doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `apps/core/skills/read_note/manifest.yaml`:

```yaml
id: read_note
name: Read Note
description: Returns the full content of a note from your Obsidian vault by its relative path. Returns null content if the note does not exist.
voice_invokable: false
input_schema:
  type: object
  properties:
    path:
      type: string
  required:
    - path
output_schema:
  type: object
  properties:
    content:
      type: string
```

Create `apps/core/skills/read_note/skill.py`:

```python
from pathlib import Path

from core.config import get_settings
from core.providers.knowledge.obsidian import ObsidianVaultSource

BASE_DIR = Path(__file__).resolve().parents[2]


def run(inputs: dict) -> dict:
    settings = get_settings()
    vault_root = BASE_DIR / settings.knowledge_vault_dir
    source = ObsidianVaultSource(vault_root)
    content = source.read(inputs["path"])
    return {"content": content}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_read_note_skill.py -v`
Expected: PASS (3 tests)

Then run the full backend suite: `cd apps/core && .venv/bin/python -m pytest -q`
Expected: all pass, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add apps/core/skills/read_note/ apps/core/tests/test_read_note_skill.py
git commit -m "feat(core): add read_note skill"
```

---

### Task 3: Dashboard config — add `notes` widget id + `updated_at` fix

**Files:**
- Modify: `apps/core/core/app.py`
- Modify: `apps/core/tests/test_dashboard_config.py`

**Interfaces:**
- Produces: `KNOWN_WIDGET_IDS`/`DEFAULT_WIDGET_ORDER` now include `"notes"`; `PUT /dashboard/config` sets `updated_at` on every save.

- [ ] **Step 1: Write the failing test**

In `apps/core/tests/test_dashboard_config.py`, change the module-level constant:

```python
KNOWN_WIDGETS = ["skills", "voice", "automations", "tasks"]
```

to:

```python
KNOWN_WIDGETS = ["skills", "voice", "automations", "tasks", "notes"]
```

Change `test_put_dashboard_config_saves_and_round_trips` from:

```python
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
```

to:

```python
def test_put_dashboard_config_saves_and_round_trips(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.put(
        "/dashboard/config",
        json={"widget_order": ["tasks", "automations", "voice", "skills", "notes"], "hidden_widgets": ["voice"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "widget_order": ["tasks", "automations", "voice", "skills", "notes"],
        "hidden_widgets": ["voice"],
    }

    follow_up = client.get("/dashboard/config")
    assert follow_up.json() == {
        "widget_order": ["tasks", "automations", "voice", "skills", "notes"],
        "hidden_widgets": ["voice"],
    }
```

Append this new test to the end of the file:

```python
def test_put_dashboard_config_updates_updated_at_timestamp(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    client, app = _client(tmp_path, monkeypatch)
    client.get("/dashboard/config")  # creates the default row

    with app.state.session_factory() as session:
        row = session.query(DashboardConfig).one()
        row.updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        session.commit()

    client.put(
        "/dashboard/config",
        json={"widget_order": KNOWN_WIDGETS, "hidden_widgets": []},
    )

    with app.state.session_factory() as session:
        updated = session.query(DashboardConfig).one()
        assert updated.updated_at.year != 2020
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_dashboard_config.py -v`
Expected: `test_put_dashboard_config_saves_and_round_trips` FAILs with a 400 (the 5-item permutation is rejected since `KNOWN_WIDGET_IDS` in `app.py` still only has 4 known ids); `test_put_dashboard_config_updates_updated_at_timestamp` FAILs (year is still 2020, since nothing updates it yet).

- [ ] **Step 3: Write minimal implementation**

In `apps/core/core/app.py`, add the datetime import. Change:

```python
import asyncio
import uuid
from pathlib import Path
```

to:

```python
import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
```

Change:

```python
KNOWN_WIDGET_IDS = {"skills", "voice", "automations", "tasks"}
DEFAULT_WIDGET_ORDER = ["skills", "voice", "automations", "tasks"]
```

to:

```python
KNOWN_WIDGET_IDS = {"skills", "voice", "automations", "tasks", "notes"}
DEFAULT_WIDGET_ORDER = ["skills", "voice", "automations", "tasks", "notes"]
```

In the `put_dashboard_config` route, change:

```python
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

to:

```python
        with app.state.session_factory() as session:
            row = session.query(DashboardConfig).first()
            if row is None:
                row = DashboardConfig(widget_order=request.widget_order, hidden_widgets=request.hidden_widgets)
                session.add(row)
            else:
                row.widget_order = request.widget_order
                row.hidden_widgets = request.hidden_widgets
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            return {"widget_order": row.widget_order, "hidden_widgets": row.hidden_widgets}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_dashboard_config.py -v`
Expected: PASS (8 tests: 7 existing, one modified in place, plus 1 new)

Then run the full backend suite: `cd apps/core && .venv/bin/python -m pytest -q`
Expected: all pass, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/app.py apps/core/tests/test_dashboard_config.py
git commit -m "feat(core): add notes widget id and fix DashboardConfig.updated_at"
```

---

### Task 4: `client.ts` — `NoteMatch`, `searchNotes`, `fetchNoteContent`

**Files:**
- Modify: `apps/desktop/src/api/client.ts`
- Modify: `apps/desktop/src/api/client.test.ts`

**Interfaces:**
- Produces: `interface NoteMatch { path: string; title: string; excerpt: string; line_number: number; }`, `async function searchNotes(query: string): Promise<NoteMatch[]>`, `async function fetchNoteContent(path: string): Promise<string | null>`.

- [ ] **Step 1: Write the failing test**

Update the import line at the top of `apps/desktop/src/api/client.test.ts` — change:

```typescript
import { fetchSkills, invokeSkill, invokeVoice, voiceAudioUrl, fetchDashboardConfig, saveDashboardConfig, fetchAutomations, fetchAutomationRuns, fetchTasks } from "./client";
```

to:

```typescript
import { fetchSkills, invokeSkill, invokeVoice, voiceAudioUrl, fetchDashboardConfig, saveDashboardConfig, fetchAutomations, fetchAutomationRuns, fetchTasks, searchNotes, fetchNoteContent } from "./client";
```

(If the existing import line doesn't match exactly — earlier tasks may have wrapped it differently — just add `searchNotes, fetchNoteContent` to whatever the existing import list from `"./client"` already contains.)

Append to `apps/desktop/src/api/client.test.ts`:

```typescript
describe("searchNotes", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("invokes the search_notes skill and returns matches", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ outputs: { matches: [{ path: "a.md", title: "A", excerpt: "hi", line_number: 1 }] } }),
    } as Response);

    const result = await searchNotes("hi");

    expect(result).toEqual([{ path: "a.md", title: "A", excerpt: "hi", line_number: 1 }]);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8420/skills/search_notes/invoke",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inputs: { query: "hi" } }),
      }
    );
  });
});

describe("fetchNoteContent", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("invokes the read_note skill and returns content", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ outputs: { content: "full note text" } }),
    } as Response);

    const result = await fetchNoteContent("a.md");

    expect(result).toBe("full note text");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8420/skills/read_note/invoke",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inputs: { path: "a.md" } }),
      }
    );
  });

  it("returns null when the note doesn't exist", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ outputs: { content: null } }),
    } as Response);

    const result = await fetchNoteContent("missing.md");

    expect(result).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/api/client.test.ts`
Expected: FAIL — `does not provide an export named 'searchNotes'`

- [ ] **Step 3: Write minimal implementation**

Append to `apps/desktop/src/api/client.ts`:

```typescript
export interface NoteMatch {
  path: string;
  title: string;
  excerpt: string;
  line_number: number;
}

export async function searchNotes(query: string): Promise<NoteMatch[]> {
  const result = await invokeSkill("search_notes", { query });
  return (result.outputs as { matches: NoteMatch[] }).matches;
}

export async function fetchNoteContent(path: string): Promise<string | null> {
  const result = await invokeSkill("read_note", { path });
  return (result.outputs as { content: string | null }).content;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/api/client.test.ts`
Expected: PASS (all tests in file)

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/api/client.ts apps/desktop/src/api/client.test.ts
git commit -m "feat(desktop): add searchNotes/fetchNoteContent to client"
```

---

### Task 5: `NotesWidget`

**Files:**
- Create: `apps/desktop/src/widgets/NotesWidget.tsx`
- Test: `apps/desktop/src/widgets/NotesWidget.test.tsx`

**Interfaces:**
- Consumes: `searchNotes`/`fetchNoteContent`/`NoteMatch` from Task 4.
- Produces: `NotesWidget` (no props) — a search box + results list where clicking a match expands its full content inline.

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/src/widgets/NotesWidget.test.tsx`:

```typescript
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { NotesWidget } from "./NotesWidget";
import * as client from "../api/client";

describe("NotesWidget", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("searches for notes and renders matches", async () => {
    vi.spyOn(client, "searchNotes").mockResolvedValue([
      { path: "project-ideas.md", title: "Project Ideas", excerpt: "Jarvis OS should eventually search my notes.", line_number: 5 },
    ]);

    render(<NotesWidget />);
    fireEvent.change(screen.getByLabelText("Search notes"), { target: { value: "jarvis" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => {
      expect(screen.getByText("Project Ideas")).toBeInTheDocument();
    });
    expect(client.searchNotes).toHaveBeenCalledWith("jarvis");
  });

  it("expands a match to show full note content on click", async () => {
    vi.spyOn(client, "searchNotes").mockResolvedValue([
      { path: "project-ideas.md", title: "Project Ideas", excerpt: "excerpt text", line_number: 5 },
    ]);
    vi.spyOn(client, "fetchNoteContent").mockResolvedValue("# Project Ideas\n\nFull content here.");

    render(<NotesWidget />);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => {
      expect(screen.getByText("Project Ideas")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Project Ideas" }));

    await waitFor(() => {
      expect(screen.getByTestId("note-content")).toHaveTextContent("Full content here.");
    });
    expect(client.fetchNoteContent).toHaveBeenCalledWith("project-ideas.md");
  });

  it("shows an error message when search fails", async () => {
    vi.spyOn(client, "searchNotes").mockRejectedValue(new Error("boom"));

    render(<NotesWidget />);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => {
      expect(screen.getByTestId("notes-widget-error")).toHaveTextContent("boom");
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/widgets/NotesWidget.test.tsx`
Expected: FAIL — `Failed to resolve import "./NotesWidget"`

- [ ] **Step 3: Write minimal implementation**

Create `apps/desktop/src/widgets/NotesWidget.tsx`:

```typescript
import { useState } from "react";
import type { NoteMatch } from "../api/client";
import { fetchNoteContent, searchNotes } from "../api/client";

export function NotesWidget() {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<NoteMatch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expandedPath, setExpandedPath] = useState<string | null>(null);
  const [expandedContent, setExpandedContent] = useState<string | null>(null);

  const handleSearch = async () => {
    setError(null);
    try {
      const results = await searchNotes(query);
      setMatches(results);
      setExpandedPath(null);
      setExpandedContent(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleExpand = async (path: string) => {
    setError(null);
    try {
      const content = await fetchNoteContent(path);
      setExpandedPath(path);
      setExpandedContent(content);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="rounded-lg border border-gray-300 p-4">
      <h2 className="text-lg font-semibold mb-2">Notes</h2>
      <div className="flex gap-2 mb-2">
        <input
          aria-label="Search notes"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="border border-gray-300 rounded px-2 py-1 flex-1"
        />
        <button onClick={handleSearch} className="bg-blue-600 text-white rounded px-3 py-1">
          Search
        </button>
      </div>
      {error && (
        <p data-testid="notes-widget-error" className="text-sm text-red-600 mb-2">
          {error}
        </p>
      )}
      <ul>
        {matches.map((match) => (
          <li key={match.path} className="text-sm mb-1">
            <button onClick={() => handleExpand(match.path)} className="underline">
              {match.title}
            </button>
            <span> — {match.excerpt}</span>
            {expandedPath === match.path && (
              <pre data-testid="note-content" className="mt-1 text-xs bg-gray-100 p-2 rounded whitespace-pre-wrap">
                {expandedContent ?? "Could not load note content."}
              </pre>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/widgets/NotesWidget.test.tsx`
Expected: PASS (3 tests)

Then run the full frontend suite: `cd apps/desktop && npx vitest run`
Expected: all pass, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/widgets/NotesWidget.tsx apps/desktop/src/widgets/NotesWidget.test.tsx
git commit -m "feat(desktop): add NotesWidget"
```

---

### Task 6: Widget registry — add `notes`; App.tsx guard filter (Polish item 2)

**Files:**
- Modify: `apps/desktop/src/widgets/registry.ts`
- Modify: `apps/desktop/src/App.tsx`
- Modify: `apps/desktop/src/App.test.tsx`

**Interfaces:**
- Consumes: `NotesWidget` from Task 5.
- Produces: `WidgetId` now includes `"notes"`; `WIDGET_REGISTRY`/`ALL_WIDGET_IDS` include it; both `App.tsx`'s dashboard render list and `CustomizePanel`'s initial order filter out unknown widget ids.

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

const defaultConfig = {
  widget_order: ["skills", "voice", "automations", "tasks", "notes"],
  hidden_widgets: [],
};

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

  it("renders all 5 widgets in the configured order by default", async () => {
    mockBaseFetches();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });
    expect(screen.getByText("Voice")).toBeInTheDocument();
    expect(screen.getByText("Automations")).toBeInTheDocument();
    expect(screen.getByText("Claude Code Tasks")).toBeInTheDocument();
    expect(screen.getByText("Notes")).toBeInTheDocument();
  });

  it("hides a widget listed in hidden_widgets", async () => {
    vi.spyOn(client, "fetchDashboardConfig").mockResolvedValue({
      widget_order: ["skills", "voice", "automations", "tasks", "notes"],
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

  it("ignores an unknown widget id present in a stale saved config", async () => {
    vi.spyOn(client, "fetchDashboardConfig").mockResolvedValue({
      widget_order: ["skills", "voice", "automations", "tasks", "bogus-old-widget"],
      hidden_widgets: [],
    });
    vi.spyOn(client, "fetchSkills").mockResolvedValue([]);
    vi.spyOn(client, "fetchAutomations").mockResolvedValue([]);
    vi.spyOn(client, "fetchAutomationRuns").mockResolvedValue([]);
    vi.spyOn(client, "fetchTasks").mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });
    expect(screen.getByText("Claude Code Tasks")).toBeInTheDocument();
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
      widget_order: ["skills", "voice", "automations", "tasks", "notes"],
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
        widget_order: ["skills", "voice", "automations", "tasks", "notes"],
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
Expected: FAIL — "Notes" heading not found (registry doesn't have a `notes` entry yet), and the "ignores an unknown widget id" test fails because there's no guard filter yet (attempting to render `WIDGET_REGISTRY["bogus-old-widget"]` throws, since it's `undefined`).

- [ ] **Step 3: Write minimal implementation**

Replace the full contents of `apps/desktop/src/widgets/registry.ts`:

```typescript
import type { ComponentType } from "react";
import { AutomationsWidget } from "./AutomationsWidget";
import { NotesWidget } from "./NotesWidget";
import { SkillsWidget } from "./SkillsWidget";
import { TasksWidget } from "./TasksWidget";
import { VoiceWidget } from "./VoiceWidget";

export type WidgetId = "skills" | "voice" | "automations" | "tasks" | "notes";

export const WIDGET_REGISTRY: Record<WidgetId, { label: string; component: ComponentType }> = {
  skills: { label: "Skills", component: SkillsWidget },
  voice: { label: "Voice", component: VoiceWidget },
  automations: { label: "Automations", component: AutomationsWidget },
  tasks: { label: "Claude Code Tasks", component: TasksWidget },
  notes: { label: "Notes", component: NotesWidget },
};

export const ALL_WIDGET_IDS: WidgetId[] = ["skills", "voice", "automations", "tasks", "notes"];
```

In `apps/desktop/src/App.tsx`, change the `CustomizePanel` function's first line of state:

```typescript
  const [order, setOrder] = useState<WidgetId[]>(config.widget_order as WidgetId[]);
```

to:

```typescript
  const [order, setOrder] = useState<WidgetId[]>(
    (config.widget_order as WidgetId[]).filter((id) => id in WIDGET_REGISTRY)
  );
```

And change the `App` function's `visibleOrderedWidgets` computation:

```typescript
  const visibleOrderedWidgets: WidgetId[] = config
    ? (config.widget_order as WidgetId[]).filter((id) => !config.hidden_widgets.includes(id))
    : [];
```

to:

```typescript
  const visibleOrderedWidgets: WidgetId[] = config
    ? (config.widget_order as WidgetId[])
        .filter((id) => id in WIDGET_REGISTRY)
        .filter((id) => !config.hidden_widgets.includes(id))
    : [];
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/App.test.tsx`
Expected: PASS (6 tests: 5 existing + 1 new)

Then run the full frontend suite: `cd apps/desktop && npx vitest run`
Expected: all pass, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/widgets/registry.ts apps/desktop/src/App.tsx apps/desktop/src/App.test.tsx
git commit -m "feat(desktop): add notes widget to registry, guard against unknown widget ids"
```

---

### Task 7: `useEventToasts` hook + `ToastContainer`

**Files:**
- Create: `apps/desktop/src/notifications/useEventToasts.ts`
- Create: `apps/desktop/src/notifications/ToastContainer.tsx`
- Test: `apps/desktop/src/notifications/useEventToasts.test.ts`
- Test: `apps/desktop/src/notifications/ToastContainer.test.tsx`

**Interfaces:**
- Produces: `interface Toast { id: string; message: string; kind: "success" | "error"; }`, `function useEventToasts(): Toast[]`, `function ToastContainer({ toasts }: { toasts: Toast[] })`.

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/src/notifications/useEventToasts.test.ts`:

```typescript
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useEventToasts } from "./useEventToasts";

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  constructor(_url: string) {}
  close() {}
}

let currentFakeSocket: FakeWebSocket;

describe("useEventToasts", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "WebSocket",
      class extends FakeWebSocket {
        constructor(url: string) {
          super(url);
          currentFakeSocket = this;
        }
      }
    );
  });

  it("adds a success toast when an automation_run completed event arrives", async () => {
    const { result } = renderHook(() => useEventToasts());

    act(() => {
      currentFakeSocket.onmessage?.({
        data: JSON.stringify({ type: "automation_run", stage: "completed", run_id: "run-1", automation_id: "ask_digest" }),
      });
    });

    await waitFor(() => {
      expect(result.current).toHaveLength(1);
    });
    expect(result.current[0].kind).toBe("success");
    expect(result.current[0].message).toContain("ask_digest");
  });

  it("adds an error toast when a claude_code_task failed event arrives", async () => {
    const { result } = renderHook(() => useEventToasts());

    act(() => {
      currentFakeSocket.onmessage?.({
        data: JSON.stringify({ type: "claude_code_task", stage: "failed", task_id: "task-1" }),
      });
    });

    await waitFor(() => {
      expect(result.current).toHaveLength(1);
    });
    expect(result.current[0].kind).toBe("error");
  });

  it("ignores events that are not a completion/failure of a tracked type", () => {
    const { result } = renderHook(() => useEventToasts());

    act(() => {
      currentFakeSocket.onmessage?.({
        data: JSON.stringify({ type: "automation_run", stage: "started", run_id: "run-1", automation_id: "ask_digest" }),
      });
    });

    expect(result.current).toHaveLength(0);
  });
});
```

Create `apps/desktop/src/notifications/ToastContainer.test.tsx`:

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToastContainer } from "./ToastContainer";

describe("ToastContainer", () => {
  it("renders nothing when there are no toasts", () => {
    const { container } = render(<ToastContainer toasts={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders each toast's message", () => {
    render(
      <ToastContainer
        toasts={[
          { id: "1", message: "Automation completed.", kind: "success" },
          { id: "2", message: "Task failed.", kind: "error" },
        ]}
      />
    );

    expect(screen.getByText("Automation completed.")).toBeInTheDocument();
    expect(screen.getByText("Task failed.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/notifications/`
Expected: FAIL — `Failed to resolve import "./useEventToasts"` / `"./ToastContainer"`

- [ ] **Step 3: Write minimal implementation**

Create `apps/desktop/src/notifications/useEventToasts.ts`:

```typescript
import { useEffect, useState } from "react";

export interface Toast {
  id: string;
  message: string;
  kind: "success" | "error";
}

interface WSEvent {
  type: string;
  stage?: string;
  run_id?: string;
  automation_id?: string;
  task_id?: string;
}

const WS_URL = "ws://127.0.0.1:8420/ws";
const TOAST_DURATION_MS = 6000;

function messageForEvent(data: WSEvent): Toast | null {
  if (data.type === "automation_run" && (data.stage === "completed" || data.stage === "failed")) {
    return {
      id: `${data.run_id}-${data.stage}`,
      message:
        data.stage === "completed"
          ? `Automation "${data.automation_id}" completed.`
          : `Automation "${data.automation_id}" failed.`,
      kind: data.stage === "completed" ? "success" : "error",
    };
  }
  if (data.type === "claude_code_task" && (data.stage === "completed" || data.stage === "failed")) {
    return {
      id: `${data.task_id}-${data.stage}`,
      message: data.stage === "completed" ? `Task ${data.task_id} completed.` : `Task ${data.task_id} failed.`,
      kind: data.stage === "completed" ? "success" : "error",
    };
  }
  return null;
}

export function useEventToasts(): Toast[] {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    ws.onmessage = (event) => {
      const data: WSEvent = JSON.parse(event.data);
      const toast = messageForEvent(data);
      if (!toast) return;
      setToasts((prev) => [...prev, toast]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== toast.id));
      }, TOAST_DURATION_MS);
    };
    return () => ws.close();
  }, []);

  return toasts;
}
```

Create `apps/desktop/src/notifications/ToastContainer.tsx`:

```typescript
import type { Toast } from "./useEventToasts";

export function ToastContainer({ toasts }: { toasts: Toast[] }) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 flex flex-col gap-2 z-50">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          data-testid="toast"
          className={
            toast.kind === "success"
              ? "bg-green-600 text-white rounded px-4 py-2 shadow"
              : "bg-red-600 text-white rounded px-4 py-2 shadow"
          }
        >
          {toast.message}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/notifications/`
Expected: PASS (5 tests)

Then run the full frontend suite: `cd apps/desktop && npx vitest run`
Expected: all pass, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/notifications/
git commit -m "feat(desktop): add useEventToasts hook and ToastContainer"
```

---

### Task 8: Wire toasts into `App.tsx`

**Files:**
- Modify: `apps/desktop/src/App.tsx`
- Modify: `apps/desktop/src/App.test.tsx`

**Interfaces:**
- Consumes: `useEventToasts`/`ToastContainer` from Task 7.

- [ ] **Step 1: Write the failing test**

Replace the full contents of `apps/desktop/src/App.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, render, screen, fireEvent, waitFor, cleanup, within } from "@testing-library/react";
import App from "./App";
import * as client from "./api/client";

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  static instances: FakeWebSocket[] = [];
  constructor(_url: string) {
    FakeWebSocket.instances.push(this);
  }
  close() {}
}

const defaultConfig = {
  widget_order: ["skills", "voice", "automations", "tasks", "notes"],
  hidden_widgets: [],
};

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
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    cleanup();
  });

  it("renders all 5 widgets in the configured order by default", async () => {
    mockBaseFetches();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });
    expect(screen.getByText("Voice")).toBeInTheDocument();
    expect(screen.getByText("Automations")).toBeInTheDocument();
    expect(screen.getByText("Claude Code Tasks")).toBeInTheDocument();
    expect(screen.getByText("Notes")).toBeInTheDocument();
  });

  it("hides a widget listed in hidden_widgets", async () => {
    vi.spyOn(client, "fetchDashboardConfig").mockResolvedValue({
      widget_order: ["skills", "voice", "automations", "tasks", "notes"],
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

  it("ignores an unknown widget id present in a stale saved config", async () => {
    vi.spyOn(client, "fetchDashboardConfig").mockResolvedValue({
      widget_order: ["skills", "voice", "automations", "tasks", "bogus-old-widget"],
      hidden_widgets: [],
    });
    vi.spyOn(client, "fetchSkills").mockResolvedValue([]);
    vi.spyOn(client, "fetchAutomations").mockResolvedValue([]);
    vi.spyOn(client, "fetchAutomationRuns").mockResolvedValue([]);
    vi.spyOn(client, "fetchTasks").mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });
    expect(screen.getByText("Claude Code Tasks")).toBeInTheDocument();
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
      widget_order: ["skills", "voice", "automations", "tasks", "notes"],
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
        widget_order: ["skills", "voice", "automations", "tasks", "notes"],
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

  it("shows a toast when an automation_run completed event arrives over the WebSocket", async () => {
    mockBaseFetches();

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });

    act(() => {
      FakeWebSocket.instances.forEach((ws) =>
        ws.onmessage?.({
          data: JSON.stringify({ type: "automation_run", stage: "completed", run_id: "run-1", automation_id: "ask_digest" }),
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId("toast")).toHaveTextContent("ask_digest");
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/App.test.tsx`
Expected: the new "shows a toast" test FAILs (no toast is ever rendered since `App.tsx` doesn't call `useEventToasts`/`ToastContainer` yet); all other tests still pass.

- [ ] **Step 3: Write minimal implementation**

In `apps/desktop/src/App.tsx`, add these imports (after the existing `import type { WidgetId } from "./widgets/registry";` line):

```typescript
import { useEventToasts } from "./notifications/useEventToasts";
import { ToastContainer } from "./notifications/ToastContainer";
```

In the `App` function, add this line right after `const [customizing, setCustomizing] = useState(false);`:

```typescript
  const toasts = useEventToasts();
```

And add `<ToastContainer toasts={toasts} />` as the first child inside the `<main>` element (right after the opening `<main className="p-6 max-w-2xl mx-auto">` tag, before the `<div className="flex items-center justify-between mb-4">` line).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/App.test.tsx`
Expected: PASS (7 tests: 6 from Task 6 + 1 new)

Then run the full frontend suite: `cd apps/desktop && npx vitest run`
Expected: all pass, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/App.tsx apps/desktop/src/App.test.tsx
git commit -m "feat(desktop): wire toast notifications into the dashboard shell"
```

---

### Task 9: Full-suite verification and manual smoke check

**Files:** None created or modified — verification only.

**Interfaces:** None — consumes everything from Tasks 1-8.

- [ ] **Step 1: Run the full backend suite**

Run: `cd apps/core && .venv/bin/python -m pytest -q`
Expected: all tests pass, 0 failed.

- [ ] **Step 2: Run the full frontend suite**

Run: `cd apps/desktop && npx vitest run`
Expected: all tests pass, 0 failed.

- [ ] **Step 3: Manual smoke check against a live backend**

Start the backend from `apps/core`: `.venv/bin/uvicorn core.app:create_app --factory --port 8420 &` and wait ~2s, then:

```bash
curl -s http://127.0.0.1:8420/skills | python3 -c "import sys, json; print([s['id'] for s in json.load(sys.stdin)])"
```

Expected: the list includes `"read_note"` alongside the existing skills.

```bash
curl -s -X POST http://127.0.0.1:8420/skills/read_note/invoke -H "Content-Type: application/json" -d '{"inputs": {"path": "project-ideas.md"}}'
```

Expected: a response containing the full content of the fixture note (this runs against whatever `knowledge_vault_dir` resolves to in the running app — the default fixture vault, same as Milestone 8's manual check).

```bash
curl -s http://127.0.0.1:8420/dashboard/config
```

Expected: `widget_order` includes `"notes"` if this is a fresh dev DB (a pre-existing dev DB from Milestone 7/8 manual testing may already have a saved 4-widget row from before this milestone — that's fine, it's not a regression, just confirm the endpoint responds successfully either way).

Stop the backend: `kill %1` (or find and kill the uvicorn process by port if job control isn't available).

- [ ] **Step 4: Update the progress ledger**

Append to `.superpowers/sdd/progress.md` in this worktree:

```
Task 9: complete (verification only, no commit; full backend suite green, full frontend suite green, read_note manually verified end-to-end against a live backend, /dashboard/config confirmed responding)

## All tasks complete. Ready for final whole-branch review.
```

No commit for this task (verification-only, matching the established pattern from Milestones 6-8).
