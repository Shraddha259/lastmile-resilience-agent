import { useParams } from "react-router-dom";
import { Footer } from "../components/Footer";

/** Resident phone simulator (PRD §16.5). Live voice arrives in milestone M4. */
export function Resident() {
  const { residentId } = useParams();
  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto w-full max-w-sm flex-1 p-6">
        <div className="rounded-3xl border-4 border-slate-800 bg-white p-6 text-center shadow">
          <span className="rounded bg-blue-700 px-2 py-0.5 text-xs font-semibold text-white">LIVE DEMO</span>
          <h1 className="mt-3 text-xl font-bold">{residentId}</h1>
          <p className="mt-4 text-slate-700">No call yet.</p>
          <p className="mt-2 text-sm text-slate-600">Live voice calls are coming in milestone M4.</p>
        </div>
      </main>
      <Footer />
    </div>
  );
}
