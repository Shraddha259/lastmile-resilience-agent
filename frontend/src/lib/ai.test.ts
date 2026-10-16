import { describe, expect, it } from "vitest";
import type { AgentEvent } from "../types.gen";
import { aiStatus } from "./ai";

const ev = (over: Partial<AgentEvent>): AgentEvent =>
  ({
    ts: null,
    actor: "agent",
    event_type: "AGENT_DECISION",
    resident_id: "R-1",
    tool: null,
    args_summary: null,
    result: "ok",
    reason: "",
    model: null,
    latency_ms: null,
    fallback_used: false,
    status_from: null,
    status_to: null,
    ...over,
  }) as AgentEvent;

describe("aiStatus", () => {
  it("reports live when a real model made a recent decision", () => {
    expect(aiStatus([ev({ model: "gemini-2.5-flash-lite" })])).toEqual({
      mode: "live",
      model: "gemini-2.5-flash-lite",
    });
  });
  it("reports scripted in fake mode", () => {
    expect(aiStatus([ev({ model: "fake" })]).mode).toBe("scripted");
  });
  it("reports fallback when only policy acted or the classifier was cached", () => {
    expect(aiStatus([ev({ actor: "policy", event_type: "STATUS_CHANGE" })]).mode).toBe("fallback");
    expect(aiStatus([ev({ tool: "classifier", event_type: "STATUS_CHANGE", model: "cached" })]).mode).toBe(
      "fallback",
    );
  });
  it("is idle with no events", () => {
    expect(aiStatus([]).mode).toBe("idle");
  });
});
