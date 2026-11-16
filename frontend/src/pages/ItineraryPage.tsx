import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { TripMap } from "../components/Maps";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { MONTHS, countryNames, nights } from "../lib/format";
import type { Itinerary, ItineraryDay, ItineraryStop, ItineraryThing, Journey, Stop, Tier } from "../lib/types";
import { PlacePop } from "../components/PlacePop";
import { KIND_LABEL, countryName, km, loadPlaces, type GlobePlace } from "../lib/worldmap";
import { TripBag } from "../components/TripBag";

const MIN_DAYS = 3, MAX_DAYS = 35;
const n0 = (n: number) => Math.round(n).toLocaleString("en-US");

/** The region's pickers (Manu 2026-11-16: "lo chiede all'utente quanto ci vuole stare ... scopre
 *  sul tool in che mese andare"; then "anche 10 giorni, 17 giorni"): the weeks, any number of days,
 *  then the twelve months, the best ones marked, the ones with no route off. */
function Pickers({ j, it, month, onPick }: { j: Journey; it: Itinerary; month: number;
  onPick: (slug: string, month: number, days?: number) => void }) {
  const weeks = [...new Set(j.routes.map((r) => r.weeks))].sort();
  const week = it.days % 7 === 0 && weeks.includes(it.days / 7) ? it.days / 7 : null;
  // the routes a length of this trip is built from: that many weeks, or the nearest
  const near = Math.min(4, Math.max(1, Math.round(it.days / 7)));
  const mine = j.routes.filter((r) => r.weeks === near);
  const pickDays = (d: number) => {
    const at = j.routes.find((r) => r.days === d && r.months.includes(month));
    if (at) onPick(at.slug, month); else onPick(it.slug, month, d);
  };
  return (
    <div className="mf-pick">
      <div className="mf-lenrow">
        {/* one control for how long (flow audit, Manu 2026-11-16): the weeks pills said the same */}
        <div className="mf-daysn" role="group" aria-label="How many days">
          <button type="button" aria-label="One day less" disabled={it.days <= MIN_DAYS} onClick={() => pickDays(it.days - 1)}>−</button>
          <span><b>{it.days}</b> days</span>
          <button type="button" aria-label="One day more" disabled={it.days >= MAX_DAYS} onClick={() => pickDays(it.days + 1)}>+</button>
        </div>
      </div>
      <div className="mf-months" role="radiogroup" aria-label="When">
        {MONTHS.map((m, i) => {
          const ok = (week ? j.routes.filter((r) => r.weeks === week) : j.routes).some((r) => r.months.includes(i + 1));
          const best = mine.some((r) => r.best_months.includes(i + 1));
          const pick = () => {
            if (!week) { onPick(it.slug, i + 1, it.days); return; }
            const r = j.routes.find((x) => x.weeks === week && x.months.includes(i + 1));
            if (r) onPick(r.slug, i + 1);
          };
          return (
            <button type="button" role="radio" key={m} aria-checked={i + 1 === month} disabled={!ok}
              className={`${i + 1 === month ? "on" : ""}${best ? " best" : ""}`}
              title={!ok ? "No trip then" : best ? "Best weather" : "Possible"} onClick={pick}>{m}</button>
          );
        })}
      </div>
      <span className="mf-k mf-mlegend"><i className="best" /> best weather <i /> possible</span>
    </div>
  );
}

/** One thing of the day: how hard and long, hour by hour, and its walk, whose line is on the map. */
function Thing({ t }: { t: ItineraryThing }) {
  const tr = t.trail;
  const walk = tr && [!/km/.test(t.hours) && tr.km ? `${tr.km} km` : "", tr.gain_m ? `${n0(tr.gain_m)} m up` : ""].filter(Boolean).join(" · ");
  return (
    <div className="mf-thing">
      <div className="mf-thead">
        <b>{t.spare && <span className="mf-k">If it is clear: </span>}{t.name}</b>
        {tr && <Link className="mf-btn sm" to={`/trails/${tr.id}`}>The walk ›</Link>}
      </div>
      <span className="mf-k">{[t.effort, t.hours, walk].filter(Boolean).join(" · ")}</span>
      {t.steps.length > 0 ? (
        <ol className="mf-steps">
          {t.steps.map((x, i) => <li key={i}><span className="mf-k">{x.at}</span><span>{x.what}{x.note && <small>: {x.note}</small>}</span></li>)}
        </ol>
      ) : t.why && <p className="mf-why">{t.why}</p>}
    </div>
  );
}

/** A day's line: what you do, in a few words ("Laguna de los Tres", "Spare day"). */
function dayLine(d: ItineraryDay): string {
  const main = d.things.filter((t) => !t.spare).map((t) => t.name);
  if (d.kind === "free") return main.length ? main.join(" · ") : "Spare day for the weather";
  if (main.length) return (d.kind === "arrive" ? "Arrive · " : "") + main.join(" · ");
  return d.title.replace(/\.$/, "");
}

/** What the stop's days are about, for its row: the things you do, not the activity types. */
function stopDoes(s: ItineraryStop): string {
  const names = s.days.flatMap((d) => d.things.filter((t) => !t.spare).map((t) => t.name.split(/,| \(|: /)[0]));
  return [...new Set(names)].join(", ");
}

/** One stop, opened in the list itself (Manu 2026-11-16: "lo voglio direttamente sulla cosa a
 *  sinistra", no card beside it): its days, each one opening on what to do hour by hour. */
function StopDays({ s, from, day, onDay }: { s: ItineraryStop; from: number; day: number | null; onDay: (i: number | null) => void }) {
  if (!s.days.length) {
    return <ol className="mf-dlist">{s.plan.map((p, i) => <li key={i}><div className="mf-drow static"><span className="mf-k">Day {from + i}</span><span>{p}</span></div></li>)}</ol>;
  }
  const tour = s.excursions[0];
  return (
    <ol className="mf-dlist">
      {s.days.map((d, i) => (
        <li key={i} className={day === i ? "open" : ""}>
          <button type="button" className="mf-drow" aria-expanded={day === i} onClick={() => onDay(day === i ? null : i)}>
            <span className="mf-k">Day {from + i}</span><span>{dayLine(d)}</span><Chev />
          </button>
          {day === i && (
            <div className="mf-dmore">
              {d.things.length ? d.things.map((t) => <Thing t={t} key={t.id} />) : <p className="mf-why">{d.title}</p>}
            </div>
          )}
        </li>
      ))}
      {tour && (
        <li className="mf-dtour"><span className="mf-k">Tours here</span>
          {tour.links.map((l) => <a key={l.provider} href={l.href} target="_blank" rel="noopener sponsored">{l.label} ↗</a>)}
        </li>
      )}
    </ol>
  );
}

/** Look a place up and add it as a stop, as on Google Maps (Manu 2026-11-16: "le voglio anche
 *  aggiungere a mo' di Google Maps"): any place of the map, by name; the trip's countries first. */
function AddStop({ near, mine, onPick, disabled }: { near: string[]; mine: string[]; onPick: (p: GlobePlace) => void; disabled?: boolean }) {
  const [all, setAll] = useState<GlobePlace[] | null>(null);
  const [q, setQ] = useState("");
  const [hi, setHi] = useState(0);
  const load = () => { if (!all) loadPlaces().then((d) => setAll(d.places)).catch(() => setAll([])); };
  const res = useMemo(() => {
    const k = fold(q.trim());
    if (!all || k.length < 2) return [];
    const home = new Set(near);
    const score = (p: GlobePlace) => {
      const n = fold(p.name);
      const at = n.startsWith(k) ? 0 : n.split(/[\s-]+/).some((w) => w.startsWith(k)) ? 1 : n.includes(k) ? 2 : 9;
      return at * 100 - (home.has(p.country) ? 50 : 0) - p.level * 5;
    };
    return all.map((p) => [p, score(p)] as const).filter(([, v]) => v < 800).sort((a, b) => a[1] - b[1]).slice(0, 6).map(([p]) => p);
  }, [all, q, near]);
  useEffect(() => setHi(0), [q]);
  const pick = (p: GlobePlace) => { onPick(p); setQ(""); };
  return (
    <div className="mf-add ip-add">
      <Plus />
      <input type="search" value={q} placeholder="Add a stop" aria-label="Add a stop" autoComplete="off" disabled={disabled}
        onFocus={load} onChange={(e) => { load(); setQ(e.target.value); }}
        onKeyDown={(e) => {
          if (e.key === "Escape") setQ("");
          if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(res.length - 1, h + 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(0, h - 1)); }
          if (e.key === "Enter" && res[hi]) { e.preventDefault(); pick(res[hi]); }
        }} />
      {q.trim().length >= 2 && !all && <span className="spin" />}
      {res.length > 0 && (
        <ul className="mf-res" role="listbox">
          {res.map((p, i) => (
            <li key={p.id}><button type="button" role="option" aria-selected={i === hi} className={i === hi ? "hi" : ""} onClick={() => pick(p)}>
              <b>{p.name}</b><small>{mine.includes(p.id) ? "In your trip" : `${KIND_LABEL[p.kind]} · ${countryName(p.country)}`}</small>
            </button></li>
          ))}
        </ul>
      )}
      {all && q.trim().length >= 2 && !res.length && <ul className="mf-res"><li><span className="mf-k ip-none">No place called that on the map yet.</span></li></ul>}
    </div>
  );
}

const fold = (x: string) => x.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

/** A recommended trip, map first: the route on the globe with each stop's drawing, and in the
 *  panel the length, the month and the stops, each opening on its days (Manu 2026-11-16). */
export default function ItineraryPage() {
  const { slug = "" } = useParams();
  const [q] = useSearchParams();
  const nav = useNavigate();
  const qMonth = Number(q.get("month")) || undefined;
  const qDays = Number(q.get("days")) || undefined;
  const qStops = q.get("stops") || undefined;
  const [it, setIt] = useState<Itinerary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [day, setDay] = useState<number | null>(null);
  const [walk, setWalk] = useState<[number, number][] | null>(null);
  const [offer, setOffer] = useState<GlobePlace | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [desk, setDesk] = useState(() => typeof matchMedia === "undefined" || matchMedia("(min-width: 900px)").matches);
  const [drag, setDrag] = useState<number | null>(null);
  const { ensureUser, toast, user } = useApp();
  // the trip this page keeps up to date, its clothes under the route (Manu 2026-11-16: "sta tutto
  // dentro la stessa pagina"): one per region and browser tab, saved only when you press Save
  const [trip, setTrip] = useState<{ id: string; saved: boolean } | null>(null);
  const [ver, setVer] = useState(0);
  const [tier, setTier] = useState<Tier>("medium");
  const sync = useRef<Promise<unknown>>(Promise.resolve());

  useEffect(() => {
    const mq = matchMedia("(min-width: 900px)");
    const f = () => setDesk(mq.matches);
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, []);

  // another length or season is another route: the stops close
  useEffect(() => { setSel(null); setDay(null); setOffer(null); }, [slug, qDays]);
  useEffect(() => { setDay(null); }, [sel]);

  useEffect(() => {
    setErr(null);
    let live = true;
    setBusy(true);
    api.itinerary(slug, undefined, qMonth, qDays, qStops).then((x) => { if (live) { setIt(x); setMsg(null); } })
      .catch((e) => { if (live) { if (qStops) setMsg((e as Error).message); else setErr((e as Error).message); } })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [slug, qMonth, qDays, qStops]);

  // the open day's walk on the map: its trail's own line, as on the Walks page
  const trailId = sel != null && day != null ? it?.stops[sel]?.days[day]?.things.find((t) => t.trail?.has_map)?.trail?.id ?? null : null;
  useEffect(() => {
    setWalk(null);
    if (!trailId) return;
    let live = true;
    api.trail(trailId).then((t) => { if (live && t.line.length > 1) setWalk(t.line); }).catch(() => undefined);
    return () => { live = false; };
  }, [trailId]);

  // every change of the route (month, days, stops) goes to the same trip, one after the other
  useEffect(() => {
    if (!it) return;
    const m = qMonth ?? Number(it.start_date.slice(5, 7));
    const st: [string, number][] | undefined = qStops ? it.stops.map((s) => [s.place ?? "", nights(s.start_date, s.end_date)]) : undefined;
    const d = qDays && it.journey ? it.days : undefined;
    const tripKey = `ip-trip:${it.journey?.id ?? it.slug}`;
    sync.current = sync.current.then(async () => {
      try {
        await ensureUser();
        let id: string | null = null;
        try { id = sessionStorage.getItem(tripKey); } catch { /* private window */ }
        const t = await api.packItinerary(it.slug, undefined, m, st ? undefined : d, st, id ?? undefined);
        try { sessionStorage.setItem(tripKey, t.id); } catch { /* private window */ }
        setTrip({ id: t.id, saved: !!t.saved });
        setVer((v) => v + 1);
      } catch (e) { setMsg((e as Error).message); }
    });
  }, [it]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (!msg) return; const t = setTimeout(() => setMsg(null), 6000); return () => clearTimeout(t); }, [msg]);

  const save = useCallback(async () => {
    if (!trip) return;
    const t = await api.patchTrip(trip.id, { saved: !trip.saved });
    setTrip({ id: t.id, saved: !!t.saved });
    toast(t.saved ? (user?.is_guest ? "Saved in Trips. Create a free account to keep it on every device." : "Saved in Trips.") : "Removed from Saved.");
  }, [trip, toast, user]);

  if (err) return <main className="page"><div className="wrap"><p className="err">{err}</p><Link to="/">All recommended trips</Link></div></main>;
  if (!it) return <main className="page"><div className="wrap"><p className="loading"><span className="spin" /></p></div></main>;

  const month = qMonth ?? Number(it.start_date.slice(5, 7));
  const starts: number[] = [];
  it.stops.reduce((d, s) => { starts.push(d); return d + nights(s.start_date, s.end_date); }, 1);
  const inset = desk ? { top: 20, right: 60, bottom: 90, left: offer ? 860 : 470 } : { top: 0, right: 0, bottom: 22, left: 0 };
  const short = !qStops && qDays && it.days < qDays;

  // the trip is edited right here (Manu 2026-11-16: "da qui stesso posso direttamente editare il
  // viaggio"): days per stop, a stop out, a place tapped on the map in; the page shows the result
  const mine: [string, number][] = it.stops.map((s) => [s.place ?? "", nights(s.start_date, s.end_date)]);
  const canEdit = mine.every(([p]) => p);
  const edit = (next: [string, number][]) => {
    const total = next.reduce((n, [, d]) => n + d, 0);
    if (total < MIN_DAYS || total > MAX_DAYS) { setMsg(`A trip here is ${MIN_DAYS} to ${MAX_DAYS} days.`); return; }
    setOffer(null); setSel(null);
    nav(`/ideas/${slug}?month=${month}&stops=${next.map(([p, d]) => `${p}:${d}`).join(",")}`, { replace: true });
  };
  const nightsAt = (i: number, d: number) => edit(mine.map(([p, n], k) => [p, k === i ? Math.min(10, Math.max(1, n + d)) : n]));
  const drop = (i: number) => edit(mine.filter((_, k) => k !== i));
  const slot = offer ? bestSlot(it.stops, offer.lat, offer.lon) : 0;
  const tapped = (p: GlobePlace) => {
    const i = it.stops.findIndex((x) => x.place === p.id || km(x.latitude, x.longitude, p.lat, p.lon) < 2);
    if (i >= 0) { setOffer(null); setSel(i); } else if (canEdit) setOffer(p);
  };
  const addOffer = () => { if (offer) edit([...mine.slice(0, slot), [offer.id, 2], ...mine.slice(slot)]); };
  // a place looked up by name goes where it makes the shortest detour; then drag it where you like
  const addPlace = (p: GlobePlace) => {
    const had = it.stops.findIndex((x) => x.place === p.id);
    if (had >= 0) { setSel(had); setMsg(`${p.name} is already stop ${had + 1}: give it more days with +.`); return; }
    if (mine.length >= 15) { setMsg("15 stops at most."); return; }
    const i = bestSlot(it.stops, p.lat, p.lon);
    edit([...mine.slice(0, i), [p.id, 2], ...mine.slice(i)]);
  };
  const moveTo = (from: number, to: number) => {
    if (from === to) return;
    const next = [...mine];
    const [x] = next.splice(from, 1);
    next.splice(to, 0, x);
    edit(next);
  };
  const toBag = () => document.getElementById("bag")?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <main className="trk itinerary-mf ip-one">
      <div className="ip-top">
      <div className="mf">
        <div className="mf-map">
          <TripMap stops={it.stops as unknown as Stop[]} focusIndex={sel} bare inset={inset} onPin={(i) => setSel(i)} walk={walk} onPlace={tapped} />
        </div>

        <section className="mf-float mf-panel" aria-label={it.title}>
          <div className="mf-trailhead">
            <div className="ip-crumbrow">
              <Link className="mf-k mf-crumb" to="/"><Back /> Recommended · {countryNames(it.journey?.countries ?? it.countries)}</Link>
              <button type="button" className={`mf-btn sm x-save${trip?.saved ? " on" : ""}`} aria-pressed={!!trip?.saved} disabled={!trip} onClick={save}>
                {trip?.saved ? "Saved" : "Save"}
              </button>
            </div>
            <h1>{it.journey?.name ?? it.title}</h1>
            {it.journey && <Pickers j={it.journey} it={it} month={month}
              onPick={(s, m, d) => nav(qStops && s === slug && (d === undefined || d === it.days)
                ? `/ideas/${s}?month=${m}&stops=${qStops}` // another month, the same edited trip
                : `/ideas/${s}?month=${m}${d ? `&days=${d}` : ""}`, { replace: true })} />}
            {short && <span className="mf-k">The longest trip here in {MONTHS[month - 1]} is {it.days} days.</span>}
            {msg && <p className="mf-msg bad" role="status">{msg}</p>}
          </div>
          {offer && !desk && <PlacePop place={offer} slot={slot} busy={busy} floating={false} onAdd={addOffer} onClose={() => setOffer(null)} />}
          <div className={desk ? "mf-scroll" : "mf-ibody"}>
            <ol className={`mf-stops${busy ? " busy" : ""}`}>
              {it.stops.map((s, i) => {
                const n = nights(s.start_date, s.end_date);
                const open = sel === i;
                return (
                  <li key={`${s.place}-${i}`} className={`${open ? "open" : ""}${drag === i ? " drag" : ""}`}
                    onDragOver={(e) => { if (drag != null) e.preventDefault(); }}
                    onDrop={(e) => { e.preventDefault(); if (drag != null) moveTo(drag, i); setDrag(null); }}>
                    <div className="mf-irow" draggable={desk && canEdit && !busy} onDragStart={() => setDrag(i)} onDragEnd={() => setDrag(null)}>
                      {canEdit && desk && <span className="ip-grip" aria-hidden="true" title="Drag to move"><Grip /></span>}
                      <button type="button" className={`mf-trow${open ? " sel" : ""}`} aria-expanded={open} onClick={() => setSel(open ? null : i)}>
                        <span className="mf-num">{i + 1}</span>
                        {s.art && <span className="mf-thumb"><Illustration art={s.art} /></span>}
                        <span className="mf-nm">
                          <b>{s.name}</b>
                          <small>{n > 1 ? `Days ${starts[i]}–${starts[i] + n - 1}` : `Day ${starts[i]}`}{stopDoes(s) ? ` · ${stopDoes(s)}` : ""}</small>
                        </span>
                      </button>
                      {canEdit && <span className="mf-step">
                        <button type="button" onClick={() => nightsAt(i, -1)} disabled={n <= 1 || busy} aria-label={`One day less in ${s.name}`}>−</button>
                        <span>{n}<i> {n === 1 ? "day" : "days"}</i></span>
                        <button type="button" onClick={() => nightsAt(i, 1)} disabled={n >= 10 || busy} aria-label={`One day more in ${s.name}`}>+</button>
                      </span>}
                      {canEdit && !desk && i > 0 && <button type="button" className="mf-ib" onClick={() => moveTo(i, i - 1)} disabled={busy} aria-label={`Move ${s.name} earlier`}><Up /></button>}
                      {canEdit && it.stops.length > 1 && <button type="button" className="mf-ib" onClick={() => drop(i)} disabled={busy} aria-label={`Remove ${s.name}`}><X /></button>}
                    </div>
                    {open && <StopDays s={s} from={starts[i]} day={day} onDay={setDay} />}
                  </li>
                );
              })}
            </ol>
          </div>
          {canEdit && <AddStop near={it.journey?.countries ?? it.countries} mine={mine.map(([p]) => p)} onPick={addPlace} disabled={busy} />}
          {canEdit && <p className="mf-k mf-first ip-or">Or tap a place on the map.</p>}
        </section>

        {desk && offer && <PlacePop place={offer} slot={slot} busy={busy} floating onAdd={addOffer} onClose={() => setOffer(null)} />}
        {desk && <button type="button" className="mf-float ip-cue" onClick={toBag}>What to wear · {it.days} days in {MONTHS[month - 1]} <Down /></button>}
      </div>
      </div>
      <TripBag tripId={trip?.id ?? null} ver={ver} tier={tier} setTier={setTier}
        title={<>What to wear <span>{it.days} days in {MONTH_FULL[month - 1]}</span></>} />
    </main>
  );
}

const Back = () => <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>;
const Chev = () => <svg className="mf-chev" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>;
const Up = () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>;
const Down = () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 5v14M5 12l7 7 7-7" /></svg>;
const Plus = () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>;
const Grip = () => <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><circle cx="9" cy="6" r="1.6" /><circle cx="15" cy="6" r="1.6" /><circle cx="9" cy="12" r="1.6" /><circle cx="15" cy="12" r="1.6" /><circle cx="9" cy="18" r="1.6" /><circle cx="15" cy="18" r="1.6" /></svg>;
const MONTH_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const X = () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>;

/** A place tapped on the map goes where it makes the shortest detour (never before the first stop
 *  of a round trip's way out, never after its way home). */
function bestSlot(stops: ItineraryStop[], lat: number, lon: number): number {
  if (!stops.length) return 0;
  const d = (a: ItineraryStop, la: number, lo: number) => km(a.latitude, a.longitude, la, lo);
  const ring = stops.length > 1 && stops[0].place === stops[stops.length - 1].place;
  let best = ring ? stops.length - 1 : stops.length, cost = ring ? Infinity : d(stops[stops.length - 1], lat, lon);
  for (let i = 1; i < stops.length; i++) {
    const c = d(stops[i - 1], lat, lon) + d(stops[i], lat, lon) - d(stops[i - 1], stops[i].latitude, stops[i].longitude);
    if (c < cost) { cost = c; best = i; }
  }
  return best;
}
