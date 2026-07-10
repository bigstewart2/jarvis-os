import { useEffect, useState } from "react";
import type { SkillManifest } from "../api/client";
import { fetchSkills } from "../api/client";
import { SkillForm } from "../components/SkillForm";
import { Card, EmptyHint } from "../components/Card";

export function SkillsWidget() {
  const [skills, setSkills] = useState<SkillManifest[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSkills()
      .then(setSkills)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  return (
    <Card title="Skills">
      {error && (
        <p data-testid="skills-widget-error" className="mb-2 text-sm text-danger">
          {error}
        </p>
      )}
      {!error && skills.length === 0 && <EmptyHint>No skills loaded yet.</EmptyHint>}
      {skills.map((skill) => (
        <SkillForm key={skill.id} skill={skill} />
      ))}
    </Card>
  );
}
