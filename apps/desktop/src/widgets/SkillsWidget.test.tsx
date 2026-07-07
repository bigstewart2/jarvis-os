import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { SkillsWidget } from "./SkillsWidget";
import * as client from "../api/client";
import type { SkillManifest } from "../api/client";

const echoManifest: SkillManifest = {
  id: "echo",
  name: "Echo",
  description: "Repeats back text.",
  input_schema: { type: "object", properties: { text: { type: "string" } }, required: ["text"] },
  output_schema: { type: "object", properties: { text: { type: "string" } } },
  voice_invokable: true,
  ui_component: null,
};

describe("SkillsWidget", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("renders a SkillForm for each fetched skill", async () => {
    vi.spyOn(client, "fetchSkills").mockResolvedValue([echoManifest]);

    render(<SkillsWidget />);

    await waitFor(() => {
      expect(screen.getByText("Echo")).toBeInTheDocument();
    });
  });

  it("shows an error if fetching skills fails", async () => {
    vi.spyOn(client, "fetchSkills").mockRejectedValue(new Error("network down"));

    render(<SkillsWidget />);

    await waitFor(() => {
      expect(screen.getByTestId("skills-widget-error")).toHaveTextContent("network down");
    });
  });
});
