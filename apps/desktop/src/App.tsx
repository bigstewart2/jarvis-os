import { useEffect, useState } from "react";
import type { SkillManifest } from "./api/client";
import { fetchSkills } from "./api/client";
import { SkillForm } from "./components/SkillForm";
import { VoiceButton } from "./components/VoiceButton";

function App() {
  const [skills, setSkills] = useState<SkillManifest[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSkills()
      .then(setSkills)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  return (
    <main className="p-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Jarvis OS</h1>
      {error && (
        <p data-testid="app-error" className="text-red-600">
          {error}
        </p>
      )}
      <VoiceButton />
      {skills.map((skill) => (
        <SkillForm key={skill.id} skill={skill} />
      ))}
    </main>
  );
}

export default App;
