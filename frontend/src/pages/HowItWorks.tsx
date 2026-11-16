import { Link } from "react-router-dom";
import { brandName, useApp } from "../lib/app-context";

export default function HowItWorks() {
  const { config } = useApp();
  const name = brandName(config);
  return (
    <main className="page how-mf">
      <div className="how-grid">
        <header className="how-head">
          <p className="kicker">Method</p>
          <h1>How {name} decides what you wear</h1>
          <div className="mf-warn">
            Everything here is an <b>estimate</b>. The warmth model is a simplified heat balance, not a lab test, and it has not been
            validated on real trips yet. Use it to compare options, not as a safety guarantee in the mountains.
          </div>
          <p className="mf-k">{config?.disclosure ?? "The app is free. Shop links may earn a commission."} <Link to="/legal/affiliate">Read the disclosure</Link>.</p>
        </header>
        {/* three steps, the maths folded away (flow audit, Manu 2026-11-16: fewer words) */}
        <div className="how-cards">
          <ol className="how-steps">
            <li className="how-card"><span className="how-n">1</span><h2>Pick a place</h2>
              <p>A recommended trip, a walk, or your own stops on the map.</p></li>
            <li className="how-card"><span className="how-n">2</span><h2>We read the weather</h2>
              <p>Every stop, every day: cold, wind, rain and altitude. The coldest hour sets the bag.</p></li>
            <li className="how-card"><span className="how-n">3</span><h2>One bag for the trip</h2>
              <p>The lightest layers that keep you warm everywhere. What you own first, then what to get.</p></li>
          </ol>
          <details className="how-card how-more">
            <summary>The details</summary>
            <h3>Weather and climate</h3>
            <p>Up to about two weeks out we use the forecast; further out, the climate of the same days over the last five years.
              Temperatures are corrected for altitude (−6.5 °C per 1000 m). Data: Open-Meteo.</p>
            <h3>How much warmth you need</h3>
            <p>For every stop we compute the insulation (in clo: 1 clo is roughly a business suit) that keeps you comfortable while
              moving and while stopped, from temperature, wind, how hard you work and whether you run cold. Layers add up with a
              standard formula (0.835 × sum + 0.16); no windproof layer costs about 15% of your warmth, no waterproof one about 30%.</p>
            <h3>Products and your own clothes</h3>
            <p>Every product gets 1 to 5 stars for the job; one that fails a hard need (water-resistant where you need waterproof)
              gets at most 2. Your own clothes are used first, at zero cost. The shop's price is the one that counts.</p>
            <h3>Where AI is used</h3>
            <p>The plan is computed by fixed rules, the same every time. A local AI model only reads your clothes from photos and
              answers questions about a plan. If it is off, everything still works.</p>
          </details>
        </div>
      </div>
    </main>
  );
}
