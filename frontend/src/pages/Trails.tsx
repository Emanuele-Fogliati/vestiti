import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { TrailCards } from "../components/TrailCards";
import { api } from "../lib/api";
import type { TrailCard, TrailDifficulty } from "../lib/types";

const REGION = (() => { try { return new Intl.DisplayNames(["en"], { type: "region" }); } catch { return null; } })();
const countryName = (c: string) => { try { return REGION?.of(c) ?? c; } catch { return c; } };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LEVELS: (TrailDifficulty | "")[] = ["", "easy", "moderate", "hard", "technical"];

/** Every trail we have written, by country: pick by how hard, how long and when you go. */
export default function Trails() {
  const [q, setQ] = useSearchParams();
  const country = q.get("country") ?? "";
  const month = Number(q.get("month")) || undefined;
  const level = (q.get("level") ?? "") as TrailDifficulty | "";
  const kind = q.get("kind") ?? "";
  const style = q.get("style") ?? "";
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
    && (!style || (t.style ?? "trek") === style)
    && (!find || [t.name, t.country, t.region, t.base].join(" ").toLowerCase().includes(find)))
    // in season first, then the ones with a drawing (the famous ones), then the rest
    .sort((a, b) => Number(b.in_season !== false) - Number(a.in_season !== false) || Number(!!b.art) - Number(!!a.art)
      || Number(b.tier === "A") - Number(a.tier === "A")), [all, level, kind, style, find]);
  // thousands of walks: show a page at a time, so the list opens fast and the drawings load
  const PAGE = 40;
  const [limit, setLimit] = useState(PAGE);
  useEffect(() => setLimit(PAGE), [all, level, kind, style, find]);

  // country codes as names, A to Z (the list holds every country we have walks for)
  const byName = useMemo(() => {
    const l = countries.map((c) => [c, countryName(c)] as const);
    if (country && !countries.includes(country)) l.push([country, countryName(country)]);
    return l.sort((a, b) => a[1].localeCompare(b[1]));
  }, [countries, country]);

  return (
    <main className="page"><div className="wrap trailsidx">
      <div className="page-head"><div><p className="kicker">Walks and treks</p><h1>Treks</h1></div></div>
      <p className="lede">The best walks of each country, trail by trail: where to start, how far and how high, when to turn back, and what to wear on it.</p>
      <div className="tfilters" role="group" aria-label="Filter the trails">
        <select aria-label="Country" value={country} onChange={(e) => set("country", e.target.value)}>
          <option value="">Every country</option>
          {byName.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
        </select>
        <select aria-label="How hard" value={level} onChange={(e) => set("level", e.target.value)}>
          {LEVELS.map((l) => <option key={l} value={l}>{l ? l[0].toUpperCase() + l.slice(1) : "Any difficulty"}</option>)}
        </select>
        <select aria-label="Treks or city walks" value={style} onChange={(e) => set("style", e.target.value)}>
          <option value="">All walks</option>
          <option value="trek">Treks</option>
          <option value="city">City walks</option>
        </select>
        <select aria-label="How long" value={kind} onChange={(e) => set("kind", e.target.value)}>
          <option value="">Any length</option>
          <option value="day">Day walks</option>
          <option value="multiday">Several days</option>
        </select>
        <select aria-label="When you go" value={month ?? ""} onChange={(e) => set("month", e.target.value)}>
          <option value="">Any month</option>
          {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
        </select>
      </div>
      {err && <p className="err">{err}</p>}
      {!all && !err && <div className="loading"><span className="spin" /></div>}
      {all && (shown.length ? <>
        <p className="small muted tcount">{shown.length.toLocaleString("en-US")} {shown.length === 1 ? "walk" : "walks"}</p>
        <TrailCards trails={shown.slice(0, limit)} query={month ? `?month=${month}` : ""} />
        {shown.length > limit && (
          <p className="tmore"><button type="button" className="btn" onClick={() => setLimit(limit + PAGE * 2)}>
            Show more ({(shown.length - limit).toLocaleString("en-US")} left)</button></p>
        )}
      </> : <p className="muted">No trail matches: try another filter.</p>)}
    </div></main>
  );
}
