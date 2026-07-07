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

export async function invokeVoice(audio: Blob, invocationId: string): Promise<VoiceInvokeResponse> {
  const formData = new FormData();
  formData.append("audio", audio, "clip.webm");
  formData.append("invocation_id", invocationId);
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

export interface DashboardConfig {
  widget_order: string[];
  hidden_widgets: string[];
}

export async function fetchDashboardConfig(): Promise<DashboardConfig> {
  const response = await fetch(`${BASE_URL}/dashboard/config`);
  if (!response.ok) {
    throw new Error(`Failed to fetch dashboard config: ${response.status}`);
  }
  return response.json();
}

export async function saveDashboardConfig(config: DashboardConfig): Promise<DashboardConfig> {
  const response = await fetch(`${BASE_URL}/dashboard/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(`Failed to save dashboard config: ${response.status} ${JSON.stringify(body)}`);
  }
  return response.json();
}

export interface Automation {
  id: string;
  name: string | null;
  enabled: boolean | null;
  status: string;
  last_run: { run_id: string; status: string; finished_at: string | null } | null;
}

export interface AutomationRunSummary {
  run_id: string;
  automation_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
}

export async function fetchAutomations(): Promise<Automation[]> {
  const response = await fetch(`${BASE_URL}/automations`);
  if (!response.ok) {
    throw new Error(`Failed to fetch automations: ${response.status}`);
  }
  return response.json();
}

export async function fetchAutomationRuns(limit: number): Promise<AutomationRunSummary[]> {
  const response = await fetch(`${BASE_URL}/automations/runs?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch automation runs: ${response.status}`);
  }
  return response.json();
}

export interface Task {
  task_id: string;
  status: string;
  prompt: string;
  created_at: string | null;
  finished_at: string | null;
}

export async function fetchTasks(limit: number): Promise<Task[]> {
  const response = await fetch(`${BASE_URL}/tasks?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch tasks: ${response.status}`);
  }
  return response.json();
}

export interface NoteMatch {
  path: string;
  title: string;
  excerpt: string;
  line_number: number;
}

export async function searchNotes(query: string): Promise<NoteMatch[]> {
  const result = await invokeSkill("search_notes", { query });
  return (result.outputs as { matches: NoteMatch[] }).matches;
}

export async function fetchNoteContent(path: string): Promise<string | null> {
  const result = await invokeSkill("read_note", { path });
  return (result.outputs as { content: string | null }).content;
}
