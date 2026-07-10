import type { SkillManifest } from "../api/client";

const VOICE_EXAMPLES: Record<string, string> = {
  daily_brief: "Give me my daily brief.",
  get_calendar_events: "What's on my calendar for the next three days?",
  search_email: "Search my email for messages from recruiters.",
  search_notes: "Search my notes for interview prep.",
  read_note: "Read my note called Jarvis OS.",
  ask: "Anything else — questions fall through to the assistant.",
  speak: "Say: dinner is at seven.",
  echo: "Echo test.",
  claude_code_task: "Run a Claude Code task.",
};

export function CapabilitiesPanel({
  skills,
  onClose,
}: {
  skills: SkillManifest[];
  onClose: () => void;
}) {
  const voiceSkills = skills.filter((s) => s.voice_invokable);
  const buttonSkills = skills.filter((s) => !s.voice_invokable);

  return (
    <section
      data-testid="capabilities-panel"
      className="animate-rise rounded-card border border-edge-soft bg-surface px-5 py-4"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold">What can Jarvis do?</h2>
        <button
          onClick={onClose}
          aria-label="Close capabilities"
          className="rounded-md px-2 py-1 text-sm text-ink-mute transition-colors duration-150 hover:text-ink"
        >
          Close
        </button>
      </div>
      <p className="mt-1 max-w-prose text-sm text-ink-mute">
        Hold the talk button and say any of these. Every skill also runs as a button in the
        Skills panel, and automations can chain them on a schedule.
      </p>
      <ul className="mt-3 space-y-2">
        {voiceSkills.map((skill) => (
          <li key={skill.id} className="flex flex-wrap items-baseline gap-x-3 text-sm">
            <span className="w-40 shrink-0 font-medium">{skill.name}</span>
            <span className="text-ink-mute">
              "{VOICE_EXAMPLES[skill.id] ?? skill.description}"
            </span>
          </li>
        ))}
      </ul>
      {buttonSkills.length > 0 && (
        <p className="mt-3 border-t border-edge-soft pt-3 text-sm text-ink-faint">
          Button-only (deliberately not voice-triggered):{" "}
          {buttonSkills.map((s) => s.name).join(", ")}.
        </p>
      )}
    </section>
  );
}
