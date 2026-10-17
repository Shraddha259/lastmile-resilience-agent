// Derive "is real AI being used?" from the audit log, so judges see it honestly.
import type { AgentEvent } from "../types.gen";

export type AiMode = "live" | "scripted" | "fallback" | "idle";

const NON_LIVE = new Set(["fake", "cached", "fallback", null, undefined, ""]);

/** Look at the most recent model-backed events (decisions + classifier) and summarise. */
export function aiStatus(events: AgentEvent[], window = 40): { mode: AiMode; model: string | null } {
  const recent = events.slice(0, window);
  const modelEvents = recent.filter((e) => e.event_type === "AGENT_DECISION" || e.tool === "classifier");
  const live = modelEvents.find((e) => !NON_LIVE.has(e.model));
  if (live) return { mode: "live", model: live.model ?? null };
  if (modelEvents.some((e) => e.model === "fake")) return { mode: "scripted", model: "fake" };
  if (recent.some((e) => e.actor === "policy" || e.model === "cached"))
    return { mode: "fallback", model: null };
  return { mode: "idle", model: null };
}

export const ACTOR_STYLE: Record<string, string> = {
  agent: "bg-purple-100 text-purple-900",
  policy: "bg-slate-200 text-slate-900",
  volunteer: "bg-teal-100 text-teal-900",
  coordinator: "bg-blue-100 text-blue-900",
  system: "bg-slate-100 text-slate-700",
};

export const ACTOR_LABEL: Record<string, string> = {
  agent: "Agent",
  policy: "Policy",
  volunteer: "Volunteer",
  coordinator: "Coordinator",
  system: "System",
};
