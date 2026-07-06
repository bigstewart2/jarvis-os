import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { VoiceButton } from "./VoiceButton";
import * as client from "../api/client";

afterEach(() => cleanup());

class FakeMediaRecorder {
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(_stream: unknown) {}
  start() {}
  stop() {
    this.ondataavailable?.({ data: new Blob(["chunk"]) });
    this.onstop?.();
  }
}

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  constructor(_url: string) {}
  close() {}
}

function makeFakeStream() {
  const tracks = [{ stop: vi.fn() }, { stop: vi.fn() }];
  return { tracks, stream: { getTracks: () => tracks } };
}

beforeEach(() => {
  vi.restoreAllMocks();
  const { stream } = makeFakeStream();
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    configurable: true,
  });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.stubGlobal("WebSocket", FakeWebSocket);
});

describe("VoiceButton", () => {
  it("renders in idle state with a hold-to-talk button", () => {
    render(<VoiceButton />);
    expect(screen.getByTestId("voice-button")).toHaveTextContent("Hold to talk");
  });

  it("records then invokes voice and shows the result on release", async () => {
    vi.spyOn(client, "invokeVoice").mockResolvedValue({
      invocation_id: "abc-123",
      transcript: "what is two plus two",
      skill_id: "ask",
      fallback_used: true,
      fallback_reason: "model_chose_ask",
      outputs: { response: "4" },
      response_text: "4",
      audio_url: null,
      error: null,
    });

    render(<VoiceButton />);
    const button = screen.getByTestId("voice-button");

    fireEvent.mouseDown(button);
    expect(button).toHaveTextContent("Recording");

    fireEvent.mouseUp(button);

    await waitFor(() => {
      expect(screen.getByTestId("voice-result")).toHaveTextContent("what is two plus two");
    });
    expect(screen.getByTestId("voice-result")).toHaveTextContent("fell back to ask");

    const call = (client.invokeVoice as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(typeof call[1]).toBe("string");
    expect(call[1].length).toBeGreaterThan(0);
  });

  it("shows an error message when invokeVoice rejects", async () => {
    vi.spyOn(client, "invokeVoice").mockRejectedValue(new Error("backend down"));

    render(<VoiceButton />);
    const button = screen.getByTestId("voice-button");
    fireEvent.mouseDown(button);
    fireEvent.mouseUp(button);

    await waitFor(() => {
      expect(screen.getByTestId("voice-error")).toHaveTextContent("backend down");
    });
  });

  it("recovers to idle and shows an error when getUserMedia rejects (mic permission denied)", async () => {
    Object.defineProperty(navigator, "mediaDevices", {
      value: {
        getUserMedia: vi.fn().mockRejectedValue(new DOMException("Permission denied", "NotAllowedError")),
      },
      configurable: true,
    });

    render(<VoiceButton />);
    const button = screen.getByTestId("voice-button");

    fireEvent.mouseDown(button);

    await waitFor(() => {
      expect(screen.getByTestId("voice-error")).toBeInTheDocument();
    });
    expect(button).toHaveTextContent("Hold to talk");
  });

  it("stops every MediaStream track after a recording completes", async () => {
    const { tracks, stream } = makeFakeStream();
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
      configurable: true,
    });
    vi.spyOn(client, "invokeVoice").mockResolvedValue({
      invocation_id: "abc-123",
      transcript: "hello",
      skill_id: "echo",
      fallback_used: false,
      fallback_reason: null,
      outputs: { text: "hi" },
      response_text: "hi",
      audio_url: null,
      error: null,
    });

    render(<VoiceButton />);
    const button = screen.getByTestId("voice-button");

    fireEvent.mouseDown(button);
    fireEvent.mouseUp(button);

    await waitFor(() => {
      expect(screen.getByTestId("voice-result")).toBeInTheDocument();
    });

    for (const track of tracks) {
      expect(track.stop).toHaveBeenCalled();
    }
  });
});
