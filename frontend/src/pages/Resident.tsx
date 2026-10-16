import { Headphones, Mic, Phone, PhoneOff, Send } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { ApiError, api, voiceSocketUrl, type VoiceSession } from "../api";
import { Footer } from "../components/Footer";
import { Player } from "../audio/player";
import { startRecorder, type Recorder } from "../audio/recorder";
import { usePasscode } from "../lib/passcode";
import { LANGUAGE_NAMES, statusLabel } from "../lib/status";
import { useDoc } from "../lib/useFirestore";
import type { Case, CaseStatus, Resident as ResidentDoc } from "../types.gen";

type Phase = "waiting" | "incoming" | "connecting" | "in_call" | "ended";
type Caption = { role: "agent" | "resident"; text: string };

/** Resident phone simulator (PRD §16.5, FR-42): answer the live safety call by voice or chat. */
export function Resident() {
  const { incidentId = "", residentId = "" } = useParams();
  const { passcode, setPasscode } = usePasscode();
  const caseDoc = useDoc<Case>(`incidents/${incidentId}/cases/${residentId}`);
  const resident = useDoc<ResidentDoc>(`residents/${residentId}`);

  const [phase, setPhase] = useState<Phase>("waiting");
  const [mode, setMode] = useState<VoiceSession["mode"]>("voice");
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [recorded, setRecorded] = useState<CaseStatus | null>(null);
  const [endReason, setEndReason] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState(0);
  const [seconds, setSeconds] = useState(0);
  const [draft, setDraft] = useState("");
  const ws = useRef<WebSocket | null>(null);
  const player = useRef<Player | null>(null);
  const recorder = useRef<Recorder | null>(null);
  const captionsEnd = useRef<HTMLLIElement | null>(null);

  const status = caseDoc.data?.status;
  // Ringing drives the incoming-call screen; a declined call simply times out (ring timeout).
  useEffect(() => {
    if (phase === "waiting" && status === "RINGING") setPhase("incoming");
    if (phase === "incoming" && status !== "RINGING") setPhase("waiting");
  }, [status, phase]);

  useEffect(() => {
    if (phase !== "in_call") return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [phase]);

  useEffect(() => {
    // Block body: newer browsers return a Promise from scrollIntoView, which must not be
    // handed back to React as an effect cleanup.
    void captionsEnd.current?.scrollIntoView({ block: "end" });
  }, [captions]);

  const cleanup = useCallback(() => {
    recorder.current?.stop();
    recorder.current = null;
    player.current?.close();
    player.current = null;
    setLevel(0);
  }, []);

  useEffect(
    () => () => {
      ws.current?.close();
      cleanup();
    },
    [cleanup],
  );

  async function answer() {
    setError(null);
    setPhase("connecting");
    try {
      const session = await api.createVoiceSession(passcode, incidentId, residentId);
      setMode(session.mode);
      if (session.mode === "voice") {
        player.current = new Player();
        await player.current.resume(); // inside the click: autoplay rules
      }
      const sock = new WebSocket(voiceSocketUrl(session));
      sock.binaryType = "arraybuffer";
      ws.current = sock;
      sock.onopen = async () => {
        setCaptions([]);
        setSeconds(0);
        setPhase("in_call");
        if (session.mode === "voice") {
          try {
            recorder.current = await startRecorder(
              (frame) => sock.readyState === WebSocket.OPEN && sock.send(frame),
              setLevel,
            );
          } catch {
            setError("Microphone permission was denied. Allow the microphone and answer again.");
            sock.send(JSON.stringify({ type: "hangup" }));
          }
        }
      };
      sock.onmessage = (e: MessageEvent) => {
        if (e.data instanceof ArrayBuffer) {
          player.current?.enqueue(e.data);
          return;
        }
        const msg = JSON.parse(e.data as string);
        if (msg.type === "transcript") setCaptions((c) => [...c, { role: msg.role, text: msg.text }]);
        if (msg.type === "interrupted") player.current?.flush();
        if (msg.type === "status") setRecorded(msg.live_status);
        if (msg.type === "error") setError(msg.message);
        if (msg.type === "call_ended") setEndReason(msg.reason);
      };
      sock.onclose = (e) => {
        cleanup();
        if (e.code === 4401) setError("This call link expired or was already used.");
        if (e.code === 4403) setError("This page's address is not allowed to connect.");
        setPhase("ended");
      };
    } catch (err) {
      cleanup();
      setError(err instanceof ApiError ? err.message : "Could not reach the LastMile API");
      setPhase(status === "RINGING" ? "incoming" : "waiting");
    }
  }

  function hangUp() {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify({ type: "hangup" }));
  }

  function sendText(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || ws.current?.readyState !== WebSocket.OPEN) return;
    ws.current.send(JSON.stringify({ type: "user_text", text }));
    setDraft("");
  }

  const r = resident.data;
  const lang = r ? (LANGUAGE_NAMES[r.preferred_language] ?? r.preferred_language) : "";

  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto w-full max-w-sm flex-1 p-4">
        <div className="flex min-h-[36rem] flex-col rounded-3xl border-4 border-slate-800 bg-white p-5 shadow">
          <div className="text-center">
            <span className="rounded bg-blue-700 px-2 py-0.5 text-xs font-semibold text-white">
              LIVE DEMO
            </span>
            <h1 className="mt-2 text-xl font-bold">{r?.display_name ?? residentId}</h1>
            <p className="text-sm text-slate-600">
              {residentId} · {lang}
              {r?.dialect_hint ? ` (${r.dialect_hint})` : ""} · Synthetic data
            </p>
          </div>

          {!passcode && phase !== "in_call" && (
            <label className="mt-4 block text-sm">
              Demo passcode
              <input
                type="password"
                autoComplete="off"
                className="mt-1 block w-full rounded border px-2 py-1"
                onChange={(e) => setPasscode(e.target.value)}
              />
            </label>
          )}

          {error && (
            <p role="alert" className="mt-3 rounded bg-red-50 p-2 text-sm text-red-800">
              {error}
            </p>
          )}

          {phase === "waiting" && (
            <div className="mt-10 flex-1 text-center text-slate-700">
              <Phone className="mx-auto text-slate-400" size={40} aria-hidden="true" />
              <p className="mt-3">No call yet.</p>
              <p className="mt-1 text-sm text-slate-500">
                {status ? `Case status: ${statusLabel(status)}` : "Waiting for the incident to start."}
              </p>
            </div>
          )}

          {(phase === "incoming" || phase === "connecting") && (
            <div className="mt-8 flex-1 text-center" role="status" aria-live="assertive">
              <Phone className="mx-auto animate-bounce text-green-700" size={44} aria-hidden="true" />
              <p className="mt-3 text-lg font-semibold">Incoming call</p>
              <p className="text-sm text-slate-600">LastMile flood safety check</p>
              <p className="mt-3 flex items-center justify-center gap-1 text-xs text-slate-600">
                <Headphones size={14} aria-hidden="true" /> Use headphones for best results
              </p>
              <div className="mt-6 flex justify-center gap-6">
                <button
                  type="button"
                  onClick={answer}
                  disabled={!passcode || phase === "connecting"}
                  className="flex items-center gap-1 rounded-full bg-green-700 px-5 py-3 font-semibold text-white disabled:opacity-50"
                >
                  <Phone size={18} aria-hidden="true" /> {phase === "connecting" ? "Connecting…" : "Answer"}
                </button>
                <button
                  type="button"
                  onClick={() => setPhase("waiting")}
                  className="flex items-center gap-1 rounded-full bg-red-700 px-5 py-3 font-semibold text-white"
                >
                  <PhoneOff size={18} aria-hidden="true" /> Decline
                </button>
              </div>
            </div>
          )}

          {(phase === "in_call" || phase === "ended") && (
            <div className="mt-4 flex flex-1 flex-col">
              <div className="flex items-center justify-between text-sm">
                <span className="font-semibold">{phase === "in_call" ? "In call" : "Call ended"}</span>
                <span className="tabular-nums text-slate-600">
                  {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
                </span>
              </div>
              {phase === "in_call" && mode === "voice" && (
                <div className="mt-2 flex items-center gap-2" aria-label="Microphone level">
                  <Mic size={16} aria-hidden="true" />
                  <div className="h-2 flex-1 overflow-hidden rounded bg-slate-200">
                    <div
                      className="h-full bg-green-600"
                      style={{ width: `${Math.min(100, level * 140)}%` }}
                    />
                  </div>
                </div>
              )}
              <ol
                aria-label="Live captions"
                aria-live="polite"
                className="mt-3 flex-1 space-y-2 overflow-auto text-sm"
              >
                {captions.map((c, i) => (
                  <li
                    key={i}
                    className={`rounded-lg px-3 py-2 ${c.role === "agent" ? "bg-slate-100" : "ml-6 bg-blue-50"}`}
                  >
                    <span className="block text-[10px] uppercase text-slate-500">
                      {c.role === "agent" ? "LastMile assistant" : "You"}
                    </span>
                    {c.text}
                  </li>
                ))}
                <li ref={captionsEnd} aria-hidden="true" />
              </ol>
              {phase === "in_call" && mode === "text" && (
                <form onSubmit={sendText} className="mt-2 flex gap-2">
                  <input
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="Type your answer…"
                    aria-label="Your answer"
                    className="flex-1 rounded border px-2 py-1 text-sm"
                    autoFocus
                  />
                  <button type="submit" aria-label="Send" className="rounded bg-blue-700 px-3 text-white">
                    <Send size={16} aria-hidden="true" />
                  </button>
                </form>
              )}
              {phase === "in_call" && (
                <button
                  type="button"
                  onClick={hangUp}
                  className="mt-3 flex items-center justify-center gap-1 rounded-full bg-red-700 py-2 font-semibold text-white"
                >
                  <PhoneOff size={18} aria-hidden="true" /> Hang up
                </button>
              )}
              {phase === "ended" && (
                <div className="mt-3 rounded bg-slate-50 p-3 text-sm" role="status">
                  <p>
                    Recorded status: <strong>{recorded ? statusLabel(recorded) : "none"}</strong>
                  </p>
                  {endReason && <p className="text-slate-600">Ended: {endReason.replaceAll("_", " ")}</p>}
                  <p className="mt-1 text-slate-600">The coordinator console now shows what happens next.</p>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
      <Footer />
    </div>
  );
}
