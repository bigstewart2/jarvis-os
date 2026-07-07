# Jarvis OS Milestone 8: Integrations — Design

**Process note:** Authored in one pass, continuing Stephen's standing "keep working non-stop, don't wait for me" instruction from earlier tonight. Scoping decisions below are called out explicitly with rationale for later review.

## Scope Decision (the main call made here)

The master roadmap lists this milestone as "Integrations — Obsidian, Google Calendar, Gmail." Those are three genuinely independent subsystems, and two of them (Google Calendar, Gmail) require an OAuth app registration in Google Cloud Console, a configured consent screen, and a live browser-based consent flow — none of which can be done unattended. There's no way to responsibly build and prove a working Gmail/Calendar integration without Stephen present to click through Google's consent UI and hand over real client credentials.

**Decision: this milestone builds the `KnowledgeSource` protocol (the abstraction the master architecture doc named in Milestone 0) and one concrete implementation — Obsidian vault search — which needs no external auth at all, just a local directory of markdown files.** Google Calendar and Gmail become a follow-up milestone (call it 8b) that starts with Stephen setting up the Google Cloud OAuth app together with me, since that first step is inherently a human-in-the-loop action.

This mirrors Milestone 3's pattern exactly: M3 built the `LLMProvider` protocol and proved it against two real, swappable backends (Claude, Ollama) rather than trying to wire up every possible LLM provider at once. Same idea here — prove the `KnowledgeSource` abstraction holds with one real, fully-buildable implementation, and leave the roadmap line's remaining items to a follow-up now that the shape is proven.

**Vault path:** rather than guess at Stephen's real Obsidian vault location (which I can't verify from here, and got no reliable filesystem signal for), the vault root is a config value (`settings.knowledge_vault_dir`, following the exact pattern of `settings.skills_dir`/`settings.automations_dir` from earlier milestones). This milestone's own tests and proof step run against a small fixture vault checked into the repo (`apps/core/tests/fixtures/vault/`, a handful of real markdown files). Pointing it at Stephen's actual vault later is a one-line config change — no code change needed.

## Purpose

Add a `KnowledgeSource` protocol (structural interface, matching the `LLMProvider`/`STTProvider`/`TTSProvider` pattern) with one implementation, `ObsidianVaultSource`, that searches a directory of markdown files by substring/keyword match and returns matching notes' paths, titles (first `# heading` or filename), and matching excerpts. Expose it as a new skill, `search_notes`, so it's invokable from the UI, voice, and future automations exactly like every other skill.

## Non-Goals

- Google Calendar and Gmail integrations — deferred to Milestone 8b, which starts with a live OAuth setup session with Stephen (see Scope Decision above).
- Full-text semantic/embedding search. Plain substring/keyword matching only — this proves the `KnowledgeSource` abstraction and gives a genuinely useful "find my notes on X" skill without a vector DB dependency. Semantic search is a reasonable future upgrade behind the same protocol, not needed to prove the pattern.
- Writing to the vault (creating/editing notes). Read-only this milestone.
- Watching the vault for live changes (file-system watcher). Each search reads the current directory state fresh — sufficient for a personal, infrequently-searched vault; no caching/invalidation complexity needed.
- Obsidian-specific features (wikilinks `[[note]]` resolution, tags, backlinks, frontmatter parsing beyond what's needed for a title). This is markdown-file search that happens to point at an Obsidian vault, not an Obsidian API integration (Obsidian has no local API to integrate with anyway — vaults are just folders of `.md` files, which is exactly why this is buildable at all).

## `KnowledgeSource` Protocol

```python
from typing import Protocol

class NoteMatch(TypedDict):
    path: str        # relative to the vault root
    title: str        # first "# " heading in the file, or the filename stem if none
    excerpt: str       # ~200 chars of context around the first match, with the matched term
    line_number: int   # 1-indexed line where the match was found

class KnowledgeSource(Protocol):
    def search(self, query: str, limit: int = 10) -> list[NoteMatch]: ...
```

Lives at `apps/core/core/providers/knowledge/base.py`, matching the existing `providers/llm/`, `providers/stt/`, `providers/tts/` structure exactly (each has a `base.py` Protocol + a factory + one or more concrete implementations — confirmed by reading the existing `providers/` tree before writing this spec).

## `ObsidianVaultSource` Implementation

`apps/core/core/providers/knowledge/obsidian.py`:

- Constructor takes the vault root directory (a `Path`).
- `search(query, limit)`: case-insensitive substring match. Walks the vault directory for `*.md` files (using `Path.rglob("*.md")`), skips any path that resolves outside the vault root (defense against a maliciously crafted vault path config, and a straightforward `resolve()`-and-`is_relative_to()` check — cheap insurance, not because vault configs are an untrusted input in practice, but because "read arbitrary files from a path built from config" is exactly the kind of thing worth a boundary check even when the trust level is high, matching this project's existing caution around file paths e.g. Milestone 5's `working_dir` handling for Claude Code tasks). For each file, reads its content, finds the first line containing the query substring (case-insensitively), builds an excerpt centered on that line trimmed to ~200 chars, extracts a title (first line matching `^# ` if present, else the filename stem). Returns up to `limit` matches, files with no match excluded. Files that fail to read (permission error, binary garbage that isn't valid UTF-8) are skipped silently — a single bad file must not break search across the rest of the vault (same "one bad item doesn't take down the whole operation" invariant used for automation file loading in Milestone 6).
- No results found → empty list, not an error. An empty/missing vault directory → empty list, not an error (a fresh Jarvis OS install with no vault configured yet shouldn't crash on first search).

## `search_notes` Skill

`apps/core/skills/search_notes/manifest.yaml` + `skill.py`:

- `input_schema`: `{"query": "string"}` (required).
- `output_schema`: `{"matches": "array"}` — each entry shaped like `NoteMatch` above (as a JSON-serializable dict).
- `voice_invokable: true` — "find my notes about X" is exactly the kind of thing worth saying out loud, and it's a fast, read-only, side-effect-free operation, unlike `claude_code_task` (M5, deliberately excluded from voice).
- `run(inputs)`: resolves the configured `ObsidianVaultSource` from settings, calls `.search(inputs["query"])`, returns `{"matches": [...]}`.

## Configuration

`apps/core/core/config.py` gains `knowledge_vault_dir: str = "tests/fixtures/vault"` (a Settings field, following the exact pattern of `skills_dir`/`automations_dir`). The default points at this milestone's own fixture vault so a fresh checkout has a working, demonstrable skill out of the box; changing it to a real vault path is the one-line config change mentioned above. If the configured directory doesn't exist at all when the skill runs, `search_notes` returns `{"matches": []}` rather than raising — matching the "empty/missing vault → empty list" behavior in the provider itself, so there's exactly one behavior to test, not two.

## Fixture Vault

`apps/core/tests/fixtures/vault/` — 3-4 small real markdown files (e.g. a note with a `# Heading`, a note with no heading, a note with the search term appearing multiple times, a subdirectory with a nested note) checked into the repo, used by both the automated tests and the milestone's manual proof step. This is real test fixture data, not a mock — the provider genuinely reads these files from disk during tests.

## Error Handling

- Vault directory doesn't exist → empty results, not an error (see above).
- A file inside the vault fails to read/decode → that file is skipped, search continues over the rest (see above).
- Query is an empty string → returns whatever the substring-match logic naturally does for `""` (every line "contains" the empty string, so in practice this would match the first line of every file up to `limit`) — no special-cased validation needed; this isn't a security or correctness boundary, just a degenerate input with a well-defined, harmless result.

## Testing Strategy

- `apps/core/tests/test_knowledge_obsidian.py`: unit tests against the real fixture vault directory (`tests/fixtures/vault/`) — no mocking of the filesystem. Cases: finds a match with correct path/title/excerpt/line_number; case-insensitive matching; respects `limit`; returns empty list for a query with no matches; returns empty list for a nonexistent vault directory; skips a deliberately-added unreadable/binary file in a dedicated sub-fixture without failing the whole search; does not escape the vault root (a symlink-based or `..`-based traversal attempt, if one is constructable in a test, is rejected — otherwise this is documented as a code-review-verified invariant rather than a fully reproducible test, matching how such boundary checks are sometimes hard to force in a unit test).
- `apps/core/tests/test_search_notes_skill.py`: skill-level test using the fixture vault via config override (the existing `monkeypatch.setenv("JARVIS_...")` pattern used throughout this project's settings-dependent tests), proving the skill's manifest and `run()` wiring work end-to-end.
- Manual proof step (mirroring the "prove the real thing works" pattern from every prior milestone's final task): start the real backend, `curl` or invoke `search_notes` against the real fixture vault, confirm real results.

## Open Questions Deferred

- Google Calendar / Gmail integrations — Milestone 8b, starts with a live OAuth app setup session with Stephen.
- Semantic/embedding-based search — future upgrade behind the same `KnowledgeSource` protocol if plain substring search proves insufficient in practice.
- Live vault file-watching — not needed until search feels stale in real use.
