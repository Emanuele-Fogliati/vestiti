import { Link } from "react-router-dom";
import { brandName, useApp } from "../lib/app-context";

export default function HowItWorks() {
  const { config } = useApp();
  const name = brandName(config);
  return (
    <main className="page">
      <div className="wrap prose" style={{ maxWidth: 760 }}>
        <p className="kicker">Method</p>
        <h1 style={{ fontSize: 44, marginBottom: 20 }}>How {name} decides what you wear</h1>
        <div className="banner warn" style={{ marginBottom: 24 }}>
          Everything below is an <b>estimate</b>. The warmth model is a simplified heat balance, not a lab test, and it has not been
          validated on real trips yet. Use it to compare options, not as a safety guarantee in the mountains.
        </div>

        <h2>1. Your trip, stage by stage</h2>
        <p>Each stop has dates, an elevation and activities. If you don't know how hard a day will be, pick "don't know yet":
          we plan for both the easy and the hard version, so the kit covers both.</p>

        <h2>2. Weather and climate</h2>
        <p>Up to about two weeks out we use the forecast. Further out we use the climate of the same days over the last five years
          (average, cold nights, how often it rains). Past dates use observed weather. Temperatures are corrected for altitude
          (−6.5 °C per 1000 m) and wind gets stronger with height. Data: Open-Meteo.</p>

        <h2>3. How much insulation you need (clo)</h2>
        <p>"Clo" is the standard unit of clothing insulation: 1 clo is roughly a business suit. For every stage we compute how much
          clo keeps you comfortable, both while moving and while stopped, from:</p>
        <ul>
          <li>air temperature and wind (the faster the air, the thinner the still-air layer around you),</li>
          <li>how hard you work (city walk, easy hike, technical climb...),</li>
          <li>short stops (a 10-minute break is not a night outside),</li>
          <li>your profile: "I run cold / warm" shifts everything by up to ±0.3 clo.</li>
        </ul>
        <p>Then we add up your layers. Layers don't simply sum: we use a standard ensemble formula (0.835 × sum + 0.16).
          Without a windproof layer wind costs about 15% of your warmth; without a waterproof layer rain costs about 30%,
          and wet down loses about 45%.</p>

        <h2>4. The layer strategy</h2>
        <p>For each layer slot (shell, insulation, fleece, base layer, legs, head, hands, feet) we decide whether it is worn,
          carried in the pack for stops, or not needed. The rule is: the lightest kit that closes the gap. Hats and gloves only
          show up when it's actually cold (feels like 10 °C or less).</p>
        <p>Click any "why" in the plan to see the numbers behind a decision. If the kit is short, we show the cheapest single
          upgrade that fixes it.</p>

        <h2>5. Products, tiers and your own clothes</h2>
        <p>Every product gets 1 to 5 stars for how well it fits the job: warmth, waterproofing, weight, ankle support.
          A product that fails a hard requirement (e.g. a "water-resistant" jacket where you need a waterproof one) gets at most
          2 stars. Your wardrobe is used first, at zero cost, in all three tiers, and we say so when what you own is fine.</p>
        <p>Product specs from shop feeds are partly extracted automatically and marked as estimates. Prices change: the shop's
          price is the one that counts.</p>

        <h2>6. Where AI is used, and where it isn't</h2>
        <p>The plan itself (warmth, layers, products, prices) is computed by fixed rules, the same every time. A local AI model is
          only used to read a trip you describe in your own words, to explain a plan in plain language and to answer questions.
          If the AI is off, everything still works.</p>

        <h2>7. Money</h2>
        <p>{config?.disclosure ?? "The app is free. Shop links may earn a commission."} <Link to="/legal/affiliate">Read the disclosure</Link>.</p>
      </div>
    </main>
  );
}
