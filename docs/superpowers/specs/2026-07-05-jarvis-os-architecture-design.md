# Jarvis OS — Master Architecture Design (Milestone 0)

Status: Approved
Date: 2026-07-05

## Purpose

Jarvis OS is a personal AI operating system for Stephen's desktop (macOS only). It centralizes voice interaction, Claude Code, local models, reusable skills, dashboards, and automations into a single production-quality application. This document is the system-wide design produced before any code is written, per Stephen's request. It fixes the tech stack, component boundaries, data flow, folder structure, and milestone roadmap. Each milestone below gets its own spec + implementation plan before being built.

## Non-Goals (for this design phase)

- Cross-platform support (Windows/Linux). macOS only, by explicit decision.
- Picking exact STT/TTS model versions beyond "best quality, local" — concrete model selection happens at the voice milestone (Milestone 4), constrained to the chosen provider interfaces.
- Specifying every skill Jarvis will ever have. Only the skill *system* (contract, registry, composition) is designed now.

## Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Desktop shell | Tauri 2 + React + TypeScript + Vite | Small footprint, native macOS feel, low memory vs Electron, mature plugin model |
| Core backend | Python 3.12 + FastAPI, run as a local sidecar process launched by the Tauri app | Best ecosystem for STT/TTS bindings, LLM SDKs, and subprocess control over the Claude Code CLI |
| Local state | SQLite via SQLAlchemy | Zero-ops, file-based, sufficient for a single-user desktop app |
| Frontend↔Backend transport | WebSocket event bus (live state: voice status, task progress, notifications) + REST (request/response: invoke skill, fetch dashboard config) | Matches the read-mostly / event-heavy nature of a dashboard + voice UI |
| LLM providers | Anthropic (Claude, default), OpenAI, Ollama (local) | Behind one `LLMProvider` interface; config-selected, not hardcoded |
| STT | whisper.cpp (large-v3 class model via a Python binding, e.g. faster-whisper) | Best local transcription quality, per Stephen's stated priority |
| TTS | Piper or Kokoro (local) | Natural-sounding, local, swappable behind `TTSProvider` |
| Automation scheduler | APScheduler inside the Python backend | Cron-like + event-based triggers without extra infrastructure |

## Provider Abstraction Pattern

Every subsystem Stephen wants swappable is defined as a Python `Protocol` (structural interface), with concrete implementations registered in a small provider registry and selected via config (`config.yaml` / `.env`) rather than code changes:

- `LLMProvider` — Claude, OpenAI, Ollama implementations
- `STTProvider` — whisper.cpp implementation to start
- `TTSProvider` — Piper/Kokoro implementation to start
- `KnowledgeSource` — Obsidian vault, Gmail, Google Calendar
- `AutomationTrigger` — cron-based, event-based (e.g. "new email arrived")

The UI never talks to a provider directly — only to the skill/automation layer, which resolves providers through the registry. This is what makes "swap providers without rewriting the application" true in practice.

## Skill System

The skill system is the core abstraction everything else composes through.

Each skill is a self-contained package under `apps/core/skills/<skill_id>/`:
- `manifest.yaml` — `id`, `name`, `description`, input schema, output schema (Pydantic/JSON Schema), `voice_invokable: bool`, optional `ui_component` hint for a custom widget
- `run(inputs) -> outputs` — the entrypoint; a pure function of its declared inputs

At startup, the **skill registry** scans this directory, validates each manifest, and exposes every skill three ways automatically:
1. **UI** — a button auto-rendered from the manifest's input schema, or a custom widget if `ui_component` is set
2. **Voice** — matched via a lightweight intent layer (a Claude call classifies "is this a skill invocation, and which one, or is it open chat?" — no separate NLU stack needed)
3. **Programmatic** — invoked by the automation engine as one step in a pipeline

**Composability**: a pipeline is an ordered/branching list of skill calls with output→input wiring. No custom workflow DSL is introduced at this stage — YAGNI. If pipeline needs grow complex enough to need branching/conditionals beyond simple sequencing, that becomes its own milestone decision, not a Milestone 0 commitment.

## Data Flow (illustrative: voice path)

```
Mic → STT (local) → Intent Router (Claude call classifies: skill invocation vs open chat)
   → Skill Engine executes the matched skill
        (may call an LLMProvider, the Claude Code CLI, or an integration/KnowledgeSource)
   → Response text → TTS (local) → speaker
                    → WebSocket event → UI updates (status, transcript, result card)
```

Claude Code integration is itself a skill (`claude_code_task`): it shells out to the Claude Code CLI headlessly (e.g. `claude -p "<prompt>" --output-format json`) for coding/agentic tasks and streams progress back over the WebSocket event bus. This same mechanism is how "headless task execution" and background automations report progress to the dashboard.

## Folder Structure

Project home: `~/Desktop/AI Projects/projects/productivity/jarvis-os/` — placed under the `productivity/` domain per the existing domain-first convention (sibling to `second-brain`, `morning-operator`), since Jarvis OS is fundamentally a productivity tool, not a separate top-level domain.

```
jarvis-os/
  apps/
    desktop/            # Tauri + React + TS frontend
    core/               # Python FastAPI backend
      core/
        providers/      # llm/, stt/, tts/, knowledge/
        skills/         # skill registry + loader
        automation/     # scheduler, pipeline engine
        events/         # WebSocket event bus
        db/             # SQLite models/migrations
      skills/           # actual skill packages (manifest.yaml + run())
      tests/
  packages/
    shared-types/       # JSON Schema / types shared between frontend & backend
  docs/
    superpowers/specs/  # design docs (this file lives here)
  orchestrator.py        # thin manual front door, per Stephen's project convention
```

## Roadmap (each item gets its own spec + plan before being built)

1. **Core backend skeleton** — FastAPI service, SQLite schema, skill registry, one trivial "echo" skill, WebSocket event bus. Goal: prove the skill contract end-to-end with no UI polish.
2. **Desktop shell** — Tauri+React app connects to the backend, lists skills, invokes one via a button, shows the result.
3. **LLM provider abstraction** — a real "ask Claude" skill; swap-tested against a local Ollama model to prove the `LLMProvider` interface actually holds.
4. **Voice pipeline** — local STT + TTS wired up, push-to-talk in the UI, voice invokes a skill end-to-end.
5. **Claude Code integration skill** — headless CLI invocation, streamed progress in the UI.
6. **Automation engine** — scheduler + skill pipelines, one real automation (e.g. a daily briefing).
7. **Dashboard widgets** — configurable layout, persisted widget config.
8. **Integrations** — Obsidian, Google Calendar, Gmail.
9. **Notifications, document viewer, polish pass.**

## Open Questions Deferred to Later Milestones

- Exact whisper.cpp / Piper-or-Kokoro model sizes and quantization (Milestone 4).
- Intent-routing accuracy threshold and fallback behavior when the router is unsure (Milestone 4).
- Pipeline/DAG expressiveness beyond simple sequencing, if a real automation needs it (Milestone 6).
- Plugin packaging/distribution format if skills are ever shared beyond this one machine (not currently in scope).
