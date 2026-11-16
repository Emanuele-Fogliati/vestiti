import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { HomeGlobe } from "../components/Maps";
import { api } from "../lib/api";
import { monthRuns, regionBest } from "../lib/format";
import type { ItineraryCard } from "../lib/types";
import { reducedMotion } from "../lib/worldmap";

type Phase = "space" | "zoom" | "done";
const SEEN = "thruwear-intro-seen";
const SPACE_MIN_MS = 700; // the universe shows at least this long...
const SPACE_MAX_MS = 4000; // ...and if the globe is not drawn by then, the home just appears
const ZOOM_MS = 2600; // then the Earth flies in, spinning

function playIntro(): boolean {
  if (reducedMotion()) return false;
  try { return !sessionStorage.getItem(SEEN); } catch { return true; }
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const SHOWN = 5;

const norm = (x: string) => x.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const REGION = (() => { try { return new Intl.DisplayNames(["en"], { type: "region" }); } catch { return null; } })();
const countryName = (c: string) => { try { return REGION?.of(c) ?? c; } catch { return c; } };

interface Region { lead: ItineraryCard; routes: ItineraryCard[]; best: number[] }

/** The travel regions of Recommended, each with its routes and the months it is at its best. */
function regions(all: ItineraryCard[]): Region[] {
  return all.filter((it) => it.lead).map((lead) => {
    const routes = all.filter((x) => x.journey === lead.journey);
    return { lead, routes, best: regionBest(routes, 2) };
  });
}

/** Where a region opens: its two-week route for that month's season. */
function routeFor(r: Region, month: number): string {
  const two = r.routes.find((x) => x.weeks === 2 && x.months.includes(month));
  return two ? `/ideas/${two.slug}?month=${month}` : `/ideas/${r.lead.slug}`;
}

/** "Patagonia", "torres del paine", "japan", "kyoto": the regions whose name, countries or stops match. */
function matches(rs: Region[], q: string): Region[] {
  const w = norm(q).trim();
  if (w.length < 2) return [];
  const hay = (r: Region) => norm([r.lead.destination ?? "", r.lead.title, ...r.lead.countries.map(countryName),
    ...r.routes.flatMap((x) => x.places)].join(" | "));
  const named = (r: Region) => norm(r.lead.destination ?? r.lead.title).includes(w);
  return rs.filter((r) => hay(r).includes(w)).sort((a, b) => Number(named(b)) - Number(named(a)));
}

/** Home (Manu 2026-11-16, option A "Explore utile, menu più corto"): the globe and "Pick a place. We pack the
 *  bag.", one box that goes straight to the recommended trip of the place you type (Patagonia, Japan, Cusco...),
 *  and a month: the globe lights up where it is good to go then, and those trips are listed under it.
 *  Explore is not in the top menu any more: the logo comes back here. The first time per visit it opens with the
 *  universe and the Earth flying in. */
export default function Landing() {
  const nav = useNavigate();
  const [text, setText] = useState("");
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [all, setAll] = useState<Region[] | null>(null);
  const [hi, setHi] = useState(0);
  const [phase, setPhase] = useState<Phase>(() => (playIntro() ? "space" : "done"));
  const [ready, setReady] = useState(false);
  const [t0] = useState(() => performance.now());

  // the page is one screen: no scrolling, the top bar sits over the sky
  useEffect(() => {
    document.body.classList.add("home-page");
    return () => document.body.classList.remove("home-page", "home-intro");
  }, []);
  useEffect(() => { document.body.classList.toggle("home-intro", phase !== "done"); }, [phase]);
  useEffect(() => { api.itineraries().then((x) => setAll(regions(x))).catch(() => setAll([])); }, []);

  // universe -> (globe ready, or too slow) -> the Earth flies in -> the home
  useEffect(() => {
    if (phase === "space") {
      // the Earth flies in only once it is drawn: never an empty disc
      const wait = ready ? SPACE_MIN_MS - (performance.now() - t0) : SPACE_MAX_MS - (performance.now() - t0);
      const t = window.setTimeout(() => setPhase(ready ? "zoom" : "done"), Math.max(0, wait));
      return () => window.clearTimeout(t);
    }
    if (phase === "zoom") {
      const t = window.setTimeout(() => setPhase("done"), ZOOM_MS);
      return () => window.clearTimeout(t);
    }
    try { sessionStorage.setItem(SEEN, "1"); } catch { /* private mode: it plays again next time */ }
  }, [phase, ready, t0]);

  const found = useMemo(() => (all ? matches(all, text).slice(0, 4) : []), [all, text]);
  useEffect(() => setHi(0), [text]);
  const good = useMemo(() => (all ?? []).filter((r) => r.best.includes(month)), [all, month]);
  const glow = useMemo(() => good.flatMap((r) => r.lead.points ?? []), [good]);

  const [diving, setDiving] = useState(false);
  function goTo(to: string) {
    // the globe rushes at you, then the next page opens (prototype motion 5)
    if (reducedMotion()) { nav(to); return; }
    setDiving(true);
    window.setTimeout(() => nav(to), 650);
  }
  function go(e: React.FormEvent) {
    e.preventDefault();
    const q = text.trim();
    if (!q) return;
    // a place we have a trip for: that trip; anywhere else: a new trip starting there
    goTo(found.length ? routeFor(found[Math.min(hi, found.length - 1)], month) : `/trips/new?q=${encodeURIComponent(q)}`);
  }
  const keys = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(h + 1, Math.max(0, found.length - 1))); }
    if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(0, h - 1)); }
  };

  const skip = () => setPhase("done");
  const q = text.trim();

  return (
    <main className={`home2 ${phase}${diving ? " dive" : ""}`} onPointerDown={phase !== "done" ? skip : undefined}>
      <div className="home2-space" aria-hidden="true" />
      <div className="home2-globe"><HomeGlobe bare mode="trip" intro={phase !== "done"} onReady={() => setReady(true)} glow={glow} /></div>
      <Link to="/trips?tab=saved" className="home2-bag" aria-label="My trips">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><rect x="5" y="7" width="14" height="13" rx="3" /><path d="M9 7V4h6v3" /></svg>
      </Link>
      <section className="home2-ui">
        <h1>Pick a place.<br /><span>We pack the bag.</span></h1>
        <form className="home2-search" onSubmit={go} role="search">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></svg>
          <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={keys} aria-label="Where to?" placeholder="Where to?"
            role="combobox" aria-expanded={!!q} aria-controls="home2-sugg" autoComplete="off" />
          <button type="submit" aria-label="Go">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
          </button>
          {q.length >= 2 && all && (
            <div className="home2-sugg" id="home2-sugg" role="listbox">
              {found.map((r, i) => (
                <Link key={r.lead.slug} to={routeFor(r, month)} role="option" aria-selected={i === hi} className={`doors-row${i === hi ? " on" : ""}`}>
                  <span className="pic">{r.lead.art ? <Illustration art={r.lead.art} /> : null}</span>
                  <span className="tx"><b>{r.lead.destination ?? r.lead.title}</b><small>{r.best.includes(month) ? `good in ${MONTHS[month - 1]}` : `best ${monthRuns(r.best)}`}</small></span>
                </Link>
              ))}
              <Link to={`/trips/new?q=${encodeURIComponent(q)}`} className="home2-own">+ My own trip to {q}</Link>
            </div>
          )}
        </form>
        <div className="home2-month" role="group" aria-label="When">
          <button type="button" aria-label="Previous month" onClick={() => setMonth(month === 1 ? 12 : month - 1)}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg></button>
          <b>Good in {MONTHS[month - 1]}</b>
          <button type="button" aria-label="Next month" onClick={() => setMonth(month === 12 ? 1 : month + 1)}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg></button>
        </div>
        <div className="doors-rows home2-good" aria-live="polite">
          {all === null ? <p className="loading"><span className="spin" /></p> : good.slice(0, SHOWN).map((r, i) => (
            <Link key={r.lead.slug} to={routeFor(r, month)} className="doors-row" style={{ "--i": i } as React.CSSProperties}>
              <span className="pic">{r.lead.art ? <Illustration art={r.lead.art} /> : null}</span>
              <span className="tx"><b>{r.lead.destination ?? r.lead.title}</b><small>{(() => { const c = r.lead.countries.map(countryName).join(" · "); return c === (r.lead.destination ?? "") ? `best ${monthRuns(r.best)}` : c; })()}</small></span>
            </Link>
          ))}
          {all && !good.length && <p className="doors-note">No trip at its best in {MONTHS[month - 1]}.</p>}
          {good.length > SHOWN && <Link className="doors-all" to="/trips?tab=recommended">All {good.length} →</Link>}
        </div>
      </section>
      {phase !== "done" && <button type="button" className="home2-skip" onClick={skip}>Skip</button>}
    </main>
  );
}
