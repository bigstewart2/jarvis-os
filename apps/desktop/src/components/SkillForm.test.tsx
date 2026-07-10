import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { SkillForm } from "./SkillForm";
import * as client from "../api/client";
import type { SkillManifest } from "../api/client";

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

describe("SkillForm", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders one input per input_schema property and the run button", () => {
    render(<SkillForm skill={echoManifest} />);

    expect(screen.getByText("Echo")).toBeInTheDocument();
    expect(screen.getByLabelText("text")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run" })).toBeInTheDocument();
  });

  it("shows the result after a successful invoke", async () => {
    vi.spyOn(client, "invokeSkill").mockResolvedValue({ outputs: { text: "hi" } });

    render(<SkillForm skill={echoManifest} />);
    fireEvent.change(screen.getByLabelText("text"), { target: { value: "hi" } });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(screen.getByTestId("skill-result")).toHaveTextContent('"text": "hi"');
    });
    expect(client.invokeSkill).toHaveBeenCalledWith("echo", { text: "hi" });
  });

  it("shows an error message when invoke fails", async () => {
    vi.spyOn(client, "invokeSkill").mockRejectedValue(new Error("boom"));

    render(<SkillForm skill={echoManifest} />);
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(screen.getByTestId("skill-error")).toHaveTextContent("boom");
    });
  });
});
