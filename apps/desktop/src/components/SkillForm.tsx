import { useState } from "react";
import type { SkillManifest } from "../api/client";
import { invokeSkill } from "../api/client";

interface SkillFormProps {
  skill: SkillManifest;
}

function OutputValue({ value }: { value: unknown }) {
  if (typeof value === "string") {
    return <p className="whitespace-pre-wrap text-sm">{value}</p>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <p className="text-sm text-ink-faint">No results.</p>;
    return (
      <ul className="space-y-2">
        {value.map((item, i) => (
          <li key={i} className="rounded-md bg-surface-2 px-3 py-2 text-sm">
            {typeof item === "object" && item !== null ? (
              Object.entries(item as Record<string, unknown>)
                .filter(([, v]) => v !== "" && v !== null)
                .map(([k, v]) => (
                  <p key={k}>
                    <span className="text-ink-faint">{k.replace(/_+$/, "")}: </span>
                    {String(v)}
                  </p>
                ))
            ) : (
              String(item)
            )}
          </li>
        ))}
      </ul>
    );
  }
  return <p className="text-sm">{String(value)}</p>;
}

export function SkillForm({ skill }: SkillFormProps) {
  const fieldNames = Object.keys(skill.input_schema.properties ?? {});
  const required = new Set(skill.input_schema.required ?? []);
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fieldNames.map((name) => [name, ""]))
  );
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const handleChange = (name: string, value: string) => {
    setValues((prev) => ({ ...prev, [name]: value }));
  };

  const handleInvoke = async () => {
    setError(null);
    setResult(null);
    setRunning(true);
    try {
      const response = await invokeSkill(skill.id, values);
      setResult(response.outputs);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="border-b border-edge-soft py-3 last:border-b-0">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold">{skill.name}</h3>
        {skill.voice_invokable && (
          <span className="font-mono text-[0.65rem] text-ink-faint" title="Works by voice">
            voice
          </span>
        )}
      </div>
      <p className="mt-0.5 max-w-prose text-sm text-ink-mute">{skill.description}</p>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        {fieldNames.map((name) => (
          <label key={name} className="flex flex-col gap-1 text-xs text-ink-mute">
            {name.replace(/_/g, " ")}
            {required.has(name) ? "" : " (optional)"}
            <input
              aria-label={name}
              value={values[name]}
              onChange={(e) => handleChange(name, e.target.value)}
              className="rounded-md border border-edge bg-surface-2 px-2 py-1.5 text-sm text-ink placeholder:text-ink-faint"
            />
          </label>
        ))}
        <button
          onClick={handleInvoke}
          disabled={running}
          className="rounded-md border border-edge bg-surface-2 px-3 py-1.5 text-sm font-medium transition-colors duration-150 hover:border-primary disabled:opacity-50"
        >
          {running ? "Running…" : "Run"}
        </button>
      </div>
      {result && (
        <div data-testid="skill-result" className="mt-3 animate-rise space-y-3">
          {Object.entries(result).map(([key, value]) => (
            <div key={key}>
              {Object.keys(result).length > 1 && (
                <p className="mb-1 font-mono text-[0.65rem] text-ink-faint">{key}</p>
              )}
              <OutputValue value={value} />
            </div>
          ))}
          <details className="text-xs text-ink-faint">
            <summary className="cursor-pointer">Raw output</summary>
            <pre className="mt-1 overflow-x-auto rounded-md bg-surface-2 p-2 font-mono">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      )}
      {error && (
        <p data-testid="skill-error" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
