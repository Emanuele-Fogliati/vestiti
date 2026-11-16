import { Fragment, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { WalkWear } from "../components/WalkWear";
import { Illustration } from "../components/Illustration";
import { DIFFICULTY, TrailFacts } from "../components/TrailCards";
import TrailMap from "../components/TrailMap";
import TrailProfile from "../components/TrailProfile";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { activityText } from "../lib/format";
import type { Activity, Trail, TripSummary } from "../lib/types";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const fmt = (n: number) => n.toLocaleString("en-US");
const hrs = (h: number) => (h < 1 ? `${Math.max(1, Math.round(h * 60))} min` : `${Math.floor(h)} h${h % 1 >= 0.25 ? ` ${Math.round((h % 1) * 60)}` : ""}`);

/** One trail, all you need to walk it (Manu, 2026-11-13), map first like Treks (2026-11-16):
 *  the trail fills the screen, the way and the facts in the panel on the left, what to wear in
 *  your month in the card beside it, and what to get for it in the bar at the bottom. */
export default function TrailPage() {
  const { id = "" } = useParams();
  const [q] = useSearchParams();
  const tripId = q.get("trip"), stopId = q.get("stop");
  const [t, setT] = useState<Trail | null>(null);
  const { user, ensureUser, setUser, toast } = useApp();
  const [err, setErr] = useState<string | null>(null);
  const [focus, setFocus] = useState<number | null>(null);
  const [desk, setDesk] = useState(() => typeof matchMedia === "undefined" || matchMedia("(min-width: 900px)").matches);
  const [month, setMonth] = useState<number | null>(null);

  useEffect(() => {
    const mq = matchMedia("(min-width: 900px)");
    const f = () => setDesk(mq.matches);
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, []);

  useEffect(() => {
    setT(null); setErr(null); setFocus(null); setMonth(null);
    api.trail(id).then((x) => {
      setT(x);
      const now = new Date().getMonth() + 1;
      setMonth(Number(q.get("month")) || (x.months.includes(now) ? now : x.months[0] ?? now));
    }).catch((e) => setErr((e as Error).message));
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <div className="wrap section"><h1>Trail not found</h1><p>{err}</p><Link to="/trails">All trails</Link></div>;
  if (!t || !month) return <div className="loading"><span className="spin" /></div>;

  const seg = (i: number) => t.segments.find((s) => s.from === t.points[i].id && s.to === t.points[i + 1]?.id);
  const shape = t.shape === "out_and_back" ? "There and back" : t.shape === "loop" ? "A loop" : "One way";
  const inset = desk ? { top: 20, right: 60, bottom: 90, left: 470 } : { top: 0, right: 0, bottom: 22, left: 0 };

  const saved = (user?.saved_trails ?? []).includes(t.id);
  async function toggleSave() {
    const u = user ?? await ensureUser();
    const now = u.saved_trails ?? [];
    setUser(await api.updateMe({ saved_trails: saved ? now.filter((x) => x !== t!.id) : [t!.id, ...now] }));
    toast(saved ? "Removed from Saved." : "Saved in Walks.");
  }

  const toBag = () => document.getElementById("bag")?.scrollIntoView({ behavior: "smooth", block: "start" });
  const head = (
    <div className="mf-trailhead">
      <Link className="mf-k mf-crumb" to={`/trails?country=${t.country}&t=${t.id}`}><Back /> Walks · {t.region || t.base}</Link>
      <div className="mf-th1"><h1>{t.name}</h1>
        <span className="mf-th-acts">
          {!(tripId && stopId) && <AddWalk t={t} month={month} />}
          <button type="button" className={`mf-btn sm x-save${saved ? " on" : ""}`} aria-pressed={saved} onClick={toggleSave}>{saved ? "✓ Saved" : "Save"}</button>
        </span></div>
      <div className="tags">
        <span className={`tag diff-${t.difficulty}`}>{DIFFICULTY[t.difficulty]}</span>
        {t.kind === "multiday" && <span className="tag">{t.days} days</span>}
        {t.glacier && <span className="tag">On a glacier</span>}
        <span className="tag">{shape}</span>
        <span className="tag">Best {t.months_text}</span>
      </div>
      <TrailFacts t={t} />
      {/* the month, as on a recommended trip: green when it is the walk's season */}
      <div className="mf-pick">
        <div className="mf-months" role="radiogroup" aria-label="When">
          {MONTHS.map((m, i) => {
            const best = t.months.includes(i + 1);
            return (
              <button type="button" role="radio" key={m} aria-checked={i + 1 === month}
                className={`${i + 1 === month ? "on" : ""}${best ? " best" : ""}`}
                title={best ? "In season" : "Off season"} onClick={() => setMonth(i + 1)}>{m.slice(0, 3)}</button>
            );
          })}
        </div>
        <span className="mf-k mf-mlegend"><i className="best" /> in season <i /> off season</span>
      </div>
      {!desk && <button type="button" className="mf-btn go wide" onClick={toBag}>What to wear in {MONTHS[month - 1]} <Down /></button>}
    </div>
  );

  const body = (
    <>
      <p className="mf-lede">{t.why}</p>
      <p className="mf-k">{t.difficulty_text}.{t.published ? <> Distance and climb as <a href={t.published.source} target="_blank" rel="noopener noreferrer">published by the park</a>.</> : null}</p>
      {t.profile.length > 0 && <TrailProfile profile={t.profile} points={t.points} onFocus={setFocus} />}
      <div className="mf-acts">
        {focus !== null && <button type="button" className="mf-btn sm" onClick={() => setFocus(null)}>Whole trail</button>}
        {t.line.length > 0 && <a className="mf-btn sm" href={`/api/trails/${t.id}.gpx`} download>Download GPX</a>}
        {t.line.length > 0 && <span className="mf-k">for Organic Maps, Gaia, Komoot…</span>}
      </div>
      {!t.line.length && <p className="mf-k">The map of this trail is being drawn: its points and notes are already checked against the park's pages.</p>}

      <section className="mf-tsec" aria-label="Before you go">
        <b className="mf-sub">Before you go</b>
        <dl className="mf-dl">
          <div><dt>Start from</dt><dd>{t.points[0].name}{t.start_by && <>, by <b>{t.start_by}</b></>}</dd></div>
          {t.turnaround && <div><dt>Turn back</dt><dd>{t.turnaround}</dd></div>}
          {t.book && <div><dt>Permits</dt><dd>{t.book}</dd></div>}
          {t.water && <div><dt>Water & food</dt><dd>{t.water}</dd></div>}
        </dl>
        {t.dangers.length > 0 && <div className="mf-warn"><b>Watch out</b><ul>{t.dangers.map((d, i) => <li key={i}>{d}</li>)}</ul></div>}
      </section>

      <section className="mf-tsec" aria-label="Step by step">
        <b className="mf-sub">Step by step</b>
        <ol className="tsteps mf-tsteps">
          {t.points.map((p, i) => {
            const s = seg(i);
            return (
              <Fragment key={p.id}>
                <li className={`tstep ${p.role}${focus === i ? " on" : ""}`}>
                  <button type="button" className="tnum" onClick={() => setFocus(i)} aria-label={`Show ${p.name} on the map`}>{i + 1}</button>
                  <div className="tstep-text">
                    <h3>{p.name}</h3>
                    <p className="mf-k">{p.km != null && <>km {p.km.toFixed(1)}</>}{p.ele != null && <> · {fmt(p.ele)} m</>}{p.night && <> · you sleep here</>}</p>
                    {p.note && <p>{p.note}</p>}
                  </div>
                  {p.art && <div className="tstep-art"><Illustration art={p.art} label={p.name} /></div>}
                </li>
                {s && (
                  <li className="tseg" aria-label={`From ${s.from_name} to ${s.to_name}`}>
                    <span>{s.km.toFixed(1)} km</span>
                    {s.up > 0 && <span>+{fmt(s.up)} m</span>}
                    {s.down > 0 && <span>−{fmt(s.down)} m</span>}
                    <span>about {hrs(s.hours > 0 ? s.hours : s.km / 4)}</span>
                  </li>
                )}
              </Fragment>
            );
          })}
        </ol>
        {t.shape === "out_and_back" && <p className="mf-k">Then back the same way.</p>}
        {t.segments.length > 0 && <p className="mf-k">Stretch times by the Alpine clubs' rule (4 km/h on the flat, 300 m an hour up, 500 down), without breaks.</p>}
      </section>

      {tripId && stopId && <AddToTrip t={t} tripId={tripId} stopId={stopId} />}
      {t.base_trails.length > 0 && <MoreFrom t={t} />}
      <p className="mf-k">Sources: {t.sources.map((u, i) => <Fragment key={u}>{i ? " · " : ""}<a href={u} target="_blank" rel="noopener noreferrer">{new URL(u).hostname.replace(/^www\./, "")}</a></Fragment>)}.
        {t.attribution ? ` ${t.attribution}.` : ""} Conditions change: check the park's page and the weather the day before you go.</p>
    </>
  );

  // the drawings on the map, each on the place itself: what the walk is for, then what you pass
  const arts = [
    ...(t.art && t.art_at ? [{ id: t.art.id, name: t.name, lat: t.art_at[0], lon: t.art_at[1], art: t.art }] : []),
    ...(t.sights ?? []),
  ].filter((a) => near(a));

  // like a recommended trip (Manu 2026-11-16 "allinea a quella di Trips"): the map and the walk on
  // top, the clothes for this walk below it, one scroll down; no second panel over the map
  return (
    <main className="trk trailpage-mf ip-one">
      <div className="ip-top">
        <div className="mf">
          <div className="mf-map">
            {t.line.length > 0 || t.points.length > 0
              ? <TrailMap line={t.line} points={t.points} focus={focus} onFocus={setFocus} inset={inset} arts={arts} />
              : null}
          </div>
          <section className="mf-float mf-panel" aria-label={t.name}>
            {head}
            <div className={desk ? "mf-scroll" : "mf-ibody"}>{body}</div>
          </section>
          {desk && <button type="button" className="mf-float ip-cue" onClick={toBag}>What to wear · {MONTHS[month - 1].slice(0, 3)} <Down /></button>}
        </div>
      </div>
      <WalkWear id={t.id} name={t.name} month={month} />
    </main>
  );

  /** a drawing far from the walk (a whole range, a big glacier) stays off this map */
  function near(a: { lat: number; lon: number }) {
    const pts = t!.line.length ? t!.line.map(([lo, la]) => [la, lo]) : t!.points.map((p) => [p.lat, p.lon]);
    return pts.some(([la, lo]) => Math.hypot(la - a.lat, (lo - a.lon) * Math.cos((la * Math.PI) / 180)) < 0.09); // ~10 km
  }
}

const Down = () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 5v14M5 12l7 7 7-7" /></svg>;

const Back = () => <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>;

/** "I'll do it": the trail becomes one of this stop's activities, so the trip's kit dresses you for it. */
/** "Add to my trip" (flow audit, Manu 2026-11-16): a trip shows the walks from its stops, and now a walk
 *  goes into a trip too: one of yours, after its last stop, or a new trip. The stop carries the walk, so
 *  the bag follows it. */
function AddWalk({ t, month }: { t: Trail; month: number }) {
  const nav = useNavigate();
  const { user, ensureUser } = useApp();
  const [open, setOpen] = useState(false);
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!open || trips) return;
    if (!user) { setTrips([]); return; }
    api.trips().then((x) => setTrips(x.filter((y) => y.saved))).catch(() => setTrips([]));
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const p0 = t.points[0];
  const stop = (from: Date) => {
    const end = new Date(from); end.setDate(end.getDate() + Math.max(1, t.days) - 1);
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    return { name: t.base || p0.name, country_code: t.country, latitude: p0.lat, longitude: p0.lon, elevation_m: p0.ele ?? 0,
      start_date: iso(from), end_date: iso(end), activities: [t.activity], notes: null };
  };
  async function into(id: string | null) {
    setBusy(true); setErr(null);
    try {
      await ensureUser();
      if (id) {
        const trip = await api.trip(id);
        const last = trip.stops.reduce((m, s) => (s.end_date > m ? s.end_date : m), "");
        const from = last ? new Date(`${last}T00:00:00`) : new Date();
        from.setDate(from.getDate() + 1);
        await api.addStop(id, stop(from));
        nav(`/trips/${id}`);
      } else {
        const now = new Date();
        const from = new Date(now.getFullYear() + (month < now.getMonth() + 1 ? 1 : 0), month - 1, month === now.getMonth() + 1 ? now.getDate() + 7 : 1);
        const trip = await api.createTrip(t.name, [stop(from)], true, [t.country]);
        await api.patchTrip(trip.id, { saved: true });
        nav(`/trips/${trip.id}`);
      }
    } catch (e) { setErr((e as Error).message); setBusy(false); }
  }
  return (
    <span className="mf-addwalk">
      <button type="button" className="mf-btn sm go" aria-expanded={open} onClick={() => setOpen(!open)}>Add to my trip</button>
      {open && (
        <span className="x-menu" role="menu">
          {trips === null ? <span className="spin" /> : trips.map((x) => (
            <button key={x.id} type="button" role="menuitem" disabled={busy} onClick={() => into(x.id)}>{x.name}</button>
          ))}
          <button type="button" role="menuitem" disabled={busy} onClick={() => into(null)}>+ New trip</button>
          {err && <span className="err">{err}</span>}
        </span>
      )}
    </span>
  );
}

function AddToTrip({ t, tripId, stopId }: { t: Trail; tripId: string; stopId: string }) {
  const [state, setState] = useState<"idle" | "busy" | "done" | "had">("idle");
  const [err, setErr] = useState<string | null>(null);
  const same = (a: Activity) => a.type === t.activity.type && (a.difficulty ?? null) === (t.activity.difficulty ?? null)
    && Math.round(a.max_altitude_m ?? 0) === Math.round(t.activity.max_altitude_m ?? 0) && !!a.glacier === !!t.activity.glacier;
  async function add() {
    setState("busy"); setErr(null);
    try {
      const trip = await api.trip(tripId);
      const stop = trip.stops.find((s) => s.id === stopId);
      if (!stop) throw new Error("This stop is no longer in your trip.");
      const acts = stop.activities ?? [];
      if (acts.some(same)) { setState("had"); return; }
      // a city-only stop becomes a walking stop; other plans stay
      const keep = acts.filter((a) => a.type !== "city" || acts.length > 1);
      await api.patchStop(tripId, stopId, { activities: [...keep, t.activity] });
      setState("done");
    } catch (e) { setErr((e as Error).message); setState("idle"); }
  }
  return (
    <section className="mf-tsec mf-tadd" aria-label="Add to your trip">
      <b className="mf-sub">Doing it?</b>
      <p className="mf-k">Add it to your stop and the clothes of your trip follow: {activityText(t.activity)}.</p>
      {state === "done" || state === "had" ? (
        <p className="okline">{state === "done" ? "Added." : "Your stop already has this walk."} <Link to={`/trips/${tripId}`}>Back to your trip</Link></p>
      ) : (
        <button type="button" className="mf-btn go" disabled={state === "busy"} onClick={add}>{state === "busy" ? <span className="spin" /> : "I'll do it: dress me for it"}</button>
      )}
      {err && <p className="err">{err}</p>}
    </section>
  );
}

function MoreFrom({ t }: { t: Trail }) {
  const [list, setList] = useState<{ id: string; name: string }[]>([]);
  useEffect(() => {
    api.trails({ country: t.country }).then((r) => setList(r.trails.filter((x) => t.base_trails.includes(x.id)))).catch(() => setList([]));
  }, [t.id, t.country, t.base_trails]);
  if (!list.length) return null;
  return (
    <section className="mf-tsec" aria-label={`More from ${t.base}`}>
      <b className="mf-sub">More from {t.base}</b>
      <ul className="tmore">{list.slice(0, 6).map((x) => <li key={x.id}><Link to={`/trails/${x.id}${location.search}`}>{x.name}</Link></li>)}</ul>
    </section>
  );
}
