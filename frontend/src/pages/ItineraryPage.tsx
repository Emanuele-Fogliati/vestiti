import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ElevationProfile } from "../components/ElevationProfile";
import { Illustration } from "../components/Illustration";
import { TripMap } from "../components/Maps";
import { PlaceGuide } from "../components/PlaceGuide";
import { Visits } from "../components/Stops";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { activityText, monthRange, monthYear, nights, today } from "../lib/format";
import { terrainFor } from "../lib/terrain";
import type { Itinerary, ItineraryStop } from "../lib/types";
import { DRESS_ME } from "./Start";

const COUNTRY: Record<string, string> = { PE: "Peru", AR: "Argentina", CL: "Chile", IS: "Iceland", VN: "Vietnam" };

/** "Dress me for this trip": optional start date, then the itinerary becomes the user's own
 *  trip (stops, days and activities can all be changed there) and the kit is worked out. */
function PackForm({ it, id }: { it: Itinerary; id?: string }) {
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
      const t = await api.packItinerary(it.slug, start || undefined);
      nav(`/trips/${t.id}`);
    } catch (e2) {
      setErr((e2 as Error).message);
      setBusy(false);
    }
  }

  return (
    <form className="brief pack" onSubmit={pack} aria-label={DRESS_ME}>
      <h2>Like this trip?</h2>
      <p className="small muted">We read the weather at every stop and dress you for all of it: what to wear, what to pack, at three budgets. It becomes your trip, so you can change stops and days after. Free.</p>
      <div className="field">
        <label htmlFor={`start-${id ?? "top"}`}>When do you leave? (optional)</label>
        <input id={`start-${id ?? "top"}`} type="date" value={start} min={today()} onChange={(e) => setStart(e.target.value)} />
      </div>
      <p className="small muted">{start ? `${it.days} days from this date.` : `No date yet? We plan for ${monthYear(it.start_date)} and you set the date later.`}</p>
      {err && <p className="err">{err}</p>}
      <button className="btn primary" type="submit" disabled={busy}>{busy ? <span className="spin" /> : DRESS_ME}</button>
    </form>
  );
}

function StopBlock({ stop, index, dayFrom }: { stop: ItineraryStop; index: number; dayFrom: number }) {
  const n = nights(stop.start_date, stop.end_date);
  const terrain = terrainFor(stop, index);
  return (
    <li className="stop istop" id={`stop-${index}`}>
      <div className="days">{n > 1 ? "Days" : "Day"} <b>{n > 1 ? `${dayFrom}–${dayFrom + n - 1}` : dayFrom}</b></div>
      <Illustration terrain={terrain} art={stop.art} />
      <div className="info">
        <h3>{stop.name}</h3>
        <div className="acts">
          {stop.activities.map((a, i) => <span className="tag" key={i}>{activityText(a)}</span>)}
          <span className="tag">{Math.round(stop.elevation_m).toLocaleString("en-US")} m</span>
        </div>
        <PlaceGuide guide={stop.guide} />
        <ol className="plan">
          {stop.plan.map((p, i) => <li key={i}><span className="vd">Day {dayFrom + i}</span>{p}</li>)}
        </ol>
        {/* the day plan already names every place: only the ones with their own picture come back here */}
        <Visits stop={{ ...stop, visits: (stop.visits ?? []).filter((v) => v.art && v.art.id !== stop.art?.id) }}
          dayFrom={dayFrom} terrain={terrain} />
        {(stop.do.length > 0 || stop.skip.length > 0) && (
          <div className="tips">
            {stop.do.length > 0 && <div className="tip-do"><h4>Worth it</h4><ul>{stop.do.map((t, i) => <li key={i}>{t}</li>)}</ul></div>}
            {stop.skip.length > 0 && <div className="tip-skip"><h4>Skip</h4><ul>{stop.skip.map((t, i) => <li key={i}>{t}</li>)}</ul></div>}
          </div>
        )}
        {stop.excursions.length > 0 && (
          <div className="exc">
            <h4>Book a tour here</h4>
            {stop.excursions.map((x, i) => (
              <div className="exc-row" key={i}>
                <span>{x.title}</span>
                <span className="exc-links">
                  {x.links.map((l) => (
                    <a key={l.provider} className="btn sm" href={l.href} target="_blank" rel="noopener sponsored">{l.label} ↗</a>
                  ))}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}

export default function ItineraryPage() {
  const { slug = "" } = useParams();
  const [it, setIt] = useState<Itinerary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState(0);

  useEffect(() => {
    setIt(null); setErr(null);
    api.itinerary(slug).then(setIt).catch((e) => setErr((e as Error).message));
  }, [slug]);

  if (err) return <main className="page"><div className="wrap"><p className="err">{err}</p><Link to="/ideas">All recommended trips</Link></div></main>;
  if (!it) return <main className="page"><div className="wrap"><p className="loading"><span className="spin" /></p></div></main>;

  const starts: number[] = [];
  it.stops.reduce((d, s) => { starts.push(d); return d + nights(s.start_date, s.end_date); }, 1);
  const pick = (i: number) => { setSel(i); document.getElementById(`stop-${i}`)?.scrollIntoView({ behavior: "smooth", block: "start" }); };

  return (
    <main>
      <section className="hero">
        <div className="wrap hero-in">
          <div>
            <p className="kicker"><Link to="/ideas">Recommended trips</Link> · {it.countries.map((c) => COUNTRY[c] ?? c).join(" & ")}</p>
            <h1 className="ititle">{it.title}</h1>
            <p className="lede">{it.summary}</p>
            <div className="facts">
              <div className="fact"><b>{it.days}</b><span>Days, {it.stops.length} stops</span></div>
              <div className="fact"><b>{monthRange(it.best_months)}</b><span>Best months</span></div>
              <div className="fact"><b>{Math.round(it.highest_m).toLocaleString("en-US")} m</b><span>Highest point</span></div>
            </div>
            <p className="small muted" style={{ marginTop: 14, maxWidth: "62ch" }}>{it.season_note}</p>
          </div>
          <PackForm it={it} />
        </div>
      </section>

      <section className="band alt">
        <div className="wrap">
          <header className="sh"><p className="sh-k">Day by day</p><h2>The route</h2>
            <p>Stops in the order that works best. Tap a stop on the map to zoom in and see what is around it.</p></header>
          <TripMap stops={it.stops} />
          <ElevationProfile stops={it.stops} selected={sel} onSelect={pick} />
          <ol className="stops" style={{ marginTop: 24 }}>
            {it.stops.map((s, i) => <StopBlock key={s.id} stop={s} index={i} dayFrom={starts[i]} />)}
          </ol>
          <p className="small muted" style={{ marginTop: 16 }}>
            Tour links go to GetYourGuide and Viator. We may earn a commission when you book, at no extra cost to you.
            It never decides which places we suggest or tell you to skip.
          </p>
        </div>
      </section>

      {it.group_trips.length > 0 && (
        <section className="band">
          <div className="wrap">
            <header className="sh"><p className="sh-k">Rather go with a group?</p><h2>Organised trips on a similar route</h2>
              <p>Guide, transport and most tours included. The clothes are still on you: tap “{DRESS_ME}” either way.</p></header>
            <ul className="gtrips">
              {it.group_trips.map((g, i) => (
                <li key={i}>
                  <a href={g.href} target="_blank" rel="noopener sponsored">
                    <span className="label">{g.operator}</span>
                    <b>{g.title}</b>
                    <span className="small muted">{g.days} days ↗</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      <section className="band alt">
        <div className="wrap pack-end">
          <PackForm it={it} id="bottom" />
        </div>
      </section>
    </main>
  );
}
