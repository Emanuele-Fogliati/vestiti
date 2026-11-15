import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ItineraryCards, useItineraries } from "../components/ItineraryCards";
import { HomeGlobe } from "../components/Maps";
import { TripStarter } from "../components/TripStarter";
import { MONTHS } from "../lib/format";
import type { GlobeFocus } from "../components/Globe";

export const DRESS_ME = "Dress me for this trip";

const LENGTHS: [string, (d: number) => boolean][] = [
  ["Any length", () => true], ["Up to 10 days", (d) => d <= 10], ["11–14 days", (d) => d > 10 && d <= 14], ["15+ days", (d) => d >= 15],
];

/** Your own trip: say it, type it, or list the stops (components/TripStarter). */
export function OwnTripForm({ compact }: { compact?: boolean }) {
  return <TripStarter compact={compact} />;
}

/** One place to start a trip: your own, or one of the recommended ones. */
export default function Start({ tab }: { tab: "own" | "ideas" }) {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const items = useItineraries();
  const [month, setMonth] = useState<number | null>(null);
  const [len, setLen] = useState(0);
  const lenOk = LENGTHS[len][1];
  const [focus, setFocus] = useState<GlobeFocus[]>([]);
  // computer: the page is one screen, the map on the left and the plan scrolling on its own on the right
  useEffect(() => {
    if (tab !== "own") return;
    document.body.classList.add("fit-page");
    return () => document.body.classList.remove("fit-page");
  }, [tab]);

  if (tab === "own") return (
    <main className="plan3">
      <div className="plan3-map"><HomeGlobe bare focus={focus} /></div>
      <section className="plan3-sheet">
        <div className="wrap stack">
          <TripStarter initial={params.get("q") ?? undefined}
            onStops={(s) => setFocus(s.map((x) => ({ lat: x.lat, lon: x.lon, name: x.name })))} />
          <h3 style={{ fontSize: 20, marginTop: 8 }}>Rather start from a ready trip?</h3>
          <ItineraryCards items={items} limit={3} />
          <Link className="btn" to="/ideas">All recommended trips</Link>
        </div>
      </section>
    </main>
  );

  return (
    <main className="page">
      <div className="wrap">
        {<div className="page-head">
          <div>
            <p className="kicker">Plan a trip</p>
            <h1>Recommended trips, day by day</h1>
            <p className="lede" style={{ marginTop: 12, maxWidth: "62ch" }}>
              Routes built from the places travellers visit most, with what is worth it and what to skip. Pick one, change anything you like, and we dress you for it.
            </p>
          </div>
        </div>}
        {<div className="doors" role="tablist" aria-label="How do you want to start?">
          <button type="button" role="tab" aria-selected={false} className="door" onClick={() => nav("/start")}>
            <b>I have a trip in mind</b><span>Say it or type it: a region, your stops, or just an idea</span>
          </button>
          <button type="button" role="tab" aria-selected className="door" onClick={() => nav("/ideas")}>
            <b>Inspire me</b><span>Start from a recommended trip and make it yours</span>
          </button>
        </div>}

        {(
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
