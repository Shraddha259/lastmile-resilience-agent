import { MessageSquare, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toDate } from "../lib/time";
import type { AgentEvent } from "../types.gen";

type Toast = { key: string; rid: string; text: string };

/** Toast for each new (simulated) next-of-kin message (PRD §15.4). */
export function NokToasts({ events }: { events: AgentEvent[] }) {
  const seen = useRef<Set<string> | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const nok = events.filter((e) => e.tool === "contact_next_of_kin" && e.status_to);
    const keyOf = (e: AgentEvent) => `${e.resident_id}-${toDate(e.ts)?.getTime() ?? ""}`;
    if (seen.current === null) {
      seen.current = new Set(nok.map(keyOf)); // don't replay old messages on page load
      return;
    }
    const fresh = nok.filter((e) => !seen.current!.has(keyOf(e)));
    if (!fresh.length) return;
    fresh.forEach((e) => seen.current!.add(keyOf(e)));
    // "Message sent to son (+60 1X-XXX 4821) — simulated: <message>" -> keep the first part.
    const items = fresh.map((e) => ({
      key: keyOf(e),
      rid: e.resident_id ?? "",
      text: (e.args_summary ?? "Next-of-kin contacted — simulated").split(" — simulated")[0] + " — simulated",
    }));
    setToasts((t) => [...items, ...t].slice(0, 4));
    const timer = setTimeout(
      () => setToasts((t) => t.filter((x) => !items.some((i) => i.key === x.key))),
      8000,
    );
    return () => clearTimeout(timer);
  }, [events]);

  if (!toasts.length) return null;
  return (
    <div className="fixed bottom-4 left-4 z-[1800] space-y-2" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.key}
          className="flex max-w-sm items-start gap-2 rounded-lg bg-slate-900 p-3 text-sm text-white shadow-lg"
        >
          <MessageSquare size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            <span className="font-mono">{t.rid}</span>: {t.text}
          </span>
          <button
            type="button"
            aria-label="Dismiss"
            onClick={() => setToasts((all) => all.filter((x) => x.key !== t.key))}
            className="ml-auto"
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>
      ))}
    </div>
  );
}
