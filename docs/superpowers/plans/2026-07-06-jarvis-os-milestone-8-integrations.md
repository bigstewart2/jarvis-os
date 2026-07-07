# Jarvis OS Milestone 8: Integrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `KnowledgeSource` protocol and a concrete `ObsidianVaultSource` implementation (local markdown-file search, no auth needed), exposed as a voice-invokable `search_notes` skill.

**Architecture:** `KnowledgeSource` is a `Protocol` at `core/providers/knowledge/base.py`, matching the existing `LLMProvider`/`STTProvider`/`TTSProvider` structure exactly. `ObsidianVaultSource` walks a configured vault directory, substring-matches markdown files, and returns path/title/excerpt/line_number per match. The `search_notes` skill wires this into the existing skill system with no new invocation path — it's a plain `run(inputs) -> outputs` skill like every other.

**Tech Stack:** Python 3.12, stdlib `pathlib` only (no new dependencies — this is local filesystem search, not a Google API integration).

## Global Constraints

- Google Calendar and Gmail integrations are explicitly OUT of scope for this milestone (deferred to Milestone 8b, which requires a live OAuth setup session with Stephen) — see the design spec's Scope Decision section.
- The `KnowledgeSource` protocol signature is exactly: `def search(self, query: str, limit: int = 10) -> list[NoteMatch]`, where `NoteMatch` is a `TypedDict` with keys `path: str`, `title: str`, `excerpt: str`, `line_number: int`.
- `ObsidianVaultSource` must never raise for: a missing vault directory (return `[]`), a file that fails to read/decode (skip that file, continue), or a path that resolves outside the vault root (skip it — defense against a malformed vault config).
- New config field: `knowledge_vault_dir: str = "tests/fixtures/vault"` on `Settings` (`core/config.py`), following the exact pattern of `skills_dir`/`automations_dir`.
- `search_notes` skill: `voice_invokable: true`, `input_schema: {"query": "string"}` (required), `output_schema: {"matches": "array"}`.
- No new Python dependencies.
- Backend tests follow the existing conventions: real-filesystem tests against a checked-in fixture vault (`apps/core/tests/fixtures/vault/`) for the provider, and the `monkeypatch.setitem(loaded.run.__globals__, ...)` pattern (established in `test_speak_skill.py`) for the skill-level test.

---

### Task 1: `KnowledgeSource` protocol + `ObsidianVaultSource` + fixture vault

**Files:**
- Create: `apps/core/core/providers/knowledge/__init__.py` (empty, matching `providers/stt/__init__.py`/`providers/llm/__init__.py`)
- Create: `apps/core/core/providers/knowledge/base.py`
- Create: `apps/core/core/providers/knowledge/obsidian.py`
- Create: `apps/core/tests/fixtures/vault/project-ideas.md`
- Create: `apps/core/tests/fixtures/vault/no-heading.md`
- Create: `apps/core/tests/fixtures/vault/subdir/nested-note.md`
- Test: `apps/core/tests/test_knowledge_obsidian.py`

**Interfaces:**
- Produces: `NoteMatch` (`TypedDict`: `path: str`, `title: str`, `excerpt: str`, `line_number: int`), `KnowledgeSource` (`Protocol` with `search(query: str, limit: int = 10) -> list[NoteMatch]`), `ObsidianVaultSource(vault_root: Path)` with a `.search(query, limit=10) -> list[NoteMatch]` method implementing that protocol.

- [ ] **Step 1: Create the fixture vault files**

Create `apps/core/tests/fixtures/vault/project-ideas.md`:

```markdown
# Project Ideas

Some notes about upcoming projects.

Jarvis OS should eventually search my notes.
This is a second mention of jarvis in the same file.
```

Create `apps/core/tests/fixtures/vault/no-heading.md`:

```markdown
Just a plain note with no heading.

Recipe: mix flour and water for dough.
```

Create `apps/core/tests/fixtures/vault/subdir/nested-note.md`:

```markdown
# Quarterly Review

Notes from the quarterly review meeting.
Action items go here.
```

- [ ] **Step 2: Write the failing test**

Create `apps/core/tests/test_knowledge_obsidian.py`:

```python
import shutil

from core.providers.knowledge.obsidian import ObsidianVaultSource

FIXTURE_VAULT = None  # set below after Path import to keep this block copy-pasteable


from pathlib import Path  # noqa: E402

FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"


def test_finds_match_with_correct_fields():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    matches = source.search("jarvis")

    assert len(matches) == 1
    assert matches[0]["path"] == "project-ideas.md"
    assert matches[0]["title"] == "Project Ideas"
    assert "jarvis" in matches[0]["excerpt"].lower()
    assert matches[0]["line_number"] == 5


def test_case_insensitive_matching():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    matches = source.search("RECIPE")

    assert len(matches) == 1
    assert matches[0]["path"] == "no-heading.md"
    assert matches[0]["title"] == "no-heading"


def test_respects_limit():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    matches = source.search("note", limit=2)

    assert len(matches) == 2


def test_no_matches_returns_empty_list():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    matches = source.search("zzzznomatchzzzz")

    assert matches == []


def test_missing_vault_directory_returns_empty_list(tmp_path):
    source = ObsidianVaultSource(tmp_path / "does-not-exist")

    matches = source.search("anything")

    assert matches == []


def test_skips_unreadable_file_without_failing_search(tmp_path):
    vault_copy = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault_copy)
    (vault_copy / "broken.md").write_bytes(b"\xff\xfe\x00\x01invalid utf-8 note bytes")

    source = ObsidianVaultSource(vault_copy)

    matches = source.search("note")

    assert all(m["path"] != "broken.md" for m in matches)
    assert len(matches) >= 1


def test_does_not_escape_vault_root(tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    secret_file = outside_dir / "secret.md"
    secret_file.write_text("# Secret\n\nThis contains the word targetphrase.\n")

    vault_copy = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault_copy)
    (vault_copy / "escape-link.md").symlink_to(secret_file)

    source = ObsidianVaultSource(vault_copy)

    matches = source.search("targetphrase")

    assert matches == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_knowledge_obsidian.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.providers.knowledge'`

- [ ] **Step 4: Write minimal implementation**

Create `apps/core/core/providers/knowledge/__init__.py` (empty file).

Create `apps/core/core/providers/knowledge/base.py`:

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
```

Create `apps/core/core/providers/knowledge/obsidian.py`:

```python
from pathlib import Path

from core.providers.knowledge.base import NoteMatch


def _build_excerpt(line: str, query_lower: str, max_len: int = 200) -> str:
    stripped = line.strip()
    if len(stripped) <= max_len:
        return stripped

    idx = stripped.lower().find(query_lower)
    if idx == -1:
        return stripped[:max_len]

    start = max(0, idx - max_len // 2)
    end = min(len(stripped), start + max_len)
    excerpt = stripped[start:end]
    if start > 0:
        excerpt = "…" + excerpt
    if end < len(stripped):
        excerpt = excerpt + "…"
    return excerpt


class ObsidianVaultSource:
    def __init__(self, vault_root: Path):
        self.vault_root = vault_root

    def search(self, query: str, limit: int = 10) -> list[NoteMatch]:
        if not self.vault_root.exists():
            return []

        resolved_root = self.vault_root.resolve()
        query_lower = query.lower()
        matches: list[NoteMatch] = []

        for path in sorted(self.vault_root.rglob("*.md")):
            resolved_path = path.resolve()
            if not resolved_path.is_relative_to(resolved_root):
                continue

            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            lines = text.splitlines()
            match_line_index = None
            for index, line in enumerate(lines):
                if query_lower in line.lower():
                    match_line_index = index
                    break
            if match_line_index is None:
                continue

            title = path.stem
            for line in lines:
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

            matches.append({
                "path": str(path.relative_to(self.vault_root)),
                "title": title,
                "excerpt": _build_excerpt(lines[match_line_index], query_lower),
                "line_number": match_line_index + 1,
            })
            if len(matches) >= limit:
                break

        return matches
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_knowledge_obsidian.py -v`
Expected: PASS (7 tests). If `test_finds_match_with_correct_fields`'s `line_number == 5` assertion fails, count the actual 1-indexed line of "Jarvis OS should eventually search my notes." in the fixture file you created (blank lines count) and adjust the assertion to match — the fixture content above is authoritative, the line number in this test is a description of what it should be if the fixture is exactly as written.

- [ ] **Step 6: Commit**

```bash
git add apps/core/core/providers/knowledge/ apps/core/tests/fixtures/vault/ apps/core/tests/test_knowledge_obsidian.py
git commit -m "feat(core): add KnowledgeSource protocol and ObsidianVaultSource"
```

---

### Task 2: `search_notes` skill

**Files:**
- Modify: `apps/core/core/config.py` (add `knowledge_vault_dir` field)
- Create: `apps/core/skills/search_notes/manifest.yaml`
- Create: `apps/core/skills/search_notes/skill.py`
- Test: `apps/core/tests/test_search_notes_skill.py`

**Interfaces:**
- Consumes: `ObsidianVaultSource` from Task 1 (`core.providers.knowledge.obsidian`).
- Produces: the `search_notes` skill, loadable by the existing `SkillRegistry`, `run({"query": str}) -> {"matches": list[dict]}`.

- [ ] **Step 1: Write the failing test**

Create `apps/core/tests/test_search_notes_skill.py`:

```python
from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"


def test_manifest_is_voice_invokable():
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)

    loaded = registry.get("search_notes")

    assert loaded is not None
    assert loaded.manifest.voice_invokable is True


def test_run_returns_matches_from_configured_vault(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("search_notes")

    class FakeSettings:
        knowledge_vault_dir = str(FIXTURE_VAULT)

    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: FakeSettings())

    result = loaded.run({"query": "jarvis"})

    assert len(result["matches"]) == 1
    assert result["matches"][0]["path"] == "project-ideas.md"
    assert result["matches"][0]["title"] == "Project Ideas"


def test_run_returns_empty_matches_for_no_hits(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)
    loaded = registry.get("search_notes")

    class FakeSettings:
        knowledge_vault_dir = str(FIXTURE_VAULT)

    monkeypatch.setitem(loaded.run.__globals__, "get_settings", lambda: FakeSettings())

    result = loaded.run({"query": "zzzznomatchzzzz"})

    assert result["matches"] == []
```

Note: `FakeSettings.knowledge_vault_dir` is set to the fixture vault's **absolute** path deliberately. In `pathlib`, `Path("anything") / "/an/absolute/path"` evaluates to just `/an/absolute/path` — joining an absolute path onto any base path discards the base and keeps the absolute path. This means `skill.py`'s `BASE_DIR / settings.knowledge_vault_dir` will resolve correctly to `FIXTURE_VAULT` regardless of what `BASE_DIR` is in the test process, so this test does not need to mock `BASE_DIR` at all.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_search_notes_skill.py -v`
Expected: FAIL — `loaded is None` (skill doesn't exist yet), or a manifest-loading error.

- [ ] **Step 3: Write minimal implementation**

In `apps/core/core/config.py`, add this field to the `Settings` class, immediately after the `automations_dir: str = "automations"` line:

```python
    knowledge_vault_dir: str = "tests/fixtures/vault"
```

Create `apps/core/skills/search_notes/manifest.yaml`:

```yaml
id: search_notes
name: Search Notes
description: Searches your Obsidian vault for notes matching a query and returns matching excerpts.
voice_invokable: true
input_schema:
  type: object
  properties:
    query:
      type: string
  required:
    - query
output_schema:
  type: object
  properties:
    matches:
      type: array
```

Create `apps/core/skills/search_notes/skill.py`:

```python
from pathlib import Path

from core.config import get_settings
from core.providers.knowledge.obsidian import ObsidianVaultSource

BASE_DIR = Path(__file__).resolve().parents[2]


def run(inputs: dict) -> dict:
    settings = get_settings()
    vault_root = BASE_DIR / settings.knowledge_vault_dir
    source = ObsidianVaultSource(vault_root)
    matches = source.search(inputs["query"])
    return {"matches": matches}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/core && .venv/bin/python -m pytest tests/test_search_notes_skill.py -v`
Expected: PASS (3 tests)

Then run the full backend suite to confirm nothing else broke:

Run: `cd apps/core && .venv/bin/python -m pytest -q`
Expected: all tests pass, 0 failed (adds this task's 3 tests plus Task 1's 7 tests to the existing ~178-test baseline)

- [ ] **Step 5: Commit**

```bash
git add apps/core/core/config.py apps/core/skills/search_notes/ apps/core/tests/test_search_notes_skill.py
git commit -m "feat(core): add search_notes skill"
```

---

### Task 3: Manual verification

**Files:** None created or modified — verification only, mirrors the manual smoke-test pattern from every prior milestone's final task.

**Interfaces:** None — consumes everything from Tasks 1-2 and confirms the whole system holds together against a real running backend.

- [ ] **Step 1: Run the full backend suite**

Run: `cd apps/core && .venv/bin/python -m pytest -q`
Expected: all tests pass, 0 failed

- [ ] **Step 2: Manual smoke check against a live backend**

Start the backend from `apps/core`: `.venv/bin/uvicorn core.app:create_app --factory --port 8420 &` and wait ~2s for startup, then:

```bash
curl -s http://127.0.0.1:8420/skills | python3 -c "import sys, json; print([s['id'] for s in json.load(sys.stdin)])"
```

Expected: the list includes `"search_notes"` alongside the existing `"ask"`, `"echo"`, `"speak"`, `"claude_code_task"`.

```bash
curl -s -X POST http://127.0.0.1:8420/skills/search_notes/invoke -H "Content-Type: application/json" -d '{"inputs": {"query": "jarvis"}}'
```

Expected: this searches whatever `knowledge_vault_dir` currently resolves to in the running app's actual working directory (the default `tests/fixtures/vault`, relative to `apps/core`, so the search runs against the checked-in fixture vault since no `.env` override is expected in this dev environment) — response should include a `matches` array with the `project-ideas.md` entry, proving the skill executes end-to-end through the real HTTP invocation path, not just in isolated unit tests.

Stop the backend: `kill %1` (or find and kill the uvicorn process by port if job control isn't available in the shell).

- [ ] **Step 3: Update the progress ledger**

Append to `.superpowers/sdd/progress.md` in this worktree:

```
Task 3: complete (verification only, no commit; full backend suite green, GET /skills confirms search_notes is registered, POST /skills/search_notes/invoke manually verified end-to-end against the real fixture vault via a live backend)

## All tasks complete. Ready for final whole-branch review.
```

No commit for this task (verification-only, matching the pattern from Milestones 6 and 7).
