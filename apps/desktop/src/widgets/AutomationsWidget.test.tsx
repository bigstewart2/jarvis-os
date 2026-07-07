import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { AutomationsWidget } from "./AutomationsWidget";
import * as client from "../api/client";

describe("AutomationsWidget", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("renders automations and recent runs", async () => {
    vi.spyOn(client, "fetchAutomations").mockResolvedValue([
      { id: "ask_digest", name: "Daily Ask Digest", enabled: true, status: "scheduled", last_run: null },
    ]);
    vi.spyOn(client, "fetchAutomationRuns").mockResolvedValue([
      { run_id: "run-1", automation_id: "ask_digest", status: "completed", started_at: "2026-07-06T09:00:00Z", finished_at: "2026-07-06T09:00:05Z" },
    ]);

    render(<AutomationsWidget />);

    await waitFor(() => {
      expect(screen.getByText("Daily Ask Digest")).toBeInTheDocument();
      expect(screen.getByText(/run-1/)).toBeInTheDocument();
    });
  });

  it("shows an error if fetching automations fails", async () => {
    vi.spyOn(client, "fetchAutomations").mockRejectedValue(new Error("boom"));
    vi.spyOn(client, "fetchAutomationRuns").mockResolvedValue([]);

    render(<AutomationsWidget />);

    await waitFor(() => {
      expect(screen.getByTestId("automations-widget-error")).toHaveTextContent("boom");
    });
  });
});
