import { useState } from "react";
import { dayMonth } from "../lib/format";

/** The trip's dates are a guess (only places were given, or no start date): ask for what is
 * missing, or let the traveller keep the guess. Both inputs are optional. */
export function EstimateForm({ start, days, firstDay, totalDays, busy, keepLabel = "Keep the guess", onApply, onKeep }: {
  start: boolean; days: boolean; firstDay: string; totalDays: number; busy?: boolean; keepLabel?: string;
  onApply: (v: { start?: string; total?: number }) => void; onKeep: () => void;
}) {
  const [when, setWhen] = useState("");
  const [len, setLen] = useState<number | "">("");
  const what = start && days ? "the dates and how long you stay in each place are" : start ? "the start date is" : "how long you stay in each place is";
  return (
    <div className="banner warn estimate" role="region" aria-label="Estimated dates">
      <p><b>This plan is an estimate:</b> {what} a guess.
        {" "}It starts on {dayMonth(firstDay)} and lasts {totalDays} {totalDays === 1 ? "day" : "days"}
        {days ? ", spread evenly over the places" : ""}. Tell us what you know, or keep the guess: weather and kit follow these dates.</p>
      <div className="est-row">
        {start && <div className="field"><label htmlFor="est-start">When do you leave?</label>
          <input id="est-start" type="date" value={when} onChange={(e) => setWhen(e.target.value)} /></div>}
        {days && <div className="field"><label htmlFor="est-len">How many days in total?</label>
          <input id="est-len" type="number" min={1} max={365} value={len} placeholder={String(totalDays)}
            onChange={(e) => setLen(e.target.value === "" ? "" : Math.max(1, Math.min(365, Number(e.target.value))))} /></div>}
        <div className="row">
          <button type="button" className="btn primary" disabled={busy || (!when && len === "")}
            onClick={() => onApply({ start: when || undefined, total: len === "" ? undefined : len })}>Apply</button>
          <button type="button" className="btn" disabled={busy} onClick={onKeep}>{keepLabel}</button>
        </div>
      </div>
    </div>
  );
}
