/** FR-22: every simulated item carries this tag. */
export function SimulatedTag() {
  return (
    <span className="rounded border border-slate-400 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-slate-700">
      SIMULATED
    </span>
  );
}

export function LiveTag() {
  return (
    <span className="rounded bg-blue-700 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-white">
      LIVE
    </span>
  );
}
