import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ItineraryCards, useItineraries } from "../components/ItineraryCards";
import { MONTHS } from "../lib/format";

export const DRESS_ME = "Dress me for this trip";

const LENGTHS: [string, (d: number) => boolean][] = [
  ["Any length", () => true], ["Up to 10 days", (d) => d <= 10], ["11–14 days", (d) => d > 10 && d <= 14], ["15+ days", (d) => d >= 15],
];

const EXAMPLE = "From 12 June 2027: 3 days in Reykjavik, then 4 days hard trekking in Landmannalaugar up to 1100 m, then 2 days in Vík";

/** Your own trip: describe it, we read it and dress it. */
export function OwnTripForm({ compact }: { compact?: boolean }) {
  const nav = useNavigate();
  const [text, setText] = useState("");
  function go(e: React.FormEvent) {
    e.preventDefault();
    nav("/trips/new", { state: { text: text.trim() || EXAMPLE } });
  }
  return (
    <form className="brief" onSubmit={go} aria-label="Describe your trip">
      {!compact && <div className="row"><h2>Your trip</h2><span className="spacer" /><span className="label">Plain words are fine</span></div>}
      <div className="field">
        <label htmlFor="trip-text">Where, when, what you'll do</label>
        <textarea id="trip-text" value={text} maxLength={50_000} onChange={(e) => setText(e.target.value)} placeholder={EXAMPLE} rows={5} />
      </div>
      <p className="small muted">Not sure what you'll do somewhere? Write "don't know yet" and we cover both easy and technical days. Or paste your agency's day-by-day program.</p>
      <button className="btn primary big" type="submit">{DRESS_ME}</button>
      <Link className="btn" to="/trips/new">Or add stops one by one</Link>
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
                ? "Tell us your route in your own words. We read the weather at every stop and dress you for all of it, at three budgets."
                : "Routes built from the places travellers visit most, with what is worth it and what to skip. Pick one, change anything you like, and we dress you for it."}
            </p>
          </div>
        </div>
        <div className="doors" role="tablist" aria-label="How do you want to start?">
          <button type="button" role="tab" aria-selected={tab === "own"} className="door" onClick={() => nav("/start")}>
            <b>I have a trip in mind</b><span>Write it, paste it or add stops one by one</span>
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
