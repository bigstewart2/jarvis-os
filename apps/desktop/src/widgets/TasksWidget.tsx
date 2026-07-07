import { useEffect, useState } from "react";
import type { Task } from "../api/client";
import { fetchTasks } from "../api/client";

const POLL_INTERVAL_MS = 5000;

export function TasksWidget() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = () => {
      fetchTasks(10)
        .then((nextTasks) => {
          if (cancelled) return;
          setTasks(nextTasks);
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
      <h2 className="text-lg font-semibold mb-2">Claude Code Tasks</h2>
      {error && (
        <p data-testid="tasks-widget-error" className="text-sm text-red-600 mb-2">
          {error}
        </p>
      )}
      <ul>
        {tasks.map((task) => (
          <li key={task.task_id} className="text-sm mb-1">
            {task.task_id} — {task.status} — {task.prompt}
          </li>
        ))}
      </ul>
    </div>
  );
}
