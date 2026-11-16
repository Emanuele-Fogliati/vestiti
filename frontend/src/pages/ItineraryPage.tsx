import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { TripMap } from "../components/Maps";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { MONTHS, countryNames, monthYear, nights, today } from "../lib/format";
import type { Itinerary, ItineraryDay, ItineraryStop, ItineraryThing, Journey, Stop } from "../lib/types";
import { DRESS_ME } from "../lib/words";

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
  const pickWeeks = (w: number) => {
    const rs = j.routes.filter((r) => r.weeks === w);
    const r = rs.find((x) => x.months.includes(month)) ?? rs[0];
    onPick(r.slug, r.months.includes(month) ? month : (r.best_months[0] ?? r.months[0]));
  };
  const pickDays = (d: number) => {
    const at = j.routes.find((r) => r.days === d && r.months.includes(month));
    if (at) onPick(at.slug, month); else onPick(it.slug, month, d);
  };
  return (
    <div className="mf-pick">
      <div className="mf-lenrow">
        <div className="mf-seg mf-weeks" role="radiogroup" aria-label="How long" style={{ gridTemplateColumns: `repeat(${weeks.length}, 1fr)` }}>
          {weeks.map((w) => (
            <button type="button" role="radio" key={w} aria-checked={w === week} className={w === week ? "on" : ""}
              onClick={() => pickWeeks(w)}>{w} {w === 1 ? "week" : "weeks"}</button>
          ))}
        </div>
        <div className={`mf-daysn${week ? "" : " on"}`} role="group" aria-label="Or a number of days">
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

/** "Use this trip": optional start date, then the itinerary becomes the user's own trip; the
 *  clothes come there, the next step (Manu 2026-11-16: here the traveller is still choosing). */
function PackForm({ it, month, days }: { it: Itinerary; month: number; days?: number }) {
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
      const t = await api.packItinerary(it.slug, start || undefined, start ? undefined : month, days);
      nav(`/trips/${t.id}`);
    } catch (e2) {
      setErr((e2 as Error).message);
      setBusy(false);
    }
  }

  return (
    <form className="mf-pack" onSubmit={pack} aria-label={DRESS_ME}>
      <div className="mf-pack-t"><b>Like it?</b></div>
      <label className="mf-pack-d"><span className="mf-k">Leaving</span>
        <input type="date" value={start} min={today()} onChange={(e) => setStart(e.target.value)}
          title={start ? `${it.days} days from this date` : `No date yet? We plan for ${monthYear(it.start_date)}`} />
      </label>
      <button className="mf-btn go" type="submit" disabled={busy}>{busy ? <span className="spin" /> : DRESS_ME}</button>
      {err && <p className="err">{err}</p>}
    </form>
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
  const [it, setIt] = useState<Itinerary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [day, setDay] = useState<number | null>(null);
  const [walk, setWalk] = useState<[number, number][] | null>(null);
  const [desk, setDesk] = useState(() => typeof matchMedia === "undefined" || matchMedia("(min-width: 900px)").matches);

  useEffect(() => {
    const mq = matchMedia("(min-width: 900px)");
    const f = () => setDesk(mq.matches);
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, []);

  // another length or season is another route: the stops close
  useEffect(() => { setSel(null); setDay(null); }, [slug, qDays]);
  useEffect(() => { setDay(null); }, [sel]);

  useEffect(() => {
    setErr(null);
    let live = true;
    api.itinerary(slug, undefined, qMonth, qDays).then((x) => { if (live) setIt(x); })
      .catch((e) => { if (live) setErr((e as Error).message); });
    return () => { live = false; };
  }, [slug, qMonth, qDays]);

  // the open day's walk on the map: its trail's own line, as on the Walks page
  const trailId = sel != null && day != null ? it?.stops[sel]?.days[day]?.things.find((t) => t.trail?.has_map)?.trail?.id ?? null : null;
  useEffect(() => {
    setWalk(null);
    if (!trailId) return;
    let live = true;
    api.trail(trailId).then((t) => { if (live && t.line.length > 1) setWalk(t.line); }).catch(() => undefined);
    return () => { live = false; };
  }, [trailId]);

  if (err) return <main className="page"><div className="wrap"><p className="err">{err}</p><Link to="/trips?tab=recommended">All recommended trips</Link></div></main>;
  if (!it) return <main className="page"><div className="wrap"><p className="loading"><span className="spin" /></p></div></main>;

  const month = qMonth ?? Number(it.start_date.slice(5, 7));
  const starts: number[] = [];
  it.stops.reduce((d, s) => { starts.push(d); return d + nights(s.start_date, s.end_date); }, 1);
  const inset = desk ? { top: 20, right: 60, bottom: 130, left: 470 } : { top: 0, right: 0, bottom: 22, left: 0 };
  const custom = qDays && it.journey ? it.days : undefined;
  const short = qDays && it.days < qDays;

  return (
    <main className="trk itinerary-mf">
      <div className="mf">
        <div className="mf-map">
          <TripMap stops={it.stops as unknown as Stop[]} focusIndex={sel} bare inset={inset} onPin={(i) => setSel(i)} walk={walk} />
        </div>

        <section className="mf-float mf-panel" aria-label={it.title}>
          <div className="mf-trailhead">
            <Link className="mf-k mf-crumb" to="/trips?tab=recommended"><Back /> Recommended · {countryNames(it.journey?.countries ?? it.countries)}</Link>
            <h1>{it.journey?.name ?? it.title}</h1>
            {it.journey && <Pickers j={it.journey} it={it} month={month}
              onPick={(s, m, d) => nav(`/ideas/${s}?month=${m}${d ? `&days=${d}` : ""}`, { replace: true })} />}
            {short && <span className="mf-k">The longest trip here in {MONTHS[month - 1]} is {it.days} days.</span>}
          </div>
          <div className={desk ? "mf-scroll" : "mf-ibody"}>
            <ol className="mf-stops">
              {it.stops.map((s, i) => {
                const n = nights(s.start_date, s.end_date);
                const open = sel === i;
                return (
                  <li key={s.id} className={open ? "open" : ""}>
                    <button type="button" className={`mf-trow${open ? " sel" : ""}`} aria-expanded={open} onClick={() => setSel(open ? null : i)}>
                      <span className="mf-num">{i + 1}</span>
                      {s.art && <span className="mf-thumb"><Illustration art={s.art} /></span>}
                      <span className="mf-nm">
                        <b>{s.name}</b>
                        <small>{n > 1 ? `Days ${starts[i]}–${starts[i] + n - 1}` : `Day ${starts[i]}`}{stopDoes(s) ? ` · ${stopDoes(s)}` : ""}</small>
                      </span>
                    </button>
                    {open && <StopDays s={s} from={starts[i]} day={day} onDay={setDay} />}
                  </li>
                );
              })}
            </ol>
          </div>
          {!desk && <div className="mf-phone-go"><PackForm it={it} month={month} days={custom} /></div>}
        </section>

        {desk && <section className="mf-float mf-buy mf-packbar" aria-label={DRESS_ME}><PackForm it={it} month={month} days={custom} /></section>}
      </div>
    </main>
  );
}

const Back = () => <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>;
const Chev = () => <svg className="mf-chev" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>;
