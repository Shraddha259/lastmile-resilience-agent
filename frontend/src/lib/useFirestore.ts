// Small hooks around Firestore onSnapshot listeners.
import { collection, doc, onSnapshot, query, type QueryConstraint } from "firebase/firestore";
import { useEffect, useState } from "react";
import { db } from "../firebase";

type State<T> = { data: T; loading: boolean; error: string | null };

export function useDoc<T>(path: string | null): State<T | null> {
  const [state, setState] = useState<State<T | null>>({ data: null, loading: true, error: null });
  useEffect(() => {
    if (!path) return;
    return onSnapshot(
      doc(db, path),
      (snap) => setState({ data: snap.exists() ? (snap.data() as T) : null, loading: false, error: null }),
      (err) => setState({ data: null, loading: false, error: err.message }),
    );
  }, [path]);
  return state;
}

export function useCollection<T>(
  path: string | null,
  constraints: QueryConstraint[] = [],
  key = "",
): State<T[]> {
  const [state, setState] = useState<State<T[]>>({ data: [], loading: true, error: null });
  useEffect(() => {
    if (!path) return;
    return onSnapshot(
      query(collection(db, path), ...constraints),
      (snap) => setState({ data: snap.docs.map((d) => d.data() as T), loading: false, error: null }),
      (err) => setState({ data: [], loading: false, error: err.message }),
    );
    // constraints are recreated each render; `key` identifies them.
  }, [path, key]);
  return state;
}
