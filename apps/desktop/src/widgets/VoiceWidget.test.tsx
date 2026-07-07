import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { VoiceWidget } from "./VoiceWidget";

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  constructor(_url: string) {}
  close() {}
}

describe("VoiceWidget", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("renders the voice button", () => {
    render(<VoiceWidget />);

    expect(screen.getByTestId("voice-button")).toBeInTheDocument();
  });
});
