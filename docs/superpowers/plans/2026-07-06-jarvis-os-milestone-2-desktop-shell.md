# Jarvis OS Milestone 2: Desktop Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Tauri + React desktop shell that discovers skills from the running Milestone 1 backend, renders an input form for each skill from its manifest's `input_schema`, invokes it, and shows the result — proving the skill contract's UI leg end-to-end.

**Architecture:** A Tauri 2 + React + TypeScript + Vite app (`apps/desktop/`) with three layers: `api/client.ts` (typed `fetch` wrapper against the Milestone 1 backend), `components/SkillForm.tsx` (renders one skill's fields + invoke button + result/error), and `App.tsx` (fetches the skill list and renders a `SkillForm` per manifest). The backend gets one addition — CORS middleware — since this is its first cross-origin caller.

**Tech Stack:** Tauri 2, React 18, TypeScript, Vite, Tailwind CSS 4 (via `@tailwindcss/vite`), Vitest + React Testing Library + jsdom for frontend tests; Python/FastAPI (existing, from Milestone 1) for the one backend change.

## Global Constraints

- macOS only.
- The desktop app lives at `apps/desktop/` inside the `jarvis-os` repo.
- The desktop app assumes the Milestone 1 backend is already running at `http://127.0.0.1:8420` (started manually via `python3 orchestrator.py`). No sidecar process management in this milestone.
- No WebSocket-driven live status in the UI this milestone — invocation results come from the plain `POST /skills/{id}/invoke` REST response only.
- Every `input_schema` property is rendered as a plain text input. No general JSON-Schema-to-form renderer.
- No visual/theming polish beyond a working Tailwind setup — "premium" UI design is a later milestone.

---

### Task 1: Rust Toolchain & Tauri Scaffold

**Files:**
- Create: `apps/desktop/` (entire directory tree, via the Tauri scaffolding tool)

**Interfaces:**
- Produces: a runnable Tauri dev shell (`npm run tauri dev` from `apps/desktop/`) serving a default React page, which later tasks will replace piece by piece.

- [ ] **Step 1: Install the Rust toolchain (if not already present)**

Run: `which cargo rustc`
If both are found, skip to Step 2. Otherwise install Rust non-interactively:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
```

Run: `cargo --version && rustc --version`
Expected: both print version numbers with no error.

- [ ] **Step 2: Scaffold the Tauri + React + TypeScript app**

From the `jarvis-os` repo root, run:

```bash
cd apps
npm create tauri-app@latest
```

This is interactive. Answer the prompts as follows (the exact wording may vary slightly by tool version — answer the closest matching option):
- Project name: `desktop`
- Identifier (reverse-domain): `com.jarvisos.desktop`
- Choose which language to use for your frontend: **TypeScript / JavaScript**
- Choose your package manager: **npm**
- Choose your UI template: **React**
- Choose your UI flavor: **TypeScript**

This creates `apps/desktop/` with a `src/` (React+Vite frontend) and `src-tauri/` (Rust shell) subtree.

- [ ] **Step 3: Install frontend dependencies and verify the dev shell runs**

```bash
cd apps/desktop
npm install
```

Expected: installs with no errors.

Start the dev shell in the background to verify it builds, then stop it:

```bash
nohup npm run tauri dev > /tmp/jarvis-desktop-dev-smoke.log 2>&1 &
DEV_PID=$!
sleep 20
cat /tmp/jarvis-desktop-dev-smoke.log | tail -30
kill $DEV_PID 2>/dev/null
pkill -f "vite" 2>/dev/null
```

Expected: the log shows the Vite dev server starting (e.g. "VITE ... ready in ... ms" and a Local URL) and no Rust compile errors. The first run compiles the Rust shell and can take a minute or two — that's expected, not a failure. If the window fails to open because there's no display attached to this shell session, that's fine; what matters is no build/compile errors in the log.

- [ ] **Step 4: Commit the scaffold**

```bash
cd "$(git rev-parse --show-toplevel)"
git add apps/desktop
git commit -m "feat(desktop): scaffold Tauri + React + TypeScript app"
```

---

### Task 2: Tailwind CSS & Frontend Test Tooling

**Files:**
- Modify: `apps/desktop/vite.config.ts`
- Create: `apps/desktop/src/styles.css`
- Modify: `apps/desktop/src/main.tsx`
- Create: `apps/desktop/src/test/setup.ts`
- Modify: `apps/desktop/package.json` (add a `test` script)
- Test: `apps/desktop/src/App.test.tsx` (a placeholder smoke test proving Vitest + RTL work; later tasks replace this file's contents)

**Interfaces:**
- Consumes: the scaffold from Task 1.
- Produces: a working `npm test` command (Vitest) and Tailwind classes available anywhere in `src/`, both of which every later frontend task relies on.

- [ ] **Step 1: Install Tailwind and the frontend test toolchain**

From `apps/desktop/`:

```bash
npm install tailwindcss @tailwindcss/vite
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

Expected: installs with no errors.

- [ ] **Step 2: Wire Tailwind into Vite**

Open `apps/desktop/vite.config.ts`. It was generated by the Tauri scaffold and already contains Tauri-specific settings (a `server` block with a fixed port/host, `clearScreen: false`, etc.) — do not remove any of that. Add exactly two things to the existing file:

1. Add this import near the top, alongside the existing `react` plugin import:
```typescript
import tailwindcss from "@tailwindcss/vite";
```

2. Add `tailwindcss()` to the existing `plugins` array, alongside the existing `react()` entry, so it reads (adjust to match the existing array's exact current entries, just adding this one):
```typescript
  plugins: [react(), tailwindcss()],
```

- [ ] **Step 3: Create the global stylesheet and import it**

`apps/desktop/src/styles.css`:
```css
@import "tailwindcss";
```

Open `apps/desktop/src/main.tsx` and add this as the very first import line (before any other imports):
```typescript
import "./styles.css";
```

- [ ] **Step 4: Add the Vitest test environment config**

Open `apps/desktop/vite.config.ts` again and add a `test` block to the `defineConfig({...})` object, alongside the existing `plugins` and `server` keys (do not remove those):
```typescript
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
```

`apps/desktop/src/test/setup.ts`:
```typescript
import "@testing-library/jest-dom";
```

- [ ] **Step 5: Add the test script**

Open `apps/desktop/package.json` and add this entry to the `"scripts"` object:
```json
    "test": "vitest run"
```

- [ ] **Step 6: Write a placeholder test proving the toolchain works**

`apps/desktop/src/App.test.tsx`:
```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";

describe("App", () => {
  it("renders without crashing", () => {
    render(<App />);
    expect(screen.getByText(/tauri|vite|react/i)).toBeInTheDocument();
  });
});
```

This test targets the scaffold's default placeholder page (which mentions Tauri/Vite/React) — it exists only to prove Vitest + RTL + jsdom work end-to-end. Task 5 replaces this file's contents entirely once `App.tsx` is rewritten.

- [ ] **Step 7: Run the test**

Run (from `apps/desktop/`): `npm test`
Expected: 1 passed.

- [ ] **Step 8: Commit**

```bash
git add apps/desktop/vite.config.ts apps/desktop/src/styles.css apps/desktop/src/main.tsx apps/desktop/src/test/setup.ts apps/desktop/package.json apps/desktop/package-lock.json apps/desktop/src/App.test.tsx
git commit -m "feat(desktop): add Tailwind CSS and Vitest/RTL test tooling"
```

---

### Task 3: API Client

**Files:**
- Create: `apps/desktop/src/api/client.ts`
- Test: `apps/desktop/src/api/client.test.ts`

**Interfaces:**
- Produces: `SkillManifest` type; `fetchSkills(): Promise<SkillManifest[]>`; `invokeSkill(skillId: string, inputs: Record<string, string>): Promise<{ outputs: Record<string, unknown> }>` — both used by `SkillForm` (Task 4) and `App` (Task 5).

- [ ] **Step 1: Write the failing tests**

`apps/desktop/src/api/client.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchSkills, invokeSkill } from "./client";

describe("fetchSkills", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed skill manifests on success", async () => {
    const mockSkills = [
      {
        id: "echo",
        name: "Echo",
        description: "Repeats back text.",
        input_schema: {
          type: "object",
          properties: { text: { type: "string" } },
          required: ["text"],
        },
        output_schema: { type: "object", properties: { text: { type: "string" } } },
        voice_invokable: true,
        ui_component: null,
      },
    ];
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockSkills,
    } as Response);

    const result = await fetchSkills();

    expect(result).toEqual(mockSkills);
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8420/skills");
  });

  it("throws when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    } as Response);

    await expect(fetchSkills()).rejects.toThrow("Failed to fetch skills: 500");
  });
});

describe("invokeSkill", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns outputs on success", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ outputs: { text: "hello" } }),
    } as Response);

    const result = await invokeSkill("echo", { text: "hello" });

    expect(result).toEqual({ outputs: { text: "hello" } });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8420/skills/echo/invoke",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inputs: { text: "hello" } }),
      }
    );
  });

  it("throws with status and body when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Unknown skill: nope" }),
    } as Response);

    await expect(invokeSkill("nope", {})).rejects.toThrow(
      'Failed to invoke skill nope: 404 {"detail":"Unknown skill: nope"}'
    );
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `apps/desktop/`): `npm test -- src/api/client.test.ts`
Expected: FAIL — `Cannot find module './client'` (or similar).

- [ ] **Step 3: Write the client**

`apps/desktop/src/api/client.ts`:
```typescript
export interface SkillManifest {
  id: string;
  name: string;
  description: string;
  input_schema: {
    type?: string;
    properties?: Record<string, { type?: string }>;
    required?: string[];
  };
  output_schema: {
    type?: string;
    properties?: Record<string, { type?: string }>;
  };
  voice_invokable: boolean;
  ui_component: string | null;
}

const BASE_URL = "http://127.0.0.1:8420";

export async function fetchSkills(): Promise<SkillManifest[]> {
  const response = await fetch(`${BASE_URL}/skills`);
  if (!response.ok) {
    throw new Error(`Failed to fetch skills: ${response.status}`);
  }
  return response.json();
}

export async function invokeSkill(
  skillId: string,
  inputs: Record<string, string>
): Promise<{ outputs: Record<string, unknown> }> {
  const response = await fetch(`${BASE_URL}/skills/${skillId}/invoke`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inputs }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      `Failed to invoke skill ${skillId}: ${response.status} ${JSON.stringify(body)}`
    );
  }
  return response.json();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- src/api/client.test.ts`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/api/client.ts apps/desktop/src/api/client.test.ts
git commit -m "feat(desktop): add typed API client for skills endpoints"
```

---

### Task 4: SkillForm Component

**Files:**
- Create: `apps/desktop/src/components/SkillForm.tsx`
- Test: `apps/desktop/src/components/SkillForm.test.tsx`

**Interfaces:**
- Consumes: `SkillManifest` type, `invokeSkill` (Task 3).
- Produces: `SkillForm({ skill: SkillManifest })` React component, used by `App` (Task 5).

- [ ] **Step 1: Write the failing tests**

`apps/desktop/src/components/SkillForm.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SkillForm } from "./SkillForm";
import * as client from "../api/client";
import type { SkillManifest } from "../api/client";

const echoManifest: SkillManifest = {
  id: "echo",
  name: "Echo",
  description: "Repeats back text.",
  input_schema: {
    type: "object",
    properties: { text: { type: "string" } },
    required: ["text"],
  },
  output_schema: { type: "object", properties: { text: { type: "string" } } },
  voice_invokable: true,
  ui_component: null,
};

describe("SkillForm", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders one input per input_schema property and the invoke button", () => {
    render(<SkillForm skill={echoManifest} />);

    expect(screen.getByText("Echo")).toBeInTheDocument();
    expect(screen.getByLabelText("text")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Invoke" })).toBeInTheDocument();
  });

  it("shows the result after a successful invoke", async () => {
    vi.spyOn(client, "invokeSkill").mockResolvedValue({ outputs: { text: "hi" } });

    render(<SkillForm skill={echoManifest} />);
    fireEvent.change(screen.getByLabelText("text"), { target: { value: "hi" } });
    fireEvent.click(screen.getByRole("button", { name: "Invoke" }));

    await waitFor(() => {
      expect(screen.getByTestId("skill-result")).toHaveTextContent('"text": "hi"');
    });
    expect(client.invokeSkill).toHaveBeenCalledWith("echo", { text: "hi" });
  });

  it("shows an error message when invoke fails", async () => {
    vi.spyOn(client, "invokeSkill").mockRejectedValue(new Error("boom"));

    render(<SkillForm skill={echoManifest} />);
    fireEvent.click(screen.getByRole("button", { name: "Invoke" }));

    await waitFor(() => {
      expect(screen.getByTestId("skill-error")).toHaveTextContent("boom");
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- src/components/SkillForm.test.tsx`
Expected: FAIL — `Cannot find module './SkillForm'`.

- [ ] **Step 3: Write the component**

`apps/desktop/src/components/SkillForm.tsx`:
```tsx
import { useState } from "react";
import type { SkillManifest } from "../api/client";
import { invokeSkill } from "../api/client";

interface SkillFormProps {
  skill: SkillManifest;
}

export function SkillForm({ skill }: SkillFormProps) {
  const fieldNames = Object.keys(skill.input_schema.properties ?? {});
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fieldNames.map((name) => [name, ""]))
  );
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (name: string, value: string) => {
    setValues((prev) => ({ ...prev, [name]: value }));
  };

  const handleInvoke = async () => {
    setError(null);
    setResult(null);
    try {
      const response = await invokeSkill(skill.id, values);
      setResult(response.outputs);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="rounded-lg border border-gray-300 p-4 mb-4">
      <h2 className="text-lg font-semibold">{skill.name}</h2>
      <p className="text-sm text-gray-600 mb-2">{skill.description}</p>
      {fieldNames.map((name) => (
        <input
          key={name}
          aria-label={name}
          value={values[name]}
          onChange={(e) => handleChange(name, e.target.value)}
          className="border border-gray-300 rounded px-2 py-1 mr-2 mb-2"
        />
      ))}
      <button onClick={handleInvoke} className="bg-blue-600 text-white rounded px-3 py-1">
        Invoke
      </button>
      {result && (
        <pre data-testid="skill-result" className="mt-2 text-sm bg-gray-100 p-2 rounded">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
      {error && (
        <p data-testid="skill-error" className="mt-2 text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- src/components/SkillForm.test.tsx`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/components/SkillForm.tsx apps/desktop/src/components/SkillForm.test.tsx
git commit -m "feat(desktop): add SkillForm component"
```

---

### Task 5: App Wiring

**Files:**
- Modify: `apps/desktop/src/App.tsx` (replace entire contents)
- Modify: `apps/desktop/src/App.test.tsx` (replace entire contents — Task 2's placeholder test is fully superseded)

**Interfaces:**
- Consumes: `fetchSkills` (Task 3), `SkillForm` (Task 4).
- Produces: the app's root component, rendering one `SkillForm` per fetched skill.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `apps/desktop/src/App.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import * as client from "./api/client";
import type { SkillManifest } from "./api/client";

const echoManifest: SkillManifest = {
  id: "echo",
  name: "Echo",
  description: "Repeats back text.",
  input_schema: {
    type: "object",
    properties: { text: { type: "string" } },
    required: ["text"],
  },
  output_schema: { type: "object", properties: { text: { type: "string" } } },
  voice_invokable: true,
  ui_component: null,
};

describe("App", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders a SkillForm for each fetched skill", async () => {
    vi.spyOn(client, "fetchSkills").mockResolvedValue([echoManifest]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Echo")).toBeInTheDocument();
    });
  });

  it("shows an error if fetching skills fails", async () => {
    vi.spyOn(client, "fetchSkills").mockRejectedValue(new Error("network down"));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("app-error")).toHaveTextContent("network down");
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- src/App.test.tsx`
Expected: FAIL — the current `App.tsx` (scaffold placeholder) doesn't render "Echo" or an `app-error` test id.

- [ ] **Step 3: Rewrite App.tsx**

Replace the entire contents of `apps/desktop/src/App.tsx`:
```tsx
import { useEffect, useState } from "react";
import type { SkillManifest } from "./api/client";
import { fetchSkills } from "./api/client";
import { SkillForm } from "./components/SkillForm";

function App() {
  const [skills, setSkills] = useState<SkillManifest[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSkills()
      .then(setSkills)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  return (
    <main className="p-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Jarvis OS</h1>
      {error && (
        <p data-testid="app-error" className="text-red-600">
          {error}
        </p>
      )}
      {skills.map((skill) => (
        <SkillForm key={skill.id} skill={skill} />
      ))}
    </main>
  );
}

export default App;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- src/App.test.tsx`
Expected: 2 passed.

- [ ] **Step 5: Run the full frontend test suite**

Run: `npm test`
Expected: all tests pass (client: 4, SkillForm: 3, App: 2 — 9 total).

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src/App.tsx apps/desktop/src/App.test.tsx
git commit -m "feat(desktop): wire App to fetch and render skills"
```

---

### Task 6: Backend CORS Middleware

**Files:**
- Modify: `apps/core/core/app.py`
- Modify: `apps/core/tests/test_api.py`

**Interfaces:**
- Consumes: `create_app()` (Milestone 1, Task 8's version of `apps/core/core/app.py`).
- Produces: no new interface — this only changes response headers for cross-origin requests.

- [ ] **Step 1: Write the failing test**

Append this test to `apps/core/tests/test_api.py` (it uses the existing `_client(tmp_path, monkeypatch)` helper already defined in that file):
```python
def test_cors_allows_tauri_dev_origin(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/skills", headers={"Origin": "http://localhost:1420"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:1420"
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `apps/core/`): `.venv/bin/pytest tests/test_api.py::test_cors_allows_tauri_dev_origin -v`
Expected: FAIL — `KeyError: 'access-control-allow-origin'` (header absent).

- [ ] **Step 3: Add CORS middleware**

In `apps/core/core/app.py`, add this import alongside the existing FastAPI imports:
```python
from fastapi.middleware.cors import CORSMiddleware
```

Then, inside `create_app()`, immediately after the line `app = FastAPI(title="Jarvis OS Core")`, add:
```python
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:1420", "tauri://localhost"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_api.py::test_cors_allows_tauri_dev_origin -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/pytest -v`
Expected: 19 passed (the 18 from Milestone 1, plus this one).

- [ ] **Step 6: Commit**

```bash
git add apps/core/core/app.py apps/core/tests/test_api.py
git commit -m "feat(core): allow CORS from the Tauri dev origin"
```

---

### Task 7: End-to-End Manual Smoke Test

**Files:** None (verification only).

**Interfaces:** None — this task exercises the full stack built across Tasks 1-6.

- [ ] **Step 1: Start the Milestone 1 backend**

```bash
cd apps/core
nohup .venv/bin/python3 main.py > /tmp/jarvis-backend-smoke.log 2>&1 &
BACKEND_PID=$!
sleep 2
curl -s http://127.0.0.1:8420/skills
```
Expected: JSON array containing the `echo` skill manifest.

- [ ] **Step 2: Start the desktop app in dev mode**

```bash
cd apps/desktop
nohup npm run tauri dev > /tmp/jarvis-desktop-smoke.log 2>&1 &
DESKTOP_PID=$!
sleep 20
tail -30 /tmp/jarvis-desktop-smoke.log
```
Expected: no build/compile errors in the log; the Tauri window opens (if a display is attached) showing "Jarvis OS" with an Echo form (a "text" input and an "Invoke" button).

- [ ] **Step 3: Exercise the UI (if a display is attached to this environment)**

Type a value into the "text" field, click "Invoke", and confirm the result renders below the form as `{"text": "<the value you typed>"}`. If no display is attached to this environment (headless dev container), skip this manual UI check and instead confirm via Step 2's log output plus the automated test suites (Tasks 3-6) as evidence the wiring is correct; note this explicitly in your report.

- [ ] **Step 4: Stop both processes**

```bash
kill $DESKTOP_PID 2>/dev/null
kill $BACKEND_PID 2>/dev/null
pkill -f "vite" 2>/dev/null
pkill -f "apps/core/main.py" 2>/dev/null
```

- [ ] **Step 5: Run both full test suites one final time**

```bash
cd apps/core && .venv/bin/pytest -v
cd ../desktop && npm test
```
Expected: 19 passed (backend), 9 passed (frontend).

No commit for this task — it's verification only, nothing changes.
