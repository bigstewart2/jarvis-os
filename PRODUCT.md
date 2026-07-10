# Product

## Register

product

## Users

One user: Stephen, on his own Mac, throughout the day. He's a PM (not an engineer) who directed AI agents to build this. Context of use: glancing at it in the morning for a briefing, talking to it by voice for quick lookups (notes, calendar, email), and occasionally running skills or automations by hand. He is not a power user of his own tool yet — the interface must teach him what Jarvis can do.

## Product Purpose

Jarvis OS is a personal AI operating system for macOS: voice assistant (local STT/TTS), Claude-backed skills, an automation engine, and integrations with Obsidian, Google Calendar, and Gmail. Success = Stephen opens it every morning because the daily brief is genuinely useful, and reaches for voice search instead of digging through apps. The dashboard's job is to make capabilities discoverable and results legible — not to look like a developer debug panel.

## Brand Personality

Calm, capable, quietly futuristic. "A trusted aide at a desk lamp," not "sci-fi movie HUD." Three words: composed, legible, personal. It should feel like a crafted personal instrument — one owner, one machine — with warmth in the details rather than spectacle.

## Anti-references

- Iron Man HUD cosplay: neon cyan glows, scanlines, fake radar circles.
- Generic SaaS admin dashboards: identical white cards in a grid, hero metrics, blue-600 buttons.
- Developer debug panels: raw JSON dumps, IDs as primary text, unstyled `<pre>` blocks as the main output surface.

## Design Principles

1. **Answer "what can it do?" on screen** — every capability visible and invokable; no memorizing commands.
2. **Results are for reading, not parsing** — skill/voice output rendered as prose and structured lists, never raw JSON as the primary surface.
3. **The brief is the front page** — the most valuable daily content (today's calendar, email, notes) leads; plumbing (runs, task IDs) recedes.
4. **Status is ambient** — backend/voice/automation state readable at a glance without interaction.
5. **One owner, one machine** — personal touches (greeting, time-awareness) are appropriate; multi-tenant genericism is not.

## Accessibility & Inclusion

Single known user, but keep WCAG AA contrast (≥4.5:1 body text), full keyboard operability, visible focus states, and `prefers-reduced-motion` alternatives for all animation.
