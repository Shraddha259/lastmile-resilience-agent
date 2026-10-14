// Status visual language (PRD §16.4, FR-41): always colour + icon + text.
import {
  Clock,
  Footprints,
  PhoneCall,
  PhoneMissed,
  ShieldCheck,
  Siren,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import type { CaseStatus } from "../types.gen";

export type StatusGroup =
  "waiting" | "in_contact" | "retrying" | "needs_action" | "help_on_way" | "human_needed" | "done";

export const GROUPS: Record<
  StatusGroup,
  { label: string; statuses: CaseStatus[]; color: string; bg: string; text: string; icon: LucideIcon }
> = {
  waiting: {
    label: "Waiting",
    statuses: ["PENDING", "QUEUED"],
    color: "#64748b",
    bg: "bg-slate-100",
    text: "text-slate-800",
    icon: Clock,
  },
  in_contact: {
    label: "In contact",
    statuses: ["RINGING", "CONTACTING"],
    color: "#2563eb",
    bg: "bg-blue-100",
    text: "text-blue-900",
    icon: PhoneCall,
  },
  retrying: {
    label: "Retrying",
    statuses: ["NO_ANSWER", "RETRY_SCHEDULED", "NEXT_OF_KIN_CONTACTED"],
    color: "#7c3aed",
    bg: "bg-violet-100",
    text: "text-violet-900",
    icon: PhoneMissed,
  },
  needs_action: {
    label: "Needs action",
    statuses: ["NEEDS_HELP", "NEEDS_EVACUATION", "SHELTER_RESERVED", "VOLUNTEER_PENDING"],
    color: "#d97706",
    bg: "bg-amber-100",
    text: "text-amber-900",
    icon: TriangleAlert,
  },
  help_on_way: {
    label: "Help on the way",
    statuses: ["VOLUNTEER_EN_ROUTE", "AT_SHELTER"],
    color: "#0d9488",
    bg: "bg-teal-100",
    text: "text-teal-900",
    icon: Footprints,
  },
  human_needed: {
    label: "Human needed",
    statuses: ["MEDICAL", "ESCALATED"],
    color: "#dc2626",
    bg: "bg-red-100",
    text: "text-red-900",
    icon: Siren,
  },
  done: {
    label: "Done",
    statuses: ["SAFE_IN_PLACE", "CONFIRMED_SAFE"],
    color: "#16a34a",
    bg: "bg-green-100",
    text: "text-green-900",
    icon: ShieldCheck,
  },
};

const BY_STATUS = new Map<CaseStatus, StatusGroup>();
for (const [g, def] of Object.entries(GROUPS)) {
  for (const s of def.statuses) BY_STATUS.set(s, g as StatusGroup);
}

export function groupOf(status: CaseStatus): StatusGroup {
  return BY_STATUS.get(status) ?? "waiting";
}

export function statusLabel(status: CaseStatus): string {
  return status
    .toLowerCase()
    .split("_")
    .map((w, i) => (i === 0 ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

export const LANGUAGE_NAMES: Record<string, string> = {
  zh: "Mandarin",
  ms: "Malay",
  ta: "Tamil",
  en: "English",
  yue: "Cantonese",
};
