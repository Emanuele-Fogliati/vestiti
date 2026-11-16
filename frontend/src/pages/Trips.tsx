import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { useItineraries } from "../components/ItineraryCards";
import { MyTripsMap } from "../components/Maps";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { countryNames, dayMonth, monthRuns, regionBest } from "../lib/format";
import type { ItineraryCard, StopArt, TripSummary } from "../lib/types";


/** Trips (Manu 2026-11-16: "o crea un nuovo viaggio oppure viaggi raccomandati, fine"): one button
 *  to draw a new trip on the map, the recommended trips, and the trips you saved. Map first: the
 *  picked trip shows on the globe along its roads, its stops as their drawings; no card in
 *  between, the picked row has its Open button. */
export default function Trips() {
  const { user, loading } = useApp();
  const nav = useNavigate();
  const [q, setQ] = useSearchParams();
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const items = useItineraries();
  const [sel, setSel] = useState<string | null>(null);
  const [stops, setStops] = useState<{ points: number[][]; arts: (StopArt | null)[]; names: string[] }>({ points: [], arts: [], names: [] });
  const [find, setFind] = useState("");
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
  // Recommended always opens first (Manu 2026-11-16: "di default mi devi andare su Recommended")
  const tab = (q.get("tab") === "saved" ? "saved" : "recommended") as "saved" | "recommended";
  const setTab = (t: string) => { setSel(null); setQ({ tab: t }, { replace: true }); };

  // Manu 2026-11-16: one card per travel region, not one per length or month: the region's page
  // asks how long and shows when to go
  // search (Manu 2026-11-16: "nei recommended voglio anche un cerca"): a region, a country or a
  // place on any of its routes ("Fitz Roy" finds Patagonia)
  const fold = (s: string) => s.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const shown = useMemo(() => {
    const all = items ?? [];
    const w = fold(find.trim());
    return all.filter((x) => x.lead && (!w || all.filter((y) => y.journey === x.journey).some((y) =>
      fold([y.destination ?? "", y.title, countryNames(y.countries), ...y.places].join(" ")).includes(w))));
  }, [items, find]); // eslint-disable-line react-hooks/exhaustive-deps
  const best = (x: ItineraryCard) => monthRuns(regionBest((items ?? []).filter((y) => y.journey === x.journey), x.weeks ?? 2));
  // the countries only when the name does not already say them ("Japan", not "Japan · Japan")
  const lands = (x: ItineraryCard) => {
    const c = countryNames([...new Set([x, ...(items ?? []).filter((y) => y.journey === x.journey)].flatMap((y) => y.countries))]);
    return fold(c) === fold(x.destination ?? x.title) ? "" : `${c} · `;
  };
  const link = (slug: string) => `/ideas/${slug}`;
  const it = tab === "recommended" && sel ? (items ?? []).find((x) => x.slug === sel) ?? null : null;

  // a recommended trip picked: its stops on the globe, joined along the roads
  useEffect(() => {
    setStops({ points: [], arts: [], names: [] });
    if (!it) return;
    let live = true;
    api.itinerary(it.slug).then((r) => {
      if (live) setStops({ points: r.stops.map((s) => [s.latitude, s.longitude]), arts: r.stops.map((s) => s.art ?? null), names: r.stops.map((s) => s.name) });
    }).catch(() => undefined);
    return () => { live = false; };
  }, [it?.slug]); // eslint-disable-line react-hooks/exhaustive-deps

  const mapTrips = tab === "saved" ? saved.map((x) => ({ id: x.id, points: x.points ?? [], arts: x.arts, names: x.places }))
    : it && stops.points.length ? [{ id: it.slug, ...stops }] : [];
  // Saved on a wide screen: the first trip is on the map straight away, its stops as drawings
  useEffect(() => {
    if (desk && tab === "saved" && !sel && saved.length) setSel(saved[0].id);
  }, [desk, tab, saved]); // eslint-disable-line react-hooks/exhaustive-deps
  const open = (id: string, to: string) => (desk ? setSel(sel === id && tab === "recommended" ? null : id) : nav(to));
  const when = (x: TripSummary) => x.start_date ? `${dayMonth(x.start_date)} – ${dayMonth(x.end_date!)}` : `${x.stop_count} ${x.stop_count === 1 ? "stop" : "stops"}`;

  const recRows = (list: ItineraryCard[]) => (
    <ul className="mf-treks">
      {list.map((x) => (
        <li key={x.slug} className="mf-recrow">
          {/* a tap shows the trip on the map with its drawings; Open goes to its page (no card in between) */}
          <button type="button" className={`mf-trow${sel === x.slug ? " sel" : ""}`} onClick={() => open(x.slug, link(x.slug))}
            onDoubleClick={() => nav(link(x.slug))}>
            <span className="mf-thumb">{x.art ? <Illustration art={x.art} /> : null}</span>
            <span className="mf-nm"><b>{x.destination ?? x.title}</b><small>{lands(x)}best {best(x)}</small></span>
          </button>
          {sel === x.slug && <Link className="mf-btn go sm mf-recopen" to={link(x.slug)}>Open</Link>}
        </li>
      ))}
    </ul>
  );

  const savedRows = (
    <ul className="mf-treks">
      {saved.map((x) => (
        <li key={x.id} className="mf-recrow">
          <button type="button" className={`mf-trow${sel === x.id ? " sel" : ""}`} onClick={() => open(x.id, `/trips/${x.id}`)} onDoubleClick={() => nav(`/trips/${x.id}`)}>
            <span className="mf-thumb">{x.art ? <Illustration art={x.art} /> : null}</span>
            <span className="mf-nm"><b>{x.name}</b><small>{when(x)}</small></span>
          </button>
          {sel === x.id && <Link className="mf-btn go sm mf-recopen" to={`/trips/${x.id}`}>Open</Link>}
        </li>
      ))}
    </ul>
  );

  const body = tab === "recommended" ? (
    <>
      <form className="mf-say mf-search" role="search" onSubmit={(e) => e.preventDefault()}>
        <Search />
        <input type="search" value={find} onChange={(e) => { setFind(e.target.value); setSel(null); }}
          placeholder="Search a country or a place" aria-label="Search recommended trips" />
        {find && <button type="button" aria-label="Clear" onClick={() => setFind("")}>×</button>}
      </form>
      {items === null ? <div className="loading"><span className="spin" /></div>
        : <div className="mf-scroll">{shown.length ? recRows(shown) : <p className="mf-k">Nothing found.</p>}</div>}
    </>
  ) : trips === null ? <div className="loading"><span className="spin" /></div> : (
    <div className="mf-scroll">
      {saved.length ? savedRows : <div className="mf-empty"><p>Nothing saved yet.</p></div>}
    </div>
  );

  return (
    <main className="trk mytrips">
      <div className="mf">
        <div className="mf-map">
          <MyTripsMap trips={mapTrips} selected={tab === "saved" ? sel : it?.slug ?? null}
            onPick={(id) => (tab === "saved" ? open(id, `/trips/${id}`) : undefined)}
            inset={desk ? { top: 20, right: 60, bottom: 20, left: 470 } : undefined} />
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

      </div>
    </main>
  );
}

const I = (d: string) => () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d={d} /></svg>;
const Plus = I("M12 5v14M5 12h14");
const Search = I("M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14M20 20l-4-4");
