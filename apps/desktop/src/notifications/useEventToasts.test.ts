import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useEventToasts } from "./useEventToasts";

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  constructor(_url: string) {}
  close() {}
}

let currentFakeSocket: FakeWebSocket;

describe("useEventToasts", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "WebSocket",
      class extends FakeWebSocket {
        constructor(url: string) {
          super(url);
          currentFakeSocket = this;
        }
      }
    );
  });

  it("adds a success toast when an automation_run completed event arrives", async () => {
    const { result } = renderHook(() => useEventToasts());

    act(() => {
      currentFakeSocket.onmessage?.({
        data: JSON.stringify({ type: "automation_run", stage: "completed", run_id: "run-1", automation_id: "ask_digest" }),
      });
    });

    await waitFor(() => {
      expect(result.current).toHaveLength(1);
    });
    expect(result.current[0].kind).toBe("success");
    expect(result.current[0].message).toContain("ask_digest");
  });

  it("adds an error toast when a claude_code_task failed event arrives", async () => {
    const { result } = renderHook(() => useEventToasts());

    act(() => {
      currentFakeSocket.onmessage?.({
        data: JSON.stringify({ type: "claude_code_task", stage: "failed", task_id: "task-1" }),
      });
    });

    await waitFor(() => {
      expect(result.current).toHaveLength(1);
    });
    expect(result.current[0].kind).toBe("error");
  });

  it("ignores events that are not a completion/failure of a tracked type", () => {
    const { result } = renderHook(() => useEventToasts());

    act(() => {
      currentFakeSocket.onmessage?.({
        data: JSON.stringify({ type: "automation_run", stage: "started", run_id: "run-1", automation_id: "ask_digest" }),
      });
    });

    expect(result.current).toHaveLength(0);
  });
});
