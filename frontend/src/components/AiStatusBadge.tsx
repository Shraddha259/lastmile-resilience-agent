import { Bot, Cog, Sparkles } from "lucide-react";
import { aiStatus } from "../lib/ai";
import type { AgentEvent } from "../types.gen";

/** Header badge: is Gemini actually making the calls right now? (colour + icon + text) */
export function AiStatusBadge({ events }: { events: AgentEvent[] }) {
  const { mode, model } = aiStatus(events);
  const style = {
    live: {
      cls: "bg-green-100 text-green-900",
      Icon: Sparkles,
      text: `Gemini live${model ? ` · ${model}` : ""}`,
    },
    scripted: { cls: "bg-slate-200 text-slate-900", Icon: Bot, text: "AI scripted (fake mode)" },
    fallback: { cls: "bg-amber-100 text-amber-900", Icon: Cog, text: "Rule-based fallback" },
    idle: { cls: "bg-slate-100 text-slate-700", Icon: Bot, text: "AI idle" },
  }[mode];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${style.cls}`}
      title="Based on the latest decisions and classifications in the agent log"
    >
      <style.Icon size={13} aria-hidden="true" />
      {style.text}
    </span>
  );
}
