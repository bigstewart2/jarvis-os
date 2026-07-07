import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchSkills, invokeSkill, invokeVoice, voiceAudioUrl, fetchDashboardConfig, saveDashboardConfig, fetchAutomations, fetchAutomationRuns } from "./client";

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

describe("invokeVoice", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("posts multipart form data and returns the parsed pipeline result", async () => {
    const mockResult = {
      invocation_id: "abc-123",
      transcript: "what is two plus two",
      skill_id: "ask",
      fallback_used: true,
      fallback_reason: "model_chose_ask",
      outputs: { response: "4" },
      response_text: "4",
      audio_url: "/voice/audio/abc-123",
      error: null,
    };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResult,
    } as Response);

    const blob = new Blob(["fake-audio-bytes"], { type: "audio/webm" });
    const result = await invokeVoice(blob, "test-invocation-id");

    expect(result).toEqual(mockResult);
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toBe("http://127.0.0.1:8420/voice/invoke");
    expect(call[1].method).toBe("POST");
    expect((call[1].body as FormData).get("audio")).toBeInstanceOf(Blob);
    expect((call[1].body as FormData).get("invocation_id")).toBe("test-invocation-id");
  });

  it("throws when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: "pipeline error" }),
    } as Response);

    const blob = new Blob(["fake-audio-bytes"], { type: "audio/webm" });
    await expect(invokeVoice(blob, "test-invocation-id")).rejects.toThrow(
      "Failed to invoke voice: 500"
    );
  });
});

describe("voiceAudioUrl", () => {
  it("prefixes the path with the backend base URL", () => {
    expect(voiceAudioUrl("/voice/audio/abc-123")).toBe(
      "http://127.0.0.1:8420/voice/audio/abc-123"
    );
  });
});

describe("fetchDashboardConfig", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns the parsed dashboard config on success", async () => {
    const mockConfig = { widget_order: ["skills", "voice", "automations", "tasks"], hidden_widgets: [] };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockConfig,
    } as Response);

    const result = await fetchDashboardConfig();

    expect(result).toEqual(mockConfig);
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8420/dashboard/config");
  });

  it("throws when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    } as Response);

    await expect(fetchDashboardConfig()).rejects.toThrow("Failed to fetch dashboard config: 500");
  });
});

describe("saveDashboardConfig", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("PUTs the config and returns the parsed response on success", async () => {
    const mockConfig = { widget_order: ["voice", "skills", "tasks", "automations"], hidden_widgets: ["tasks"] };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockConfig,
    } as Response);

    const result = await saveDashboardConfig(mockConfig);

    expect(result).toEqual(mockConfig);
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8420/dashboard/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(mockConfig),
    });
  });

  it("throws with status and body when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "widget_order must be exactly a permutation of [...]" }),
    } as Response);

    await expect(
      saveDashboardConfig({ widget_order: ["skills"], hidden_widgets: [] })
    ).rejects.toThrow(/Failed to save dashboard config: 400/);
  });
});

describe("fetchAutomations", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed automations on success", async () => {
    const mockAutomations = [
      {
        id: "ask_digest",
        name: "Daily Ask Digest",
        enabled: true,
        status: "scheduled",
        last_run: { run_id: "run-1", status: "completed", finished_at: "2026-07-06T09:00:00Z" },
      },
    ];
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockAutomations,
    } as Response);

    const result = await fetchAutomations();

    expect(result).toEqual(mockAutomations);
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8420/automations");
  });

  it("throws when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 } as Response);

    await expect(fetchAutomations()).rejects.toThrow("Failed to fetch automations: 500");
  });
});

describe("fetchAutomationRuns", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed runs with the limit query param", async () => {
    const mockRuns = [
      { run_id: "run-1", automation_id: "ask_digest", status: "completed", started_at: "2026-07-06T09:00:00Z", finished_at: "2026-07-06T09:00:05Z" },
    ];
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockRuns,
    } as Response);

    const result = await fetchAutomationRuns(10);

    expect(result).toEqual(mockRuns);
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8420/automations/runs?limit=10");
  });

  it("throws when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 } as Response);

    await expect(fetchAutomationRuns(10)).rejects.toThrow("Failed to fetch automation runs: 500");
  });
});
