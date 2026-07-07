import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, render, screen, fireEvent, waitFor, cleanup, within } from "@testing-library/react";
import App from "./App";
import * as client from "./api/client";

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  static instances: FakeWebSocket[] = [];
  constructor(_url: string) {
    FakeWebSocket.instances.push(this);
  }
  close() {}
}

const defaultConfig = {
  widget_order: ["skills", "voice", "automations", "tasks", "notes"],
  hidden_widgets: [],
};

function mockBaseFetches() {
  vi.spyOn(client, "fetchDashboardConfig").mockResolvedValue(defaultConfig);
  vi.spyOn(client, "fetchSkills").mockResolvedValue([]);
  vi.spyOn(client, "fetchAutomations").mockResolvedValue([]);
  vi.spyOn(client, "fetchAutomationRuns").mockResolvedValue([]);
  vi.spyOn(client, "fetchTasks").mockResolvedValue([]);
}

describe("App", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    cleanup();
  });

  it("renders all 5 widgets in the configured order by default", async () => {
    mockBaseFetches();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });
    expect(screen.getByText("Voice")).toBeInTheDocument();
    expect(screen.getByText("Automations")).toBeInTheDocument();
    expect(screen.getByText("Claude Code Tasks")).toBeInTheDocument();
    expect(screen.getByText("Notes")).toBeInTheDocument();
  });

  it("hides a widget listed in hidden_widgets", async () => {
    vi.spyOn(client, "fetchDashboardConfig").mockResolvedValue({
      widget_order: ["skills", "voice", "automations", "tasks", "notes"],
      hidden_widgets: ["voice"],
    });
    vi.spyOn(client, "fetchSkills").mockResolvedValue([]);
    vi.spyOn(client, "fetchAutomations").mockResolvedValue([]);
    vi.spyOn(client, "fetchAutomationRuns").mockResolvedValue([]);
    vi.spyOn(client, "fetchTasks").mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });
    expect(screen.queryByText("Voice")).not.toBeInTheDocument();
  });

  it("ignores an unknown widget id present in a stale saved config", async () => {
    vi.spyOn(client, "fetchDashboardConfig").mockResolvedValue({
      widget_order: ["skills", "voice", "automations", "tasks", "bogus-old-widget"],
      hidden_widgets: [],
    });
    vi.spyOn(client, "fetchSkills").mockResolvedValue([]);
    vi.spyOn(client, "fetchAutomations").mockResolvedValue([]);
    vi.spyOn(client, "fetchAutomationRuns").mockResolvedValue([]);
    vi.spyOn(client, "fetchTasks").mockResolvedValue([]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });
    expect(screen.getByText("Claude Code Tasks")).toBeInTheDocument();
  });

  it("shows an error if fetching the dashboard config fails", async () => {
    vi.spyOn(client, "fetchDashboardConfig").mockRejectedValue(new Error("network down"));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("app-error")).toHaveTextContent("network down");
    });
  });

  it("opens the Customize panel, hides a widget, and saves", async () => {
    mockBaseFetches();
    vi.spyOn(client, "saveDashboardConfig").mockResolvedValue({
      widget_order: ["skills", "voice", "automations", "tasks", "notes"],
      hidden_widgets: ["voice"],
    });

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Customize" }));
    const panel = screen.getByTestId("customize-panel");
    fireEvent.click(within(panel).getByLabelText("Voice"));
    fireEvent.click(within(panel).getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(client.saveDashboardConfig).toHaveBeenCalledWith({
        widget_order: ["skills", "voice", "automations", "tasks", "notes"],
        hidden_widgets: ["voice"],
      });
    });
    expect(screen.queryByTestId("customize-panel")).not.toBeInTheDocument();
  });

  it("shows an inline error and keeps the panel open when saving fails", async () => {
    mockBaseFetches();
    vi.spyOn(client, "saveDashboardConfig").mockRejectedValue(new Error("widget_order must be exactly a permutation"));

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Customize" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(screen.getByTestId("customize-error")).toHaveTextContent("widget_order must be exactly a permutation");
    });
    expect(screen.getByTestId("customize-panel")).toBeInTheDocument();
  });

  it("upgrades a stale 4-widget config to include the missing widget and saves the full permutation", async () => {
    vi.spyOn(client, "fetchDashboardConfig").mockResolvedValue({
      widget_order: ["skills", "voice", "automations", "tasks"],
      hidden_widgets: [],
    });
    vi.spyOn(client, "fetchSkills").mockResolvedValue([]);
    vi.spyOn(client, "fetchAutomations").mockResolvedValue([]);
    vi.spyOn(client, "fetchAutomationRuns").mockResolvedValue([]);
    vi.spyOn(client, "fetchTasks").mockResolvedValue([]);
    vi.spyOn(client, "saveDashboardConfig").mockResolvedValue({
      widget_order: ["skills", "voice", "automations", "tasks", "notes"],
      hidden_widgets: [],
    });

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Customize" }));
    const panel = screen.getByTestId("customize-panel");
    expect(within(panel).getByLabelText("Notes")).toBeInTheDocument();

    fireEvent.click(within(panel).getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(client.saveDashboardConfig).toHaveBeenCalledWith({
        widget_order: ["skills", "voice", "automations", "tasks", "notes"],
        hidden_widgets: [],
      });
    });
    expect(screen.queryByTestId("customize-panel")).not.toBeInTheDocument();
  });

  it("shows a toast when an automation_run completed event arrives over the WebSocket", async () => {
    mockBaseFetches();

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText("Skills")).toBeInTheDocument();
    });

    act(() => {
      FakeWebSocket.instances.forEach((ws) =>
        ws.onmessage?.({
          data: JSON.stringify({ type: "automation_run", stage: "completed", run_id: "run-1", automation_id: "ask_digest" }),
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId("toast")).toHaveTextContent("ask_digest");
    });
  });
});
