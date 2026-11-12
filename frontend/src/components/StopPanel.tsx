import { useState } from "react";
import { api } from "../lib/api";
import { activitiesFrom, sameActivities } from "../lib/board";
import { activityText, addDays } from "../lib/format";
import { terrainFor } from "../lib/terrain";
import type { BoardStop, LegMode, PlanChoices, PlanDayOut, Sky, StopStatus, TodoItem, Trip } from "../lib/types";
import { Illustration } from "./Illustration";
import { PlaceGuide } from "./PlaceGuide";
import { PlaceQuestion } from "./PlaceQuestion";
import { StopForm } from "./Stops";

const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const D = (s: string) => new Date(s + "T12:00:00Z");
const dayLabel = (s: string) => { const d = D(s); return `${DOW[d.getUTCDay()]} ${d.getUTCDate()} ${MON[d.getUTCMonth()]}`; };
const SKY_TEXT: Record<Sky, string> = { clear: "Clear", cloud: "Cloudy", rain: "Rain", wind: "Strong wind", unknown: "Not known yet" };
const EFFORT = { easy: "Easy", moderate: "Moderate", hard: "Hard" };

export function SkyIcon({ sky }: { sky: Sky }) {
  const p = { width: 14, height: 14, viewBox: "0 0 16 16", "aria-hidden": true } as const;
  if (sky === "clear") return <svg {...p}><circle cx="8" cy="8" r="3.3" fill="currentColor" /><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6 13 13M3 13l1.4-1.4M11.6 4.4 13 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>;
  if (sky === "rain") return <svg {...p}><path d="M4.5 9.5h7.2a3 3 0 0 0 .2-6 4 4 0 0 0-7.6 1.2 2.4 2.4 0 0 0 .2 4.8z" fill="currentColor" /><path d="M5 11.5 4 14M8.5 11.5l-1 2.5M12 11.5 11 14" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>;
  if (sky === "wind") return <svg {...p}><path d="M1.5 6h9a2 2 0 1 0-2-2M1.5 10h11a2 2 0 1 1-2 2M1.5 8h6" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>;
  if (sky === "cloud") return <svg {...p}><path d="M4.5 12.5h7.2a3 3 0 0 0 .2-6 4 4 0 0 0-7.6 1.2 2.4 2.4 0 0 0 .2 4.8z" fill="currentColor" /></svg>;
  return <svg {...p}><circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeDasharray="2 2" /></svg>;
}

export function LegIcon({ mode }: { mode: LegMode }) {
  const p = { width: 14, height: 14, viewBox: "0 0 16 16", "aria-hidden": true, className: "legico" } as const;
  if (mode === "flight") return <svg {...p}><path d="M15 8.6 9.5 6.8V2.2a1.2 1.2 0 0 0-2.4 0v4.6L1.5 8.6v1.6l5.6-1.3v3.4L5.5 13.4V15l2.8-.8 2.8.8v-1.6l-1.6-1.1V8.9l5.5 1.3z" fill="currentColor" /></svg>;
  if (mode === "bus" || mode === "car") return <svg {...p}><rect x="2" y="3" width="12" height="9" rx="2" fill="currentColor" /><circle cx="5" cy="13" r="1.5" fill="currentColor" /><circle cx="11" cy="13" r="1.5" fill="currentColor" /></svg>;
  if (mode === "boat") return <svg {...p}><path d="M2 10h12l-2 4H4zM8 2v7M8 3l4 5H8" fill="currentColor" /></svg>;
  if (mode === "train") return <svg {...p}><rect x="3.5" y="2" width="9" height="10" rx="2" fill="currentColor" /><path d="M5 15l1.5-2.5M11 15l-1.5-2.5" stroke="currentColor" strokeWidth="1.4" /></svg>;
  return <svg {...p}><circle cx="8" cy="8" r="2.5" fill="currentColor" /></svg>;
}

function NeedTag({ it }: { it: TodoItem }) {
  return <span className={`tag need-${it.need}`}>{it.need_text}</span>;
}

export function StopPanel({ trip, stop, index, count, busy, onResize, onMove, onRemove, onStatus, onChanged, onMsg }: {
  trip: Trip; stop: BoardStop; index: number; count: number; busy: boolean;
  onResize: (d: number) => void; onMove: (d: -1 | 1) => void; onRemove: () => void;
  onStatus: (s: StopStatus, note?: string) => void; onChanged: () => void;
  onMsg: (text: string, kind: "ok" | "bad") => void;
}) {
  const full = trip.stops.find((s) => s.id === stop.id);
  const [askNote, setAskNote] = useState(false);
  const [note, setNote] = useState(stop.fixed_note ?? "");
  const [sleep, setSleep] = useState(stop.sleep ?? "");
  const [skyMenu, setSkyMenu] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const choices: PlanChoices = stop.plan.choices ?? {};
  const fixed = stop.status === "fixed";
  const todo = stop.todo;
  const planned = stop.plan.days.flatMap((d) => d.things);
  const clothes = activitiesFrom(planned.map((t) => t.act));
  const clothesDiffer = clothes.length > 0 && full && !sameActivities(clothes, full.activities ?? []);

  async function savePlan(patch: Partial<PlanChoices>, ok?: string) {
    try {
      await api.patchBoardStop(trip.id, stop.id, { plan: { skip: choices.skip ?? [], pins: choices.pins ?? {}, weather: (choices.weather ?? {}) as PlanChoices["weather"], mode: choices.mode ?? null, ...patch } });
      if (ok) onMsg(ok, "ok");
      onChanged();
    } catch (e) { onMsg((e as Error).message, "bad"); }
  }
  const skip = new Set(choices.skip ?? []);
  const toggleSkip = (it: TodoItem) => {
    const s = new Set(skip);
    if (s.has(it.id)) s.delete(it.id); else s.add(it.id);
    savePlan({ skip: [...s] }, s.has(it.id) ? `${it.name}: skipped.` : `${it.name}: back in the plan.`);
  };
  const pin = (it: TodoItem, date: string) => {
    const p = { ...(choices.pins ?? {}) };
    if (date) p[it.id] = date; else delete p[it.id];
    savePlan({ pins: p }, date ? `${it.name} on ${dayLabel(date)}.` : `${it.name}: day chosen by the weather.`);
  };
  const setSky = (date: string, sky: Sky | null) => {
    const w = { ...(choices.weather ?? {}) } as Record<string, Sky>;
    if (sky) w[date] = sky; else delete w[date];
    setSkyMenu(null);
    savePlan({ weather: w }, sky ? `${dayLabel(date)}: ${SKY_TEXT[sky].toLowerCase()}. The plan is redone.` : `${dayLabel(date)}: back to the forecast.`);
  };
  async function saveSleep() {
    if ((stop.sleep ?? "") === sleep.trim()) return;
    try { await api.patchBoardStop(trip.id, stop.id, { sleep: sleep.trim() || null }); onMsg("Saved where you sleep.", "ok"); onChanged(); }
    catch (e) { onMsg((e as Error).message, "bad"); }
  }
  async function useClothes() {
    try { await api.patchBoardStop(trip.id, stop.id, { activities: clothes }); onMsg(`The clothes for ${stop.name} now follow these plans.`, "ok"); onChanged(); }
    catch (e) { onMsg((e as Error).message, "bad"); }
  }
  const dates = Array.from({ length: stop.days }, (_, i) => addDays(stop.start_date, i));
  const route = todo.routes.find((r) => r.id === stop.plan.mode);

  return (
    <section className="bd-panel" aria-label={stop.name}>
      <div className="bp-head">
        <div>
          <h3>{stop.name}</h3>
          <p className="muted small">{dayLabel(stop.start_date)} – {dayLabel(stop.end_date)} · {stop.days} day{stop.days > 1 ? "s" : ""}</p>
        </div>
        <div className="bp-ctrl">
          <div className="seg" role="group" aria-label="Status">
            {(["idea", "flex", "fixed"] as const).map((s) => (
              <button key={s} type="button" aria-pressed={stop.status === s}
                onClick={() => { if (s === "fixed" && !fixed) setAskNote(true); else if (s !== stop.status) onStatus(s); }}>
                {s === "idea" ? "Idea" : s === "flex" ? "Flexible" : "Fixed"}</button>
            ))}
          </div>
          <button type="button" className="btn sm" disabled={busy || fixed || stop.days <= 1} onClick={() => onResize(-1)} aria-label="One day less">− day</button>
          <button type="button" className="btn sm" disabled={busy || fixed} onClick={() => onResize(1)} aria-label="One day more">+ day</button>
          <button type="button" className="btn sm" disabled={busy || fixed || index === 0} onClick={() => onMove(-1)}>← Earlier</button>
          <button type="button" className="btn sm" disabled={busy || fixed || index === count - 1} onClick={() => onMove(1)}>Later →</button>
          <button type="button" className="btn sm danger" disabled={busy || fixed} onClick={onRemove}>Remove</button>
        </div>
      </div>
      {askNote && (
        <div className="bd-msg ok">
          <label htmlFor="bp-note">What did you book?</label>
          <input id="bp-note" type="text" value={note} maxLength={120} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Refugios on the W, hotel" />
          <button type="button" className="btn sm primary" onClick={() => { setAskNote(false); onStatus("fixed", note.trim()); }}>Fix it</button>
          <button type="button" className="btn sm ghost" onClick={() => setAskNote(false)}>Cancel</button>
        </div>
      )}
      {fixed && <p className="small muted">Fixed{stop.fixed_note ? `: ${stop.fixed_note}` : ""}. Its days can't move; make it flexible to change them.</p>}

      <div className="bp-cols">
        <div className="bp-days">
          {todo.routes.length > 0 && (
            <div className="row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              <span className="label">How you do it</span>
              <div className="seg" role="group" aria-label="How you do it">
                <button type="button" aria-pressed={!stop.plan.mode} onClick={() => savePlan({ mode: null })}>From one base, day trips</button>
                {todo.routes.map((r) => <button key={r.id} type="button" aria-pressed={stop.plan.mode === r.id} onClick={() => savePlan({ mode: r.id })}>{r.name}</button>)}
              </div>
            </div>
          )}
          {route && <p className="small">{route.summary}</p>}
          <h4>Your days</h4>
          <ol className="bp-daylist">
            {stop.plan.days.map((d) => (
              <DayRow key={d.date} d={d} open={skyMenu === d.date} onSky={() => setSkyMenu(skyMenu === d.date ? null : d.date)} onSet={(s) => setSky(d.date, s)} />
            ))}
          </ol>
          {stop.plan.advice.map((a, i) => <p key={i} className="small muted">{a}</p>)}
          {(() => {
            // a thing on set weekdays that none of these days is: the advice above already says so
            const wd = new Set(stop.plan.days.map((d) => (new Date(d.date + "T12:00:00Z").getUTCDay() + 6) % 7));
            const left = stop.plan.waiting.filter((w) => !w.weekdays?.length || w.weekdays.some((x) => wd.has(x)));
            return left.length > 0 && <p className="small">Not in the plan, no day left: {left.map((w) => w.name).join(", ")}. One more day here would fit {left.length > 1 ? "them" : "it"}.</p>;
          })()}
          {stop.plan.out_of_season.length > 0 && <p className="small muted">Not in season on your dates: {stop.plan.out_of_season.join(", ")}.</p>}
        </div>

        <div className="bp-side">
          {todo.items.length > 0 && (
            <div className="stack" style={{ gap: 6 }}>
              <h4>{todo.source === "guide" ? "Best things to do, in order" : "Most visited near here"}</h4>
              {todo.source === "nearby" && <p className="small muted">In order of how many travellers go. No times or weather advice for this place yet.</p>}
              <ol className="bp-rank">
                {todo.items.map((it) => (
                  <li key={it.id} className={skip.has(it.id) ? "skipped" : ""}>
                    <div>
                      <b>{it.name}</b>
                      {it.hours && <span className="small muted"> · {it.hours}</span>}
                      {it.why && <p className="small">{it.why}</p>}
                      <div className="tags">
                        {todo.source === "guide" && <NeedTag it={it} />}
                        {todo.source === "guide" && <span className="tag">{EFFORT[it.effort]}</span>}
                        {it.best && <span className="tag">{it.best}</span>}
                        {it.book && <span className="tag book">{it.book}</span>}
                      </div>
                      <div className="row" style={{ gap: 8, marginTop: 6, flexWrap: "wrap" }}>
                        <button type="button" className="link small" onClick={() => toggleSkip(it)}>{skip.has(it.id) ? "Add back" : "Skip"}</button>
                        {!skip.has(it.id) && (
                          <select aria-label={`Day for ${it.name}`} value={choices.pins?.[it.id] ?? ""} onChange={(e) => pin(it, e.target.value)}>
                            <option value="">Day: by the weather</option>
                            {dates.map((d) => <option key={d} value={d}>{dayLabel(d)}</option>)}
                          </select>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
              {todo.sources.length > 0 && (
                <p className="small muted">Sources: {todo.sources.map((u, i) => <a key={u} href={u} target="_blank" rel="noopener noreferrer">{i + 1}</a>).reduce<React.ReactNode[]>((a, x, i) => (i ? [...a, " · ", x] : [x]), [])}</p>
              )}
            </div>
          )}
          {todo.source === "none" && <p className="small muted">We don't know this place's sights yet. Add what you plan to do with "Change the place or what you do".</p>}

          <div className="bp-box">
            <label htmlFor="bp-sleep" className="label">Where you sleep</label>
            <input id="bp-sleep" type="text" value={sleep} maxLength={200} onChange={(e) => setSleep(e.target.value)} onBlur={saveSleep}
              onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} placeholder="Add it when you know: hotel, refugio, friend" />
            {todo.sleep_tip && <p className="small muted">{todo.sleep_tip}</p>}
          </div>
          {todo.season && <div className="bp-box"><span className="label">Weather here</span><p className="small">{todo.season}</p></div>}

          {clothesDiffer && (
            <div className="bp-box clothes">
              <span className="label">Clothes for these plans</span>
              <p className="small">{clothes.map(activityText).join(" · ")}</p>
              <p className="small muted">Now: {(full?.activities ?? []).map(activityText).join(" · ") || "nothing yet"}</p>
              <button type="button" className="btn sm primary" onClick={useClothes}>Dress me for these plans</button>
            </div>
          )}

          {full && (
            <div className="bp-place">
              <Illustration terrain={terrainFor(full, index)} art={full.art} />
              <PlaceGuide guide={full.guide} />
              {full.place_status === "check" && (
                <PlaceQuestion place={{ name: full.name, country_code: full.country_code }} issues={full.place_note ? [full.place_note] : []}
                  onYes={async () => { await api.patchStop(trip.id, full.id, { place_confirmed: true }); onChanged(); }}
                  onSearch={() => setEditing(true)} />
              )}
              {editing ? (
                <StopForm tripId={trip.id} stop={full} defaultStart={full.start_date} countries={trip.countries}
                  onDone={() => { setEditing(false); onChanged(); }} onCancel={() => setEditing(false)} />
              ) : (
                <button type="button" className="link small" onClick={() => setEditing(true)}>Change the place or what you do</button>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function DayRow({ d, open, onSky, onSet }: { d: PlanDayOut; open: boolean; onSky: () => void; onSet: (s: Sky | null) => void }) {
  const known = d.sky !== "unknown";
  return (
    <li className={`bp-day k-${d.kind}${d.things.some((t) => t.moved) ? " moved" : ""}`}>
      <div className="bp-when">
        <b>{dayLabel(d.date)}</b>
        <button type="button" className={`skychip ${d.sky}`} onClick={onSky} aria-expanded={open}
          aria-label={`Weather ${SKY_TEXT[d.sky]}, change it`}>
          <SkyIcon sky={d.sky} />{known ? SKY_TEXT[d.sky] : `${d.rain_chance}% wet`}
        </button>
        <span className="small muted">{d.tmin}…{d.tmax} °C{d.override ? " · your call" : d.source === "forecast" ? " · forecast" : ""}</span>
        {open && (
          <div className="skymenu" role="group" aria-label="What does the sky do?">
            {(["clear", "cloud", "rain", "wind"] as const).map((s) => <button key={s} type="button" className="fchip" aria-pressed={d.sky === s && d.override} onClick={() => onSet(s)}>{SKY_TEXT[s]}</button>)}
            {d.override && <button type="button" className="fchip" onClick={() => onSet(null)}>Back to the forecast</button>}
          </div>
        )}
      </div>
      <div className="bp-what">
        {d.things.map((t) => (
          <div key={t.id} className="bp-thing">
            <b>{t.name}</b>{t.hours && <span className="small muted"> · {t.hours}</span>}
            {t.note && <p className="small warnline">{t.note}</p>}
            {t.moved && <p className="small okline">Moved here for the weather</p>}
            {t.pinned && <p className="small muted">You chose this day</p>}
          </div>
        ))}
        {!d.things.length && <div className="bp-thing"><b>{d.title}</b>{d.note && <p className="small muted">{d.note}</p>}</div>}
        {d.kind === "route" && d.things.length === 0 ? null : null}
      </div>
    </li>
  );
}
