import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { BagIcon, KitSheet, ProductRow, totalOf, type BuyPick } from "../components/BuyBar";
import { Garment } from "../components/Garment";
import { Illustration } from "../components/Illustration";
import { DIFFICULTY, TrailFacts } from "../components/TrailCards";
import TrailMap from "../components/TrailMap";
import TrailProfile from "../components/TrailProfile";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { activityText, money } from "../lib/format";
import type { Activity, Item, Trail, TrailWear, TripSummary } from "../lib/types";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const FOOT: Record<string, string> = {
  sneaker: "Trainers", trail_runner: "Trail shoes", hiking_boot: "Hiking boots", mountaineering_boot: "Mountaineering boots",
  sandal: "Sandals",
};
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
  const [w, setW] = useState<TrailWear | null>(null);
  const [wErr, setWErr] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Record<string, Item>>({});
  const [buyOpen, setBuyOpen] = useState(false);

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

  // what to wear on it in the month: the trip's own warmth model, run on this walk
  useEffect(() => {
    if (!t || !month) return;
    let live = true;
    setW(null); setWErr(null); setChosen({});
    api.trailWear(t.id, month).then((x) => { if (live) setW(x); }).catch((e) => { if (live) setWErr((e as Error).message); });
    return () => { live = false; };
  }, [t, month]);

  const picks: BuyPick[] = useMemo(() => (w?.pieces ?? []).flatMap((p) => {
    const it = chosen[p.slot] ?? p.products?.medium ?? p.products?.cheap ?? p.products?.premium;
    return it ? [{ slot: p.slot, label: p.name.replace(/\s*\/.*$/, ""), item: it, cheaper: p.products?.cheap, better: p.products?.premium }] : [];
  }), [w, chosen]);
  const pick = (slot: string, it: Item) => setChosen((c) => ({ ...c, [slot]: it }));

  if (err) return <div className="wrap section"><h1>Trail not found</h1><p>{err}</p><Link to="/trails">All trails</Link></div>;
  if (!t || !month) return <div className="loading"><span className="spin" /></div>;

  const seg = (i: number) => t.segments.find((s) => s.from === t.points[i].id && s.to === t.points[i + 1]?.id);
  const shape = t.shape === "out_and_back" ? "There and back" : t.shape === "loop" ? "A loop" : "One way";
  const cur = picks[0]?.item.currency;
  const boots = w?.pieces.find((p) => p.slot === "footwear");
  const inset = desk ? { top: 20, right: 60, bottom: 150, left: 870 } : { top: 0, right: 0, bottom: 22, left: 0 };

  const saved = (user?.saved_trails ?? []).includes(t.id);
  async function toggleSave() {
    const u = user ?? await ensureUser();
    const now = u.saved_trails ?? [];
    setUser(await api.updateMe({ saved_trails: saved ? now.filter((x) => x !== t!.id) : [t!.id, ...now] }));
    toast(saved ? "Removed from Saved." : "Saved in Walks.");
  }

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
    </div>
  );

  const wear = (
    <div className={desk ? "mf-float mf-card mf-tcard mf-twear" : "mf-tcard mf-twear in"}>
      {desk && t.art && <div className="mf-art"><Illustration art={t.art} label={t.name} /></div>}
      <div className="mf-card-in">
        <div className="mf-twear-h">
          <b className="mf-sub">What you wear on it</b>
          <label className="mf-k">in <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}{t.months.includes(i + 1) ? "" : " (off season)"}</option>)}
          </select></label>
        </div>
        {wErr && <p className="err">{wErr}</p>}
        {!w && !wErr && <p className="mf-k"><span className="spin" /> Reading the weather of this trail…</p>}
        {w && (
          <>
            {!w.in_season && <p className="mf-warn">{MONTHS[month - 1]} is outside the trail's season: snow, closures or bad weather are likely.</p>}
            {w.weather && <span className="mf-k">At the start: {w.weather.tmin}–{w.weather.tmax}°, wind {w.weather.wind_kmh} km/h, {w.weather.rain_chance}% chance of rain{w.weather.source === "climate" ? " (past years)" : ""}.</span>}
            {w.coldest && <span className="mf-k">Coldest: feels like {w.coldest.feels_like_c}°, {w.coldest.where}.</span>}
            <ul className="mf-wear">
              {w.pieces.map((p) => {
                const it = chosen[p.slot] ?? p.products?.medium ?? null;
                const why = p.slot === "footwear" && boots
                  ? `${FOOT[boots.footwear_type ?? ""] ?? "Shoes"}${boots.ankle_support ? ", ankle support" : ""}${boots.waterproof ? ", waterproof" : ""}`
                  : p.reasons.find((x) => !/clo|already on/.test(x))?.replace(/^[^:]+: /, "") ?? p.level;
                return (
                  <li key={p.slot} className="get">
                    <Garment slot={p.slot} />
                    <span className="mf-nm"><span>{p.name}{p.waterproof ? " · waterproof" : ""}</span><small>{it ? `${it.brand} ${it.name}` : why}</small></span>
                    {it?.image_url && <img src={it.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" />}
                    {it && <span className="mf-pr">{money(it.price, it.currency)}</span>}
                  </li>
                );
              })}
            </ul>
            {desk && picks.length > 0 && (
              <button type="button" className="mf-btn go wide mf-twear-buy" onClick={() => setBuyOpen(true)}>
                <BagIcon />Buy the {picks.length} · {money(totalOf(picks), cur)}</button>)}
          </>
        )}
      </div>
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

  return (
    <main className="trk trailpage-mf">
      <div className="mf">
        <div className="mf-map">
          {t.line.length > 0 || t.points.length > 0
            ? <TrailMap line={t.line} points={t.points} focus={focus} onFocus={setFocus} inset={inset} />
            : null}
        </div>

        <section className="mf-float mf-panel" aria-label={t.name}>
          {head}
          {desk ? <div className="mf-scroll">{body}</div> : (
            <>
              {wear}
              {picks.length > 0 && <div className="mf-phone-buy"><div className="mf-k">To get for this walk · {money(totalOf(picks), cur)}</div>
                <ProductRow picks={picks} onPick={pick} /></div>}
              {body}
              <div className="mf-phone-go">
                <button type="button" className="mf-btn go wide" disabled={!picks.length} onClick={() => setBuyOpen(true)}>
                  <BagIcon />{picks.length ? `Buy the ${picks.length} pieces · ${money(totalOf(picks), cur)}` : w ? "Nothing to buy for it" : "Working out the kit…"}</button>
              </div>
            </>
          )}
        </section>

        {/* one block of clothes (flow audit, Manu 2026-11-16): the card, no second bar under it */}
        {desk && wear}
      </div>
      <KitSheet open={buyOpen} onClose={() => setBuyOpen(false)} title={`Your kit for ${t.name}`} picks={picks} />
    </main>
  );
}

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
      <ul className="tmore">{list.map((x) => <li key={x.id}><Link to={`/trails/${x.id}${location.search}`}>{x.name}</Link></li>)}</ul>
    </section>
  );
}
