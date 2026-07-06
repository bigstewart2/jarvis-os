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
