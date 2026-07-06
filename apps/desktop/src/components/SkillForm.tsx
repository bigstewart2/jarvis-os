import { useState } from "react";
import type { SkillManifest } from "../api/client";
import { invokeSkill } from "../api/client";

interface SkillFormProps {
  skill: SkillManifest;
}

export function SkillForm({ skill }: SkillFormProps) {
  const fieldNames = Object.keys(skill.input_schema.properties ?? {});
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fieldNames.map((name) => [name, ""]))
  );
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (name: string, value: string) => {
    setValues((prev) => ({ ...prev, [name]: value }));
  };

  const handleInvoke = async () => {
    setError(null);
    setResult(null);
    try {
      const response = await invokeSkill(skill.id, values);
      setResult(response.outputs);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="rounded-lg border border-gray-300 p-4 mb-4">
      <h2 className="text-lg font-semibold">{skill.name}</h2>
      <p className="text-sm text-gray-600 mb-2">{skill.description}</p>
      {fieldNames.map((name) => (
        <input
          key={name}
          aria-label={name}
          value={values[name]}
          onChange={(e) => handleChange(name, e.target.value)}
          className="border border-gray-300 rounded px-2 py-1 mr-2 mb-2"
        />
      ))}
      <button onClick={handleInvoke} className="bg-blue-600 text-white rounded px-3 py-1">
        Invoke
      </button>
      {result && (
        <pre data-testid="skill-result" className="mt-2 text-sm bg-gray-100 p-2 rounded">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
      {error && (
        <p data-testid="skill-error" className="mt-2 text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
