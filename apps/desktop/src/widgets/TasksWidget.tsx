import { useEffect, useState } from "react";
import type { Task } from "../api/client";
import { fetchTasks } from "../api/client";
import { Card, EmptyHint } from "../components/Card";
import { relativeTime } from "../lib/format";

const POLL_INTERVAL_MS = 5000;

const STATUS_STYLES: Record<string, string> = {
  completed: "text-ok",
  failed: "text-danger",
  running: "text-signal",
};

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
    <Card title="Claude Code Tasks">
      {error && (
        <p data-testid="tasks-widget-error" className="mb-2 text-sm text-danger">
          {error}
        </p>
      )}
      {!error && tasks.length === 0 && (
        <EmptyHint>No tasks yet — say "run a Claude Code task" or use the skill.</EmptyHint>
      )}
      <ul className="space-y-2">
        {tasks.map((task) => (
          <li key={task.task_id} className="text-sm">
            <p className="line-clamp-2">{task.prompt}</p>
            <p className="mt-0.5 font-mono text-xs text-ink-faint">
              <span className={STATUS_STYLES[task.status] ?? "text-ink-mute"}>
                {task.status}
              </span>
              {task.finished_at
                ? ` · ${relativeTime(task.finished_at)}`
                : task.created_at
                  ? ` · started ${relativeTime(task.created_at)}`
                  : ""}
            </p>
          </li>
        ))}
      </ul>
    </Card>
  );
}
