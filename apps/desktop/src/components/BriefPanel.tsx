import { useEffect, useState } from "react";
import { invokeSkill } from "../api/client";
import { eventTime, greeting, longDate } from "../lib/format";

interface BriefEvent {
  title: string;
  start: string;
  end: string;
  location: string;
  attendee_count: number;
}

interface BriefMessage {
  from_: string;
  subject: string;
  date: string;
  snippet: string;
}

interface StoredBrief {
  date: string;
  brief: string;
  events: BriefEvent[];
  messages: BriefMessage[];
  generatedAt: string;
}

const STORAGE_KEY = "jarvis.daily_brief";

function todayKey(): string {
  return new Date().toDateString();
}

function loadStoredBrief(): StoredBrief | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredBrief;
    return parsed.date === todayKey() ? parsed : null;
  } catch {
    return null;
  }
}

export function BriefPanel() {
  const [brief, setBrief] = useState<StoredBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setBrief(loadStoredBrief());
  }, []);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await invokeSkill("daily_brief", {});
      const outputs = response.outputs as unknown as {
        brief: string;
        events: BriefEvent[];
        messages: BriefMessage[];
      };
      const stored: StoredBrief = {
        date: todayKey(),
        brief: outputs.brief,
        events: outputs.events ?? [],
        messages: outputs.messages ?? [],
        generatedAt: new Date().toISOString(),
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
      setBrief(stored);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section
      data-testid="brief-panel"
      className="rounded-card border border-edge-soft bg-surface px-5 py-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-lg font-semibold">{greeting()}</p>
          <p className="text-sm text-ink-mute">{longDate()}</p>
        </div>
        <button
          onClick={generate}
          disabled={loading}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-ink transition-colors duration-150 hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "Composing…" : brief ? "Refresh brief" : "Generate today's brief"}
        </button>
      </div>

      {loading && (
        <div className="mt-4 space-y-2" aria-hidden="true">
          <div className="h-3 w-4/5 animate-pulse rounded bg-surface-2" />
          <div className="h-3 w-3/5 animate-pulse rounded bg-surface-2" />
          <div className="h-3 w-2/3 animate-pulse rounded bg-surface-2" />
        </div>
      )}

      {error && (
        <p data-testid="brief-error" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}

      {!loading && !brief && !error && (
        <p className="mt-3 max-w-prose text-sm text-ink-mute">
          One button, one digest: today's calendar and the email that matters, written up by
          Jarvis. It runs on its own every morning at 7:30 — or generate it now.
        </p>
      )}

      {!loading && brief && (
        <div className="mt-4 animate-rise">
          <div className="max-w-prose space-y-3 text-[0.95rem] leading-relaxed">
            {brief.brief.split(/\n{2,}/).map((paragraph, i) => (
              <p key={i}>{paragraph}</p>
            ))}
          </div>

          {brief.events.length > 0 && (
            <ul className="mt-4 space-y-1 border-t border-edge-soft pt-3">
              {brief.events.map((event, i) => (
                <li key={i} className="flex items-baseline gap-3 text-sm">
                  <span className="w-16 shrink-0 font-mono text-xs text-ink-faint">
                    {eventTime(event.start)}
                  </span>
                  <span>{event.title}</span>
                  {event.location && <span className="text-ink-faint">· {event.location}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
