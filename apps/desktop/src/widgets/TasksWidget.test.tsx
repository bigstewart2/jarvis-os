import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { TasksWidget } from "./TasksWidget";
import * as client from "../api/client";

describe("TasksWidget", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("renders recent tasks", async () => {
    vi.spyOn(client, "fetchTasks").mockResolvedValue([
      { task_id: "task-1", status: "completed", prompt: "do X", created_at: "2026-07-06T09:00:00Z", finished_at: "2026-07-06T09:00:05Z" },
    ]);

    render(<TasksWidget />);

    await waitFor(() => {
      expect(screen.getByText(/task-1/)).toBeInTheDocument();
    });
  });

  it("shows an error if fetching tasks fails", async () => {
    vi.spyOn(client, "fetchTasks").mockRejectedValue(new Error("boom"));

    render(<TasksWidget />);

    await waitFor(() => {
      expect(screen.getByTestId("tasks-widget-error")).toHaveTextContent("boom");
    });
  });
});
