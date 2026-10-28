# Jarvis OS

**Retired — October 22, 2026:** Jarvis is a retired desktop-assistant project. Stephen chose Old Projects as its retained home. Source, history, settings, saved data and dependencies remain preserved here. Earlier active-development wording below is historical; this organization change does not restart the app.

A personal AI operating system for the desktop — voice interaction, local and cloud LLMs, Claude Code, reusable skills, dashboards, and automations, unified into a single macOS application.

> **Status: in active development.** This is a milestone-driven build. The system-wide architecture was designed and approved *before any code was written* ([Milestone 0 spec](docs/superpowers/specs/2026-07-05-jarvis-os-architecture-design.md)), and the app is being built out milestone by milestone against that design. It is not finished — the roadmap below shows where it's headed.

## Why this project

I wanted a single, production-quality place to run my day: talk to it by voice, have it reach into my notes and calendar, drive Claude Code, run local models when I don't want to hit an API, and automate recurring work — without stitching together a dozen disconnected tools. Jarvis OS is that system, designed from the architecture down rather than bolted together.

## Architecture at a glance

| Layer | Choice |
|---|---|
| Desktop shell | Tauri 2 + React + TypeScript + Vite |
| Core backend | Python 3.12 + FastAPI (local sidecar process) |
| State | SQLite via SQLAlchemy |
| Transport | WebSocket event bus (live state) + REST (request/response) |
| LLM providers | Anthropic (default), OpenAI, Ollama (local) — behind one interface |
| Speech-to-text | whisper.cpp / faster-whisper (local) |
| Text-to-speech | Piper / Kokoro (local) |
| Scheduler | APScheduler (cron + event triggers) |

**Core design principle — swappable providers.** Every subsystem meant to be swappable (LLM, speech-to-text, text-to-speech, knowledge sources, automation triggers) is defined as a Python `Protocol` and selected via config, not code changes. The UI never talks to a provider directly — only to the skill/automation layer, which resolves providers through a registry. That's what makes "swap the LLM without rewriting the app" true in practice.

**Skill system.** The core abstraction everything composes through. Each skill is a self-contained package with a manifest (input/output schemas, whether it's voice-invokable) and a single `run(inputs) -> outputs` entrypoint. At startup a registry scans, validates, and exposes every skill three ways automatically: as a UI widget, as a voice command, and as an API endpoint.

## Repository layout

```
apps/core/       Python + FastAPI backend (providers, skills, automations, routing, db)
apps/desktop/    Tauri + React desktop shell
docs/            Architecture spec + per-milestone design docs and implementation plans
orchestrator.py  Entry point
```

## Roadmap

The full architecture and a spec + implementation plan for each milestone live in [`docs/`](docs/superpowers). The milestones:

0. Master architecture design *(approved)*
1. Backend skeleton
2. Desktop shell
3. LLM provider abstraction
4. Voice pipeline (speech-to-text / text-to-speech)
5. Claude Code integration
6. Automation engine
7. Dashboard widgets
8. Integrations (Obsidian, Gmail, Calendar)
9. Notifications, document viewer, polish

## Running it

This is a personal macOS-only project under active development; it's shared here to show the architecture and engineering approach rather than as a packaged release. Configuration is driven by environment variables and a local `.env` (never committed) — no secrets live in the repo.

## Earlier voice-pipeline source

The [retained earlier test source](docs/Work%20Records/Voice%20Pipeline/Source%20History/test_voice_pipeline.py.txt) was filed October 21, 2026 from `_scratch/orphans/productivity-stale-worktree/jarvis-os/.claude/worktrees/jarvis-os-m4-voice-pipeline/apps/core/tests/test_voice_pipeline.py` in the parent AI Projects repository. Its bytes are unchanged; the `.txt` suffix keeps this private historical copy out of ordinary test discovery. It is not the current suite or proof that any test passed.

Use [the active voice-pipeline tests](apps/core/tests/test_voice_pipeline.py) for current implementation work. The earlier copy has seven calls without the current invocation-ID argument; the active file also includes two later tests. This filing does not merge or execute the older copy, or change the app.
