import { Link } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { ItineraryCards } from "../components/ItineraryCards";
import { brandName, useApp } from "../lib/app-context";
import { DRESS_ME, OwnTripForm } from "./Start";

export default function Landing() {
  const { config } = useApp();
  const name = brandName(config);

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
          <div className="stack" style={{ gap: 12 }}>
            <OwnTripForm />
            <Link className="btn ghost hero-alt" to="/ideas">No trip yet? Start from a recommended one →</Link>
          </div>
        </div>
      </section>

      <section className="band">
        <div className="wrap">
          <header className="sh"><p className="sh-k">No trip yet?</p><h2>Start from a recommended trip</h2>
            <p>Day-by-day routes built from the places organised trips visit most, with what each place is, a fun fact, and what is worth it or not at every stop. Change anything, then tap “{DRESS_ME}”.</p></header>
          <ItineraryCards />
          <p style={{ marginTop: 20 }}><Link className="btn" to="/ideas">All recommended trips</Link></p>
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
            <Link className="btn primary" to="/start">Plan a trip</Link>
            <Link className="btn" to="/how-it-works">How we calculate warmth</Link>
          </div>
        </div>
      </section>
    </main>
  );
}
