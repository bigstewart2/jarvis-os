import { useRef, useState } from "react";
import type { VoiceInvokeResponse } from "../api/client";
import { invokeVoice, voiceAudioUrl } from "../api/client";
import { useEventSocket } from "../lib/useEventSocket";

type VoiceState = "idle" | "recording" | "processing" | "playing" | "error";

const STAGE_LABELS: Record<string, string> = {
  transcribing: "Transcribing…",
  routing: "Deciding what to do…",
  invoking_skill: "Running the skill…",
  synthesizing: "Speaking…",
  done: "",
  error: "Something went wrong.",
};

export function VoiceButton() {
  const [state, setState] = useState<VoiceState>("idle");
  const [statusLabel, setStatusLabel] = useState("");
  const [result, setResult] = useState<VoiceInvokeResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const invocationIdRef = useRef<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const stopRequestedRef = useRef(false);
  const streamRef = useRef<MediaStream | null>(null);

  useEventSocket((data) => {
    if (data.type !== "voice_status") return;
    if (data.invocation_id !== invocationIdRef.current) return;
    setStatusLabel(STAGE_LABELS[data.stage ?? ""] ?? "");
  });

  const startRecording = async () => {
    setErrorMessage(null);
    setResult(null);
    setState("recording");
    stopRequestedRef.current = false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        void handleRecordingComplete();
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      // The user may have already released the button before getUserMedia
      // resolved (a real race in push-to-talk UIs). Honor that immediately.
      if (stopRequestedRef.current) {
        recorder.stop();
      }
    } catch (err) {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      mediaRecorderRef.current = null;
      stopRequestedRef.current = false;
      setErrorMessage(
        err instanceof Error ? err.message : "Microphone access was denied."
      );
      setState("idle");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
    } else {
      stopRequestedRef.current = true;
    }
  };

  const handleRecordingComplete = async () => {
    mediaRecorderRef.current = null;
    setState("processing");
    setStatusLabel("Transcribing…");
    const invocationId = crypto.randomUUID();
    invocationIdRef.current = invocationId;
    const blob = new Blob(chunksRef.current, { type: "audio/webm" });
    try {
      const response = await invokeVoice(blob, invocationId);
      setResult(response);
      // Stage events may have been missed (socket mid-reconnect); the response
      // is the source of truth, so never leave a stale stage label behind.
      setStatusLabel("");
      if (response.audio_url && audioRef.current) {
        audioRef.current.src = voiceAudioUrl(response.audio_url);
        setState("playing");
        await audioRef.current.play().catch(() => {});
      } else {
        setState("idle");
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
      setStatusLabel("");
      setState("error");
    }
  };

  const recording = state === "recording";

  return (
    <div>
      <div className="flex items-center gap-3">
        <button
          data-testid="voice-button"
          disabled={state === "processing"}
          onMouseDown={startRecording}
          onMouseUp={stopRecording}
          onMouseLeave={() => {
            if (recording) stopRecording();
          }}
          className={
            recording
              ? "rounded-md bg-signal px-4 py-2 text-sm font-medium text-primary-ink"
              : "rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-ink transition-colors duration-150 hover:opacity-90 disabled:opacity-50"
          }
        >
          {recording ? "Listening — release to send" : "Hold to talk"}
        </button>
        {recording && (
          <span
            aria-hidden="true"
            className="h-2.5 w-2.5 animate-pulse-dot rounded-full bg-signal"
          />
        )}
        {statusLabel && (
          <p data-testid="voice-status" className="text-sm text-ink-mute">
            {statusLabel}
          </p>
        )}
      </div>
      <p className="mt-2 text-xs text-ink-faint">
        Try: "what's on my calendar tomorrow" · "search my notes for interview" · "give me my
        daily brief"
      </p>
      {result && (
        <div
          data-testid="voice-result"
          className="mt-3 animate-rise rounded-md border border-edge-soft bg-surface-2 px-3 py-2 text-sm"
        >
          <p className="text-ink-mute">"{result.transcript}"</p>
          <p className="mt-2 whitespace-pre-wrap">{result.response_text}</p>
          <p className="mt-2 font-mono text-xs text-ink-faint">
            {result.skill_id}
            {result.fallback_used && " · fell back to ask"}
          </p>
        </div>
      )}
      {errorMessage && (
        <p data-testid="voice-error" className="mt-2 text-sm text-danger">
          {errorMessage}
        </p>
      )}
      <audio ref={audioRef} data-testid="voice-audio" onEnded={() => setState("idle")} />
    </div>
  );
}
