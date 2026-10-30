import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { MONTH_LONG, monthRuns } from "../lib/format";
import type { GlobeRoute } from "../lib/worldmap";
import { countriesLabel } from "../lib/worldmap";
import { DRESS_ME } from "../pages/Start";

const nightsLabel = (d: number) => `${d} ${d === 1 ? "day" : "days"}`;

/** One route of the globe: its stops in order, what you see day by day, and "Dress me". */
/** The weather of the route in the month picked on the globe, or its best months. */
function Weather({ route, month }: { route: GlobeRoute; month: number | null }) {
  const m = month && route.months?.[month - 1];
  if (!month || !m) {
    return route.best_months.length > 0 ? <p className="small">Best weather: {monthRuns(route.best_months)}</p> : null;
  }
  const good = route.best_months.includes(month);
  const verdict = good ? "good weather" : m.note ?? (m.level === 0 ? "poor weather" : "so-so weather");
  return (
    <p className={`small rcard-wx${good ? " ok" : ""}`}>
      In {MONTH_LONG[month - 1]}: {m.lo} to {m.hi} °C · {verdict}
      {!good && route.best_months.length > 0 && <span className="muted"> · best {monthRuns(route.best_months)}</span>}
    </p>
  );
}

export function RouteCard({ route, month = null, onClose }: { route: GlobeRoute; month?: number | null; onClose: () => void }) {
  const { ensureUser } = useApp();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function dress() {
    setBusy(true); setErr(null);
    try {
      await ensureUser();
      const t = await api.routeTrip(route.id, month ? { month } : {});
      nav(`/trips/${t.id}`);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  let day = 1;
  const legs = route.stops.map((s) => { const from = day; day += s.days; return { s, from }; });

  return (
    <aside className="pcard rcard" aria-label={route.title}>
      <button type="button" className="pcard-x" aria-label="Close" onClick={onClose}>✕</button>
      <div className="pcard-in">
        <p className="kicker">{countriesLabel(route.countries)} · {route.days} days</p>
        <h3>{route.title}</h3>
        <p className="small muted">
          {route.guide
            ? "A ready-made trip with a day-by-day guide: what is worth it and what to skip."
            : "The route travellers follow most at this length, stop by stop."}
        </p>
        <Weather route={route} month={month} />
        <ol className="rcard-stops">
          {legs.map(({ s, from }, i) => (
            <li key={i}>
              <b className="rcard-n">{i + 1}</b>
              <span>
                {s.name} <span className="muted">· {nightsLabel(s.days)}</span>
                {open && s.visits.length > 0 && (
                  <span className="rcard-days">
                    {s.visits.map(([d, names]) => (
                      <span key={d}><span className="muted">Day {from + d - 1}:</span> {names.join(", ")}</span>
                    ))}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ol>
        {!route.guide && route.stops.some((s) => s.visits.length) && (
          <button type="button" className="linkish small" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? "Hide what you see each day" : "What you see each day"}
          </button>
        )}
        <div className="pcard-acts">
          <button type="button" className="btn sm primary" onClick={dress} disabled={busy}>{busy ? "Creating your trip…" : DRESS_ME}</button>
          {route.guide && <Link className="btn sm" to={`/ideas/${route.guide}`}>See it day by day</Link>}
        </div>
        <p className="small muted">It becomes your trip: change stops, days and dates after.</p>
        {err && <p className="small" role="alert">{err}</p>}
      </div>
    </aside>
  );
}
