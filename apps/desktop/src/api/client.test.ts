import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchSkills, invokeSkill } from "./client";

describe("fetchSkills", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed skill manifests on success", async () => {
    const mockSkills = [
      {
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
      },
    ];
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockSkills,
    } as Response);

    const result = await fetchSkills();

    expect(result).toEqual(mockSkills);
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8420/skills");
  });

  it("throws when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    } as Response);

    await expect(fetchSkills()).rejects.toThrow("Failed to fetch skills: 500");
  });
});

describe("invokeSkill", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns outputs on success", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ outputs: { text: "hello" } }),
    } as Response);

    const result = await invokeSkill("echo", { text: "hello" });

    expect(result).toEqual({ outputs: { text: "hello" } });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8420/skills/echo/invoke",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inputs: { text: "hello" } }),
      }
    );
  });

  it("throws with status and body when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Unknown skill: nope" }),
    } as Response);

    await expect(invokeSkill("nope", {})).rejects.toThrow(
      'Failed to invoke skill nope: 404 {"detail":"Unknown skill: nope"}'
    );
  });
});
