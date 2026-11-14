import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { HomeGlobe } from "../components/Maps";
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

const PLANE = "M21 15.5l-8-4.5V5.5a1.5 1.5 0 0 0-3 0V11l-8 4.5V17l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-4.5l8 2.5z";
const PEAK = "M2 20L9 7l4 6 2.5-3.5L22 20z";

/** Home (design M10 "Notte chiara"): the globe on a light night sky, one question, Trip or Trek,
 *  one box. The first time per visit it opens with the universe and the Earth flying in. */
export default function Landing() {
  const nav = useNavigate();
  const [mode, setMode] = useState<"trip" | "trek">("trip");
  const [text, setText] = useState("");
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

  function go(e: React.FormEvent) {
    e.preventDefault();
    const q = text.trim();
    if (mode === "trip") nav(q ? `/start?q=${encodeURIComponent(q)}` : "/start");
    else nav(q ? `/trails?find=${encodeURIComponent(q)}` : "/trails");
  }

  const skip = () => setPhase("done");

  return (
    <main className={`home2 ${phase}`} onPointerDown={phase !== "done" ? skip : undefined}>
      <div className="home2-space" aria-hidden="true" />
      <div className="home2-globe"><HomeGlobe bare intro={phase !== "done"} onReady={() => setReady(true)} /></div>
      <Link to="/trips" className="home2-bag" aria-label="My trips">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><rect x="5" y="7" width="14" height="13" rx="3" /><path d="M9 7V4h6v3" /></svg>
      </Link>
      <section className="home2-ui">
        <h1>Where to?</h1>
        <div className="home2-tabs" role="tablist" aria-label="What are you planning?">
          {(["trip", "trek"] as const).map((m) => (
            <button key={m} type="button" role="tab" aria-selected={mode === m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d={m === "trip" ? PLANE : PEAK} /></svg>
              {m === "trip" ? "Trip" : "Trek"}
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
      </section>
      {phase !== "done" && <button type="button" className="home2-skip" onClick={skip}>Skip</button>}
    </main>
  );
}
