import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { DIFFICULTY, TrailFacts } from "../components/TrailCards";
import TrailMap from "../components/TrailMap";
import TrailProfile from "../components/TrailProfile";
import { api } from "../lib/api";
import { activityText } from "../lib/format";
import type { Activity, Trail, TrailWear } from "../lib/types";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const FOOT: Record<string, string> = {
  sneaker: "Trainers", trail_runner: "Trail shoes", hiking_boot: "Hiking boots", mountaineering_boot: "Mountaineering boots",
  sandal: "Sandals",
};
const fmt = (n: number) => n.toLocaleString("en-US");
const hrs = (h: number) => (h < 1 ? `${Math.round(h * 60)} min` : `${Math.floor(h)} h${h % 1 >= 0.25 ? ` ${Math.round((h % 1) * 60)}` : ""}`);

/** One trail, all you need to walk it: where it starts, the way point by point with the drawing
 *  of each, the map and the altitude, the time of every stretch, when to turn back, and what to
 *  wear on it in your month (Manu, 2026-11-13). */
export default function TrailPage() {
  const { id = "" } = useParams();
  const [q] = useSearchParams();
  const tripId = q.get("trip"), stopId = q.get("stop");
  const [t, setT] = useState<Trail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [focus, setFocus] = useState<number | null>(null);

  useEffect(() => {
    setT(null); setErr(null); setFocus(null);
    api.trail(id).then(setT).catch((e) => setErr((e as Error).message));
  }, [id]);

  if (err) return <div className="wrap section"><h1>Trail not found</h1><p>{err}</p><Link to="/trails">All trails</Link></div>;
  if (!t) return <div className="loading"><span className="spin" /></div>;

  const seg = (i: number) => t.segments.find((s) => s.from === t.points[i].id && s.to === t.points[i + 1]?.id);
  const shape = t.shape === "out_and_back" ? "There and back the same way" : t.shape === "loop" ? "A loop" : "One way";

  return (
    <div className="trailpage">
      <section className="thead">
        <div className="wrap thead-in">
          <div className="thead-text">
            <p className="kicker"><Link to={`/trails?country=${t.country}`}>Trekking</Link> · {t.region || t.base}</p>
            <h1>{t.name}</h1>
            <p className="lede">{t.why}</p>
            <div className="tags">
              <span className={`tag diff-${t.difficulty}`}>{DIFFICULTY[t.difficulty]}</span>
              {t.kind === "multiday" && <span className="tag">{t.days} days</span>}
              {t.glacier && <span className="tag">On a glacier</span>}
              <span className="tag">{shape}</span>
              <span className="tag">Best {t.months_text}</span>
            </div>
            <TrailFacts t={t} />
            <p className="small muted">{t.difficulty_text}.{t.published ? <> Distance and climb as <a href={t.published.source} target="_blank" rel="noopener noreferrer">published by the park</a>.</> : null}</p>
          </div>
          {t.art && <div className="thead-art"><Illustration art={t.art} label={t.name} /></div>}
        </div>
      </section>

      <div className="wrap tbody">
        <section className="tbox tbefore" aria-label="Before you go">
          <h2>Before you go</h2>
          <dl>
            <div><dt>Start from</dt><dd>{t.points[0].name}{t.start_by && <>, by <b>{t.start_by}</b></>}</dd></div>
            {t.turnaround && <div><dt>Turn back</dt><dd>{t.turnaround}</dd></div>}
            {t.book && <div><dt>Permits & booking</dt><dd>{t.book}</dd></div>}
            {t.water && <div><dt>Water & food</dt><dd>{t.water}</dd></div>}
          </dl>
          {t.dangers.length > 0 && (
            <div className="tdanger">
              <span className="label">Watch out</span>
              <ul>{t.dangers.map((d, i) => <li key={i}>{d}</li>)}</ul>
            </div>
          )}
        </section>

        {(t.line.length > 0 || t.profile.length > 0) && (
          <section className="tbox" aria-label="Map and altitude">
            <h2>Where it goes</h2>
            {t.line.length > 0 && <TrailMap line={t.line} points={t.points} focus={focus} onFocus={setFocus} />}
            <TrailProfile profile={t.profile} points={t.points} onFocus={setFocus} />
            <div className="row tmap-ctl">
              {focus !== null && <button type="button" className="btn sm" onClick={() => setFocus(null)}>Whole trail</button>}
              {t.line.length > 0 && <a className="btn sm" href={`/api/trails/${t.id}.gpx`} download>Download GPX</a>}
              <span className="small muted">Open the GPX in your navigation app (Organic Maps, Gaia, Komoot…) to follow it on the trail.</span>
            </div>
            {t.attribution && <p className="small muted">{t.attribution}.</p>}
          </section>
        )}
        {!t.line.length && <p className="small muted tbox">The map of this trail is being drawn: its points and notes below are already checked against the park's pages.</p>}

        <section className="tbox" aria-label="Step by step">
          <h2>Step by step</h2>
          <ol className="tsteps">
            {t.points.map((p, i) => {
              const s = seg(i);
              return (
                <Fragment key={p.id}>
                  <li className={`tstep ${p.role}${focus === i ? " on" : ""}`}>
                    <button type="button" className="tnum" onClick={() => setFocus(i)} aria-label={`Show ${p.name} on the map`}>{i + 1}</button>
                    <div className="tstep-text">
                      <h3>{p.name}</h3>
                      <p className="small muted">
                        {p.km != null && <>km {p.km.toFixed(1)}</>}{p.ele != null && <> · {fmt(p.ele)} m</>}
                        {p.night && <> · you sleep here</>}
                      </p>
                      {p.note && <p>{p.note}</p>}
                    </div>
                    {p.art && <div className="tstep-art"><Illustration art={p.art} label={p.name} /></div>}
                  </li>
                  {s && (
                    <li className="tseg" aria-label={`From ${s.from_name} to ${s.to_name}`}>
                      <span>{s.km.toFixed(1)} km</span>
                      {s.up > 0 && <span>+{fmt(s.up)} m</span>}
                      {s.down > 0 && <span>−{fmt(s.down)} m</span>}
                      <span>about {hrs(s.hours)}</span>
                    </li>
                  )}
                </Fragment>
              );
            })}
          </ol>
          {t.shape === "out_and_back" && <p className="small muted">Then back the same way.</p>}
          {t.segments.length > 0 && <p className="small muted">Stretch times by the Alpine clubs' rule (4 km/h on the flat, 300 m an hour up, 500 down), without breaks.</p>}
        </section>

        <WearBox t={t} />

        {tripId && stopId && <AddToTrip t={t} tripId={tripId} stopId={stopId} />}

        <section className="tbox small muted">
          <p>Sources: {t.sources.map((u, i) => <Fragment key={u}>{i ? " · " : ""}<a href={u} target="_blank" rel="noopener noreferrer">{new URL(u).hostname.replace(/^www\./, "")}</a></Fragment>)}</p>
          <p>Conditions change: check the park's page and the weather the day before you go.</p>
        </section>

        {t.base_trails.length > 0 && <MoreFrom t={t} />}
      </div>
    </div>
  );
}

/** What to wear on this trail in a month: the trip's own warmth model, run on this walk. */
function WearBox({ t }: { t: Trail }) {
  const [q] = useSearchParams();
  const now = new Date().getMonth() + 1;
  const first = Number(q.get("month")) || (t.months.includes(now) ? now : t.months[0]);
  const [month, setMonth] = useState(first);
  const [w, setW] = useState<TrailWear | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setW(null); setErr(null);
    api.trailWear(t.id, month).then(setW).catch((e) => setErr((e as Error).message));
  }, [t.id, month]);
  const pieces = useMemo(() => (w?.pieces ?? []).filter((p) => p.slot !== "footwear"), [w]);
  const boots = w?.pieces.find((p) => p.slot === "footwear");
  return (
    <section className="tbox twear" aria-label="What to wear">
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <h2>What to wear</h2>
        <label className="small">In <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
          {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}{t.months.includes(i + 1) ? "" : " (off season)"}</option>)}
        </select></label>
      </div>
      {err && <p className="err">{err}</p>}
      {!w && !err && <p className="small muted"><span className="spin" /> Reading the weather of this trail…</p>}
      {w && (
        <>
          {!w.in_season && <p className="warnline small">{MONTHS[month - 1]} is outside the trail's season: snow, closures or bad weather are likely.</p>}
          {w.weather && <p className="small">At the start in {MONTHS[month - 1]}: {w.weather.tmin}…{w.weather.tmax} °C, wind {w.weather.wind_kmh} km/h, {w.weather.rain_chance}% chance of rain{w.weather.source === "climate" ? " (the average of past years)" : ""}.</p>}
          {w.coldest && <p className="small"><b>Coldest moment:</b> feels like {w.coldest.feels_like_c} °C, {w.coldest.where}.</p>}
          {boots && <p className="tboots"><b>{FOOT[boots.footwear_type ?? ""] ?? "Shoes"}</b>{boots.ankle_support ? ", with ankle support" : ""}{boots.waterproof ? ", waterproof" : ""}. {boots.reasons.filter((r) => !r.startsWith("activities")).join("; ")}</p>}
          <ul className="twear-list">
            {pieces.map((p) => (
              <li key={p.slot}><b>{p.name}</b>{p.waterproof ? " (waterproof)" : ""}{(() => { const r = p.reasons.find((x) => !/clo|already on/.test(x)); return r ? <span className="small muted"> · {r.replace(/^[^:]+: /, "")}</span> : null; })()}</li>
            ))}
          </ul>
          <p className="small muted">Your whole trip's kit, with what you already own and products at three budgets, is on your trip's Bag tab.</p>
        </>
      )}
    </section>
  );
}

/** "I'll do it": the trail becomes one of this stop's activities, so the trip's kit dresses you for it. */
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
    <section className="tbox tadd" aria-label="Add to your trip">
      <h2>Doing it?</h2>
      <p className="small">Add it to your stop and the clothes of your trip follow: {activityText(t.activity)}.</p>
      {state === "done" || state === "had" ? (
        <p className="okline">{state === "done" ? "Added." : "Your stop already has this walk."} <Link to={`/trips/${tripId}`}>Back to your trip</Link></p>
      ) : (
        <button type="button" className="btn primary" disabled={state === "busy"} onClick={add}>{state === "busy" ? <span className="spin" /> : "I'll do it: dress me for it"}</button>
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
    <section className="tbox" aria-label={`More from ${t.base}`}>
      <h2>More from {t.base}</h2>
      <ul className="tmore">{list.map((x) => <li key={x.id}><Link to={`/trails/${x.id}${location.search}`}>{x.name}</Link></li>)}</ul>
    </section>
  );
}
