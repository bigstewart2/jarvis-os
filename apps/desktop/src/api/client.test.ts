import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchSkills, invokeSkill, invokeVoice, voiceAudioUrl } from "./client";

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
    const result = await invokeVoice(blob);

    expect(result).toEqual(mockResult);
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toBe("http://127.0.0.1:8420/voice/invoke");
    expect(call[1].method).toBe("POST");
    expect((call[1].body as FormData).get("audio")).toBeInstanceOf(Blob);
  });

  it("throws when the response is not ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: "pipeline error" }),
    } as Response);

    const blob = new Blob(["fake-audio-bytes"], { type: "audio/webm" });
    await expect(invokeVoice(blob)).rejects.toThrow("Failed to invoke voice: 500");
  });
});

describe("voiceAudioUrl", () => {
  it("prefixes the path with the backend base URL", () => {
    expect(voiceAudioUrl("/voice/audio/abc-123")).toBe(
      "http://127.0.0.1:8420/voice/audio/abc-123"
    );
  });
});
