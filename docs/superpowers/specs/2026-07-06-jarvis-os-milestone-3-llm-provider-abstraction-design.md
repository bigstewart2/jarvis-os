# Jarvis OS Milestone 3 — LLM Provider Abstraction Design

Status: Approved
Date: 2026-07-06

## Purpose

Milestones 1-2 proved the skill contract end-to-end (backend + desktop UI) with one trivial "echo" skill. Milestone 3 proves the master architecture's other core promise: that a subsystem like the LLM can be swapped between providers via config alone, with no code change. This milestone adds a real `LLMProvider` interface with two implementations (Anthropic, Ollama), a new `ask` skill that uses it, and an automated contract test that proves both providers satisfy the same interface.

## Non-Goals (for this milestone)

- No streaming responses. `complete(prompt) -> str` returns the full text at once.
- No chat history / multi-turn context. Each call is a single independent prompt.
- No OpenAI provider. The master architecture lists it as a future option; it isn't needed to prove the abstraction and is deferred until a real use case needs it.
- No voice pipeline (Milestone 4) or Claude Code CLI integration (Milestone 5). The `ask` skill calls the Anthropic API directly via SDK, not the Claude Code CLI — that headless-CLI mechanism is explicitly Milestone 5's job.
- No new error-handling machinery. Provider failures surface as plain exceptions, handled by the skill invocation error path already built in Milestone 1.

## Components

| Component | Responsibility |
|---|---|
| `apps/core/core/providers/llm/base.py` | `LLMProvider` Protocol: `complete(prompt: str, *, system: str \| None = None) -> str` |
| `apps/core/core/providers/llm/anthropic_provider.py` | `AnthropicProvider` — wraps the `anthropic` Python SDK's `messages.create(...)`, passing `system` through to the SDK's native `system` param when given; reads API key/model from `Settings`; raises an actionable error at construction time if no API key is configured |
| `apps/core/core/providers/llm/ollama_provider.py` | `OllamaProvider` — POSTs to a local Ollama server's `/api/generate` endpoint, passing `system` through to Ollama's native `system` field when given; reads base URL/model from `Settings` |
| `apps/core/core/providers/llm/factory.py` | `get_llm_provider(settings: Settings) -> LLMProvider` — returns the provider instance selected by `settings.llm_provider` |
| `apps/core/core/config.py` | extended with `llm_provider: Literal["anthropic", "ollama"] = "anthropic"`, `anthropic_api_key: str \| None` (resolves from either `JARVIS_ANTHROPIC_API_KEY` or bare `ANTHROPIC_API_KEY` via `validation_alias=AliasChoices(...)`, matching the repo-wide convention), `anthropic_model: str = "claude-sonnet-4-5"`, `ollama_base_url: str = "http://localhost:11434"`, `ollama_model: str = "llama3.2:3b"` |
| `apps/core/skills/ask/manifest.yaml` | `input_schema: {prompt: string}`, `output_schema: {response: string}`, `voice_invokable: true` |
| `apps/core/skills/ask/skill.py` | `run(inputs)` resolves the active provider via `get_llm_provider(get_settings())` and calls `.complete(inputs["prompt"])` |

This matches the master architecture's Provider Abstraction Pattern exactly: a `Protocol`, concrete implementations, config-selected — no UI or skill code ever imports a concrete provider class directly.

## Data Flow

```
POST /skills/ask/invoke {"inputs": {"prompt": "..."}}
  → ask skill's run() → get_llm_provider(settings) → provider.complete(prompt)
  → {"outputs": {"response": "..."}}
```

The `ask` skill itself only ever passes `prompt`; the optional `system` parameter exists on the Protocol now (cheap to add, avoids a breaking interface change) but has no caller yet in this milestone — the intent router planned for Milestone 4 is the first anticipated consumer.

Switching providers is `JARVIS_LLM_PROVIDER=ollama` in the environment + a backend restart — no code change. This is the concrete behavior the swap test proves.

## Error Handling

`complete()` implementations raise a plain exception on failure (network error, missing/invalid API key, Ollama not reachable, non-2xx response). No new handling is added at the provider layer — the existing skill-invocation error path (built in Milestone 1's `POST /skills/{id}/invoke`) already converts an exception raised inside a skill's `run()` into the standard error response.

## Testing Strategy

Two layers, so a broken provider implementation can never merge silently just because neither real backend is configured in the environment running the suite:

- `tests/test_anthropic_provider.py` / `tests/test_ollama_provider.py` — offline unit tests per provider with the `anthropic` SDK client / `httpx` (Ollama HTTP call) mocked. These verify request construction (prompt and `system` land in the right fields) and response parsing, and always run — no network, no API key, no local Ollama server required. This is what actually guards correctness on a fresh clone or in CI.
- `tests/test_llm_provider_contract.py` — one contract test, parametrized over both **real** provider instances, asserting `complete()` returns a non-empty string for a trivial prompt (e.g. `"Say the word 'test' and nothing else."`). Each provider's case is independently skipped (`pytest.mark.skipif`) when it isn't usable in the current environment:
  - `AnthropicProvider` skips if `settings.anthropic_api_key` resolves to `None` (i.e. neither `JARVIS_ANTHROPIC_API_KEY` nor `ANTHROPIC_API_KEY` is set).
  - `OllamaProvider` skips if `http://localhost:11434` is not reachable.

  This is a real-API drift check layered on top of the mocked unit tests, not a substitute for them — it keeps Anthropic API cost to only the machines/runs where a key is actually present (in practice, an occasional few-cents charge on Stephen's machine rather than a cost on every commit).
- `tests/test_ask_skill.py` — unit test for the `ask` skill itself, with `get_llm_provider` mocked at the module level. No network dependency; verifies the skill wires inputs/outputs correctly regardless of which provider is "active."
- Manual smoke test closes out the milestone: install Ollama, pull `llama3.2:3b`, invoke `ask` (via curl or the desktop UI) against Anthropic, flip `JARVIS_LLM_PROVIDER` to `ollama`, restart the backend, invoke `ask` again, confirm both return sensible text for the same prompt.

## Open Questions Deferred to Later Milestones

- OpenAI provider implementation — deferred until a concrete need arises.
- Streaming responses and multi-turn chat history — deferred until a skill (e.g. a future conversational assistant skill) actually needs them.
- Claude Code CLI-based invocation for agentic coding tasks — Milestone 5's job, distinct from this milestone's direct-API `AnthropicProvider`.
- Model/temperature/token-limit tuning per use case — this milestone uses fixed defaults; per-skill overrides are deferred until a skill needs different generation parameters.
