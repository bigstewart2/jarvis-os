import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import App from "./App";
import * as client from "./api/client";
import type { SkillManifest } from "./api/client";

const echoManifest: SkillManifest = {
  id: "echo",
  name: "Echo",
  description: "Repeats back text.",
  input_schema: {
    type: "object",
    properties: { text: { type: "string" } },
    required: ["text"],
  },
  output_schema: { type: "object", properties: { text: { type: "string" } } },
  voice_invokable: true,
  ui_component: null,
};

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  constructor(_url: string) {}
  close() {}
}

describe("App", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    cleanup();
  });

  it("renders a SkillForm for each fetched skill", async () => {
    vi.spyOn(client, "fetchSkills").mockResolvedValue([echoManifest]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Echo")).toBeInTheDocument();
    });
  });

  it("shows an error if fetching skills fails", async () => {
    vi.spyOn(client, "fetchSkills").mockRejectedValue(new Error("network down"));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("app-error")).toHaveTextContent("network down");
    });
  });
});
