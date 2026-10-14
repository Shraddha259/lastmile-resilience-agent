import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ensureSignedIn } from "./firebase";
import { PasscodeProvider } from "./lib/passcode";
import { Console } from "./pages/Console";
import { Landing } from "./pages/Landing";
import { Resident } from "./pages/Resident";

export default function App() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    ensureSignedIn()
      .then(() => setReady(true))
      .catch((e: Error) => setError(e.message));
  }, []);
  if (error)
    return (
      <p role="alert" className="p-6 text-red-700">
        Could not sign in: {error}
      </p>
    );
  if (!ready) return <p className="p-6">Loading…</p>;
  return (
    <PasscodeProvider>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/console/:incidentId" element={<Console />} />
          <Route path="/resident/:incidentId/:residentId" element={<Resident />} />
          <Route path="*" element={<p className="p-6">Page not found.</p>} />
        </Routes>
      </BrowserRouter>
    </PasscodeProvider>
  );
}
