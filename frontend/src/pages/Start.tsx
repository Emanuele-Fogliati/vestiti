import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useItineraries } from "../components/ItineraryCards";
import { Illustration } from "../components/Illustration";
import { HomeGlobe } from "../components/Maps";
import { TripStarter } from "../components/TripStarter";
import { api } from "../lib/api";
import { MONTHS, monthRange } from "../lib/format";
import type { GlobeFocus } from "../components/Globe";
import type { ItineraryCard } from "../lib/types";

export const DRESS_ME = "Dress me for this trip";

const LENGTHS: [string, (d: number) => boolean][] = [
  ["Any length", () => true], ["Up to 10 days", (d) => d <= 10], ["11–14 days", (d) => d > 10 && d <= 14], ["15+ days", (d) => d >= 15],
];
const short = (p: string) => p.replace(/ \(.*\)$/, "");

/** Your own trip: say it, type it, or list the stops (components/TripStarter). */
export function OwnTripForm({ compact }: { compact?: boolean }) {
  return <TripStarter compact={compact} />;
}

/** One place to start a trip, map first like My trips and the trip page (Manu 2026-11-16): the
 *  globe fills the screen, the panel on the left has the two ways in, "I have a trip in mind" and
 *  "Inspire me"; a recommended trip opens its card beside the panel and its stops light up. */
export default function Start({ tab }: { tab: "own" | "ideas" }) {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const items = useItineraries();
  const [month, setMonth] = useState<number | null>(null);
  const [len, setLen] = useState(0);
  const [sel, setSel] = useState<string | null>(null);
  const [focus, setFocus] = useState<GlobeFocus[]>([]);
  const [desk, setDesk] = useState(() => typeof matchMedia === "undefined" || matchMedia("(min-width: 900px)").matches);

  useEffect(() => {
    const mq = matchMedia("(min-width: 900px)");
    const f = () => setDesk(mq.matches);
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, []);
  useEffect(() => { setSel(null); setFocus([]); }, [tab]);

  // a recommended trip picked: its stops light up on the globe
  useEffect(() => {
    if (!sel) { if (tab === "ideas") setFocus([]); return; }
    let live = true;
    api.itinerary(sel).then((it) => {
      if (live) setFocus(it.stops.map((s) => ({ lat: s.latitude, lon: s.longitude, name: short(s.name) })));
    }).catch(() => undefined);
    return () => { live = false; };
  }, [sel, tab]);

  const picked = sel ? (items ?? []).find((x) => x.slug === sel) ?? null : null;
  const lenOk = LENGTHS[len][1];
  const shown = useMemo(() => (items ?? []).filter((it) => (month === null || it.best_months.includes(month)) && lenOk(it.days)),
    [items, month, lenOk]);
  const open = (slug: string) => (desk ? setSel(sel === slug ? null : slug) : nav(`/ideas/${slug}`));

  const rows = (list: ItineraryCard[]) => (
    <ul className="mf-treks">
      {list.map((it) => (
        <li key={it.slug}>
          <button type="button" className={`mf-trow${sel === it.slug ? " sel" : ""}`} onClick={() => open(it.slug)} onDoubleClick={() => nav(`/ideas/${it.slug}`)}>
            <span className="mf-thumb">{it.art ? <Illustration art={it.art} /> : null}</span>
            <span className="mf-nm">
              <b>{it.title}</b>
              <small>{it.days} days · best {monthRange(it.best_months)}</small>
              <small className="mf-base">{it.places.map(short).join(" → ")}</small>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );

  const doors = (
    <div className="mf-seg" role="tablist" aria-label="How do you want to start?">
      <button type="button" role="tab" aria-selected={tab === "own"} className={tab === "own" ? "on" : ""} onClick={() => nav("/start")}>I have a trip in mind</button>
      <button type="button" role="tab" aria-selected={tab === "ideas"} className={tab === "ideas" ? "on" : ""} onClick={() => nav("/ideas")}>Inspire me</button>
    </div>
  );

  const own = (
    <div className="mf-scroll mf-own">
      <TripStarter compact initial={params.get("q") ?? undefined}
        onStops={(s) => setFocus(s.map((x) => ({ lat: x.lat, lon: x.lon, name: x.name })))} />
      <p className="mf-k">Have the whole program from an agency or a chat? <Link to="/trips/new">Paste it</Link>.</p>
      <div className="mf-tsec">
        <b className="mf-sub">Rather start from a ready trip?</b>
        {items === null ? <div className="loading"><span className="spin" /></div> : rows(items.slice(0, 3))}
        <Link className="mf-btn wide" to="/ideas">All {items?.length ?? ""} recommended trips →</Link>
      </div>
    </div>
  );

  const ideas = (
    <>
      <div className="mf-filters">
        <div className="mf-chips" role="group" aria-label="When do you travel?">
          <button type="button" className={month === null ? "on" : ""} onClick={() => setMonth(null)}>Any month</button>
          {MONTHS.map((m, i) => <button key={m} type="button" className={month === i + 1 ? "on" : ""} onClick={() => setMonth(i + 1)}>{m}</button>)}
        </div>
        <div className="mf-chips" role="group" aria-label="How long?">
          {LENGTHS.map(([l], i) => <button key={l} type="button" className={len === i ? "on" : ""} onClick={() => setLen(i)}>{l}</button>)}
        </div>
      </div>
      {items === null ? <div className="loading"><span className="spin" /></div> : (
        <div className="mf-scroll">
          {shown.length ? rows(shown) : (
            <div className="mf-empty">
              <p>No recommended trip fits {month ? `${MONTHS[month - 1]} ` : ""}{len ? `and ${LENGTHS[len][0].toLowerCase()}` : ""} yet.</p>
              <div className="mf-acts"><button type="button" className="mf-btn" onClick={() => { setMonth(null); setLen(0); }}>Show all</button>
                <Link className="mf-btn go" to="/start">Plan my own trip</Link></div>
            </div>
          )}
        </div>
      )}
      <p className="mf-k">Routes built from the places travellers visit most. Best months are when the weather is most reliable; we dress you for your own dates either way.</p>
    </>
  );

  return (
    <main className="trk newtrip">
      <div className="mf">
        <div className="mf-map mf-globe" data-left={picked && desk ? 870 : 480}><HomeGlobe bare focus={focus} /></div>

        <section className="mf-float mf-panel" aria-label="New trip">
          <div className="mf-thead"><h1>New trip</h1>{tab === "ideas" && items && <span className="mf-k">{shown.length} recommended</span>}</div>
          {doors}
          {tab === "own" ? own : ideas}
        </section>

        {desk && picked && (
          <div className="mf-float mf-card mf-tripcard">
            <button type="button" className="mf-x" onClick={() => setSel(null)} aria-label="Close"><X /></button>
            {picked.art && <div className="mf-art"><Illustration art={picked.art} label={picked.title} /></div>}
            <div className="mf-card-in">
              <div>
                <span className="mf-k">{picked.days} days · best {monthRange(picked.best_months)} · up to {Math.round(picked.highest_m).toLocaleString("en-US")} m</span>
                <h3>{picked.title}</h3>
              </div>
              <p className="mf-lede">{picked.summary}</p>
              <ol className="mf-route">{picked.places.map((p, i) => <li key={i}><span className="mf-num">{i + 1}</span>{short(p)}</li>)}</ol>
              <Link className="mf-btn go wide" to={`/ideas/${picked.slug}`}>See it day by day →</Link>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

const X = () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>;
