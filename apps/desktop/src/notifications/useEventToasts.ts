import { useEffect, useState } from "react";

export interface Toast {
  id: string;
  message: string;
  kind: "success" | "error";
}

interface WSEvent {
  type: string;
  stage?: string;
  run_id?: string;
  automation_id?: string;
  task_id?: string;
}

const WS_URL = "ws://127.0.0.1:8420/ws";
const TOAST_DURATION_MS = 6000;

function messageForEvent(data: WSEvent): Toast | null {
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

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    ws.onmessage = (event) => {
      const data: WSEvent = JSON.parse(event.data);
      const toast = messageForEvent(data);
      if (!toast) return;
      setToasts((prev) => [...prev, toast]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== toast.id));
      }, TOAST_DURATION_MS);
    };
    return () => ws.close();
  }, []);

  return toasts;
}
