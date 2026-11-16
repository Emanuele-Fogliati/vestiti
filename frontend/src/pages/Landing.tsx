import { Fragment, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { HomeGlobe } from "../components/Maps";
import { api } from "../lib/api";
import { monthRange } from "../lib/format";
import type { ItineraryCard, StopArt, TrailCard } from "../lib/types";
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
const SHOWN = 6;

type Door = "inspire" | "trek";
interface Row { to: string; art: StopArt | null; title: string; meta: string; later?: boolean }

/** Ready trips at their best this month first; if there are few, the others after them, marked as better another month. */
function inspireRows(all: ItineraryCard[], month: number): Row[] {
  const good = all.filter((it) => it.best_months.includes(month));
  const rest = good.length >= 3 ? [] : all.filter((it) => !it.best_months.includes(month));
  return [...good, ...rest].slice(0, SHOWN).map((it) => ({
    to: `/ideas/${it.slug}`, art: it.art, title: it.title, later: !it.best_months.includes(month),
    meta: `${it.days} days · best ${monthRange(it.best_months)}`,
  }));
}

/** Treks in season this month: famous ones with a drawing first, one country after another so the list is not all one country. */
function trekRows(all: TrailCard[]): Row[] {
  const score = (t: TrailCard) => (t.art ? 0 : 2) + (t.tier === "A" ? 0 : 1);
  const by = new Map<string, TrailCard[]>();
  for (const t of all.filter((t) => t.in_season !== false).sort((a, b) => score(a) - score(b))) by.set(t.country, [...(by.get(t.country) ?? []), t]);
  const lists = [...by.values()].sort((a, b) => score(a[0]) - score(b[0]) || b.length - a.length);
  const picked: TrailCard[] = [];
  for (let i = 0; picked.length < SHOWN && lists.some((l) => l[i]); i++) for (const l of lists) if (l[i] && picked.length < SHOWN) picked.push(l[i]);
  return picked.map((t) => ({
    to: `/trails/${encodeURIComponent(t.id)}`, art: t.art, title: t.name,
    meta: `${t.kind === "day" ? `${t.hours[0]}–${t.hours[1]} h` : `${t.days} days`} · ${t.difficulty} · ${t.base}`,
  }));
}

const PLANE = "M21 15.5l-8-4.5V5.5a1.5 1.5 0 0 0-3 0V11l-8 4.5V17l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-4.5l8 2.5z";
const PEAK = "M2 20L9 7l4 6 2.5-3.5L22 20z";
const ICON = {
  inspire: <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z" />,
  trek: <path d="M2 20L9 7l4 6 2.5-3.5L22 20z" />,
};

/** Home (design M10 "Notte chiara" + the doors of option A, Manu 2026-11-15): the map fills the screen on a light night sky;
 *  over it the line "Pick a place. We pack the bag.", Trip or Trek, one box (the door for who knows where they go), and
 *  under it two more doors for who does not: Inspire me (ready trips good this month) and Find a trek (the globe shows
 *  every trek, plus the treks good this month). They open a list here, not another page: no copy of the bar below.
 *  The first time per visit it opens with the universe and the Earth flying in. */
export default function Landing() {
  const nav = useNavigate();
  const [mode, setMode] = useState<"trip" | "trek">("trip");
  const [text, setText] = useState("");
  const [door, setDoor] = useState<Door | null>(null);
  const [rows, setRows] = useState<Row[] | null>(null);
  const month = new Date().getMonth() + 1;
  const [phase, setPhase] = useState<Phase>(() => (playIntro() ? "space" : "done"));
  const [ready, setReady] = useState(false);
  const [t0] = useState(() => performance.now());

  // the page is one screen: no scrolling, the top bar sits over the sky
  useEffect(() => {
    document.body.classList.add("home-page");
    return () => document.body.classList.remove("home-page", "home-intro");
  }, []);
  useEffect(() => { document.body.classList.toggle("home-intro", phase !== "done"); }, [phase]);

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

  const [diving, setDiving] = useState(false);
  function go(e: React.FormEvent) {
    e.preventDefault();
    const q = text.trim();
    const to = mode === "trip" ? (q ? `/start?q=${encodeURIComponent(q)}` : "/start") : (q ? `/trails?find=${encodeURIComponent(q)}` : "/trails");
    // the globe rushes at you, then the next page opens (prototype motion 5)
    if (reducedMotion()) { nav(to); return; }
    setDiving(true);
    window.setTimeout(() => nav(to), 650);
  }
  const asked = useRef(0); // only the last door opened fills the list
  function open(d: Door) {
    const n = ++asked.current;
    setDoor(d);
    setMode(d === "trek" ? "trek" : "trip"); // Find a trek: the globe shows every trek
    setRows(null);
    const load = d === "inspire"
      ? api.itineraries().then((all) => inspireRows(all, month))
      : api.trails({ month }).then((r) => trekRows(r.trails));
    load.then((r) => { if (asked.current === n) setRows(r); }).catch(() => { if (asked.current === n) setRows([]); });
  }
  function shut() { asked.current++; setDoor(null); setRows(null); }

  const skip = () => setPhase("done");
  const name = MONTHS[month - 1];

  return (
    <main className={`home2 ${phase}${diving ? " dive" : ""}${door ? " has-list" : ""}`} onPointerDown={phase !== "done" ? skip : undefined}>
      <div className="home2-space" aria-hidden="true" />
      <div className="home2-globe"><HomeGlobe bare mode={mode} intro={phase !== "done"} onReady={() => setReady(true)} /></div>
      <Link to="/trips" className="home2-bag" aria-label="My trips">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><rect x="5" y="7" width="14" height="13" rx="3" /><path d="M9 7V4h6v3" /></svg>
      </Link>
      <section className="home2-ui">
        <h1>Pick a place.<br /><span>We pack the bag.</span></h1>
        {!door && <>
          <div className="home2-tabs" role="tablist" aria-label="What are you planning?">
            {(["trip", "trek"] as const).map((m) => (
              <button key={m} type="button" role="tab" aria-selected={mode === m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d={m === "trip" ? PLANE : PEAK} /></svg>
                {m === "trip" ? "Trip" : "Hike"}
              </button>
            ))}
          </div>
          <form className="home2-search" onSubmit={go} role="search">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></svg>
            <input value={text} onChange={(e) => setText(e.target.value)} aria-label={mode === "trip" ? "Where do you go?" : "Which trail, or where?"}
              placeholder={mode === "trip" ? "Where to?" : "Which trail, or where?"} />
            <button type="submit" aria-label="Go">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
            </button>
          </form>
        </>}
        {door ? (
          <div className="doors-list" aria-live="polite">
            <div className="doors-head">
              <h2>{door === "inspire" ? `Ready trips for ${name}` : `Hikes good in ${name}`}</h2>
              <button type="button" className="doors-x" onClick={shut} aria-label="Back">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>
            </div>
            {door === "trek" && <p className="doors-note">Every hike is a dot on the globe: tap one.</p>}
            {rows === null ? <p className="loading"><span className="spin" /></p> : (
              <div className="doors-rows">
                {rows.map((r, i) => (<Fragment key={r.to}>
                  {r.later && !rows[i - 1]?.later && <p className="doors-note">Better in other months</p>}
                  <Link to={r.to} className="doors-row" style={{ "--i": i } as React.CSSProperties}>
                    <span className="pic">{r.art ? <Illustration art={r.art} /> : null}</span>
                    <span className="tx"><b>{r.title}</b><small>{r.meta}</small></span>
                  </Link>
                </Fragment>))}
                {!rows.length && <p className="doors-note">Nothing yet for {name}.</p>}
                <Link className="doors-all" to={door === "inspire" ? "/ideas" : `/trails?month=${month}`}>
                  {door === "inspire" ? "All ready trips" : "All hikes"} →
                </Link>
              </div>
            )}
          </div>
        ) : (
          <div className="doors" role="group" aria-label="Not sure yet?">
            <button type="button" className="door" onClick={() => open("inspire")}>
              <span className="ic"><svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">{ICON.inspire}</svg></span>
              <span><b>Inspire me</b><small>Ready trips for {name}</small></span>
            </button>
            <button type="button" className="door" onClick={() => open("trek")}>
              <span className="ic"><svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">{ICON.trek}</svg></span>
              <span><b>Find a hike</b><small>The best for {name}</small></span>
            </button>
          </div>
        )}
      </section>
      {phase !== "done" && <button type="button" className="home2-skip" onClick={skip}>Skip</button>}
    </main>
  );
}
