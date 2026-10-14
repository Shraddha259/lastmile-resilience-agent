import type { CaseStatus } from "../types.gen";
import { GROUPS, groupOf, statusLabel } from "../lib/status";

/** Colour + icon + text, never colour alone (FR-41). */
export function StatusBadge({ status }: { status: CaseStatus }) {
  const g = GROUPS[groupOf(status)];
  const Icon = g.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${g.bg} ${g.text}`}
    >
      <Icon size={13} aria-hidden="true" />
      {statusLabel(status)}
    </span>
  );
}
