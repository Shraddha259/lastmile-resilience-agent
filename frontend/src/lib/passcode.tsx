// The demo passcode lives in React state only: never localStorage or cookies (PRD §16.1, §23).
import { createContext, useContext, useState, type ReactNode } from "react";

type Ctx = { passcode: string; setPasscode: (p: string) => void };
const PasscodeContext = createContext<Ctx>({ passcode: "", setPasscode: () => {} });

export function PasscodeProvider({ children }: { children: ReactNode }) {
  const [passcode, setPasscode] = useState("");
  return <PasscodeContext.Provider value={{ passcode, setPasscode }}>{children}</PasscodeContext.Provider>;
}

export const usePasscode = () => useContext(PasscodeContext);
