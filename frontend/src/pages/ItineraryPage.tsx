import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ElevationProfile } from "../components/ElevationProfile";
import { Illustration } from "../components/Illustration";
import { TripMap } from "../components/Maps";
import { PlaceGuide } from "../components/PlaceGuide";
import { Visits } from "../components/Stops";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { MONTHS, MONTH_LONG, activityText, countryNames, monthYear, nights, today } from "../lib/format";
import type { Itinerary, ItineraryStop, ItineraryWear, Journey, Stop } from "../lib/types";
import { DRESS_ME } from "../lib/words";

/** The region's pickers (Manu 2026-11-16: "lo chiede all'utente quanto ci vuole stare ... scopre
 *  sul tool in che mese andare"): how many weeks, then the twelve months, the best ones marked,
 *  the ones with no route for that length off. Each pick opens the route of that length and season. */
function Pickers({ j, it, onPick }: { j: Journey; it: Itinerary; onPick: (slug: string, month: number) => void }) {
  const month = it.wear.month;
  const weeks = [...new Set(j.routes.map((r) => r.weeks))].sort();
  const mine = j.routes.filter((r) => r.weeks === it.weeks);
  const pickWeeks = (w: number) => {
    const rs = j.routes.filter((r) => r.weeks === w);
    const r = rs.find((x) => x.months.includes(month)) ?? rs[0];
    onPick(r.slug, r.months.includes(month) ? month : (r.best_months[0] ?? r.months[0]));
  };
  return (
    <div className="mf-pick">
      <div className="mf-seg mf-weeks" role="radiogroup" aria-label="How long" style={{ gridTemplateColumns: `repeat(${weeks.length}, 1fr)` }}>
        {weeks.map((w) => (
          <button type="button" role="radio" key={w} aria-checked={w === it.weeks} className={w === it.weeks ? "on" : ""}
            onClick={() => pickWeeks(w)}>{w} {w === 1 ? "week" : "weeks"}</button>
        ))}
      </div>
      <div className="mf-months" role="radiogroup" aria-label="When">
        {MONTHS.map((m, i) => {
          const r = mine.find((x) => x.months.includes(i + 1));
          const best = !!r && r.best_months.includes(i + 1);
          return (
            <button type="button" role="radio" key={m} aria-checked={i + 1 === month} disabled={!r}
              className={`${i + 1 === month ? "on" : ""}${best ? " best" : ""}`}
              title={!r ? "Not a good time for this trip" : best ? "Best weather" : "Possible, not the best weather"}
              onClick={() => r && onPick(r.slug, i + 1)}>{m}</button>
          );
        })}
      </div>
      <span className="mf-k mf-mlegend"><i className="best" /> best weather <i /> possible <i className="off" /> no trip then</span>
    </div>
  );
}

/** What to wear in the chosen month (Manu 2026-11-16: "per ogni mese cosa mettere come vestito"):
 *  worked out by the layer engine from each stop's climate that month, not written by hand. */
function Wear({ w }: { w: ItineraryWear }) {
  const worn = w.pieces.filter((p) => !p.pack);
  const pack = w.pieces.filter((p) => p.pack);
  return (
    <div className="mf-tsec mf-iwear">
      <b className="mf-sub">What to wear in {MONTH_LONG[w.month - 1]}</b>
      <span className="mf-k">{w.low}° to {w.high}° · rain up to {w.rain}% of days{w.top_m >= 1500 ? ` · up to ${w.top_m.toLocaleString("en-US")} m` : ""}</span>
      {w.cold.feels < 15 && <span className="mf-k">Coldest: feels like {w.cold.feels}° in {w.cold.place}, {w.cold.what.replace(/(\d{4,}) m/, (_, n) => `${Number(n).toLocaleString("en-US")} m`)}.</span>}
      <div className="tags">{worn.map((p) => <span className="tag" key={p.slot}>{p.name}</span>)}</div>
      {pack.length > 0 && <p className="mf-k">In the bag, just in case: {pack.map((p) => p.name.toLowerCase()).join(", ")}.</p>}
      {w.hot && <p className="mf-k">Warm in {w.hot.names.filter((n, i, a) => a.indexOf(n) === i).join(", ")}: {w.hot.pieces.join(", ").toLowerCase()}.</p>}
      <span className="mf-k">From the {MONTHS[w.month - 1]} climate of each stop. Make the trip yours for the full kit with products.</span>
    </div>
  );
}

/** "Dress me for this trip": optional start date, then the itinerary becomes the user's own
 *  trip (stops, days and activities can all be changed there) and the kit is worked out. */
function PackForm({ it }: { it: Itinerary }) {
  const { ensureUser } = useApp();
  const nav = useNavigate();
  const [start, setStart] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function pack(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await ensureUser();
      const t = await api.packItinerary(it.slug, start || undefined, start ? undefined : it.wear.month);
      nav(`/trips/${t.id}`);
    } catch (e2) {
      setErr((e2 as Error).message);
      setBusy(false);
    }
  }

  return (
    <form className="mf-pack" onSubmit={pack} aria-label={DRESS_ME}>
      <div className="mf-pack-t">
        <b>Like it?</b>
        <span className="mf-k">Make it yours: change the stops, then Save.</span>
      </div>
      <label className="mf-pack-d"><span className="mf-k">Leaving</span>
        <input type="date" value={start} min={today()} onChange={(e) => setStart(e.target.value)}
          title={start ? `${it.days} days from this date` : `No date yet? We plan for ${monthYear(it.start_date)}`} />
      </label>
      <button className="mf-btn go" type="submit" disabled={busy}>{busy ? <span className="spin" /> : DRESS_ME}</button>
      {err && <p className="err">{err}</p>}
    </form>
  );
}

/** One stop of the recommended trip, as the card beside the map (inline on a phone). */
function StopCard({ stop, dayFrom, desk, onClose }: { stop: ItineraryStop; dayFrom: number; desk: boolean; onClose: () => void }) {
  const n = nights(stop.start_date, stop.end_date);
  return (
    <div className={desk ? "mf-float mf-card mf-icard" : "mf-icard in"}>
      {desk && <button type="button" className="mf-x" onClick={onClose} aria-label="Close"><X /></button>}
      {stop.art && <div className="mf-art"><Illustration art={stop.art} label={stop.name} /></div>}
      <div className="mf-card-in">
        <div>
          <span className="mf-k">{n > 1 ? `Days ${dayFrom}–${dayFrom + n - 1}` : `Day ${dayFrom}`} · {Math.round(stop.elevation_m).toLocaleString("en-US")} m</span>
          <h3>{stop.name}</h3>
        </div>
        <div className="tags">{stop.activities.map((a, i) => <span className="tag" key={i}>{activityText(a)}</span>)}</div>
        <PlaceGuide guide={stop.guide} />
        <ol className="mf-plan">
          {stop.plan.map((p, i) => <li key={i}><span className="mf-k">Day {dayFrom + i}</span>{p}</li>)}
        </ol>
        {/* the day plan already names every place: only the ones with their own picture come back here */}
        <Visits stop={{ ...stop, plan: undefined, visits: (stop.visits ?? []).filter((v) => v.art && v.art.id !== stop.art?.id) }}
          dayFrom={dayFrom} flat />
        {stop.do.length > 0 && <div className="mf-tip"><b className="mf-sub">Worth it</b><ul>{stop.do.map((t, i) => <li key={i}>{t}</li>)}</ul></div>}
        {stop.skip.length > 0 && <div className="mf-tip skip"><b className="mf-sub">Skip</b><ul>{stop.skip.map((t, i) => <li key={i}>{t}</li>)}</ul></div>}
        {stop.excursions.length > 0 && (
          <div className="mf-tip">
            <b className="mf-sub">Book a tour here</b>
            {stop.excursions.map((x, i) => (
              <div className="mf-exc" key={i}>
                <span>{x.title}</span>
                <span>{x.links.map((l) => <a key={l.provider} className="mf-btn sm" href={l.href} target="_blank" rel="noopener sponsored">{l.label} ↗</a>)}</span>
              </div>
            ))}
            <span className="mf-k">Tour links go to GetYourGuide and Viator. We may earn a commission; it never decides what we suggest or tell you to skip.</span>
          </div>
        )}
      </div>
    </div>
  );
}

/** A recommended trip, map first like the trip page (Manu 2026-11-16): the route on the map, the
 *  stops in the panel, a stop opens its card beside it, and "Dress me" sits in the bar below. */
export default function ItineraryPage() {
  const { slug = "" } = useParams();
  const [q] = useSearchParams();
  const nav = useNavigate();
  const month = Number(q.get("month")) || undefined;
  const [it, setIt] = useState<Itinerary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [desk, setDesk] = useState(() => typeof matchMedia === "undefined" || matchMedia("(min-width: 900px)").matches);

  useEffect(() => {
    const mq = matchMedia("(min-width: 900px)");
    const f = () => setDesk(mq.matches);
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, []);

  useEffect(() => {
    setIt(null); setSel(null);
  }, [slug]);

  // a new month keeps the page (and the open stop): only the dates and the clothes change
  useEffect(() => {
    setErr(null);
    let live = true;
    api.itinerary(slug, undefined, month).then((x) => { if (live) setIt(x); })
      .catch((e) => { if (live) setErr((e as Error).message); });
    return () => { live = false; };
  }, [slug, month]);

  useEffect(() => {
    if (it && matchMedia("(min-width: 900px)").matches && it.stops.length) setSel(0);
  }, [it?.slug]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <main className="page"><div className="wrap"><p className="err">{err}</p><Link to="/trips?tab=recommended">All recommended trips</Link></div></main>;
  if (!it) return <main className="page"><div className="wrap"><p className="loading"><span className="spin" /></p></div></main>;

  const starts: number[] = [];
  it.stops.reduce((d, s) => { starts.push(d); return d + nights(s.start_date, s.end_date); }, 1);
  const stop = sel != null ? it.stops[sel] : null;
  const inset = desk ? { top: 20, right: 60, bottom: 130, left: stop ? 870 : 470 } : { top: 0, right: 0, bottom: 22, left: 0 };
  const card = stop && <StopCard stop={stop} dayFrom={starts[sel!]} desk={desk} onClose={() => setSel(null)} />;

  const rows = (
    <ol className="mf-stops">
      {it.stops.map((s, i) => {
        const n = nights(s.start_date, s.end_date);
        return (
          <li key={s.id}>
            <button type="button" className={`mf-trow${sel === i ? " sel" : ""}`} onClick={() => setSel(sel === i && desk ? null : i)}>
              <span className="mf-num">{i + 1}</span>
              {s.art && <span className="mf-thumb"><Illustration art={s.art} /></span>}
              <span className="mf-nm">
                <b>{s.name}</b>
                <small>{n > 1 ? `Days ${starts[i]}–${starts[i] + n - 1}` : `Day ${starts[i]}`} · {s.activities.map(activityText).join(", ")}</small>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );

  const groups = it.group_trips.length > 0 && (
    <div className="mf-tsec">
      <b className="mf-sub">Rather go with a group?</b>
      <span className="mf-k">Organised trips on a similar route. The clothes are still on you.</span>
      <ul className="mf-groups">
        {it.group_trips.map((g, i) => (
          <li key={i}><a href={g.href} target="_blank" rel="noopener sponsored"><b>{g.title}</b><span className="mf-k">{g.operator} · {g.days} days ↗</span></a></li>
        ))}
      </ul>
    </div>
  );

  return (
    <main className="trk itinerary-mf">
      <div className="mf">
        <div className="mf-map">
          <TripMap stops={it.stops as unknown as Stop[]} focusIndex={sel} bare inset={inset} onPin={(i) => setSel(i)} />
        </div>

        <section className="mf-float mf-panel" aria-label={it.title}>
          {!desk && stop ? (
            <>
              <button type="button" className="mf-btn sm mf-back" onClick={() => setSel(null)}><Back /> All stops</button>
              {card}
            </>
          ) : (
            <>
              <div className="mf-trailhead">
                <Link className="mf-k mf-crumb" to="/trips?tab=recommended"><Back /> Recommended · {countryNames(it.journey?.countries ?? it.countries)}</Link>
                <h1>{it.journey?.name ?? it.title}</h1>
                {it.journey && <Pickers j={it.journey} it={it} onPick={(s, m) => nav(`/ideas/${s}?month=${m}`, { replace: true })} />}
              </div>
              <div className={desk ? "mf-scroll" : "mf-ibody"}>
                {it.journey && <b className="mf-sub">{it.title}</b>}
                <dl className="tfacts">
                  <div><dt>Days</dt><dd>{it.days}</dd></div>
                  <div><dt>Stops</dt><dd>{it.stops.length}</dd></div>
                  <div><dt>Highest</dt><dd>{Math.round(it.highest_m).toLocaleString("en-US")} m</dd></div>
                </dl>
                <p className="mf-lede">{it.summary}</p>
                <Wear w={it.wear} />
                <b className="mf-sub">Day by day</b>
                {rows}
                <ElevationProfile stops={it.stops as unknown as Stop[]} selected={sel ?? -1} onSelect={(i) => setSel(i)} />
                {it.season_note && <p className="mf-k">{it.season_note}</p>}
                {groups}
              </div>
            </>
          )}
          {!desk && <div className="mf-phone-go"><PackForm it={it} /></div>}
        </section>

        {desk && card}
        {desk && <section className="mf-float mf-buy mf-packbar" aria-label={DRESS_ME}><PackForm it={it} /></section>}
      </div>
    </main>
  );
}

const Back = () => <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>;
const X = () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>;
