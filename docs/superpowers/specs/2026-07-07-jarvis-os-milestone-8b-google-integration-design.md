# Jarvis OS Milestone 8b: Google Calendar & Gmail Integration — Design

**Process note:** The human-in-the-loop prerequisite (Google Cloud OAuth app + consent flow) was completed live with Stephen on 2026-07-07: OAuth client credentials live at `apps/core/google_credentials.json` and a granted token at `apps/core/google_token.json` (both gitignored), with scopes `calendar.readonly`, `calendar.events`, `gmail.readonly`, `gmail.compose`. Both APIs were smoke-tested against Stephen's real account before this spec was written. Scope was chosen by Stephen explicitly: read calendar, read/search email, draft emails (never send), create calendar events.

## Purpose

Give Jarvis real access to Stephen's Google Calendar and Gmail through four new skills, wired through the same skill system as everything else — so "what's on my calendar tomorrow?" works by voice, automations can compose a spoken morning brief, and the dashboard can act on real email.

## Security Posture (the binding constraints of this milestone)

- **No send capability.** The Gmail scope is `gmail.compose` (create drafts), deliberately not `gmail.send`. Jarvis can write a draft; only Stephen, in Gmail, can send it. This is an intentional hard boundary, not a deferred feature.
- **No delete/modify capability** on either service beyond event creation.
- Credentials and token files are gitignored and never logged. Skill outputs must never include the token.
- Voice invocation is enabled ONLY for the two read-only skills. The two write skills (`draft_email`, `create_calendar_event`) are `voice_invokable: false` this milestone — a misrouted voice command must not be able to write to Stephen's account. (Milestone 4's intent router has a known nonzero misroute rate; this is the same reasoning that kept `claude_code_task` off voice.)

## Components

**`core/providers/google/` package** (mirrors `providers/knowledge/` structure):
- `auth.py` — `get_google_credentials(settings) -> Credentials`: loads `google_token.json`, auto-refreshes via the refresh token when expired, persists the refreshed token back to disk. Raises a clear `GoogleAuthError` (with the re-auth command in the message) if the token file is missing or revoked.
- `calendar.py` — `GoogleCalendarClient`: `list_events(days_ahead: int = 1) -> list[EventSummary]` (normalized dicts: start, end, title, location, attendees-count) and `create_event(title, start_iso, end_iso, description) -> CreatedEvent` (returns id + htmlLink).
- `gmail.py` — `GmailClient`: `search_messages(query: str, limit: int = 10) -> list[MessageSummary]` (from, subject, date, snippet — Gmail's own query syntax passes through, e.g. `from:recruiter newer_than:7d`) and `create_draft(to, subject, body) -> CreatedDraft` (returns draft id).

**Four skills** (each the standard manifest + `run()` package):
| Skill | Inputs | Voice | Notes |
|---|---|---|---|
| `get_calendar_events` | `days_ahead` (int, default 1) | ✅ | "what's on my calendar" |
| `search_email` | `query` (str) | ✅ | passes through Gmail query syntax |
| `draft_email` | `to`, `subject`, `body` | ❌ | draft only, never send |
| `create_calendar_event` | `title`, `start_iso`, `end_iso`, `description` (opt) | ❌ | |

**Config:** `google_credentials_path: str = "google_credentials.json"`, `google_token_path: str = "google_token.json"` on `Settings` (same relative-to-BASE_DIR convention as every other path setting).

**Dependencies:** `google-auth`, `google-auth-oauthlib`, `google-api-python-client` added to `requirements.txt` (already installed in the dev venv during the live OAuth session).

**Re-auth script:** the one-time consent flow script (used live today) is preserved at `apps/core/scripts/google_oauth_setup.py` so re-consent (revoked token, changed scopes) is a single documented command rather than tribal knowledge.

## Non-Goals

- Sending email (hard boundary, see above).
- OS-level push/webhook sync (Gmail watch, Calendar channels) — polling/skill-invocation only.
- A dashboard widget for calendar/email this milestone — skills first; the auto-rendered skill cards make them usable from the UI already. A purpose-built widget is a natural follow-up once real usage shows what layout matters.
- Multi-account support. One Google account.

## Error Handling

- Missing/revoked token → each skill returns a `{"error": "..."}`-style failed invocation with the exact re-auth command in the message; never crashes the app (matches the skill system's existing failure contract — `invoke_and_record_skill` already catches exceptions and records failed invocations).
- Google API errors (rate limit, network) → propagate as skill failure with the API's error message; no retry logic this milestone (single-user, interactive usage patterns).
- Token refresh happens transparently inside `get_google_credentials`; a refreshed token is re-persisted so the next call doesn't refresh again.

## Testing Strategy

Google's APIs cannot be called in unit tests. Following the provider-test convention:
- `auth.py`: tested with a fake token file on disk (`tmp_path`) — valid/expired-with-refresh/missing paths. The refresh path monkeypatches `Credentials.refresh`.
- `calendar.py`/`gmail.py`: tested with mocked `googleapiclient` service objects (stub the chained `.events().list().execute()` calls), asserting normalization logic (event dict shaping, message header extraction) — the real logic this milestone adds.
- Skills: standard `monkeypatch.setitem(loaded.run.__globals__, ...)` pattern against fake clients.
- One live contract test per service, skipif-guarded on the token file existing (mirrors `test_piper_contract.py`'s pattern): a real `list_events` call and a real `search_messages` call. These run on Stephen's machine, skip in any environment without the token.
- Manual proof step: real skill invocations through a live backend (calendar events + email search already proven pre-spec; draft + event creation to be proven against the real account in the final task, then cleaned up).

## Open Questions Deferred

- A `daily_brief` composite automation (calendar + email + TTS morning briefing) — the obvious killer app on top of these skills; build as a follow-up automation once the skills merge, possibly replacing `ask_digest`'s placeholder prompt.
- Calendar/email dashboard widgets.
- Send-with-confirmation flow (if ever) — would need an explicit UI confirmation pattern that doesn't exist yet.
