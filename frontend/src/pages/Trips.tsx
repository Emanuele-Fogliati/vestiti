import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { useItineraries } from "../components/ItineraryCards";
import { MyTripsMap } from "../components/Maps";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { countryNames, dayMonth, monthRuns, regionBest } from "../lib/format";
import type { ItineraryCard, TripSummary } from "../lib/types";

const short = (p: string) => p.replace(/ \(.*\)$/, "");

/** Trips (Manu 2026-11-16: "o crea un nuovo viaggio oppure viaggi raccomandati, fine"): one button
 *  to draw a new trip on the map, the recommended trips, and the trips you saved. Map first: the
 *  picked trip shows on the globe along its roads, its card opens beside the panel. */
export default function Trips() {
  const { user, loading } = useApp();
  const nav = useNavigate();
  const [q, setQ] = useSearchParams();
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const items = useItineraries();
  const [sel, setSel] = useState<string | null>(null);
  const [stops, setStops] = useState<number[][]>([]);
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
  // Saved opens first when there is something in it
  const tab = (q.get("tab") ?? (trips && saved.length ? "saved" : trips ? "recommended" : "")) as "saved" | "recommended" | "";
  const setTab = (t: string) => { setSel(null); setQ({ tab: t }, { replace: true }); };

  // Manu 2026-11-16: one card per travel region, not one per length or month: the region's page
  // asks how long and shows when to go
  const shown = useMemo(() => (items ?? []).filter((x) => x.lead), [items]);
  const best = (x: ItineraryCard) => monthRuns(regionBest((items ?? []).filter((y) => y.journey === x.journey), x.weeks ?? 2));
  const weeks = (x: ItineraryCard) => {
    const w = [...new Set((items ?? []).filter((y) => y.journey === x.journey).map((y) => y.weeks ?? 0))].sort();
    return w.length > 1 ? `${w[0]}–${w[w.length - 1]} weeks` : `${w[0]} week${w[0] === 1 ? "" : "s"}`;
  };
  const lands = (x: ItineraryCard) => countryNames([...new Set([x, ...(items ?? []).filter((y) => y.journey === x.journey)].flatMap((y) => y.countries))]);
  const link = (slug: string) => `/ideas/${slug}`;
  const it = tab === "recommended" && sel ? (items ?? []).find((x) => x.slug === sel) ?? null : null;
  const t = tab === "saved" && sel ? saved.find((x) => x.id === sel) ?? null : null;

  // a recommended trip picked: its stops on the globe, joined along the roads
  useEffect(() => {
    setStops([]);
    if (!it) return;
    let live = true;
    api.itinerary(it.slug).then((r) => { if (live) setStops(r.stops.map((s) => [s.latitude, s.longitude])); }).catch(() => undefined);
    return () => { live = false; };
  }, [it?.slug]); // eslint-disable-line react-hooks/exhaustive-deps

  const mapTrips = tab === "saved" ? saved.map((x) => ({ id: x.id, points: x.points ?? [] }))
    : it && stops.length ? [{ id: it.slug, points: stops }] : [];
  const open = (id: string, to: string) => (desk ? setSel(sel === id ? null : id) : nav(to));
  const when = (x: TripSummary) => x.start_date ? `${dayMonth(x.start_date)} – ${dayMonth(x.end_date!)}` : "No dates";

  const recRows = (list: ItineraryCard[]) => (
    <ul className="mf-treks">
      {list.map((x) => (
        <li key={x.slug}>
          <button type="button" className={`mf-trow${sel === x.slug ? " sel" : ""}`} onClick={() => open(x.slug, link(x.slug))}>
            <span className="mf-thumb">{x.art ? <Illustration art={x.art} /> : null}</span>
            <span className="mf-nm"><b>{x.destination ?? x.title}</b><small>{lands(x)} · best {best(x)}</small></span>
          </button>
        </li>
      ))}
    </ul>
  );

  const savedRows = (
    <ul className="mf-treks">
      {saved.map((x) => (
        <li key={x.id}>
          <button type="button" className={`mf-trow${sel === x.id ? " sel" : ""}`} onClick={() => open(x.id, `/trips/${x.id}`)} onDoubleClick={() => nav(`/trips/${x.id}`)}>
            <span className="mf-thumb">{x.art ? <Illustration art={x.art} /> : null}</span>
            <span className="mf-nm"><b>{x.name}</b><small>{when(x)} · {x.stop_count} {x.stop_count === 1 ? "stop" : "stops"}</small></span>
          </button>
        </li>
      ))}
    </ul>
  );

  const body = tab === "recommended" ? (
    <>
      {items === null ? <div className="loading"><span className="spin" /></div>
        : <div className="mf-scroll">{shown.length ? recRows(shown) : <p className="mf-k">None for these filters.</p>}</div>}
    </>
  ) : tab === "saved" ? (
    <div className="mf-scroll">
      {saved.length ? savedRows : (
        <div className="mf-empty"><p>Nothing saved yet.</p><p className="mf-k">Press Save on a trip to keep it here.</p></div>
      )}
    </div>
  ) : <div className="loading"><span className="spin" /></div>;

  return (
    <main className="trk mytrips">
      <div className="mf">
        <div className="mf-map">
          <MyTripsMap trips={mapTrips} selected={tab === "saved" ? sel : it?.slug ?? null}
            onPick={(id) => (tab === "saved" ? open(id, `/trips/${id}`) : undefined)}
            inset={desk ? { top: 20, right: 60, bottom: 20, left: it || t ? 850 : 470 } : undefined} />
        </div>

        <section className="mf-float mf-panel" aria-label="Trips">
          <div className="mf-thead"><h1>Trips</h1></div>
          <Link className="mf-btn go wide mf-new" to="/trips/new"><Plus /> New trip</Link>
          <div className="mf-seg" role="tablist" aria-label="Trips">
            <button type="button" role="tab" aria-selected={tab === "recommended"} className={tab === "recommended" ? "on" : ""} onClick={() => setTab("recommended")}>Recommended</button>
            <button type="button" role="tab" aria-selected={tab === "saved"} className={tab === "saved" ? "on" : ""} onClick={() => setTab("saved")}>
              Saved{saved.length ? ` · ${saved.length}` : ""}</button>
          </div>
          {body}
        </section>

        {desk && it && (
          <div className="mf-float mf-card mf-tripcard">
            <button type="button" className="mf-x" onClick={() => setSel(null)} aria-label="Close"><X /></button>
            {it.art && <div className="mf-art"><Illustration art={it.art} label={it.title} /></div>}
            <div className="mf-card-in">
              <div>
                <span className="mf-k">{lands(it)} · {weeks(it)} · best {best(it)}</span>
                <h3>{it.destination ?? it.title}</h3>
                {it.journey_blurb && <p className="mf-lede">{it.journey_blurb}</p>}
                <span className="mf-k">For example, {it.days} days:</span>
              </div>
              <ol className="mf-route">{it.places.map((p, i) => <li key={i}><span className="mf-num">{i + 1}</span>{short(p)}</li>)}</ol>
              <Link className="mf-btn go wide" to={link(it.slug)}>Open →</Link>
            </div>
          </div>
        )}
        {desk && t && (
          <div className="mf-float mf-card mf-tripcard">
            <button type="button" className="mf-x" onClick={() => setSel(null)} aria-label="Close"><X /></button>
            {t.art && <div className="mf-art"><Illustration art={t.art} /></div>}
            <div className="mf-card-in">
              <div>
                <span className="mf-k">{when(t)} · {t.stop_count} {t.stop_count === 1 ? "stop" : "stops"}</span>
                <h3>{t.name}</h3>
              </div>
              {t.places.length > 0 && <ol className="mf-route">{t.places.map((p, i) => <li key={i}><span className="mf-num">{i + 1}</span>{p}</li>)}</ol>}
              <Link className="mf-btn go wide" to={`/trips/${t.id}`}>Open →</Link>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

const I = (d: string) => () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d={d} /></svg>;
const X = I("M6 6l12 12M18 6L6 18");
const Plus = I("M12 5v14M5 12h14");
