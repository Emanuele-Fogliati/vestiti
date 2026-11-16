import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { MyTripsMap } from "../components/Maps";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { dayMonth } from "../lib/format";
import type { TripSummary } from "../lib/types";

/** Copies of one trip (same name, same stops, same dates) show as one row: "×4". */
const sameKey = (t: TripSummary) => [t.name, t.places.join("|"), t.start_date ?? "", t.end_date ?? ""].join("#");

/** My trips, map first like the trip page and Treks (Manu 2026-11-16): every trip on one map,
 *  the list in the panel on the left, a trip opens its card beside it. One screen on a computer. */
export default function Trips() {
  const { user, loading, toast } = useApp();
  const nav = useNavigate();
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [desk, setDesk] = useState(() => typeof matchMedia === "undefined" || matchMedia("(min-width: 900px)").matches);

  useEffect(() => {
    const mq = matchMedia("(min-width: 900px)");
    const f = () => setDesk(mq.matches);
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, []);

  const load = () => api.trips().then(setTrips).catch(() => setTrips([]));
  useEffect(() => {
    if (loading) return;
    if (!user) { setTrips([]); return; }
    load();
  }, [user, loading]); // eslint-disable-line react-hooks/exhaustive-deps

  // one row per trip; identical copies fold into the newest one
  const groups = useMemo(() => {
    const by = new Map<string, TripSummary[]>();
    for (const t of trips ?? []) { const k = sameKey(t); by.set(k, [...(by.get(k) ?? []), t]); }
    // trips with no stops yet go last: there is nothing of them to show on the map
    return [...by.values()].sort((a, b) => Number(!a[0].stop_count) - Number(!b[0].stop_count));
  }, [trips]);
  // on a computer the latest trip is open from the start, so the map shows something of yours
  const [auto, setAuto] = useState(true);
  useEffect(() => {
    if (auto && desk && !sel && groups[0]?.[0].stop_count) { setSel(groups[0][0].id); setAuto(false); }
  }, [groups, desk, sel, auto]);
  const g = sel ? groups.find((x) => x[0].id === sel) : undefined;
  const t = g?.[0];

  async function dropCopies(copies: TripSummary[]) {
    setBusy(true);
    try {
      for (const c of copies.slice(1)) await api.deleteTrip(c.id);
      toast(`${copies.length - 1} ${copies.length === 2 ? "copy" : "copies"} of ${copies[0].name} removed.`);
      await load();
    } catch (e) { toast((e as Error).message); } finally { setBusy(false); }
  }

  const when = (x: TripSummary) => x.start_date ? `${x.estimated ? "≈ " : ""}${dayMonth(x.start_date)} – ${dayMonth(x.end_date!)}` : "No dates";
  const open = (id: string) => (desk ? setSel(sel === id ? null : id) : nav(`/trips/${id}`));

  const rows = (
    <ul className="mf-trips">
      {groups.map((c) => {
        const x = c[0];
        return (
          <li key={x.id}>
            <button type="button" className={`mf-trow${sel === x.id ? " sel" : ""}`} onClick={() => open(x.id)} onDoubleClick={() => nav(`/trips/${x.id}`)}>
              <span className="mf-thumb">{x.art ? <Illustration art={x.art} /> : null}</span>
              <span className="mf-nm">
                <b>{x.name}{c.length > 1 && <span className="mf-copies">×{c.length}</span>}</b>
                <small>{when(x)} · {x.stop_count} {x.stop_count === 1 ? "stop" : "stops"}</small>
                <small className="mf-base">{x.places.length ? x.places.join(" → ") : "No stops yet"}</small>
              </span>
            </button>
            {!desk && c.length > 1 && (
              <button type="button" className="mf-btn sm mf-dupe-ph" disabled={busy} onClick={() => dropCopies(c)}>
                {c.length} identical copies: keep one, remove {c.length - 1}</button>
            )}
          </li>
        );
      })}
    </ul>
  );

  return (
    <main className="trk mytrips">
      <div className="mf">
        <div className="mf-map">
          <MyTripsMap trips={groups.map((c) => ({ id: c[0].id, points: c[0].points ?? [] }))} selected={sel} onPick={(id) => open(id)}
            inset={desk ? { top: 20, right: 60, bottom: 20, left: t ? 850 : 470 } : undefined} />
        </div>

        <section className="mf-float mf-panel" aria-label="My trips">
          <div className="mf-thead"><h1>My trips</h1><span className="mf-k">{trips ? `${groups.length} ${groups.length === 1 ? "trip" : "trips"}` : ""}</span></div>
          <div className="mf-acts">
            <Link className="mf-btn go" to="/start">+ New trip</Link>
            <Link className="mf-btn" to="/ideas">Recommended trips</Link>
          </div>
          {user?.is_guest && (
            <p className="mf-note">Planning as a guest. <Link to="/register" state={{ from: "/trips" }}>Create a free account</Link> or <Link to="/login" state={{ from: "/trips" }}>sign in</Link> to keep these trips on any device.</p>
          )}
          {trips === null ? <div className="loading"><span className="spin" /></div> : trips.length === 0 ? (
            <div className="mf-empty">
              <p>No trips yet. Write your own, or start from a recommended one and make it yours.</p>
              <div className="mf-acts"><Link className="mf-btn go" to="/start">I have a trip in mind</Link><Link className="mf-btn" to="/ideas">Inspire me</Link></div>
              {!user && <p className="mf-k">Planned trips before? <Link to="/login" state={{ from: "/trips" }}>Sign in</Link> to see them.</p>}
            </div>
          ) : <div className="mf-scroll">{rows}</div>}
          {desk && trips && trips.length > 0 && <p className="mf-k mf-hint">Pick a trip to see it on the map; double-click opens it.</p>}
        </section>

        {desk && t && g && (
          <div className="mf-float mf-card mf-tripcard">
            <button type="button" className="mf-x" onClick={() => setSel(null)} aria-label="Close"><X /></button>
            {t.art && <div className="mf-art"><Illustration art={t.art} /></div>}
            <div className="mf-card-in">
              <div>
                <span className="mf-k">{when(t)} · {t.stop_count} {t.stop_count === 1 ? "stop" : "stops"}{t.estimated ? " · dates are a guess" : ""}</span>
                <h3>{t.name}</h3>
              </div>
              {t.places.length > 0 ? (
                <ol className="mf-route">{t.places.map((p, i) => <li key={i}><span className="mf-num">{i + 1}</span>{p}</li>)}</ol>
              ) : <p className="mf-k">No stops yet: open it and add the first one.</p>}
              {t.source_itinerary && <span className="mf-k">From a recommended trip</span>}
              <Link className="mf-btn go wide" to={`/trips/${t.id}`}>Open the trip →</Link>
              {g.length > 1 && (
                <div className="mf-dupe">
                  <span>You have {g.length} identical copies of this trip.</span>
                  <button type="button" className="mf-btn sm" disabled={busy} onClick={() => dropCopies(g)}>
                    Keep one, remove {g.length - 1}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

const X = () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>;
