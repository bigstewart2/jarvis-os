import { useState } from "react";
import { useEventSocket } from "../lib/useEventSocket";
import type { JarvisEvent } from "../lib/useEventSocket";

export interface Toast {
  id: string;
  message: string;
  kind: "success" | "error";
}

const TOAST_DURATION_MS = 6000;

function messageForEvent(data: JarvisEvent): Toast | null {
  if (data.type === "automation_run" && (data.stage === "completed" || data.stage === "failed")) {
    return {
      id: `${data.run_id}-${data.stage}`,
      message:
        data.stage === "completed"
          ? `Automation "${data.automation_id}" completed.`
          : `Automation "${data.automation_id}" failed.`,
      kind: data.stage === "completed" ? "success" : "error",
    };
  }
  if (data.type === "claude_code_task" && (data.stage === "completed" || data.stage === "failed")) {
    return {
      id: `${data.task_id}-${data.stage}`,
      message: data.stage === "completed" ? `Task ${data.task_id} completed.` : `Task ${data.task_id} failed.`,
      kind: data.stage === "completed" ? "success" : "error",
    };
  }
  return null;
}

export function useEventToasts(): Toast[] {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEventSocket((data) => {
    const toast = messageForEvent(data);
    if (!toast) return;
    setToasts((prev) => [...prev, toast]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== toast.id));
    }, TOAST_DURATION_MS);
  });

  return toasts;
}
