import { limit, orderBy } from "firebase/firestore";
import { FileText } from "lucide-react";
import { useState } from "react";
import { ApiError, api } from "../api";
import { usePasscode } from "../lib/passcode";
import { fmtTime } from "../lib/time";
import { useCollection } from "../lib/useFirestore";

type Sitrep = { ts: unknown; summary_en: string; model: string; grounded_on_version: number };

/** Latest grounded situation report (PRD §15.5, FR-25) + Generate button. */
export function SitrepPanel({ incidentId }: { incidentId: string }) {
  const { passcode } = usePasscode();
  const latest = useCollection<Sitrep>(
    `incidents/${incidentId}/sitreps`,
    [orderBy("ts", "desc"), limit(1)],
    "latest",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const report = latest.data[0];

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      await api.requestSitrep(passcode, incidentId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the LastMile API");
    } finally {
      setTimeout(() => setBusy(false), 1500);
    }
  }

  return (
    <section aria-label="Situation report" className="rounded-lg bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">Situation report</h2>
        <button
          type="button"
          onClick={generate}
          disabled={busy || !passcode}
          className="inline-flex items-center gap-1 rounded border border-slate-400 px-2 py-1 text-sm disabled:opacity-50"
        >
          <FileText size={14} aria-hidden="true" /> {busy ? "Generating…" : "Generate SITREP"}
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-1 text-sm text-red-700">
          {error}
        </p>
      )}
      {report ? (
        <>
          <p className="mt-2 whitespace-pre-line text-sm text-slate-800">{report.summary_en}</p>
          <p className="mt-1 text-xs text-slate-500">
            Based on data as of {fmtTime(report.ts)} ·{" "}
            {report.model === "template"
              ? "rule-based summary"
              : report.model === "fake"
                ? "scripted"
                : report.model}
          </p>
        </>
      ) : (
        <p className="mt-2 text-sm text-slate-600">No report yet.</p>
      )}
    </section>
  );
}
