import { useMemo, useState } from "react";
import { GROUPS, LANGUAGE_NAMES, groupOf, type StatusGroup } from "../lib/status";
import { fmtTime } from "../lib/time";
import type { Case, Resident } from "../types.gen";
import { LiveTag, SimulatedTag } from "./SimulatedTag";
import { StatusBadge } from "./StatusBadge";

const PRIO_ORDER = { P1: 0, P2: 1, P3: 2 } as const;

type Props = {
  cases: Case[];
  residents: Map<string, Resident>;
  onSelect?: (rid: string) => void;
};

/** Case table (PRD §16.3). Default sort: priority, then risk rank. */
export function StatusBoard({ cases, residents, onSelect }: Props) {
  const [group, setGroup] = useState<StatusGroup | "all">("all");
  const [lang, setLang] = useState<string>("all");

  const rows = useMemo(
    () =>
      cases
        .filter((c) => group === "all" || groupOf(c.status ?? "PENDING") === group)
        .filter((c) => lang === "all" || residents.get(c.resident_id)?.preferred_language === lang)
        .sort(
          (a, b) =>
            PRIO_ORDER[a.priority ?? "P3"] - PRIO_ORDER[b.priority ?? "P3"] || (a.rank ?? 0) - (b.rank ?? 0),
        ),
    [cases, residents, group, lang],
  );

  if (!cases.length) {
    return <p className="p-4 text-slate-600">No cases yet.</p>;
  }

  return (
    <section aria-label="Status board" className="flex h-full flex-col rounded-lg bg-white shadow-sm">
      <div className="flex flex-wrap items-center gap-3 border-b p-3 text-sm">
        <label className="flex items-center gap-1">
          Status
          <select
            className="rounded border px-2 py-1"
            value={group}
            onChange={(e) => setGroup(e.target.value as StatusGroup | "all")}
          >
            <option value="all">All</option>
            {Object.entries(GROUPS).map(([k, g]) => (
              <option key={k} value={k}>
                {g.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1">
          Language
          <select className="rounded border px-2 py-1" value={lang} onChange={(e) => setLang(e.target.value)}>
            <option value="all">All</option>
            {Object.entries(LANGUAGE_NAMES).map(([k, n]) => (
              <option key={k} value={k}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <span className="text-slate-600">{rows.length} shown</span>
      </div>
      <div className="overflow-auto">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-slate-100 text-xs uppercase text-slate-700">
            <tr>
              {[
                "Prio",
                "ID",
                "Name",
                "Age",
                "Language",
                "Status",
                "Tries",
                "Channel",
                "Updated",
                "Summary",
              ].map((h) => (
                <th key={h} scope="col" className="px-2 py-2 font-semibold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => {
              const r = residents.get(c.resident_id);
              return (
                <tr
                  key={c.resident_id}
                  className="cursor-pointer border-t hover:bg-slate-50 focus-within:bg-slate-50"
                  onClick={() => onSelect?.(c.resident_id)}
                >
                  <td className="px-2 py-1.5 font-semibold">{c.priority}</td>
                  <td className="px-2 py-1.5 font-mono">
                    <button
                      type="button"
                      className="underline-offset-2 hover:underline"
                      onClick={() => onSelect?.(c.resident_id)}
                    >
                      {c.resident_id}
                    </button>
                  </td>
                  <td className="px-2 py-1.5">{r?.display_name ?? "—"}</td>
                  <td className="px-2 py-1.5">{r?.age ?? c.age}</td>
                  <td className="px-2 py-1.5">
                    {LANGUAGE_NAMES[r?.preferred_language ?? ""] ?? "—"}
                    {r?.dialect_hint ? ` (${r.dialect_hint})` : ""}
                  </td>
                  <td className="px-2 py-1.5">
                    <StatusBadge status={c.status ?? "PENDING"} />
                  </td>
                  <td className="px-2 py-1.5">{c.attempts ?? 0}</td>
                  <td className="px-2 py-1.5">{c.channel === "live" ? <LiveTag /> : <SimulatedTag />}</td>
                  <td className="px-2 py-1.5 tabular-nums">{fmtTime(c.updated_at)}</td>
                  <td
                    className="max-w-[24rem] truncate px-2 py-1.5 text-slate-700"
                    title={c.last_summary_en ?? ""}
                  >
                    {c.last_summary_en ?? ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
