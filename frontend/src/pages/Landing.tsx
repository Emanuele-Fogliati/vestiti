import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { ItineraryCards } from "../components/ItineraryCards";
import { brandName, useApp } from "../lib/app-context";

const EXAMPLE =
  "From 6 May 2027: 4 days hard hiking in El Chaltén up to 1200 m, then 2 days in El Calafate, then 4 days trekking Torres del Paine, then 2 days in Ushuaia";

export default function Landing() {
  const { config } = useApp();
  const nav = useNavigate();
  const [text, setText] = useState("");
  const name = brandName(config);

  function go(e: React.FormEvent) {
    e.preventDefault();
    nav("/trips/new", { state: { text: text.trim() || EXAMPLE } });
  }

  return (
    <main>
      <section className="hero">
        <div className="wrap hero-in">
          <div>
            <p className="kicker">Free travel outfit planner</p>
            <h1>Every stop. <span className="hl">One bag.</span></h1>
            <p className="lede">
              Tell us where you're going. We read the weather at every stop, work out the layers that cover all of
              it, and show the exact pieces at three budgets. Anything you already own comes off the bill, and we say
              so when it's good enough.
            </p>
            <div className="facts">
              <div className="fact"><b>0 €</b><span>For you, always</span></div>
              <div className="fact"><b>3</b><span>Budgets: cheap, medium, premium</span></div>
              <div className="fact"><b>Per day</b><span>Weather, altitude and wind</span></div>
            </div>
          </div>
          <form className="brief" onSubmit={go} aria-label="Describe your trip">
            <div className="row"><h2>Your trip</h2><span className="spacer" /><span className="label">Plain words are fine</span></div>
            <div className="field">
              <label htmlFor="trip-text">Where, when, what you'll do</label>
              <textarea id="trip-text" value={text} maxLength={50_000} onChange={(e) => setText(e.target.value)} placeholder={EXAMPLE} rows={5} />
            </div>
            <p className="small muted">Not sure what you'll do somewhere? Write "don't know yet" and we cover both easy and technical days.</p>
            <button className="btn primary" type="submit">Dress this trip</button>
            <Link className="btn" to="/trips/new">Or add stops one by one</Link>
            <p className="small muted">No trip yet? <Link to="/ideas">Browse ready-made itineraries</Link> and we pack your bag for one.</p>
          </form>
        </div>
      </section>

      <section className="band">
        <div className="wrap">
          <header className="sh"><p className="sh-k">Looking for ideas?</p><h2>Pick a trip, we pack the bag</h2>
            <p>Day-by-day routes built from the places organised trips visit most, with what is worth it and what to skip at every stop.</p></header>
          <ItineraryCards />
          <p style={{ marginTop: 20 }}><Link className="btn" to="/ideas">All itineraries</Link></p>
        </div>
      </section>

      <section className="band alt">
        <div className="wrap">
          <header className="sh"><p className="sh-k">How it works</p><h2>Weather in, layers out</h2>
            <p>No guessing from a seasonal average for the whole country. Each stop gets its own days, its own altitude and its own wind.</p></header>
          <ol className="stops">
            {[
              { t: "alpine" as const, h: "1 · Your itinerary", p: "Dates, stops and what you'll do: city days, a hard hike to 2,600 m, a beach. Edit it any time." },
              { t: "glacier" as const, h: "2 · The weather at each stop", p: "Forecast when the dates are close, climate averages of the last years when they're far. Colder and windier with altitude." },
              { t: "hills" as const, h: "3 · The layer strategy", p: "What you wear moving, what goes on at stops, what stays in the pack. Each choice has a reason you can click." },
              { t: "coast" as const, h: "4 · The kit, three budgets", p: "Products checked against the spec, rated for fit, priced in total. Your own clothes come first." },
            ].map((s, i) => (
              <li className="stop" key={i} style={{ cursor: "default" }}>
                <div className="days">Step <b>0{i + 1}</b></div>
                <Illustration terrain={s.t} />
                <div className="info"><h3>{s.h}</h3><p className="act">{s.p}</p></div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="band">
        <div className="wrap">
          <header className="sh"><p className="sh-k">Honest by design</p><h2>If what you own is fine, we say so</h2>
            <p>{name} is free and earns a commission only when you buy through a link. That never decides the plan: owned items are used first, and a cheaper pick that passes beats an expensive one that doesn't.</p></header>
          <div className="row">
            <Link className="btn primary" to="/trips/new">Plan a trip</Link>
            <Link className="btn" to="/how-it-works">How we calculate warmth</Link>
          </div>
        </div>
      </section>
    </main>
  );
}
