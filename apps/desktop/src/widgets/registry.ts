import type { ComponentType } from "react";
import { AutomationsWidget } from "./AutomationsWidget";
import { SkillsWidget } from "./SkillsWidget";
import { TasksWidget } from "./TasksWidget";
import { VoiceWidget } from "./VoiceWidget";

export type WidgetId = "skills" | "voice" | "automations" | "tasks";

export const WIDGET_REGISTRY: Record<WidgetId, { label: string; component: ComponentType }> = {
  skills: { label: "Skills", component: SkillsWidget },
  voice: { label: "Voice", component: VoiceWidget },
  automations: { label: "Automations", component: AutomationsWidget },
  tasks: { label: "Claude Code Tasks", component: TasksWidget },
};

export const ALL_WIDGET_IDS: WidgetId[] = ["skills", "voice", "automations", "tasks"];
