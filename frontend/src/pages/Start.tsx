import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ItineraryCards, useItineraries } from "../components/ItineraryCards";
import { PlaceSearch } from "../components/PlaceSearch";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { addDays, MONTHS, today } from "../lib/format";
import type { Place } from "../lib/types";

export const DRESS_ME = "Dress me for this trip";

const LENGTHS: [string, (d: number) => boolean][] = [
  ["Any length", () => true], ["Up to 10 days", (d) => d <= 10], ["11–14 days", (d) => d > 10 && d <= 14], ["15+ days", (d) => d >= 15],
];

/** Your own trip, the way people actually plan one: first where and when, the rest later on the
 * trip's board (Manu, 2026-11-12: a text box to fill in was the wrong first step). */
export function OwnTripForm({ compact }: { compact?: boolean }) {
  const nav = useNavigate();
  const { ensureUser } = useApp();
  const [place, setPlace] = useState<Place | null>(null);
  const [start, setStart] = useState("");
  const [days, setDays] = useState(3);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function go(e: React.FormEvent) {
    e.preventDefault();
    if (!place) { setErr("Pick your first place from the list."); return; }
    setBusy(true); setErr(null);
    try {
      await ensureUser();
      const first = start || addDays(today(), 60);
      const t = await api.createTrip(place.name, [{
        name: place.name, country_code: place.country_code ?? null, latitude: place.latitude, longitude: place.longitude,
        elevation_m: place.elevation_m ?? 0, start_date: first, end_date: addDays(first, days - 1),
        activities: [{ type: "unknown" }], notes: null, visits: [], status: "flex",
      }], !start, place.country_code ? [place.country_code] : []);
      nav(`/trips/${t.id}#days`);
    } catch (e2) { setErr((e2 as Error).message); } finally { setBusy(false); }
  }

  return (
    <form className="brief quick" onSubmit={go} aria-label="Start your trip">
      {!compact && <div className="row"><h2>Your trip</h2><span className="spacer" /><span className="label">Flights and beds later</span></div>}
      <div className="qrow">
        <div className="field"><label htmlFor="q-place">Where do you start?</label>
          <PlaceSearch id="q-place" value={place} onPick={setPlace} /></div>
        <div className="field"><label htmlFor="q-start">From (if you know)</label>
          <input id="q-start" type="date" value={start} min={today()} onChange={(e) => setStart(e.target.value)} /></div>
        <div className="field"><label htmlFor="q-days">Days there</label>
          <input id="q-days" type="number" min={1} max={60} value={days} onChange={(e) => setDays(Math.max(1, Math.min(60, Number(e.target.value) || 1)))} /></div>
      </div>
      <p className="small muted">Then add the next places on your trip's days, mark what you book as fixed, and see what to do in each place day by day.</p>
      {err && <p className="err">{err}</p>}
      <button className="btn primary big" type="submit" disabled={busy}>{busy ? <span className="spin" /> : "Start my trip"}</button>
      <Link className="btn" to="/trips/new">Already have a plan? Paste it</Link>
    </form>
  );
}

/** One place to start a trip: your own, or one of the recommended ones. */
export default function Start({ tab }: { tab: "own" | "ideas" }) {
  const nav = useNavigate();
  const items = useItineraries();
  const [month, setMonth] = useState<number | null>(null);
  const [len, setLen] = useState(0);
  const lenOk = LENGTHS[len][1];

  return (
    <main className="page">
      <div className="wrap">
        <div className="page-head">
          <div>
            <p className="kicker">Plan a trip</p>
            <h1>{tab === "own" ? "Where are you going?" : "Recommended trips, day by day"}</h1>
            <p className="lede" style={{ marginTop: 12, maxWidth: "62ch" }}>
              {tab === "own"
                ? "Start with the first place. Then lay the trip out on its days: what is booked stays put, the rest can move, and each place shows what to do there with the weather."
                : "Routes built from the places travellers visit most, with what is worth it and what to skip. Pick one, change anything you like, and we dress you for it."}
            </p>
          </div>
        </div>
        <div className="doors" role="tablist" aria-label="How do you want to start?">
          <button type="button" role="tab" aria-selected={tab === "own"} className="door" onClick={() => nav("/start")}>
            <b>I have a trip in mind</b><span>Pick the places and the days, the rest comes later</span>
          </button>
          <button type="button" role="tab" aria-selected={tab === "ideas"} className="door" onClick={() => nav("/ideas")}>
            <b>Inspire me</b><span>Start from a recommended trip and make it yours</span>
          </button>
        </div>

        {tab === "own" ? (
          <div className="cols" style={{ marginTop: 24 }}>
            <OwnTripForm />
            <aside className="stack">
              <h3 style={{ fontSize: 18 }}>No route yet?</h3>
              <p className="small muted">These are ready to go. Open one to see it day by day.</p>
              <ItineraryCards items={items} limit={2} />
              <Link className="btn" to="/ideas">All recommended trips</Link>
            </aside>
          </div>
        ) : (
          <div style={{ marginTop: 24 }}>
            <div className="filters" aria-label="Filter the recommended trips">
              <div className="chips" role="group" aria-label="When do you travel?">
                <span className="label">When</span>
                <button type="button" className="fchip" aria-pressed={month === null} onClick={() => setMonth(null)}>Any time</button>
                {MONTHS.map((m, i) => (
                  <button type="button" key={m} className="fchip" aria-pressed={month === i + 1} onClick={() => setMonth(i + 1)}>{m}</button>
                ))}
              </div>
              <div className="chips" role="group" aria-label="How long?">
                <span className="label">Length</span>
                {LENGTHS.map(([l], i) => (
                  <button type="button" key={l} className="fchip" aria-pressed={len === i} onClick={() => setLen(i)}>{l}</button>
                ))}
              </div>
            </div>
            <ItineraryCards items={items}
              filter={(it) => (month === null || it.best_months.includes(month)) && lenOk(it.days)}
              empty={<div className="empty"><p>No recommended trip fits {month ? `${MONTHS[month - 1]} ` : ""}{len ? `and ${LENGTHS[len][0].toLowerCase()}` : ""} yet.</p>
                <p style={{ marginTop: 12 }}><button type="button" className="btn" onClick={() => { setMonth(null); setLen(0); }}>Show all</button>{" "}
                  <Link className="btn primary" to="/start">Plan my own trip</Link></p></div>} />
            <p className="small muted" style={{ marginTop: 16 }}>Best months are when the weather on that route is at its most reliable. You can still go in other months: we dress you for the weather of your dates.</p>
          </div>
        )}
      </div>
    </main>
  );
}
