// Firestore Timestamps arrive as objects with toDate(); tolerate strings and nulls too.
export type TsLike = { toDate: () => Date } | string | Date | null | undefined;

export function toDate(ts: unknown): Date | null {
  if (!ts) return null;
  if (ts instanceof Date) return ts;
  if (typeof ts === "string") return new Date(ts);
  if (typeof (ts as { toDate?: unknown }).toDate === "function") {
    return (ts as { toDate: () => Date }).toDate();
  }
  return null;
}

export function fmtTime(ts: unknown): string {
  const d = toDate(ts);
  return d ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
}

/** "1h 05m" style duration from seconds. */
export function fmtDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m ${String(sec).padStart(2, "0")}s`;
}
