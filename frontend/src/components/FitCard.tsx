import { useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import type { QuizResult, Tier } from "../lib/types";

const COLD: [string, string][] = [["bit_cold", "I get cold easily"], ["average", "About average"], ["warm", "I rarely get cold"]];

/** Two questions, once, on top of the bag (flow audit, Manu 2026-11-16): which cut, so a bag never
 *  mixes men's and women's pieces, and how cold you run. No popup; the rest of "about you" (pace,
 *  evenings, brands, shops) lives in You. */
export function FitCard({ tripId, tier, onDone }: { tripId: string; tier: Tier; onDone: (r: QuizResult) => void }) {
  const { user, refreshUser } = useApp();
  const [cut, setCut] = useState<"men" | "women" | null>(user?.gender_pref === "men" || user?.gender_pref === "women" ? user.gender_pref : null);
  const [busy, setBusy] = useState(false);

  async function finish(cold: string | null) {
    setBusy(true);
    try {
      if (cut && cut !== user?.gender_pref) await api.updateMe({ gender_pref: cut });
      const r = await api.quiz({ cold, pace: null, evenings: null, owned: null }, tripId, tier);
      await refreshUser();
      onDone(r);
    } finally { setBusy(false); }
  }

  return (
    <section className="x-fit" aria-label="About you">
      <div className="x-fit-q">
        <b>Clothes cut for</b>
        <div className="x-seg sm" role="group" aria-label="Cut">
          {(["men", "women"] as const).map((g) => (
            <button key={g} type="button" aria-pressed={cut === g} disabled={busy}
              onClick={async () => { setCut(g); await api.updateMe({ gender_pref: g }); await refreshUser(); }}>{g === "men" ? "Men" : "Women"}</button>
          ))}
        </div>
      </div>
      <div className="x-fit-q">
        <b>And the cold?</b>
        <div className="x-seg sm" role="group" aria-label="How cold you run">
          {COLD.map(([v, l]) => <button key={v} type="button" disabled={busy} onClick={() => finish(v)}>{l}</button>)}
        </div>
      </div>
      <button type="button" className="x-link x-fit-skip" disabled={busy} onClick={() => finish(null)}>Skip</button>
    </section>
  );
}
