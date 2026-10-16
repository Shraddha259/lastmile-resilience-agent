import { limit, orderBy } from "firebase/firestore";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { AgentLog } from "../components/AgentLog";
import { AiStatusBadge } from "../components/AiStatusBadge";
import { CaseDrawer } from "../components/CaseDrawer";
import { Footer } from "../components/Footer";
import { MapView } from "../components/MapView";
import { NokToasts } from "../components/NokToasts";
import { SafeCounter } from "../components/SafeCounter";
import { SitrepPanel } from "../components/SitrepPanel";
import { StatusBoard } from "../components/StatusBoard";
import { TaskQueue } from "../components/TaskQueue";
import { usePasscode } from "../lib/passcode";
import { fmtDuration, toDate } from "../lib/time";
import { useCollection, useDoc } from "../lib/useFirestore";
import type { AgentEvent, Case, Incident, Resident, Shelter, Volunteer } from "../types.gen";

function useNow(ms = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

/** Coordinator console (PRD §16.3): map, counter, task queue, SITREP, board, agent log, drawer. */
export function Console() {
  const { incidentId = "" } = useParams();
  const navigate = useNavigate();
  const { passcode, setPasscode } = usePasscode();
  const incident = useDoc<Incident>(`incidents/${incidentId}`);
  const cases = useCollection<Case>(`incidents/${incidentId}/cases`);
  const residentsList = useCollection<Resident>("residents");
  const shelters = useCollection<Shelter>("shelters");
  const volunteers = useCollection<Volunteer>("volunteers");
  // Capped at 200 so the UI stays fast with 300+ events (PRD §16.8) and reads stay bounded.
  const events = useCollection<AgentEvent>(
    `incidents/${incidentId}/agent_events`,
    [orderBy("ts", "desc"), limit(200)],
    "latest-200",
  );
  const [selected, setSelected] = useState<string | null>(null);
  const closeDrawer = useCallback(() => setSelected(null), []);
  const [error, setError] = useState<string | null>(null);
  const [confirmStop, setConfirmStop] = useState(false);
  const now = useNow();

  const residents = useMemo(
    () => new Map(residentsList.data.map((r) => [r.resident_id, r])),
    [residentsList.data],
  );

  if (incident.loading) return <p className="p-6">Loading incident…</p>;
  if (incident.error)
    return (
      <p role="alert" className="p-6 text-red-700">
        Error: {incident.error}
      </p>
    );
  if (!incident.data) {
    return (
      <div className="p-6">
        <p>This incident no longer exists (it may have been reset).</p>
        <Link to="/" className="text-blue-800 underline">
          Back to start
        </Link>
      </div>
    );
  }
  const inc = incident.data;
  const created = toDate(inc.created_at)?.getTime() ?? now;
  const stoppedAt = toDate((inc as Incident & { stopped_at?: unknown }).stopped_at)?.getTime();
  const elapsedSim = (((stoppedAt ?? now) - created) / 1000) * inc.sim_time_scale;

  async function run(action: "stop" | "reset") {
    setError(null);
    try {
      if (action === "stop") await api.stop(passcode, incidentId, "kill switch");
      else {
        await api.reset(passcode, incidentId);
        navigate("/");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the LastMile API");
    } finally {
      setConfirmStop(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b bg-white px-4 py-3 shadow-sm">
        <h1 className="text-lg font-bold">{inc.title}</h1>
        <span className="text-sm text-slate-700">Sim time {fmtDuration(elapsedSim)}</span>
        <span className="text-sm text-slate-700">×{inc.sim_time_scale}</span>
        <span className="text-sm text-slate-700">
          Auto-approve: {inc.auto_approve_dispatch ? "on" : "off"}
        </span>
        <AiStatusBadge events={events.data} />
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {!passcode && (
            <input
              type="password"
              placeholder="Passcode"
              aria-label="Demo passcode"
              className="rounded border px-2 py-1 text-sm"
              onChange={(e) => setPasscode(e.target.value)}
            />
          )}
          <button
            type="button"
            onClick={() => run("reset")}
            disabled={!passcode}
            className="rounded border border-slate-400 px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          >
            Reset
          </button>
          <button
            type="button"
            onClick={() => setConfirmStop(true)}
            disabled={!passcode || inc.status !== "ACTIVE"}
            className="rounded bg-red-700 px-3 py-1.5 text-sm font-bold text-white disabled:opacity-50"
          >
            STOP ALL CALLS
          </button>
        </div>
      </header>

      {inc.status !== "ACTIVE" && (
        <div role="status" className="bg-red-700 px-4 py-2 text-center font-bold text-white">
          {inc.status === "STOPPED"
            ? "STOPPED — all calls ended (kill switch)"
            : "COMPLETED — incident time limit reached"}
        </div>
      )}
      {error && (
        <p role="alert" className="bg-red-50 px-4 py-2 text-red-800">
          {error}
        </p>
      )}

      {confirmStop && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="stop-title"
          className="fixed inset-0 z-[2000] grid place-items-center bg-black/40"
        >
          <div className="max-w-sm rounded-lg bg-white p-5 shadow-xl">
            <h2 id="stop-title" className="text-lg font-bold">
              Stop all calls?
            </h2>
            <p className="mt-2 text-sm text-slate-700">
              This ends every live and simulated call now and stops all queued work for this incident.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded border px-3 py-1.5"
                onClick={() => setConfirmStop(false)}
                autoFocus
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded bg-red-700 px-3 py-1.5 font-bold text-white"
                onClick={() => run("stop")}
              >
                Stop all calls
              </button>
            </div>
          </div>
        </div>
      )}

      <main className="grid flex-1 gap-4 p-4 lg:grid-cols-[3fr_2fr]">
        <MapView
          incident={inc}
          cases={cases.data}
          residents={residents}
          shelters={shelters.data}
          volunteers={volunteers.data}
          onSelect={setSelected}
        />
        <div className="flex flex-col gap-4">
          <SafeCounter
            counters={inc.counters ?? { total: 0, confirmed_safe: 0, escalated: 0, in_progress: 0 }}
          />
          <TaskQueue incidentId={incidentId} residents={residents} onSelect={setSelected} />
          <SitrepPanel incidentId={incidentId} />
          <section
            className="rounded-lg bg-white p-4 text-sm text-slate-700 shadow-sm"
            aria-label="Official alert"
          >
            <h2 className="font-semibold text-slate-900">Official alert facts</h2>
            <ul className="mt-1 list-disc pl-5">
              {inc.official_facts.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </section>
        </div>
        <div className="grid gap-4 lg:col-span-2 xl:grid-cols-[3fr_2fr]">
          {cases.error ? (
            <p role="alert" className="text-red-700">
              Error: {cases.error}
            </p>
          ) : (
            <StatusBoard cases={cases.data} residents={residents} onSelect={setSelected} />
          )}
          <AgentLog
            events={events.data}
            loading={events.loading}
            error={events.error}
            onSelect={setSelected}
          />
        </div>
      </main>
      <NokToasts events={events.data} />
      {selected && (
        <CaseDrawer
          incidentId={incidentId}
          residentId={selected}
          resident={residents.get(selected)}
          onClose={closeDrawer}
        />
      )}
      <Footer />
    </div>
  );
}
