import { useEffect, useState } from "react";
import type { Automation, AutomationRunSummary } from "../api/client";
import { fetchAutomationRuns, fetchAutomations } from "../api/client";

const POLL_INTERVAL_MS = 5000;

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
    <div className="rounded-lg border border-gray-300 p-4">
      <h2 className="text-lg font-semibold mb-2">Automations</h2>
      {error && (
        <p data-testid="automations-widget-error" className="text-sm text-red-600 mb-2">
          {error}
        </p>
      )}
      <ul className="mb-3">
        {automations.map((automation) => (
          <li key={automation.id} className="text-sm mb-1">
            <span>{automation.name ?? automation.id}</span> — {automation.status}
          </li>
        ))}
      </ul>
      <h3 className="text-sm font-semibold mb-1">Recent runs</h3>
      <ul>
        {runs.map((run) => (
          <li key={run.run_id} className="text-sm text-gray-600 mb-1">
            {run.run_id} ({run.automation_id}) — {run.status}
          </li>
        ))}
      </ul>
    </div>
  );
}
