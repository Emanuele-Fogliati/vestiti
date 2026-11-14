/* Start a trip the way you'd tell a friend (Manu, 2026-11-12): say or type it ("Patagonia in
   January, three weeks", "Buenos Aires 6-8 January, then El Calafate..."), or list the stops
   like a multi-city flight search. The route shows up as steps you can change; then straight
   to the clothes. */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { dayText, daysOf, firstDays } from "../lib/plandays";
import { guessLeg, legText, legWeight } from "../lib/travel";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app-context";
import { MONTH_LONG, MONTHS, today } from "../lib/format";
import { dated, firstOf, LENGTHS, move, setDays, short, span, totalDays } from "../lib/plan";
import { useSpeech } from "../lib/speech";
import type { BookedDay, Place, PlanArea, PlanIdea, PlanReading, PlanStep, PlanSuggestion } from "../lib/types";
import BookedPlan from "./BookedPlan";
import HourByHour from "./HourByHour";
import { PlaceSearch } from "./PlaceSearch";

export const DRESS_ME_LABEL = "Dress me for this trip";

const EXAMPLES = [
  "Patagonia in January, three weeks",
  "Rome 3 days, Florence 2, Venice 2 from 10 May",
  "Somewhere warm by the sea in February, 10 days",
];

type Mode = "none" | "region" | "stops" | "open" | "booked";

const km = (a: { lat: number; lon: number }, b: { lat: number; lon: number }) => {
  const r = Math.PI / 180, x = (b.lon - a.lon) * r * Math.cos(((a.lat + b.lat) / 2) * r), y = (b.lat - a.lat) * r;
  return Math.sqrt(x * x + y * y) * 6371;
};
/** Where a new stop costs the least road. */
function insertAt(steps: PlanStep[], s: PlanStep): PlanStep[] {
  if (!steps.length) return [s];
  let best = Infinity, at = steps.length;
  for (let i = 0; i <= steps.length; i++) {
    const seq = [...steps.slice(0, i), s, ...steps.slice(i)];
    const c = seq.slice(1).reduce((n, x, k) => n + km(seq[k], x), 0);
    if (c < best) { best = c; at = i; }
  }
  return [...steps.slice(0, at), s, ...steps.slice(at)];
}

const plusDays = (iso: string, n: number) => {
  const x = new Date(iso + "T12:00:00Z");
  x.setUTCDate(x.getUTCDate() + n);
  return x.toISOString().slice(0, 10);
};

const stepOf =(p: Place): PlanStep => ({
  key: `p-${p.latitude.toFixed(3)},${p.longitude.toFixed(3)}`, place_id: null, name: p.name,
  country: p.country_code ?? null, lat: p.latitude, lon: p.longitude, kind: "town", days: 2,
  elevation_m: p.elevation_m ?? null, sights: [],
});

/** `initial`: words typed on the home page; they are read as soon as the page opens. */
export function TripStarter({ compact, initial }: { compact?: boolean; initial?: string }) {
  const nav = useNavigate();
  const { ensureUser } = useApp();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [mode, setMode] = useState<Mode>("none");
  const [steps, setSteps] = useState<PlanStep[]>([]);
  const [area, setArea] = useState<PlanArea | null>(null);
  const [only, setOnly] = useState<string[]>([]);
  const [more, setMore] = useState<PlanStep[]>([]);
  const [, setRoute] = useState<string | null>(null);
  const [best, setBest] = useState<number[]>([]);
  const [start, setStart] = useState("");
  const [month, setMonth] = useState<number | null>(null);
  const [target, setTarget] = useState<number | null>(null);
  const [keep, setKeep] = useState<string[]>([]);
  const [endWith, setEndWith] = useState<string[]>([]);  // "e alla fine Ushuaia": stays the last stop
  const [drop, setDrop] = useState<string[]>([]);
  const [ideas, setIdeas] = useState<PlanIdea[]>([]);
  const [home, setHome] = useState<PlanReading["home"]>(null);
  const [missing, setMissing] = useState<PlanReading["missing"]>([]);
  const [heardText, setHeardText] = useState("");
  const [sugg, setSugg] = useState<PlanSuggestion[]>([]);
  const [booked, setBooked] = useState<{ timeline: BookedDay[]; end: string; nights: number; days: number } | null>(null);
  const [adding, setAdding] = useState(false);
  const [creating, setCreating] = useState<"" | "dress" | "days">("");
  const resultRef = useRef<HTMLDivElement>(null);

  const speech = useSpeech((t) => { setText(t); read(t); });
  const first = useRef(initial?.trim() ?? "");
  useEffect(() => {
    if (first.current) { setText(first.current); read(first.current); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // regions and countries while a short name is typed
  useEffect(() => {
    const q = text.trim();
    if (q.length < 2 || q.split(/\s+/).length > 3 || speech.listening) { setSugg([]); return; }
    const t = window.setTimeout(() => api.planSuggest(q).then(setSugg).catch(() => setSugg([])), 200);
    return () => window.clearTimeout(t);
  }, [text, speech.listening]);

  function reset() {
    setErr(""); setIdeas([]); setMore([]); setRoute(null); setBest([]); setKeep([]); setEndWith([]); setDrop([]); setArea(null); setOnly([]);
  }

  async function read(t: string) {
    if (t.trim().length < 2) return;
    setBusy(true); reset(); setSugg([]);
    try {
      await ensureUser();
      const r = await api.planUnderstand(t.trim());
      setHeardText(r.text);
      setMonth(r.month); setStart(r.start_date ?? ""); setHome(r.home); setMissing(r.missing);
      setBooked(null);
      if (r.mode === "booked" && r.timeline) {
        // a trip already booked: its days as written, the beds as stops
        setMode("booked"); setSteps(r.stops); setTarget(null); setHeardText("");
        setBooked({ timeline: r.timeline, end: r.end_date ?? "", nights: r.nights ?? 0, days: r.days ?? r.timeline.length });
      } else if (r.mode === "region" && r.proposal) {
        const p = r.proposal;
        setMode("region"); setArea(p.area); setOnly(p.only); setSteps(p.stops); setMore(p.more);
        setRoute(p.route); setBest(p.best_months); setTarget(r.days ?? p.days); setKeep(r.keep ?? []); setEndWith(r.last ?? []);
      } else if (r.mode === "stops") {
        setMode("stops"); setSteps(r.stops); setTarget(null);
      } else {
        setMode("open"); setSteps([]); setIdeas(r.ideas); setTarget(r.days);
      }
      window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); } finally { setBusy(false); }
  }

  async function pickArea(s: PlanSuggestion) {
    setText(s.name); setSugg([]); reset(); setBusy(true);
    try {
      await ensureUser();
      const p = await api.planPropose({ area: s.id, month });
      setMode("region"); setArea(p.area); setOnly(p.only); setSteps(p.stops); setMore(p.more); setRoute(p.route);
      setBest(p.best_months); setTarget(p.days); setMissing(month ? ["how_long"] : ["when", "how_long"]); setHeardText("");
    } catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); } finally { setBusy(false); }
  }

  async function repropose(patch: { days?: number | null; month?: number | null; keep?: string[]; drop?: string[] }) {
    if (!area) return;
    setBusy(true);
    try {
      const p = await api.planPropose({ area: area.id, only, days: patch.days ?? target, month: patch.month ?? month,
        keep: patch.keep ?? keep, drop: patch.drop ?? drop, last: endWith.filter((k) => !(patch.drop ?? drop).includes(k)) });
      setSteps(p.stops); setMore(p.more); setRoute(p.route); setBest(p.best_months);
    } catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); } finally { setBusy(false); }
  }

  function chooseMonth(m: number | null) {
    setMonth(m); setStart(""); setMissing((x) => x.filter((k) => k !== "when"));
    if (mode === "region") repropose({ month: m });
  }
  function chooseLength(n: number) {
    setTarget(n); setMissing((x) => x.filter((k) => k !== "how_long"));
    if (mode === "region") repropose({ days: n });
  }
  function removeStep(i: number) {
    const s = steps[i];
    setSteps(steps.filter((_, j) => j !== i));
    if (mode === "region") { setDrop([...drop, s.key]); setKeep(keep.filter((k) => k !== s.key)); setMore([s, ...more]); }
  }
  function addMore(s: PlanStep) {
    setSteps(insertAt(steps, { ...s, start_date: null }));
    setMore(more.filter((m) => m.key !== s.key));
    setKeep([...keep, s.key]); setDrop(drop.filter((d) => d !== s.key));
  }
  function addPlace(p: Place) {
    const s = stepOf(p);
    setSteps(mode === "stops" || !steps.length ? [...steps, s] : insertAt(steps, s));
    if (mode === "none") setMode("stops");
    setAdding(false);
  }
  function listStops() {
    reset(); setMode("stops"); setSteps([]); setAdding(true); setMissing([]);
    window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  async function create(go: "dress" | "days") {
    if (!steps.length) return;
    setCreating(go); setErr("");
    try {
      await ensureUser();
      const t = await api.planTrip({ stops: steps, start_date: start || null, month, area: area?.id ?? null,
        home: home ? { lat: home.lat, lon: home.lon, country: home.country } : null });
      nav(`/trips/${t.id}#${go === "dress" ? "layers" : "days"}`);
    } catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); setCreating(""); }
  }

  async function startIdea(i: PlanIdea) {
    setCreating("dress");
    try {
      await ensureUser();
      const t = await api.routeTrip(i.id, { start_date: start || undefined, month });
      nav(`/trips/${t.id}#layers`);
    } catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); setCreating(""); }
  }

  const base = start || (month ? firstOf(month, today()) : "");
  const dates = useMemo(() => dated(steps, base || null), [steps, base]);
  const total = totalDays(steps);
  // days counted across the whole trip (stop 3 starts on day 15, not day 1) and the leg into each stop
  const day0 = firstDays(steps, dates.map((d) => d?.gap ?? 0));
  const legs = useMemo(() => steps.map((s, i) => (i ? guessLeg({ lat: steps[i - 1].lat, lon: steps[i - 1].lon, country: steps[i - 1].country }, s) : null)), [steps]);
  const estimate = !start && !steps.some((s) => s.start_date);
  const last = dates[dates.length - 1];
  const title = mode === "region" && area ? area.name : mode === "open" ? "Where could that be?"
    : mode === "booked" ? steps.filter((s) => s.kind !== "transit").map((s) => s.name).join(" · ") : "Your stops";

  return (
    <div className={`starter${compact ? " compact" : ""}`}>
      <form className="ask" onSubmit={(e) => { e.preventDefault(); read(text); }} role="search" aria-label="Where to?">
        {compact ? <label htmlFor="ask-text" className="ask-q">Where to?</label>
          : <h1 className="ask-q"><label htmlFor="ask-text">Where to?</label></h1>}
        <div className="ask-box">
          <textarea id="ask-text" rows={2} value={speech.listening ? speech.heard || text : text}
            placeholder="Patagonia in January, three weeks… or your stops with their dates"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); read(text); } }} />
          <div className="ask-actions">
            {speech.supported && (
              <button type="button" className={`mic${speech.listening ? " on" : ""}`} onClick={speech.listening ? speech.stop : speech.start}
                aria-pressed={speech.listening} aria-label={speech.listening ? "Stop listening" : "Say it"}>
                <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M12 15a3.5 3.5 0 0 0 3.5-3.5v-6a3.5 3.5 0 0 0-7 0v6A3.5 3.5 0 0 0 12 15Zm6-3.5a6 6 0 0 1-12 0H4.5a7.5 7.5 0 0 0 6.75 7.46V21h1.5v-2.04a7.5 7.5 0 0 0 6.75-7.46H18Z" /></svg>
                <span>{speech.listening ? "Done" : "Say it"}</span>
              </button>
            )}
            <button type="submit" className="btn primary go" disabled={busy || text.trim().length < 2}>
              {busy ? <span className="spin" /> : "Go"}
            </button>
          </div>
          {sugg.length > 0 && (
            <ul className="ask-sugg" role="listbox" aria-label="Regions and countries">
              {sugg.map((s) => (
                <li key={s.id}><button type="button" onClick={() => pickArea(s)}><b>{s.name}</b><small>{s.sub}</small></button></li>
              ))}
            </ul>
          )}
        </div>
        {speech.listening && <p className="ask-hint live">Listening… say where, when and how long. Tap Done when you finish.</p>}
        {speech.error && <p className="ask-hint err">{speech.error}</p>}
        {speech.insecure && (
          <p className="ask-hint err">
            The browser lets the microphone work only on a secure page.{" "}
            <a href={speech.insecure}>Open the secure version</a>. The first time the browser warns that the
            connection is not private: tap “Advanced”, then “Proceed” (on iPhone “Show details”, then
            “visit this website”). Or use the microphone on your keyboard.
          </p>
        )}
        {!speech.listening && mode === "none" && (
          <div className="ask-ex">
            {EXAMPLES.map((x) => <button key={x} type="button" onClick={() => { setText(x); read(x); }}>{x}</button>)}
          </div>
        )}
        <p className="ask-alt">
          <button type="button" className="link" onClick={listStops}>Know your stops? List them like a multi-city flight</button>
        </p>
      </form>

      {err && <p className="err">{err}</p>}

      {mode !== "none" && (
        <section className="tplan" ref={resultRef} aria-live="polite">
          {heardText && <p className="plan-heard">“{heardText}”</p>}
          <header className="plan-head">
            <h2>{title}</h2>
            {mode === "booked" && booked && (
              <p>{booked.days} days · {short(start)} – {short(booked.end)} · {booked.nights} nights booked</p>
            )}
            {mode !== "booked" && steps.length > 0 && last && (
              <p>{total} days · {estimate ? "≈ " : ""}{short(dates[0]!.start)} – {short(last.end)}</p>
            )}
            {mode !== "booked" && steps.length > 0 && !last && <p>{total} days · dates to choose</p>}
          </header>

          {mode === "booked" && booked && <BookedPlan steps={steps} timeline={booked.timeline} />}

          {(mode === "region" || mode === "open" || mode === "stops") && (
            <div className="plan-q">
              <div className={`pq${missing.includes("when") ? " ask-me" : ""}`}>
                <span className="pq-l">When do you go?</span>
                <div className="pq-c">
                  <select value={month ?? ""} aria-label="Month" onChange={(e) => chooseMonth(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">Pick a month</option>
                    {MONTH_LONG.map((m, i) => <option key={m} value={i + 1}>{m}{best.length <= 5 && best.includes(i + 1) ? " · best" : ""}</option>)}
                  </select>
                  <span className="muted small">or</span>
                  <input type="date" value={start} min={today()} aria-label="Exact start date"
                    onChange={(e) => { setStart(e.target.value); if (e.target.value) { setMonth(Number(e.target.value.slice(5, 7))); setMissing((x) => x.filter((k) => k !== "when")); } }} />
                </div>
                {missing.includes("when") && <span className="pq-why">The month changes the clothes more than anything.</span>}
              </div>
              {(mode === "region" || mode === "open") && (
                <div className={`pq${missing.includes("how_long") ? " ask-me" : ""}`}>
                  <span className="pq-l">How long?</span>
                  <div className="pq-c chips-row">
                    {LENGTHS.map(([l, n]) => (
                      <button key={n} type="button" className="fchip" aria-pressed={target === n} onClick={() => chooseLength(n)}>{l}</button>
                    ))}
                    <input type="number" min={1} max={120} value={target ?? ""} aria-label="Days" placeholder="days"
                      onChange={(e) => setTarget(Number(e.target.value) || null)}
                      onBlur={() => target && chooseLength(target)} style={{ width: 80 }} />
                  </div>
                </div>
              )}
            </div>
          )}

          {mode === "open" && (
            <div className="ideas">
              <p className="muted">I can't tell where yet. Type a region or a country, or start from one of these{month ? `, all good in ${MONTH_LONG[month - 1]}` : ""}:</p>
              {ideas.length === 0 && <p className="small">No trip in our routes fits that yet. Try a region (“Tuscany”, “Lapland”) or a country.</p>}
              <ul>
                {ideas.map((i) => (
                  <li key={i.id}>
                    <div><b>{i.title}</b><span className="muted small">{i.days} days{i.weather ? ` · ${i.weather}` : ""}</span></div>
                    <button type="button" className="btn sm" onClick={() => startIdea(i)} disabled={!!creating}>Start from this</button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {mode !== "open" && mode !== "booked" && (
            <ol className="steps">
              {steps.map((s, i) => {
                const d = dates[i];
                const leg = legs[i];
                const how = leg ? legText(leg) : "";
                const full = !!leg && legWeight(leg) === "full";
                return (
                  <li key={s.key} className="step">
                    <span className="step-dot" aria-hidden="true">{i + 1}</span>
                    <div className="step-main">
                      {how && (
                        <span className={`step-leg${full ? " full" : ""}`} title={`From ${steps[i - 1].name}${leg?.km ? `, ${leg.km} km` : ""}`}>
                          {how}{full ? " · travel day" : ""}
                        </span>
                      )}
                      <b className="step-name">{s.name}</b>
                      <span className="step-when">
                        {d ? `${estimate ? "≈ " : ""}${span(d)}` : "Dates later"}
                        <input type="date" className="step-date" aria-label={`Arrive in ${s.name} on`} value={s.start_date ?? ""} min={today()}
                          onChange={(e) => setSteps(steps.map((x, j) => (j === i ? { ...x, start_date: e.target.value || null, fixed_dates: !!e.target.value } : x)))} />
                      </span>
                      {s.sights.length > 0 && <span className="step-sights">{s.sights.slice(0, 3).join(" · ")}</span>}
                      {full && s.days === 1 && <span className="step-warn">Only the travel day here: add a day to see it.</span>}
                      {d && d.gap > 0 && <span className="step-gap">after {d.gap} free day{d.gap > 1 ? "s" : ""}</span>}
                    </div>
                    <div className="step-ctl">
                      <div className="stepper" role="group" aria-label={`Days in ${s.name}`}>
                        <button type="button" onClick={() => setSteps(setDays(steps, i, s.days - 1))} aria-label="One day less" disabled={s.days <= 1}>−</button>
                        <span>{s.days} {s.days === 1 ? "day" : "days"}</span>
                        <button type="button" onClick={() => setSteps(setDays(steps, i, s.days + 1))} aria-label="One day more">+</button>
                      </div>
                      <span className="step-more">
                        <button type="button" onClick={() => setSteps(move(steps, i, -1))} disabled={i === 0} aria-label="Earlier">↑</button>
                        <button type="button" onClick={() => setSteps(move(steps, i, 1))} disabled={i === steps.length - 1} aria-label="Later">↓</button>
                        <button type="button" onClick={() => removeStep(i)} aria-label={`Remove ${s.name}`}>✕</button>
                      </span>
                    </div>
                    {!!s.plan?.length && (
                      <details className="step-days">
                        <summary>Day by day <span>{s.days} {s.days === 1 ? "day" : "days"}</span></summary>
                        <ol className="dayrows">
                          {daysOf(s).map((dd) => (
                            <li key={dd.day} className={`dayrow sd-${dd.kind}`}>
                              <div className="dayrow-n">
                                <b>Day {day0[i] + dd.day - 1}</b>
                                {d && <span>{(estimate ? "≈ " : "") + short(plusDays(d.start, dd.day - 1))}</span>}
                              </div>
                              <div className="dayrow-body">
                                <p className="dayrow-t">{dayText(dd, i === 0 && dd.day === 1, leg ? { from: steps[i - 1].name, leg } : undefined)}</p>
                                {dd.items?.map((t) => (
                                  <HourByHour key={t.id} steps={t.steps} extras={t.extras} book={t.book}
                                    label={dd.items!.length > 1 ? `${t.name}: hour by hour` : "Hour by hour"} />
                                ))}
                              </div>
                            </li>
                          ))}
                        </ol>
                      </details>
                    )}
                  </li>
                );
              })}
              <li className="step add">
                <span className="step-dot" aria-hidden="true">+</span>
                {adding || !steps.length ? (
                  <div className="step-main"><PlaceSearch value={null} onPick={addPlace} autoFocus={adding} countries={only.length ? only : undefined} /></div>
                ) : (
                  <button type="button" className="link" onClick={() => setAdding(true)}>Add a stop</button>
                )}
              </li>
            </ol>
          )}

          {mode === "region" && target && total !== target && steps.length > 0 && (
            <p className="plan-note">{total > target ? `${total - target} days more than the ${target} you said.` : `${target - total} days left of the ${target} you said.`}{" "}
              <button type="button" className="link" onClick={() => repropose({ keep: steps.map((s) => s.key) })}>Fit it to {target} days</button></p>
          )}

          {mode === "region" && more.length > 0 && (
            <div className="also">
              <span className="pq-l">Also in {area?.name}</span>
              <div className="chips-row">
                {more.slice(0, 8).map((m) => (
                  <button key={m.key} type="button" className="fchip" onClick={() => addMore(m)}>+ {m.name} <small>{m.days} d</small></button>
                ))}
              </div>
            </div>
          )}

          {steps.length > 0 && (
            <div className="plan-go">
              <button type="button" className="btn primary big" onClick={() => create("dress")} disabled={!!creating}>
                {creating === "dress" ? <span className="spin" /> : DRESS_ME_LABEL}</button>
              <button type="button" className="btn ghost" onClick={() => create("days")} disabled={!!creating}>
                {creating === "days" ? <span className="spin" /> : "Plan the days first"}</button>
              <span className="small muted">{mode === "booked" ? "Your flights, car and beds stay as you wrote them." : `${estimate ? "Dates are a guess until you pick them. " : ""}Flights and beds later, if you want.`}</span>
            </div>
          )}
          {mode === "region" && <p className="small muted">The order follows what organised trips do; the days are what they give each place. Change anything.</p>}
          {mode !== "region" && month && !start && steps.length > 0 && <p className="small muted">Starting {MONTHS[month - 1]} 1 until you pick the day.</p>}
        </section>
      )}
    </div>
  );
}
