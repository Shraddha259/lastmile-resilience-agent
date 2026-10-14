import { describe, expect, it } from "vitest";
import type { CaseStatus } from "../types.gen";
import { GROUPS, groupOf, statusLabel } from "./status";
import { fmtDuration } from "./time";

const ALL: CaseStatus[] = [
  "PENDING",
  "QUEUED",
  "RINGING",
  "CONTACTING",
  "SAFE_IN_PLACE",
  "NEEDS_EVACUATION",
  "NEEDS_HELP",
  "MEDICAL",
  "NO_ANSWER",
  "RETRY_SCHEDULED",
  "NEXT_OF_KIN_CONTACTED",
  "SHELTER_RESERVED",
  "VOLUNTEER_PENDING",
  "VOLUNTEER_EN_ROUTE",
  "AT_SHELTER",
  "ESCALATED",
  "CONFIRMED_SAFE",
];

describe("FR-41 status visual language", () => {
  it("maps every status to exactly one group", () => {
    const listed = Object.values(GROUPS).flatMap((g) => g.statuses);
    expect(new Set(listed).size).toBe(listed.length);
    expect([...listed].sort()).toEqual([...ALL].sort());
  });

  it("puts MEDICAL and ESCALATED in the human-needed group", () => {
    expect(groupOf("MEDICAL")).toBe("human_needed");
    expect(groupOf("ESCALATED")).toBe("human_needed");
  });

  it("produces readable labels", () => {
    expect(statusLabel("NEXT_OF_KIN_CONTACTED")).toBe("Next of kin contacted");
  });
});

describe("fmtDuration", () => {
  it("formats minutes and hours", () => {
    expect(fmtDuration(65)).toBe("1m 05s");
    expect(fmtDuration(3900)).toBe("1h 05m");
  });
});
