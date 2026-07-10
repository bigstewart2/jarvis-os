import { useEffect, useRef } from "react";

const WS_URL = "ws://127.0.0.1:8420/ws";
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 10000;

export interface JarvisEvent {
  type: string;
  stage?: string;
  invocation_id?: string;
  run_id?: string;
  automation_id?: string;
  task_id?: string;
  detail?: Record<string, unknown>;
}

/**
 * Subscribes to the backend event bus. Unlike a bare `new WebSocket`, this
 * reconnects with backoff when the socket drops (backend restart, timeout),
 * so long-lived dashboards keep receiving events.
 */
export function useEventSocket(onEvent: (event: JarvisEvent) => void): void {
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let disposed = false;
    let attempts = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (disposed) return;
      ws = new WebSocket(WS_URL);
      ws.onopen = () => {
        attempts = 0;
      };
      ws.onmessage = (event) => {
        try {
          handlerRef.current(JSON.parse(event.data));
        } catch {
          // Ignore malformed frames; the bus only emits JSON.
        }
      };
      ws.onclose = () => {
        if (disposed) return;
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** attempts, RECONNECT_MAX_MS);
        attempts += 1;
        timer = setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      ws?.close();
    };
  }, []);
}
