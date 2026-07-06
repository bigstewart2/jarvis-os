import { useEffect, useRef, useState } from "react";
import type { VoiceInvokeResponse } from "../api/client";
import { invokeVoice, voiceAudioUrl } from "../api/client";

type VoiceState = "idle" | "recording" | "processing" | "playing" | "error";

const WS_URL = "ws://127.0.0.1:8420/ws";

const STAGE_LABELS: Record<string, string> = {
  transcribing: "Transcribing…",
  routing: "Routing…",
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

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type !== "voice_status") return;
      if (data.invocation_id !== invocationIdRef.current) return;
      setStatusLabel(STAGE_LABELS[data.stage] ?? "");
    };
    return () => ws.close();
  }, []);

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
      if (response.audio_url && audioRef.current) {
        audioRef.current.src = voiceAudioUrl(response.audio_url);
        setState("playing");
        await audioRef.current.play().catch(() => {});
      } else {
        setState("idle");
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
      setState("error");
    }
  };

  return (
    <div className="rounded-lg border border-gray-300 p-4 mb-4">
      <button
        data-testid="voice-button"
        disabled={state === "processing"}
        onMouseDown={startRecording}
        onMouseUp={stopRecording}
        onMouseLeave={() => {
          if (state === "recording") stopRecording();
        }}
        className="bg-purple-600 text-white rounded px-3 py-1"
      >
        {state === "recording" ? "Recording… release to send" : "Hold to talk"}
      </button>
      {statusLabel && <p data-testid="voice-status">{statusLabel}</p>}
      {result && (
        <div data-testid="voice-result" className="mt-2 text-sm bg-gray-100 p-2 rounded">
          <p>Transcript: {result.transcript}</p>
          <p>
            Skill: {result.skill_id}
            {result.fallback_used && " (fell back to ask)"}
          </p>
          <p>{result.response_text}</p>
        </div>
      )}
      {errorMessage && (
        <p data-testid="voice-error" className="mt-2 text-sm text-red-600">
          {errorMessage}
        </p>
      )}
      <audio ref={audioRef} data-testid="voice-audio" onEnded={() => setState("idle")} />
    </div>
  );
}
