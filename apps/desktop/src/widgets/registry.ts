import type { ComponentType } from "react";
import { AutomationsWidget } from "./AutomationsWidget";
import { NotesWidget } from "./NotesWidget";
import { SkillsWidget } from "./SkillsWidget";
import { TasksWidget } from "./TasksWidget";
import { VoiceWidget } from "./VoiceWidget";

export type WidgetId = "skills" | "voice" | "automations" | "tasks" | "notes";

export const WIDGET_REGISTRY: Record<WidgetId, { label: string; component: ComponentType }> = {
  skills: { label: "Skills", component: SkillsWidget },
  voice: { label: "Voice", component: VoiceWidget },
  automations: { label: "Automations", component: AutomationsWidget },
  tasks: { label: "Claude Code Tasks", component: TasksWidget },
  notes: { label: "Notes", component: NotesWidget },
};

export const ALL_WIDGET_IDS: WidgetId[] = ["skills", "voice", "automations", "tasks", "notes"];
