import { where } from "firebase/firestore";
import { Check, Siren, X } from "lucide-react";
import { useState } from "react";
import { ApiError, api } from "../api";
import { usePasscode } from "../lib/passcode";
import { useCollection } from "../lib/useFirestore";
import type { Resident, Task } from "../types.gen";

type Props = { incidentId: string; residents: Map<string, Resident>; onSelect: (rid: string) => void };

const URGENCY_STYLE: Record<string, string> = {
  CRITICAL: "bg-red-100 text-red-900",
  HIGH: "bg-amber-100 text-amber-900",
  NORMAL: "bg-slate-100 text-slate-800",
};

/** Coordinator queue (PRD §16.3, US-3): approve/reject dispatches; human-review items. */
export function TaskQueue({ incidentId, residents, onSelect }: Props) {
  const { passcode } = usePasscode();
  const pending = useCollection<Task>(
    `incidents/${incidentId}/tasks`,
    [where("status", "==", "PENDING_APPROVAL")],
    "pending",
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const dispatches = pending.data.filter((t) => t.type !== "HUMAN_REVIEW");
  const reviews = pending.data
    .filter((t) => t.type === "HUMAN_REVIEW")
    .sort((a, b) => (a.urgency === "CRITICAL" ? -1 : 0) - (b.urgency === "CRITICAL" ? -1 : 0));

  async function decide(t: Task, decision: "APPROVE" | "REJECT") {
    setBusy(t.task_id);
    setError(null);
    try {
      await api.decideTask(passcode, incidentId, t.task_id, decision, decision === "REJECT" ? note : "");
      setRejecting(null);
      setNote("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the LastMile API");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-label="Task queue" className="rounded-lg bg-white p-4 shadow-sm">
      <h2 className="font-semibold">Task queue</h2>
      {error && (
        <p role="alert" className="mt-1 text-sm text-red-700">
          {error}
        </p>
      )}
      {pending.error && (
        <p role="alert" className="mt-1 text-sm text-red-700">
          Error: {pending.error}
        </p>
      )}
      {!pending.data.length && !pending.loading && (
        <p className="mt-1 text-sm text-slate-600">Nothing waiting for a decision.</p>
      )}

      {dispatches.length > 0 && (
        <h3 className="mt-3 text-xs font-semibold uppercase text-slate-600">
          Approve dispatch ({dispatches.length})
        </h3>
      )}
      <ul className="mt-1 space-y-2">
        {dispatches.map((t) => (
          <li key={t.task_id} className="rounded border p-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="font-mono text-blue-800 underline-offset-2 hover:underline"
                onClick={() => onSelect(t.resident_id)}
              >
                {t.resident_id}
              </button>
              <span>{residents.get(t.resident_id)?.display_name}</span>
              <span className={`rounded px-1.5 text-xs font-semibold ${URGENCY_STYLE[t.urgency] ?? ""}`}>
                {t.urgency}
              </span>
              <span className="text-xs text-slate-600">
                {t.type.replaceAll("_", " ").toLowerCase()} · {t.volunteer_id}
              </span>
            </div>
            <p className="mt-1 text-slate-800">{t.briefing_en}</p>
            {rejecting === t.task_id ? (
              <div className="mt-2 flex gap-2">
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Why reject? (min 5 characters)"
                  aria-label={`Reason for rejecting ${t.task_id}`}
                  className="flex-1 rounded border px-2 py-1"
                  autoFocus
                />
                <button
                  type="button"
                  disabled={busy === t.task_id || note.trim().length < 5 || !passcode}
                  onClick={() => decide(t, "REJECT")}
                  className="rounded bg-red-700 px-2 text-white disabled:opacity-50"
                >
                  Reject
                </button>
                <button type="button" onClick={() => setRejecting(null)} className="rounded border px-2">
                  Cancel
                </button>
              </div>
            ) : (
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  disabled={busy === t.task_id || !passcode}
                  onClick={() => decide(t, "APPROVE")}
                  className="inline-flex items-center gap-1 rounded bg-green-700 px-2 py-1 text-white disabled:opacity-50"
                >
                  <Check size={14} aria-hidden="true" /> Approve
                </button>
                <button
                  type="button"
                  disabled={busy === t.task_id || !passcode}
                  onClick={() => {
                    setRejecting(t.task_id);
                    setNote("");
                  }}
                  className="inline-flex items-center gap-1 rounded border border-red-700 px-2 py-1 text-red-800 disabled:opacity-50"
                >
                  <X size={14} aria-hidden="true" /> Reject
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>

      {reviews.length > 0 && (
        <h3 className="mt-3 text-xs font-semibold uppercase text-slate-600">
          Needs a person ({reviews.length})
        </h3>
      )}
      <ul className="mt-1 space-y-1.5">
        {reviews.map((t) => (
          <li key={t.task_id}>
            <button
              type="button"
              onClick={() => onSelect(t.resident_id)}
              className="flex w-full items-start gap-2 rounded border p-2 text-left text-sm hover:bg-slate-50"
            >
              <Siren size={16} className="mt-0.5 shrink-0 text-red-700" aria-hidden="true" />
              <span>
                <span className="font-mono">{t.resident_id}</span>{" "}
                <span className={`rounded px-1 text-xs font-semibold ${URGENCY_STYLE[t.urgency] ?? ""}`}>
                  {t.urgency}
                </span>{" "}
                <span className="text-slate-800">{t.briefing_en}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      {!passcode && pending.data.length > 0 && (
        <p className="mt-2 text-xs text-slate-600">Enter the passcode in the header to act.</p>
      )}
    </section>
  );
}
