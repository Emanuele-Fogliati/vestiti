import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import type { Plans, QuizResult, Strategy, Tier } from "../lib/types";
import { FitCard } from "./FitCard";
import { Kit } from "./Kit";
import { PlanChange } from "./PlanChange";
import { Coldest, WeatherTab } from "./WeatherTab";

/** The clothes, under the route on the same page (Manu 2026-11-16: "sta tutto dentro la stessa
 *  pagina ... scrollare in basso e vedere i vestiti necessari ... posso in ogni momento tornare su,
 *  editare il viaggio, e i vestiti si editano"). On a plain background, never over the map.
 *  `ver` changes when the route changes: the bag is worked out again. */
export function TripBag({ tripId, ver, title, tier, setTier, onPlans }: {
  tripId: string | null; ver: string | number; title: ReactNode; tier: Tier; setTier: (t: Tier) => void;
  /** the bag came back (the trip page shows the pieces to get in the panel too) */
  onPlans?: (p: Plans, s: Strategy) => void;
}) {
  const { user, refreshUser } = useApp();
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [plans, setPlans] = useState<Plans | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [quiz, setQuiz] = useState<QuizResult | null>(null);

  const load = useCallback(async () => {
    if (!tripId) return;
    setBusy(true); setErr(null);
    try {
      const [s, p] = await Promise.all([api.strategy(tripId, tier), api.plans(tripId)]);
      setStrategy(s); setPlans(p);
      onPlans?.(p, s);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }, [tripId, tier]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load, ver]);

  async function quizDone(r: QuizResult) {
    setQuiz(r.changes.length ? r : null);
    await refreshUser();
    load();
  }

  const estimate = strategy?.stages.some((s) => s.weather_sources.includes("estimate"));
  return (
    <section className="x-trip ip-bag" id="bag" aria-label="What to wear">
      <div className="ip-bag-in">
        <header className="ip-bag-h">
          <h2>{title}</h2>
          {busy && <span className="spin" aria-label="Updating" />}
        </header>
        {err && <p className="err">{err}</p>}
        {!plans ? <p className="loading"><span className="spin" /></p> : plans.empty ? <p className="mf-k">Add a place first.</p> : (
          <div className={busy ? "ip-bag-busy" : undefined}>
            {quiz && (
              <div className="x-alert x-quizres">
                <div className="x-row"><b>{quiz.plan.pieces.length || quiz.plan.status ? "Your answers changed the bag" : "Saved. Your bag already fit you"}</b>
                  <button type="button" className="x-close" aria-label="Close" onClick={() => setQuiz(null)}>✕</button></div>
                <PlanChange changes={quiz.changes} plan={quiz.plan} />
              </div>
            )}
            {user && !user.profile_done_at && tripId && <FitCard tripId={tripId} tier={tier} onDone={quizDone} />}
            {strategy && !strategy.empty && (
              <div className="x-cold-top">
                <Coldest strategy={strategy} />
                <details className="x-wx">
                  <summary>Weather, day by day</summary>
                  {estimate && <p className="x-alert warn">The weather service could not be reached: some places use a rough estimate. Reload later.</p>}
                  <WeatherTab strategy={strategy} />
                </details>
              </div>
            )}
            {tripId && <Kit tripId={tripId} plans={plans} tier={tier} setTier={setTier} onChanged={load} />}
          </div>
        )}
      </div>
    </section>
  );
}
