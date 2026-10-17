// REST commands to the LastMile API (PRD §11). Reads come from Firestore listeners.
const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function post<T>(path: string, passcode: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Demo-Passcode": passcode },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = data?.error ?? {};
    throw new ApiError(res.status, err.code ?? "INTERNAL", err.message ?? res.statusText);
  }
  return data as T;
}

export const api = {
  startScenario: (passcode: string, autoApprove: boolean, simTimeScale?: number) =>
    post<{ incident_id: string }>("/api/scenarios", passcode, {
      scenario_id: "flood_demo",
      auto_approve_dispatch: autoApprove,
      ...(simTimeScale ? { sim_time_scale: simTimeScale } : {}),
    }),
  stop: (passcode: string, incidentId: string, reason = "kill switch") =>
    post<{ status: string }>(`/api/incidents/${incidentId}/stop`, passcode, { reason }),
  reset: (passcode: string, incidentId: string) =>
    post<{ status: string }>(`/api/incidents/${incidentId}/reset`, passcode),
  createVoiceSession: (passcode: string, incidentId: string, residentId: string) =>
    post<VoiceSession>("/api/voice/sessions", passcode, {
      incident_id: incidentId,
      resident_id: residentId,
    }),
};

export type VoiceSession = {
  token: string;
  ws_url: string;
  ws_path: string;
  expires_at: string;
  mode: "voice" | "text";
};

/** Absolute WebSocket URL for a voice session (VITE_WS_BASE_URL, else same host as the API). */
export function voiceSocketUrl(session: VoiceSession): string {
  if (/^wss?:\/\//.test(session.ws_url)) return session.ws_url;
  const base = import.meta.env.VITE_WS_BASE_URL || BASE.replace(/^http/, "ws");
  return `${base}${session.ws_path}`;
}
