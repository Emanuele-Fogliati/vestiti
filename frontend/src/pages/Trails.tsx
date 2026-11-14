import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { TrailCards } from "../components/TrailCards";
import { api } from "../lib/api";
import type { TrailCard, TrailDifficulty } from "../lib/types";

const COUNTRY: Record<string, string> = { IT: "Italy", AR: "Argentina", CL: "Chile", PE: "Peru", IS: "Iceland" };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LEVELS: (TrailDifficulty | "")[] = ["", "easy", "moderate", "hard", "technical"];

/** Every trail we have written, by country: pick by how hard, how long and when you go. */
export default function Trails() {
  const [q, setQ] = useSearchParams();
  const country = q.get("country") ?? "";
  const month = Number(q.get("month")) || undefined;
  const level = (q.get("level") ?? "") as TrailDifficulty | "";
  const kind = q.get("kind") ?? "";
  const find = (q.get("find") ?? "").trim().toLowerCase(); // words typed on the home page
  const [all, setAll] = useState<TrailCard[] | null>(null);
  const [countries, setCountries] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setAll(null);
    api.trails({ country: country || undefined, month }).then((r) => { setAll(r.trails); setCountries(r.countries); })
      .catch((e) => setErr((e as Error).message));
  }, [country, month]);

  const set = (k: string, v: string) => { const n = new URLSearchParams(q); if (v) n.set(k, v); else n.delete(k); setQ(n, { replace: true }); };
  const shown = useMemo(() => (all ?? []).filter((t) => (!level || t.difficulty === level) && (!kind || t.kind === kind)
    && (!find || [t.name, t.country, t.region, t.base].join(" ").toLowerCase().includes(find)))
    .sort((a, b) => Number(b.in_season !== false) - Number(a.in_season !== false)), [all, level, kind]);

  return (
    <div className="wrap section trailsidx">
      <h1>Trekking</h1>
      <p className="lede">The best walks of each country, trail by trail: where to start, how far and how high, when to turn back, and what to wear on it.</p>
      <div className="tfilters" role="group" aria-label="Filter the trails">
        <div className="seg" role="group" aria-label="Country">
          <button type="button" aria-pressed={!country} onClick={() => set("country", "")}>All</button>
          {countries.map((c) => <button key={c} type="button" aria-pressed={country === c} onClick={() => set("country", c)}>{COUNTRY[c] ?? c}</button>)}
        </div>
        <select aria-label="How hard" value={level} onChange={(e) => set("level", e.target.value)}>
          {LEVELS.map((l) => <option key={l} value={l}>{l ? l[0].toUpperCase() + l.slice(1) : "Any difficulty"}</option>)}
        </select>
        <select aria-label="How long" value={kind} onChange={(e) => set("kind", e.target.value)}>
          <option value="">Day walks and treks</option>
          <option value="day">Day walks</option>
          <option value="multiday">Treks of several days</option>
        </select>
        <select aria-label="When you go" value={month ?? ""} onChange={(e) => set("month", e.target.value)}>
          <option value="">Any month</option>
          {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
        </select>
      </div>
      {err && <p className="err">{err}</p>}
      {!all && !err && <div className="loading"><span className="spin" /></div>}
      {all && (shown.length ? <TrailCards trails={shown} query={month ? `?month=${month}` : ""} /> : <p className="muted">No trail matches: try another filter.</p>)}
    </div>
  );
}
