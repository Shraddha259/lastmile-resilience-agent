import type { Counters } from "../types.gen";

/** "35 / 40 confirmed safe" plus a bar: safe / in progress / escalated. */
export function SafeCounter({ counters }: { counters: Counters }) {
  const { total, confirmed_safe: safe, escalated, in_progress: prog } = counters;
  const pct = (n: number) => (total ? `${(n / total) * 100}%` : "0%");
  return (
    <section aria-label="Safety counter" className="rounded-lg bg-white p-4 shadow-sm">
      <p className="text-3xl font-bold">
        {safe} <span className="text-slate-500">/ {total}</span>
        <span className="ml-2 text-base font-medium text-slate-700">confirmed safe</span>
      </p>
      <div
        className="mt-3 flex h-3 overflow-hidden rounded-full bg-slate-200"
        role="img"
        aria-label={`${safe} safe, ${prog} in progress, ${escalated} escalated`}
      >
        <div className="bg-green-600" style={{ width: pct(safe) }} />
        <div className="bg-blue-500" style={{ width: pct(prog) }} />
        <div className="bg-red-600" style={{ width: pct(escalated) }} />
      </div>
      <dl className="mt-2 flex gap-4 text-sm text-slate-700">
        <div>
          <dt className="inline">Safe: </dt>
          <dd className="inline font-semibold">{safe}</dd>
        </div>
        <div>
          <dt className="inline">In progress: </dt>
          <dd className="inline font-semibold">{prog}</dd>
        </div>
        <div>
          <dt className="inline">Escalated: </dt>
          <dd className="inline font-semibold">{escalated}</dd>
        </div>
      </dl>
    </section>
  );
}
