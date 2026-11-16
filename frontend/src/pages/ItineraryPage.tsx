import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { TripMap } from "../components/Maps";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { MONTHS, countryNames, nights } from "../lib/format";
import type { Itinerary, ItineraryDay, ItineraryStop, ItineraryThing, Journey, Stop } from "../lib/types";
import { PlacePop } from "../components/PlacePop";
import { km, type GlobePlace } from "../lib/worldmap";

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

/** The trip as it is on the page, edited or not, becomes the traveller's and opens on its clothes
 *  (Manu 2026-11-16: no "Use this trip", no date to ask: a date in the chosen month is ours). */
function WearButton({ it, month, days, stops }: { it: Itinerary; month: number; days?: number; stops?: [string, number][] }) {
  const { ensureUser } = useApp();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function go() {
    setBusy(true); setErr(null);
    try {
      await ensureUser();
      const t = await api.packItinerary(it.slug, undefined, month, stops ? undefined : days, stops);
      nav(`/trips/${t.id}#bag`);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="mf-pack">
      <div className="mf-pack-t"><b>{it.days} days · {MONTHS[month - 1]}</b></div>
      <button className="mf-btn go" type="button" disabled={busy} onClick={go}>{busy ? <span className="spin" /> : "What to wear →"}</button>
      {err && <p className="err">{err}</p>}
    </div>
  );
}

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

  if (err) return <main className="page"><div className="wrap"><p className="err">{err}</p><Link to="/">All recommended trips</Link></div></main>;
  if (!it) return <main className="page"><div className="wrap"><p className="loading"><span className="spin" /></p></div></main>;

  const month = qMonth ?? Number(it.start_date.slice(5, 7));
  const starts: number[] = [];
  it.stops.reduce((d, s) => { starts.push(d); return d + nights(s.start_date, s.end_date); }, 1);
  const inset = desk ? { top: 20, right: 60, bottom: 130, left: offer ? 860 : 470 } : { top: 0, right: 0, bottom: 22, left: 0 };
  const custom = qDays && it.journey ? it.days : undefined;
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

  return (
    <main className="trk itinerary-mf">
      <div className="mf">
        <div className="mf-map">
          <TripMap stops={it.stops as unknown as Stop[]} focusIndex={sel} bare inset={inset} onPin={(i) => setSel(i)} walk={walk} onPlace={tapped} />
        </div>

        <section className="mf-float mf-panel" aria-label={it.title}>
          <div className="mf-trailhead">
            <Link className="mf-k mf-crumb" to="/"><Back /> Recommended · {countryNames(it.journey?.countries ?? it.countries)}</Link>
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
                  <li key={`${s.place}-${i}`} className={open ? "open" : ""}>
                    <div className="mf-irow">
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
                      {canEdit && it.stops.length > 1 && <button type="button" className="mf-ib" onClick={() => drop(i)} disabled={busy} aria-label={`Remove ${s.name}`}><X /></button>}
                    </div>
                    {open && <StopDays s={s} from={starts[i]} day={day} onDay={setDay} />}
                  </li>
                );
              })}
            </ol>
            {canEdit && <p className="mf-k mf-first">Tap a place on the map to add it.</p>}
          </div>
          {!desk && <div className="mf-phone-go"><WearButton it={it} month={month} days={custom} stops={qStops ? mine : undefined} /></div>}
        </section>

        {desk && offer && <PlacePop place={offer} slot={slot} busy={busy} floating onAdd={addOffer} onClose={() => setOffer(null)} />}
        {desk && <section className="mf-float mf-buy mf-packbar" aria-label="What to wear"><WearButton it={it} month={month} days={custom} stops={qStops ? mine : undefined} /></section>}
      </div>
    </main>
  );
}

const Back = () => <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>;
const Chev = () => <svg className="mf-chev" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>;
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
