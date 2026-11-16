import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { useItineraries } from "../components/ItineraryCards";
import { MyTripsMap } from "../components/Maps";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { countryNames, dayMonth, monthRuns, regionBest } from "../lib/format";
import type { ItineraryCard, StopArt, TripSummary } from "../lib/types";

/** Trips (Manu 2026-11-16 20:40: "non voglio avere nessuno già selezionato così che possa girare il
 *  mondo e vedere anche gli altri ... e poi manca un cerca"): a new trip, a search, the recommended
 *  trips and yours. Nothing is picked when the page opens: the globe shows every trip, thin; a tap
 *  on a row (or on its line) shows that trip with its drawings, a second tap or × goes back. */
export default function Trips() {
  const { user, loading } = useApp();
  const nav = useNavigate();
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const items = useItineraries();
  const [sel, setSel] = useState<string | null>(null);
  const [stops, setStops] = useState<{ points: number[][]; arts: (StopArt | null)[]; names: string[] } | null>(null);
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

  // Escape goes back to every trip
  useEffect(() => {
    if (!sel) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setSel(null); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [sel]);

  // the search finds a region, a country or a place on any of its routes ("Fitz Roy" finds
  // Patagonia), and your own trips by name or place
  const fold = (s: string) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const w = fold(find.trim());
  const rec = useMemo(() => {
    const all = items ?? [];
    return all.filter((x) => x.lead && (!w || all.filter((y) => y.journey === x.journey).some((y) =>
      fold([y.destination ?? "", y.title, countryNames(y.countries), ...y.places].join(" ")).includes(w))));
  }, [items, w]); // eslint-disable-line react-hooks/exhaustive-deps
  const saved = useMemo(() => (trips ?? []).filter((t) => t.saved && (!w || fold([t.name, ...(t.places ?? [])].join(" ")).includes(w))), [trips, w]); // eslint-disable-line react-hooks/exhaustive-deps

  const best = (x: ItineraryCard) => monthRuns(regionBest((items ?? []).filter((y) => y.journey === x.journey), x.weeks ?? 2));
  // the countries only when the name does not already say them ("Japan", not "Japan · Japan")
  const lands = (x: ItineraryCard) => {
    const c = countryNames([...new Set([x, ...(items ?? []).filter((y) => y.journey === x.journey)].flatMap((y) => y.countries))]);
    return fold(c) === fold(x.destination ?? x.title) ? "" : `${c} · `;
  };
  const when = (x: TripSummary) => x.start_date ? `${dayMonth(x.start_date)} – ${dayMonth(x.end_date!)}` : `${x.stop_count} ${x.stop_count === 1 ? "stop" : "stops"}`;
  const pickedRec = sel ? rec.find((x) => x.slug === sel) ?? (items ?? []).find((x) => x.slug === sel) ?? null : null;
  const pickedMine = sel ? (trips ?? []).find((x) => x.id === sel) ?? null : null;

  // a recommended trip picked: its stops' drawings (the list has only its points)
  useEffect(() => {
    setStops(null);
    if (!pickedRec) return;
    let live = true;
    api.itinerary(pickedRec.slug).then((r) => {
      if (live) setStops({ points: r.stops.map((s) => [s.latitude, s.longitude]), arts: r.stops.map((s) => s.art ?? null), names: r.stops.map((s) => s.name) });
    }).catch(() => undefined);
    return () => { live = false; };
  }, [pickedRec?.slug]); // eslint-disable-line react-hooks/exhaustive-deps

  // every trip on the globe, thin; the picked one in ink with its drawings
  const mapTrips = [
    ...rec.map((x) => x.slug === sel && stops ? { id: x.slug, ...stops } : { id: x.slug, points: x.points ?? [] }),
    ...saved.map((x) => ({ id: x.id, points: x.points ?? [], arts: x.arts, names: x.places })),
  ].filter((t) => t.points.length);
  const pick = (id: string, to: string) => (desk ? setSel(sel === id ? null : id) : nav(to));
  const pickOnMap = (id: string) => {
    const r = (items ?? []).find((x) => x.slug === id);
    pick(id, r ? `/ideas/${id}` : `/trips/${id}`);
  };

  const row = (id: string, to: string, art: StopArt | null | undefined, name: string, sub: string) => (
    <li key={id} className="mf-recrow">
      <button type="button" className={`mf-trow${sel === id ? " sel" : ""}`} aria-pressed={sel === id} onClick={() => pick(id, to)} onDoubleClick={() => nav(to)}>
        <span className="mf-thumb">{art ? <Illustration art={art} /> : null}</span>
        <span className="mf-nm"><b>{name}</b><small>{sub}</small></span>
      </button>
      {sel === id && <Link className="mf-btn go sm mf-recopen" to={to}>Open</Link>}
    </li>
  );
  const pickedName = pickedRec ? pickedRec.destination ?? pickedRec.title : pickedMine?.name;

  return (
    <main className="trk mytrips">
      <div className="mf">
        <div className="mf-map">
          <MyTripsMap trips={mapTrips} selected={sel} onPick={pickOnMap}
            inset={desk ? { top: 20, right: 60, bottom: 20, left: 470 } : undefined} />
          {desk && sel && pickedName && (
            <button type="button" className="mf-float trips-all" onClick={() => setSel(null)}>
              <X /> {pickedName} · show all trips
            </button>
          )}
        </div>

        <section className="mf-float mf-panel" aria-label="Trips">
          <div className="mf-thead"><h1>Trips</h1></div>
          <Link className="mf-btn go wide mf-new" to="/trips/new"><Plus /> New trip</Link>
          <form className="mf-say mf-search" role="search" onSubmit={(e) => e.preventDefault()}>
            <Search />
            <input type="search" value={find} onChange={(e) => { setFind(e.target.value); setSel(null); }}
              placeholder="Search a country or a place" aria-label="Search trips" />
            {find && <button type="button" aria-label="Clear" onClick={() => setFind("")}>×</button>}
          </form>
          {items === null ? <div className="loading"><span className="spin" /></div> : (
            <div className="mf-scroll">
              {saved.length > 0 && <>
                <p className="mf-k trips-h">Yours</p>
                <ul className="mf-treks">{saved.map((x) => row(x.id, `/trips/${x.id}`, x.art, x.name, when(x)))}</ul>
              </>}
              <p className="mf-k trips-h">Recommended</p>
              {rec.length ? <ul className="mf-treks">{rec.map((x) => row(x.slug, `/ideas/${x.slug}`, x.art, x.destination ?? x.title, `${lands(x)}best ${best(x)}`))}</ul>
                : <p className="mf-k">Nothing found{find ? ` for “${find}”` : ""}.</p>}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

const I = (d: string) => () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d={d} /></svg>;
const Plus = I("M12 5v14M5 12h14");
const Search = I("M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14M20 20l-4-4");
const X = I("M6 6l12 12M18 6L6 18");
