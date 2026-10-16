import { where } from "firebase/firestore";
import { ShieldCheck, Siren, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { ACTOR_LABEL, ACTOR_STYLE } from "../lib/ai";
import { usePasscode } from "../lib/passcode";
import { LANGUAGE_NAMES, statusLabel } from "../lib/status";
import { fmtTime, toDate } from "../lib/time";
import { useCollection, useDoc } from "../lib/useFirestore";
import type { AgentEvent, Case, Checkin, Resident, Task } from "../types.gen";
import { LiveTag, SimulatedTag } from "./SimulatedTag";
import { StatusBadge } from "./StatusBadge";

type Props = { incidentId: string; residentId: string; resident?: Resident; onClose: () => void };

const byTs = (a: { ts?: unknown }, b: { ts?: unknown }) =>
  (toDate(a.ts)?.getTime() ?? 0) - (toDate(b.ts)?.getTime() ?? 0);

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase text-slate-500">{label}</dt>
      <dd className="text-slate-900">{children}</dd>
    </div>
  );
}

/** Coordinator override (PRD §16.3, US-4): confirm safe or escalate, note required. */
function Override({
  incidentId,
  residentId,
  status,
}: {
  incidentId: string;
  residentId: string;
  status?: string;
}) {
  const { passcode } = usePasscode();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const terminal = status === "CONFIRMED_SAFE" || status === "ESCALATED";

  async function run(to: "CONFIRMED_SAFE" | "ESCALATED") {
    setBusy(true);
    setMsg(null);
    try {
      await api.overrideCase(passcode, incidentId, residentId, to, note.trim());
      setNote("");
      setMsg({ ok: true, text: to === "CONFIRMED_SAFE" ? "Marked confirmed safe." : "Escalated." });
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError ? err.message : "Could not reach the LastMile API" });
    } finally {
      setBusy(false);
    }
  }

  if (status === "CONFIRMED_SAFE") return null;
  const ready = note.trim().length >= 5 && !!passcode && !busy;
  return (
    <section aria-label="Coordinator override" className="rounded border border-slate-300 p-3">
      <h3 className="font-semibold">Coordinator override</h3>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
        aria-label="Override note"
        placeholder="What did you confirm? (required, min 5 characters)"
        className="mt-1 w-full rounded border px-2 py-1"
      />
      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!ready}
          onClick={() => run("CONFIRMED_SAFE")}
          className="inline-flex items-center gap-1 rounded bg-green-700 px-2 py-1 text-white disabled:opacity-50"
        >
          <ShieldCheck size={14} aria-hidden="true" /> Mark confirmed safe
        </button>
        {!terminal && (
          <button
            type="button"
            disabled={!ready}
            onClick={() => run("ESCALATED")}
            className="inline-flex items-center gap-1 rounded bg-red-700 px-2 py-1 text-white disabled:opacity-50"
          >
            <Siren size={14} aria-hidden="true" /> Escalate
          </button>
        )}
      </div>
      {!passcode && <p className="mt-1 text-xs text-slate-600">Enter the passcode in the header to act.</p>}
      {msg && (
        <p
          role={msg.ok ? "status" : "alert"}
          className={`mt-1 text-sm ${msg.ok ? "text-green-800" : "text-red-700"}`}
        >
          {msg.text}
        </p>
      )}
    </section>
  );
}

/** Case detail panel (PRD §16.3): profile, risk, transcripts, classification, timeline. */
export function CaseDrawer({ incidentId, residentId, resident, onClose }: Props) {
  const base = `incidents/${incidentId}`;
  const caseDoc = useDoc<Case>(`${base}/cases/${residentId}`);
  // Single-field filters only (no composite index needed); sort on the client.
  const checkins = useCollection<Checkin>(
    `${base}/checkins`,
    [where("resident_id", "==", residentId)],
    residentId,
  );
  const events = useCollection<AgentEvent>(
    `${base}/agent_events`,
    [where("resident_id", "==", residentId)],
    residentId,
  );
  const c = caseDoc.data;
  const task = useDoc<Task>(c?.open_task_id ? `${base}/tasks/${c.open_task_id}` : null);
  const [english, setEnglish] = useState(true);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const timeline = useMemo(() => [...events.data].sort(byTs), [events.data]);
  const calls = useMemo(() => [...checkins.data].sort((a, b) => a.attempt - b.attempt), [checkins.data]);
  const latest = calls.at(-1)?.classification;

  return (
    <aside
      role="dialog"
      aria-modal="false"
      aria-labelledby="case-title"
      className="fixed inset-y-0 right-0 z-[1500] flex w-full max-w-xl flex-col bg-white shadow-2xl"
    >
      <header className="flex items-start justify-between gap-2 border-b p-4">
        <div>
          <h2 id="case-title" className="text-lg font-bold">
            {residentId} · {resident?.display_name ?? "…"}
          </h2>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            {c?.status && <StatusBadge status={c.status} />}
            {c?.channel === "live" ? <LiveTag /> : <SimulatedTag />}
            <span className="text-xs text-slate-600">Synthetic data</span>
          </div>
        </div>
        <button
          ref={closeRef}
          type="button"
          aria-label="Close case details"
          onClick={onClose}
          className="rounded p-1 hover:bg-slate-100"
        >
          <X size={20} aria-hidden="true" />
        </button>
      </header>

      <div className="flex-1 space-y-5 overflow-auto p-4 text-sm">
        {caseDoc.error && (
          <p role="alert" className="text-red-700">
            Error: {caseDoc.error}
          </p>
        )}

        <section aria-label="Profile">
          <dl className="grid grid-cols-2 gap-3">
            <Field label="Age">{resident?.age ?? c?.age}</Field>
            <Field label="Language">
              {(resident?.languages ?? []).map((l) => LANGUAGE_NAMES[l] ?? l).join(", ")}
              {resident?.dialect_hint ? ` (${resident.dialect_hint})` : ""}
            </Field>
            <Field label="Mobility">{resident?.mobility}</Field>
            <Field label="Floor / alone">
              {resident?.floor} · {resident?.lives_alone ? "lives alone" : "with others"}
            </Field>
            <Field label="Medical">{(resident?.medical_flags ?? []).join(", ") || "none"}</Field>
            <Field label="Needs">{(c?.needs ?? []).join(", ") || "—"}</Field>
          </dl>
        </section>

        <section aria-label="Risk">
          <h3 className="font-semibold">
            Risk {c?.risk_score} · {c?.priority}
          </h3>
          <ul className="mt-1 list-disc pl-5 text-slate-700">
            {(c?.risk_reasons ?? []).map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>

        {c?.last_summary_en && (
          <section aria-label="Summary">
            <h3 className="font-semibold">Latest summary</h3>
            <p className="text-slate-800">{c.last_summary_en}</p>
          </section>
        )}

        {latest && (
          <section aria-label="Classification">
            <h3 className="font-semibold">Classification</h3>
            <dl className="mt-1 grid grid-cols-2 gap-3">
              <Field label="Status">{statusLabel(latest.status)}</Field>
              <Field label="Confidence">{Math.round(latest.confidence * 100)}%</Field>
              <Field label="Location">{latest.location_now}</Field>
              <Field label="Medical flag">{latest.medical_flag ? "yes" : "no"}</Field>
              <Field label="Human review">
                {latest.requires_human_review ? (latest.review_reason ?? "yes") : "no"}
              </Field>
              <Field label="Others at risk">{latest.household_others_at_risk ? "yes" : "no"}</Field>
            </dl>
          </section>
        )}

        {task.data && (
          <section aria-label="Open task">
            <h3 className="font-semibold">Open task</h3>
            <p>
              {task.data.type.replaceAll("_", " ").toLowerCase()} · {task.data.urgency} · {task.data.status}
              {task.data.volunteer_id ? ` · ${task.data.volunteer_id}` : ""}
            </p>
            <p className="text-slate-700">{task.data.briefing_en}</p>
          </section>
        )}

        <Override incidentId={incidentId} residentId={residentId} status={c?.status} />

        <section aria-label="Calls">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Calls ({calls.length})</h3>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={english} onChange={(e) => setEnglish(e.target.checked)} />
              English
            </label>
          </div>
          {!calls.length && <p className="text-slate-600">No calls yet.</p>}
          {calls.map((ck) => (
            <div key={ck.checkin_id} className="mt-2 rounded border p-2">
              <p className="text-xs text-slate-600">
                Attempt {ck.attempt} · {ck.state.replaceAll("_", " ").toLowerCase()}
                {ck.duration_s != null ? ` · ${Math.round(ck.duration_s)} s` : ""}
                {ck.end_reason ? ` · ${ck.end_reason.replaceAll("_", " ")}` : ""}
              </p>
              {ck.transcript.length ? (
                <ol className="mt-1 space-y-1">
                  {ck.transcript.map((line, i) => (
                    <li key={i} className={line.role === "agent" ? "text-slate-700" : "font-medium"}>
                      <span className="text-xs uppercase text-slate-500">{line.role}: </span>
                      {english ? (line.text_en ?? line.text) : line.text}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-slate-500">No speech.</p>
              )}
            </div>
          ))}
        </section>

        <section aria-label="Timeline">
          <h3 className="font-semibold">Timeline</h3>
          {!timeline.length && <p className="text-slate-600">No events yet.</p>}
          <ol className="mt-1 space-y-1.5">
            {timeline.map((e, i) => (
              <li key={i} className="flex gap-2">
                <span className="tabular-nums text-xs text-slate-500">{fmtTime(e.ts)}</span>
                <span className={`h-fit rounded px-1 text-xs font-semibold ${ACTOR_STYLE[e.actor] ?? ""}`}>
                  {ACTOR_LABEL[e.actor] ?? e.actor}
                </span>
                <span className="text-slate-800">
                  {e.status_to ? <strong>{statusLabel(e.status_to)}</strong> : (e.tool ?? e.event_type)}
                  {e.reason ? ` — ${e.reason}` : ""}
                  {e.result === "rejected" ? " (blocked by validator)" : ""}
                </span>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </aside>
  );
}
