import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { MyTripsMap } from "../components/Maps";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { dayMonth } from "../lib/format";
import type { TripSummary } from "../lib/types";


/** Trips: one button to draw a new trip on the map, and the trips you saved. Map first: the picked
 *  trip shows on the globe along its roads, its stops as their drawings; the picked row has Open. */
export default function Trips() {
  const { user, loading } = useApp();
  const nav = useNavigate();
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [desk, setDesk] = useState(() => typeof matchMedia === "undefined" || matchMedia("(min-width: 900px)").matches);

  useEffect(() => {
    const mq = matchMedia("(min-width: 900px)");
    const f = () => setDesk(mq.matches);
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user) { setTrips([]); return; }
    api.trips().then(setTrips).catch(() => setTrips([]));
  }, [user, loading]);

  const saved = useMemo(() => (trips ?? []).filter((t) => t.saved), [trips]);
  const mapTrips = saved.map((x) => ({ id: x.id, points: x.points ?? [], arts: x.arts, names: x.places }));
  // on a wide screen the first trip is on the map straight away, its stops as drawings
  useEffect(() => {
    if (desk && !sel && saved.length) setSel(saved[0].id);
  }, [desk, saved]); // eslint-disable-line react-hooks/exhaustive-deps
  const open = (id: string) => (desk ? setSel(id) : nav(`/trips/${id}`));
  const when = (x: TripSummary) => x.start_date ? `${dayMonth(x.start_date)} – ${dayMonth(x.end_date!)}` : `${x.stop_count} ${x.stop_count === 1 ? "stop" : "stops"}`;

  return (
    <main className="trk mytrips">
      <div className="mf">
        <div className="mf-map">
          <MyTripsMap trips={mapTrips} selected={sel} onPick={open}
            inset={desk ? { top: 20, right: 60, bottom: 20, left: 470 } : undefined} />
        </div>

        {/* Trips (flow audit, Manu 2026-11-16): a new trip and your trips. The recommended trips
            live on the home, by month, so there is one list of them, not two. */}
        <section className="mf-float mf-panel" aria-label="Trips">
          <div className="mf-thead"><h1>Trips</h1></div>
          <Link className="mf-btn go wide mf-new" to="/trips/new"><Plus /> New trip</Link>
          {trips === null ? <div className="loading"><span className="spin" /></div> : (
            <div className="mf-scroll">
              {saved.length ? (
                <ul className="mf-treks">
                  {saved.map((x) => (
                    <li key={x.id} className="mf-recrow">
                      <button type="button" className={`mf-trow${sel === x.id ? " sel" : ""}`} onClick={() => open(x.id)} onDoubleClick={() => nav(`/trips/${x.id}`)}>
                        <span className="mf-thumb">{x.art ? <Illustration art={x.art} /> : null}</span>
                        <span className="mf-nm"><b>{x.name}</b><small>{when(x)}</small></span>
                      </button>
                      {sel === x.id && <Link className="mf-btn go sm mf-recopen" to={`/trips/${x.id}`}>Open</Link>}
                    </li>
                  ))}
                </ul>
              ) : <div className="mf-empty"><p>No trips yet.</p><p><Link to="/">Pick a place</Link> or start a new trip.</p></div>}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

const I = (d: string) => () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d={d} /></svg>;
const Plus = I("M12 5v14M5 12h14");
