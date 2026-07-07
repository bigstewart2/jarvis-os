import { useEffect, useState } from "react";
import type { SkillManifest } from "../api/client";
import { fetchSkills } from "../api/client";
import { SkillForm } from "../components/SkillForm";

export function SkillsWidget() {
  const [skills, setSkills] = useState<SkillManifest[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSkills()
      .then(setSkills)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  return (
    <div className="rounded-lg border border-gray-300 p-4">
      <h2 className="text-lg font-semibold mb-2">Skills</h2>
      {error && (
        <p data-testid="skills-widget-error" className="text-sm text-red-600 mb-2">
          {error}
        </p>
      )}
      {skills.map((skill) => (
        <SkillForm key={skill.id} skill={skill} />
      ))}
    </div>
  );
}
