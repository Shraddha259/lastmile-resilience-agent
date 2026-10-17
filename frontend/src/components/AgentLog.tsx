import { ShieldX } from "lucide-react";
import { ACTOR_LABEL, ACTOR_STYLE } from "../lib/ai";
import { statusLabel } from "../lib/status";
import { fmtTime } from "../lib/time";
import type { AgentEvent } from "../types.gen";

type Props = {
  events: AgentEvent[];
  onSelect?: (rid: string) => void;
  loading?: boolean;
  error?: string | null;
};

/** Audit log stream (PRD §16.3): newest first, actor badge, reason, model, latency. */
export function AgentLog({ events, onSelect, loading, error }: Props) {
  return (
    <section
      aria-label="Agent log"
      className="flex h-full max-h-[32rem] flex-col rounded-lg bg-white shadow-sm"
    >
      <div className="flex items-center justify-between border-b p-3">
        <h2 className="font-semibold">Agent log</h2>
        <span className="text-xs text-slate-600">latest {events.length} (max 200)</span>
      </div>
      {error && (
        <p role="alert" className="p-3 text-sm text-red-700">
          Error: {error}
        </p>
      )}
      {loading && !events.length && <p className="p-3 text-sm text-slate-600">Loading…</p>}
      {!loading && !events.length && !error && <p className="p-3 text-sm text-slate-600">No activity yet.</p>}
      <ol className="flex-1 divide-y overflow-auto text-sm">
        {events.map((e, i) => {
          const blocked = e.result === "rejected" || e.result === "failed";
          return (
            <li key={`${String(e.ts)}-${i}`} className="px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="tabular-nums text-xs text-slate-600">{fmtTime(e.ts)}</span>
                <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${ACTOR_STYLE[e.actor] ?? ""}`}>
                  {ACTOR_LABEL[e.actor] ?? e.actor}
                </span>
                {e.resident_id && (
                  <button
                    type="button"
                    className="font-mono text-xs text-blue-800 underline-offset-2 hover:underline"
                    onClick={() => onSelect?.(e.resident_id!)}
                  >
                    {e.resident_id}
                  </button>
                )}
                {e.tool && <code className="text-xs text-slate-800">{e.tool}</code>}
                {e.event_type === "AGENT_DECISION" && (
                  <span className="text-xs font-semibold text-purple-900">plan</span>
                )}
                {e.status_from && e.status_to && (
                  <span className="text-xs text-slate-700">
                    {statusLabel(e.status_from)} → <strong>{statusLabel(e.status_to)}</strong>
                  </span>
                )}
                {blocked && (
                  <span className="inline-flex items-center gap-1 rounded bg-red-100 px-1.5 py-0.5 text-xs font-semibold text-red-900">
                    <ShieldX size={12} aria-hidden="true" />
                    {e.result === "rejected" ? "Blocked by validator" : "Tool failed"}
                  </span>
                )}
                {(e.model || e.latency_ms != null) && (
                  <span className="ml-auto text-xs text-slate-500">
                    {e.model ?? ""}
                    {e.latency_ms != null ? ` · ${e.latency_ms} ms` : ""}
                  </span>
                )}
              </div>
              {(e.reason || e.args_summary) && (
                <p className="mt-0.5 text-slate-800">
                  {e.reason}
                  {e.args_summary && <span className="text-slate-500"> — {e.args_summary}</span>}
                </p>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
