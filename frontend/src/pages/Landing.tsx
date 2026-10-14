import { limit, where } from "firebase/firestore";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { Footer } from "../components/Footer";
import { usePasscode } from "../lib/passcode";
import { useCollection } from "../lib/useFirestore";
import type { Incident } from "../types.gen";

/** Landing page (PRD §16.2, FR-40). */
export function Landing() {
  const { passcode, setPasscode } = usePasscode();
  const [autoApprove, setAutoApprove] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const active = useCollection<Incident>("incidents", [where("status", "==", "ACTIVE"), limit(1)], "active");
  const activeId = active.data[0]?.incident_id;

  async function run(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { incident_id } = await api.startScenario(passcode, autoApprove);
      navigate(`/console/${incident_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the LastMile API");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto w-full max-w-3xl flex-1 p-6">
        <h1 className="text-3xl font-bold">LastMile</h1>
        <p className="mt-1 text-lg text-slate-700">
          From disaster alert to confirmed safety for vulnerable residents.
        </p>
        <p className="mt-4 text-slate-800">
          When a flood alert is issued, LastMile ranks every vulnerable resident in the zone by risk, checks
          on each one in their own language, and takes the next step — shelter, a volunteer, next-of-kin, or a
          human coordinator — until every person is confirmed safe or handed over.
        </p>

        <section className="mt-6 rounded-lg border border-blue-200 bg-blue-50 p-4" aria-labelledby="judge">
          <h2 id="judge" className="font-semibold">
            How to judge this demo
          </h2>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-slate-800">
            <li>
              Enter the demo passcode and press <strong>Run Flood Scenario</strong>.
            </li>
            <li>Watch 40 synthetic residents move from waiting to confirmed safe on the console.</li>
            <li>
              Open a live resident in a new tab and answer the call (live calls arrive in a later build).
            </li>
            <li>
              Use <strong>STOP ALL CALLS</strong> (kill switch) and <strong>Reset</strong> when you are done.
            </li>
          </ol>
        </section>

        {activeId ? (
          <section className="mt-6 rounded-lg bg-white p-4 shadow-sm">
            <p className="text-slate-800">An incident is already running.</p>
            <Link
              className="mt-2 inline-block rounded bg-blue-700 px-4 py-2 font-semibold text-white"
              to={`/console/${activeId}`}
            >
              Open active incident
            </Link>
          </section>
        ) : (
          <form onSubmit={run} className="mt-6 space-y-4 rounded-lg bg-white p-4 shadow-sm">
            <label className="block">
              <span className="text-sm font-medium">Demo passcode</span>
              <input
                type="password"
                required
                autoComplete="off"
                value={passcode}
                onChange={(e) => setPasscode(e.target.value)}
                className="mt-1 block w-full rounded border px-3 py-2"
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={autoApprove}
                onChange={(e) => setAutoApprove(e.target.checked)}
              />
              Auto-approve volunteer dispatch
            </label>
            {error && (
              <p role="alert" className="text-sm text-red-700">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={busy || !passcode}
              className="rounded bg-blue-700 px-4 py-2 font-semibold text-white disabled:opacity-50"
            >
              {busy ? "Starting…" : "Run Flood Scenario"}
            </button>
          </form>
        )}

        {activeId && (
          <section className="mt-6 text-sm" aria-label="Live residents">
            <h2 className="font-semibold">Play a live resident</h2>
            <ul className="mt-1 list-disc pl-5">
              <li>
                <a
                  className="text-blue-800 underline"
                  target="_blank"
                  rel="noreferrer"
                  href={`/resident/${activeId}/R-001`}
                >
                  Play Mdm Tan (Mandarin, live)
                </a>
              </li>
              <li>
                <a
                  className="text-blue-800 underline"
                  target="_blank"
                  rel="noreferrer"
                  href={`/resident/${activeId}/R-002`}
                >
                  Play Mr Lim (English, live)
                </a>
              </li>
            </ul>
          </section>
        )}
      </main>
      <Footer />
    </div>
  );
}
