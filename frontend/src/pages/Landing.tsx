import { Link } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { ItineraryCards } from "../components/ItineraryCards";
import { HomeGlobe } from "../components/Maps";
import { brandName, useApp } from "../lib/app-context";
import { OwnTripForm } from "./Start";
import { useReveal } from "../lib/reveal";

export default function Landing() {
  const { config } = useApp();
  const name = brandName(config);
  useReveal();

  return (
    <main>
      <HomeGlobe />
      <section className="hero">
        <div className="wrap hero-in">
          <div>
            <p className="kicker">Free travel outfit planner</p>
            <h1>Every stop. <span className="hl">One bag.</span></h1>
            <p className="lede">
              Say where you're going. We read the weather at every stop and dress you for all of it, at three budgets.
            </p>
            <div className="facts">
              <div className="fact"><b>0 €</b><span>For you, always</span></div>
              <div className="fact"><b>3</b><span>Budgets: cheap, medium, premium</span></div>
              <div className="fact"><b>Per day</b><span>Weather, altitude and wind</span></div>
            </div>
          </div>
          <div className="stack" style={{ gap: 12 }}>
            <OwnTripForm compact />
            <Link className="btn ghost hero-alt" to="/ideas">No trip yet? Start from a recommended one →</Link>
          </div>
        </div>
      </section>

      <section className="band">
        <div className="wrap">
          <header className="sh"><p className="sh-k">No trip yet?</p><h2>Start from a recommended trip</h2></header>
          <ItineraryCards />
          <p style={{ marginTop: 20 }}><Link className="btn" to="/ideas">All recommended trips</Link></p>
        </div>
      </section>

      <section className="band alt">
        <div className="wrap">
          <header className="sh"><p className="sh-k">How it works</p><h2>Weather in, layers out</h2></header>
          <ol className="x-steps">
            {[
              { t: "alpine" as const, h: "Your trip", p: "Places, days, what you'll do." },
              { t: "glacier" as const, h: "Weather at each stop", p: "Colder and windier with altitude." },
              { t: "hills" as const, h: "Your layers", p: "What you wear, what stays in the bag." },
              { t: "coast" as const, h: "Your bag", p: "Three budgets. What you own comes first." },
            ].map((s, i) => (
              <li key={i} className="x-reveal" style={{ transitionDelay: `${i * 90}ms` }}>
                <Illustration terrain={s.t} />
                <b><span>{i + 1}</span>{s.h}</b>
                <p>{s.p}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="band">
        <div className="wrap">
          <header className="sh"><p className="sh-k">Honest by design</p><h2>If what you own is fine, we say so</h2>
            <p>{name} is free. A shop link may earn us a commission, but it never picks your clothes.</p></header>
          <div className="row">
            <Link className="btn primary" to="/start">Plan a trip</Link>
            <Link className="btn" to="/how-it-works">How we calculate warmth</Link>
          </div>
        </div>
      </section>
    </main>
  );
}
