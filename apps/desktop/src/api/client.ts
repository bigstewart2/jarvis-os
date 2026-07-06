export interface SkillManifest {
  id: string;
  name: string;
  description: string;
  input_schema: {
    type?: string;
    properties?: Record<string, { type?: string }>;
    required?: string[];
  };
  output_schema: {
    type?: string;
    properties?: Record<string, { type?: string }>;
  };
  voice_invokable: boolean;
  ui_component: string | null;
}

const BASE_URL = "http://127.0.0.1:8420";

export async function fetchSkills(): Promise<SkillManifest[]> {
  const response = await fetch(`${BASE_URL}/skills`);
  if (!response.ok) {
    throw new Error(`Failed to fetch skills: ${response.status}`);
  }
  return response.json();
}

export async function invokeSkill(
  skillId: string,
  inputs: Record<string, string>
): Promise<{ outputs: Record<string, unknown> }> {
  const response = await fetch(`${BASE_URL}/skills/${skillId}/invoke`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inputs }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      `Failed to invoke skill ${skillId}: ${response.status} ${JSON.stringify(body)}`
    );
  }
  return response.json();
}

export interface VoiceInvokeResponse {
  invocation_id: string;
  transcript: string;
  skill_id: string | null;
  fallback_used: boolean;
  fallback_reason: string | null;
  outputs: Record<string, unknown> | null;
  response_text: string;
  audio_url: string | null;
  error: string | null;
}

export async function invokeVoice(audio: Blob): Promise<VoiceInvokeResponse> {
  const formData = new FormData();
  formData.append("audio", audio, "clip.webm");
  const response = await fetch(`${BASE_URL}/voice/invoke`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(`Failed to invoke voice: ${response.status} ${JSON.stringify(body)}`);
  }
  return response.json();
}

export function voiceAudioUrl(path: string): string {
  return `${BASE_URL}${path}`;
}
