# How to actually use Jarvis

*Written 2026-07-10, after researching how people really use personal "Jarvis-style" AI
assistants — and after upgrading the app to match what the research says works.*

## The one-sentence answer

Jarvis is your **morning briefing machine**: every day at 7:30 AM it reads your calendar
and email, writes a short digest, and speaks it out loud — and during the day it's the
fastest way to search your email, calendar, and notes by voice.

## What the research says (so you don't have to wonder "what's it for" again)

I researched how people actually use DIY personal assistants day-to-day. The findings:

1. **One workflow survives past week one: the morning briefing.** Calendar + email +
   notes fused into one digest at a fixed time. Every source converges on this. Open-ended
   "ask it anything" chat is the *least* sticky thing — it's the first thing people abandon.
2. **No trigger = no habit.** Use cases tied to a schedule or event survive; "use it when
   you remember" dies. That's why the brief runs on a cron, not on willpower.
3. **Proactive-but-quiet beats interruptive.** The winning pattern is "the work is done
   and waiting for me," not push notifications.
4. **A single killer workflow beats a broad feature set.** Everything else on the
   dashboard is a bonus, not the point.

Your Jarvis already had all the plumbing (Calendar, Gmail, Obsidian, voice, automations)
— it was missing exactly this one workflow. Now it has it.

## Your daily loop

**Morning (automatic).** At 7:30 AM, if the backend is running, Jarvis composes the brief
and *speaks it*. Open the app and it's also one click away ("Generate today's brief" —
it caches per day, so re-opening is instant).

**During the day (voice).** Hold the talk button and say:
- "Give me my daily brief"
- "What's on my calendar for the next three days?"
- "Search my email for messages from recruiters"
- "Search my notes for interview prep"
- Anything else falls through to the assistant ("ask").

**Anytime (buttons).** Every skill is a form in the Skills panel. The two write-actions
are deliberately button-only and safe: **Draft Email** never sends (drafts land in Gmail
for your review), and **Create Calendar Event** only writes to your own calendar.

**"What can Jarvis do?"** — the button in the header answers exactly that, live from the
skill registry, with example phrases. When you forget what it's for, click that.

## What changed tonight (2026-07-10)

- **New `daily_brief` skill** — calendar + important recent email → LLM-written digest.
  Voice-invokable. Tested end-to-end against your real accounts.
- **New `morning_brief` automation** — daily at 7:30 AM: compose brief → speak it.
  (The old placeholder `ask_digest` "fun fact" automation is disabled, not deleted.)
- **Full dashboard redesign** — dark "pre-dawn flight deck" theme: deep cobalt ground,
  indigo accent, amber recording signal. The brief is the front page; a greeting +
  status dot replace the debug-panel feel; skill results render as readable text (raw
  JSON is tucked under a "Raw output" disclosure); automations/tasks show human times
  ("2h ago") instead of IDs.
- **Voice status bug fixed** — the label no longer sticks on "Transcribing…": WebSocket
  connections now auto-reconnect, and the label always clears when the result arrives.
- **All tests green** — backend 227 passed, frontend 51 passed.

Screenshots: `docs/screenshots/`.

## Starting it

```bash
cd "~/Desktop/AI Projects/projects/productivity/jarvis-os"
python3 orchestrator.py          # backend (port 8420)
cd apps/desktop && npm run tauri dev   # the desktop app
```

For the 7:30 brief to fire (and speak), the backend must be running. If you find
yourself liking the brief, the natural next step is a launchd job so the backend is
always up — ask me and it's a 10-minute setup.

## If you only remember one thing

Open Jarvis with your coffee. The brief is either waiting or one click away. That's the
habit; everything else hangs off it.
