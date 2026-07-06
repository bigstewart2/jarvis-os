# Jarvis OS Milestone 3: LLM Provider Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a config-selected `LLMProvider` abstraction (Anthropic + Ollama backends) behind a new `ask` skill, with automated proof that both providers satisfy the same interface.

**Architecture:** A Python `Protocol` (`LLMProvider.complete(prompt, *, system=None) -> str`) with two concrete implementations (`AnthropicProvider` via the `anthropic` SDK, `OllamaProvider` via raw HTTP to a local Ollama server), selected by a `factory.get_llm_provider(settings)` function reading `Settings.llm_provider`. A new `ask` skill is the only consumer, following the exact skill contract from Milestone 1 (`manifest.yaml` + `run(inputs) -> dict`).

**Tech Stack:** Python 3.14, FastAPI backend (existing), `anthropic` Python SDK (new dependency), `httpx` (already a dependency, used directly for Ollama's HTTP API), `pytest` + `pytest-asyncio` (existing).

## Global Constraints

- Run all backend commands from `apps/core/` using `.venv/bin/python3` / `.venv/bin/pytest` — never the system Python (see Milestone 1's `orchestrator.py` fix).
- Follow the existing `Settings` pattern exactly: `env_prefix="JARVIS_"` in `core/config.py`, `pydantic-settings`.
- New dependencies go in `apps/core/requirements.txt` with a flexible `>=` minimum-version pin (this machine runs Python 3.14; exact `==` pins have previously failed to build — see Milestone 1).
- Every task ends with a full test suite run (`.venv/bin/pytest -v`) — not just the new test — to catch regressions.
- Skill packages live under `apps/core/skills/<skill_id>/` with `manifest.yaml` + `skill.py`, loaded dynamically by `core.skills.registry.SkillRegistry` — skill modules are NOT importable as `skills.<id>.skill`; they're loaded via `importlib.util.spec_from_file_location` with a synthetic module name. Tests for skill behavior must go through `SkillRegistry`, matching `tests/test_echo_skill.py`'s existing pattern.

---

### Task 1: Extend Settings with LLM config + define the LLMProvider Protocol

**Files:**
- Modify: `apps/core/core/config.py`
- Modify: `apps/core/tests/test_config.py`
- Create: `apps/core/core/providers/__init__.py` (empty)
- Create: `apps/core/core/providers/llm/__init__.py` (empty)
- Create: `apps/core/core/providers/llm/base.py`
- Create: `apps/core/tests/test_llm_base.py`

**Interfaces:**
- Produces: `Settings.llm_provider: Literal["anthropic", "ollama"]`, `Settings.anthropic_api_key: str | None`, `Settings.anthropic_model: str`, `Settings.ollama_base_url: str`, `Settings.ollama_model: str` — all later tasks read these off a `Settings` instance.
- Produces: `LLMProvider` Protocol with `complete(self, prompt: str, *, system: str | None = None) -> str` — every provider implementation in later tasks must satisfy this exact signature.

- [ ] **Step 1: Write the failing config test**

Append to `apps/core/tests/test_config.py`:
```python
def test_llm_settings_defaults():
    settings = Settings(anthropic_api_key=None)
    assert settings.llm_provider == "anthropic"
    assert settings.anthropic_model == "claude-sonnet-4-5"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "llama3.2:3b"


def test_anthropic_api_key_resolves_from_bare_env_var(monkeypatch):
    monkeypatch.delenv("JARVIS_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "bare-env-key")
    settings = Settings()
    assert settings.anthropic_api_key == "bare-env-key"


def test_anthropic_api_key_prefers_jarvis_prefixed_env_var(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "bare-env-key")
    monkeypatch.setenv("JARVIS_ANTHROPIC_API_KEY", "prefixed-env-key")
    settings = Settings()
    assert settings.anthropic_api_key == "prefixed-env-key"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `test_llm_settings_defaults` and the two `anthropic_api_key` tests fail with `TypeError: Settings() got an unexpected keyword argument 'anthropic_api_key'` or `AttributeError`.

- [ ] **Step 3: Extend Settings**

Replace the full contents of `apps/core/core/config.py` with:
```python
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JARVIS_")

    database_url: str = "sqlite:///./jarvis.db"
    skills_dir: str = "skills"
    host: str = "127.0.0.1"
    port: int = 8420

    llm_provider: Literal["anthropic", "ollama"] = "anthropic"
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("JARVIS_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    )
    anthropic_model: str = "claude-sonnet-4-5"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run config tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS (all tests in the file, including the two pre-existing ones).

- [ ] **Step 5: Write the failing Protocol test**

Create `apps/core/tests/test_llm_base.py`:
```python
from core.providers.llm.base import LLMProvider


class ConformingProvider:
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return f"{system or ''}{prompt}"


def test_conforming_class_satisfies_protocol():
    provider: LLMProvider = ConformingProvider()
    assert provider.complete("hi") == "hi"
    assert provider.complete("hi", system="be terse") == "be tersehi"


def test_isinstance_check_against_protocol():
    provider = ConformingProvider()
    assert isinstance(provider, LLMProvider)
```

- [ ] **Step 6: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_llm_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.providers'`.

- [ ] **Step 7: Create the providers package and the Protocol**

Create `apps/core/core/providers/__init__.py` (empty file).

Create `apps/core/core/providers/llm/__init__.py` (empty file).

Create `apps/core/core/providers/llm/base.py`:
```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        ...
```

- [ ] **Step 8: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_llm_base.py -v`
Expected: PASS.

- [ ] **Step 9: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: all previous tests still pass, plus the new ones in this task (24 passed).

- [ ] **Step 10: Commit**

```bash
git add core/config.py core/providers tests/test_config.py tests/test_llm_base.py
git commit -m "feat(core): add LLM settings and LLMProvider protocol"
```

---

### Task 2: AnthropicProvider

**Files:**
- Create: `apps/core/core/providers/llm/anthropic_provider.py`
- Create: `apps/core/tests/test_anthropic_provider.py`
- Modify: `apps/core/requirements.txt`

**Interfaces:**
- Consumes: `Settings` (Task 1) — `anthropic_api_key`, `anthropic_model`.
- Consumes: `LLMProvider` Protocol (Task 1) — this class must satisfy `complete(prompt, *, system=None) -> str`.
- Produces: `AnthropicProvider(settings: Settings)` — constructor raises `ValueError` if `settings.anthropic_api_key` is falsy. Later tasks (factory, Task 4) construct this class directly.

- [ ] **Step 1: Add the anthropic dependency**

Append to `apps/core/requirements.txt`:
```
anthropic>=0.39
```

Install it:
```bash
cd apps/core && .venv/bin/pip install -r requirements.txt
```

- [ ] **Step 2: Write the failing tests**

Create `apps/core/tests/test_anthropic_provider.py`:
```python
import pytest

from core.config import Settings
from core.providers.llm.anthropic_provider import AnthropicProvider


class FakeContentBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [FakeContentBlock(text)]


class FakeMessages:
    def __init__(self) -> None:
        self.last_kwargs: dict = {}

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return FakeMessage("hello from fake anthropic")


class FakeAnthropicClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.messages = FakeMessages()


def _settings(**overrides) -> Settings:
    defaults = {"anthropic_api_key": "test-key"}
    defaults.update(overrides)
    return Settings(**defaults)


def test_complete_returns_text_from_response(monkeypatch):
    monkeypatch.setattr(
        "core.providers.llm.anthropic_provider.Anthropic", FakeAnthropicClient
    )
    provider = AnthropicProvider(_settings())

    result = provider.complete("say hi")

    assert result == "hello from fake anthropic"


def test_complete_sends_prompt_as_user_message(monkeypatch):
    monkeypatch.setattr(
        "core.providers.llm.anthropic_provider.Anthropic", FakeAnthropicClient
    )
    provider = AnthropicProvider(_settings())

    provider.complete("say hi")

    sent = provider._client.messages.last_kwargs
    assert sent["messages"] == [{"role": "user", "content": "say hi"}]
    assert "system" not in sent


def test_complete_passes_system_prompt_when_given(monkeypatch):
    monkeypatch.setattr(
        "core.providers.llm.anthropic_provider.Anthropic", FakeAnthropicClient
    )
    provider = AnthropicProvider(_settings())

    provider.complete("say hi", system="be terse")

    assert provider._client.messages.last_kwargs["system"] == "be terse"


def test_raises_value_error_without_api_key():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider(_settings(anthropic_api_key=None))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_anthropic_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.providers.llm.anthropic_provider'`.

- [ ] **Step 4: Implement AnthropicProvider**

Create `apps/core/core/providers/llm/anthropic_provider.py`:
```python
from anthropic import Anthropic

from core.config import Settings


class AnthropicProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY (or JARVIS_ANTHROPIC_API_KEY) is not set; "
                "cannot construct AnthropicProvider"
            )
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        kwargs: dict = {}
        if system is not None:
            kwargs["system"] = system
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return message.content[0].text
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_anthropic_provider.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 28 passed.

- [ ] **Step 7: Commit**

```bash
git add core/providers/llm/anthropic_provider.py tests/test_anthropic_provider.py requirements.txt
git commit -m "feat(core): add AnthropicProvider"
```

---

### Task 3: OllamaProvider

**Files:**
- Create: `apps/core/core/providers/llm/ollama_provider.py`
- Create: `apps/core/tests/test_ollama_provider.py`

**Interfaces:**
- Consumes: `Settings` (Task 1) — `ollama_base_url`, `ollama_model`.
- Consumes: `LLMProvider` Protocol (Task 1).
- Produces: `OllamaProvider(settings: Settings)`. Later tasks (factory, Task 4) construct this class directly.

- [ ] **Step 1: Write the failing tests**

Create `apps/core/tests/test_ollama_provider.py`:
```python
import httpx

from core.config import Settings
from core.providers.llm.ollama_provider import OllamaProvider


class FakeResponse:
    def __init__(self, json_data: dict, status_code: int = 200) -> None:
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error response", request=None, response=self  # type: ignore[arg-type]
            )

    def json(self) -> dict:
        return self._json_data


def test_complete_returns_text_from_response(monkeypatch):
    def fake_post(url, json, timeout):
        return FakeResponse({"response": "hello from fake ollama"})

    monkeypatch.setattr("core.providers.llm.ollama_provider.httpx.post", fake_post)

    provider = OllamaProvider(Settings(anthropic_api_key=None))
    result = provider.complete("say hi")

    assert result == "hello from fake ollama"


def test_complete_sends_prompt_and_model_no_system_by_default(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"response": "ok"})

    monkeypatch.setattr("core.providers.llm.ollama_provider.httpx.post", fake_post)

    provider = OllamaProvider(Settings(anthropic_api_key=None))
    provider.complete("say hi")

    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["json"]["prompt"] == "say hi"
    assert captured["json"]["model"] == "llama3.2:3b"
    assert captured["json"]["stream"] is False
    assert "system" not in captured["json"]


def test_complete_passes_system_prompt_when_given(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["json"] = json
        return FakeResponse({"response": "ok"})

    monkeypatch.setattr("core.providers.llm.ollama_provider.httpx.post", fake_post)

    provider = OllamaProvider(Settings(anthropic_api_key=None))
    provider.complete("say hi", system="be terse")

    assert captured["json"]["system"] == "be terse"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ollama_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.providers.llm.ollama_provider'`.

- [ ] **Step 3: Implement OllamaProvider**

Create `apps/core/core/providers/llm/ollama_provider.py`:
```python
import httpx

from core.config import Settings


class OllamaProvider:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ollama_base_url
        self._model = settings.ollama_model

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        payload: dict = {"model": self._model, "prompt": prompt, "stream": False}
        if system is not None:
            payload["system"] = system
        response = httpx.post(f"{self._base_url}/api/generate", json=payload, timeout=60.0)
        response.raise_for_status()
        return response.json()["response"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ollama_provider.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 31 passed.

- [ ] **Step 6: Commit**

```bash
git add core/providers/llm/ollama_provider.py tests/test_ollama_provider.py
git commit -m "feat(core): add OllamaProvider"
```

---

### Task 4: Provider factory

**Files:**
- Create: `apps/core/core/providers/llm/factory.py`
- Create: `apps/core/tests/test_llm_factory.py`

**Interfaces:**
- Consumes: `Settings` (Task 1), `AnthropicProvider` (Task 2), `OllamaProvider` (Task 3).
- Produces: `get_llm_provider(settings: Settings) -> LLMProvider`. This is the only function the `ask` skill (Task 5) and the live contract test (Task 6) use to obtain a provider — neither imports `AnthropicProvider`/`OllamaProvider` directly.

- [ ] **Step 1: Write the failing tests**

Create `apps/core/tests/test_llm_factory.py`:
```python
import pytest

from core.config import Settings
from core.providers.llm.anthropic_provider import AnthropicProvider
from core.providers.llm.factory import get_llm_provider
from core.providers.llm.ollama_provider import OllamaProvider


def test_returns_anthropic_provider_when_configured():
    settings = Settings(llm_provider="anthropic", anthropic_api_key="test-key")
    provider = get_llm_provider(settings)
    assert isinstance(provider, AnthropicProvider)


def test_returns_ollama_provider_when_configured():
    settings = Settings(llm_provider="ollama", anthropic_api_key=None)
    provider = get_llm_provider(settings)
    assert isinstance(provider, OllamaProvider)


def test_raises_on_unknown_provider_name():
    settings = Settings(anthropic_api_key=None)
    settings.llm_provider = "bogus"
    with pytest.raises(ValueError, match="bogus"):
        get_llm_provider(settings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_llm_factory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.providers.llm.factory'`.

- [ ] **Step 3: Implement the factory**

Create `apps/core/core/providers/llm/factory.py`:
```python
from core.config import Settings
from core.providers.llm.anthropic_provider import AnthropicProvider
from core.providers.llm.base import LLMProvider
from core.providers.llm.ollama_provider import OllamaProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings)
    if settings.llm_provider == "ollama":
        return OllamaProvider(settings)
    raise ValueError(f"Unknown llm_provider: {settings.llm_provider}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_llm_factory.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 34 passed.

- [ ] **Step 6: Commit**

```bash
git add core/providers/llm/factory.py tests/test_llm_factory.py
git commit -m "feat(core): add LLM provider factory"
```

---

### Task 5: The `ask` skill

**Files:**
- Create: `apps/core/skills/ask/manifest.yaml`
- Create: `apps/core/skills/ask/skill.py`
- Create: `apps/core/tests/test_ask_skill.py`

**Interfaces:**
- Consumes: `get_settings()` (`core.config`), `get_llm_provider(settings)` (Task 4).
- Produces: skill id `"ask"`, loadable via `SkillRegistry.load_from_directory`, with `run({"prompt": str}) -> {"response": str}`.

- [ ] **Step 1: Write the failing test**

Create `apps/core/tests/test_ask_skill.py`. This follows the same pattern as `tests/test_echo_skill.py` — loading the real skill through `SkillRegistry` rather than importing it directly, since skill modules are loaded dynamically and are not importable as `skills.ask.skill`. To replace the real LLM provider with a fake one, this test patches the loaded skill function's `__globals__` (the module namespace dict `skill.py` actually runs in) — the correct way to mock a dependency inside a dynamically-loaded module:
```python
from pathlib import Path

from core.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


class FakeProvider:
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return f"echoed: {prompt}"


def test_ask_skill_loads_and_uses_configured_provider(monkeypatch):
    registry = SkillRegistry()
    registry.load_from_directory(SKILLS_DIR)

    loaded = registry.get("ask")
    assert loaded is not None
    assert loaded.manifest.voice_invokable is True

    monkeypatch.setitem(
        loaded.run.__globals__, "get_llm_provider", lambda settings: FakeProvider()
    )

    result = loaded.run({"prompt": "hello"})

    assert result == {"response": "echoed: hello"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ask_skill.py -v`
Expected: FAIL — `assert loaded is not None` fails (`"ask"` skill doesn't exist yet), since `registry.get("ask")` returns `None`.

- [ ] **Step 3: Create the skill manifest**

Create `apps/core/skills/ask/manifest.yaml`:
```yaml
id: ask
name: Ask
description: Sends a prompt to the configured LLM provider and returns its text response.
input_schema:
  type: object
  properties:
    prompt:
      type: string
  required:
    - prompt
output_schema:
  type: object
  properties:
    response:
      type: string
voice_invokable: true
```

- [ ] **Step 4: Create the skill implementation**

Create `apps/core/skills/ask/skill.py`:
```python
from core.config import get_settings
from core.providers.llm.factory import get_llm_provider


def run(inputs: dict) -> dict:
    settings = get_settings()
    provider = get_llm_provider(settings)
    response = provider.complete(inputs["prompt"])
    return {"response": response}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ask_skill.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 35 passed.

- [ ] **Step 7: Commit**

```bash
git add skills/ask tests/test_ask_skill.py
git commit -m "feat(skills): add ask skill using the LLM provider abstraction"
```

---

### Task 6: Live contract test proving both providers are interchangeable

**Files:**
- Create: `apps/core/tests/test_llm_provider_contract.py`

**Interfaces:**
- Consumes: `Settings`, `AnthropicProvider`, `OllamaProvider` (all prior tasks). This task does not add any new production code — it is a test-only task.

- [ ] **Step 1: Write the contract test**

There is no "make it fail first" step for this task in the usual sense — both provider classes already exist and satisfy the Protocol (proven in Tasks 2 and 3's mocked tests). This test's job is to prove they behave interchangeably against real backends, when those backends are actually configured/reachable, and to skip cleanly otherwise so it never blocks a fresh clone or CI.

Create `apps/core/tests/test_llm_provider_contract.py`:
```python
import httpx
import pytest

from core.config import Settings
from core.providers.llm.anthropic_provider import AnthropicProvider
from core.providers.llm.ollama_provider import OllamaProvider

PROMPT = "Say the word 'test' and nothing else."


def _ollama_reachable(base_url: str) -> bool:
    try:
        httpx.get(base_url, timeout=1.0)
        return True
    except httpx.HTTPError:
        return False


_settings = Settings()
_anthropic_available = bool(_settings.anthropic_api_key)
_ollama_available = _ollama_reachable(_settings.ollama_base_url)


@pytest.mark.skipif(not _anthropic_available, reason="ANTHROPIC_API_KEY not configured")
def test_anthropic_provider_completes_real_prompt():
    provider = AnthropicProvider(_settings)
    result = provider.complete(PROMPT)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.skipif(not _ollama_available, reason="Ollama not reachable at configured base URL")
def test_ollama_provider_completes_real_prompt():
    provider = OllamaProvider(_settings)
    result = provider.complete(PROMPT)
    assert isinstance(result, str)
    assert len(result) > 0
```

- [ ] **Step 2: Run the test file to confirm skip behavior with neither backend configured**

Run: `.venv/bin/pytest tests/test_llm_provider_contract.py -v`
Expected: both tests show `SKIPPED` (unless this environment happens to already have `ANTHROPIC_API_KEY` set or an Ollama server running at `localhost:11434` — if so, that test runs for real instead of skipping, which is also correct behavior).

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: 37 passed (or fewer "passed" + some "skipped" if this environment has neither backend configured — total collected should be 37).

- [ ] **Step 4: Commit**

```bash
git add tests/test_llm_provider_contract.py
git commit -m "test(core): add live contract test proving LLM providers are interchangeable"
```

---

### Task 7: End-to-End Manual Smoke Test

**Files:** None (verification only).

**Interfaces:** None — this task exercises the full stack built across Tasks 1-6, including installing and configuring real Ollama, which the automated suite cannot assume is present.

- [ ] **Step 1: Install Ollama and pull the swap-test model**

```bash
brew install ollama
brew services start ollama
ollama pull llama3.2:3b
ollama list
```
Expected: `llama3.2:3b` appears in the `ollama list` output.

- [ ] **Step 2: Confirm the live contract test now exercises Ollama for real**

```bash
cd apps/core && .venv/bin/pytest tests/test_llm_provider_contract.py -v
```
Expected: `test_ollama_provider_completes_real_prompt` now shows `PASSED` (no longer skipped). `test_anthropic_provider_completes_real_prompt` skips unless `ANTHROPIC_API_KEY` is set in this shell.

- [ ] **Step 3: Start the backend with Ollama as the active provider**

```bash
cd apps/core
JARVIS_LLM_PROVIDER=ollama nohup .venv/bin/python3 main.py > /tmp/jarvis-backend-m3-smoke.log 2>&1 &
BACKEND_PID=$!
sleep 2
curl -s -X POST http://127.0.0.1:8420/skills/ask/invoke \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"prompt": "Say the word test and nothing else."}}'
```
Expected: a JSON response like `{"outputs": {"response": "test"}}` (or similar short text — small local models don't always follow instructions exactly, any non-empty text response is a pass).

- [ ] **Step 4: Stop the backend, then restart with Anthropic as the active provider (only if `ANTHROPIC_API_KEY` is available)**

```bash
kill $BACKEND_PID 2>/dev/null
```

If you have an Anthropic API key available:
```bash
cd apps/core
ANTHROPIC_API_KEY=<your-key> nohup .venv/bin/python3 main.py > /tmp/jarvis-backend-m3-smoke2.log 2>&1 &
BACKEND_PID=$!
sleep 2
curl -s -X POST http://127.0.0.1:8420/skills/ask/invoke \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"prompt": "Say the word test and nothing else."}}'
```
Expected: a JSON response like `{"outputs": {"response": "test"}}`, proving the same skill/endpoint now routes through Anthropic instead of Ollama with no code change — only the env var differed.

If no API key is available in this environment, skip this step and note it explicitly in the report; the mocked unit tests (Task 2) and the desktop-shell-verified request/response wiring (Milestone 2) already cover the Anthropic code path's correctness.

- [ ] **Step 5: Stop the backend**

```bash
kill $BACKEND_PID 2>/dev/null
pkill -f "apps/core/main.py" 2>/dev/null
```

- [ ] **Step 6: Run the full suite one final time**

```bash
cd apps/core && .venv/bin/pytest -v
```
Expected: 37 passed (plus any live-contract tests that ran for real in Steps 2-4 rather than skipping).

No commit for this task — it's verification only, nothing changes.
