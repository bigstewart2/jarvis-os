import { useEffect, useState } from "react";
import type { Automation, AutomationRunSummary } from "../api/client";
import { fetchAutomationRuns, fetchAutomations } from "../api/client";
import { Card, EmptyHint } from "../components/Card";
import { relativeTime } from "../lib/format";

const POLL_INTERVAL_MS = 5000;

function runTone(status: string): string {
  if (status === "completed") return "text-ok";
  if (status === "failed") return "text-danger";
  return "text-ink-mute";
}

export function AutomationsWidget() {
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [runs, setRuns] = useState<AutomationRunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = () => {
      Promise.all([fetchAutomations(), fetchAutomationRuns(10)])
        .then(([nextAutomations, nextRuns]) => {
          if (cancelled) return;
          setAutomations(nextAutomations);
          setRuns(nextRuns);
          setError(null);
        })
        .catch((err) => {
          if (cancelled) return;
          setError(err instanceof Error ? err.message : String(err));
        });
    };

    load();
    const intervalId = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, []);

  return (
    <Card title="Automations">
      {error && (
        <p data-testid="automations-widget-error" className="mb-2 text-sm text-danger">
          {error}
        </p>
      )}
      {!error && automations.length === 0 && <EmptyHint>No automations defined.</EmptyHint>}
      <ul className="space-y-1.5">
        {automations.map((automation) => (
          <li key={automation.id} className="flex items-baseline justify-between gap-3 text-sm">
            <span>{automation.name ?? automation.id}</span>
            <span className="shrink-0 font-mono text-xs text-ink-faint">
              {automation.status}
              {automation.last_run &&
                ` · last ${automation.last_run.status} ${relativeTime(automation.last_run.finished_at)}`}
            </span>
          </li>
        ))}
      </ul>
      {runs.length > 0 && (
        <>
          <h3 className="mb-1.5 mt-4 text-xs font-semibold text-ink-mute">Recent runs</h3>
          <ul className="space-y-1">
            {runs.map((run) => (
              <li key={run.run_id} className="flex items-baseline justify-between gap-3 text-xs">
                <span className="text-ink-mute">{run.automation_id}</span>
                <span className={`shrink-0 font-mono ${runTone(run.status)}`}>
                  {run.status}
                  {run.finished_at ? ` · ${relativeTime(run.finished_at)}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
