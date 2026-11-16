import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useItineraries } from "../components/ItineraryCards";
import { TailorChat } from "../components/TailorChat";
import { TripStudio } from "../components/TripStudio";
import { Sheet } from "../components/Sheet";
import { TripBag } from "../components/TripBag";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { dayMonth, daysBetween } from "../lib/format";
import type { Plans, Strategy, Tier, Trip } from "../lib/types";

// one page (Manu 2026-11-16: "sta tutto dentro la stessa pagina ... posso in ogni momento tornare
// su, editare il viaggio, e i vestiti si editano"): the route on the map, the clothes below it.
// Old links to the bag's sections scroll down to it.
const TO_BAG = new Set(["bag", "weather", "layers", "kit", "total"]);

export default function TripPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const loc = useLocation();
  const { toast, user, refreshUser } = useApp();
  const [trip, setTrip] = useState<Trip | null>(null);
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [plans, setPlans] = useState<Plans | null>(null);
  const [tier, setTier] = useState<Tier>("medium");
  const [stageIdx, setStageIdx] = useState(-1); // -1: the whole route, no stop open
  const [err, setErr] = useState<string | null>(null);
  const [ver, setVer] = useState(0);
  const [askOpen, setAskOpen] = useState(loc.hash === "#ask");
  const [askText, setAskText] = useState("");
  const [dateOpen, setDateOpen] = useState(false);
  const [menu, setMenu] = useState(false);
  const itineraries = useItineraries();

  // the bag below works the clothes out again whenever `ver` moves; the panel shows its pieces too
  const bagBack = useCallback((p: Plans, s: Strategy) => { setPlans(p); setStrategy(s); }, []);
  const reBag = useCallback(() => setVer((v) => v + 1), []);

  const loadAll = useCallback(async () => {
    try {
      const t = await api.trip(id);
      setTrip(t);
      setVer((v) => v + 1);
      if (!t.stops.length) { setStrategy(null); setPlans(null); }
    } catch (e) { setErr((e as Error).message); }
  }, [id]);

  useEffect(() => { loadAll(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  // the ⋯ menu closes when you tap anywhere else or press Escape
  useEffect(() => {
    if (!menu) return;
    const shut = (e: Event) => { if (!(e.target as Element).closest?.(".x-menu-w")) setMenu(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setMenu(false); };
    document.addEventListener("pointerdown", shut);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", shut); document.removeEventListener("keydown", esc); };
  }, [menu]);

  // a trip you change is a trip you want: it goes into Trips on its own (flow audit, Manu
  // 2026-11-16: an unsaved trip used to vanish when you left). Save stays, to name it.
  const tripRef = useRef<Trip | null>(null);
  tripRef.current = trip;
  const keep = useCallback(async () => {
    const t = tripRef.current;
    if (!t || t.saved) return;
    const st = [...t.stops].sort((a, b) => a.position - b.position);
    const name = t.name === "New trip" && st.length ? (st.length > 1 ? `${st[0].name} to ${st[st.length - 1].name}` : st[0].name) : undefined;
    try { setTrip(await api.patchTrip(t.id, { saved: true, ...(name ? { name } : {}) })); } catch { /* it stays a draft */ }
  }, []);
  const edited = useCallback(async () => { await loadAll(); keep(); }, [loadAll, keep]);
  const picked = useCallback(() => { reBag(); keep(); }, [reBag, keep]);

  const toBag = useCallback(() => document.getElementById("bag")?.scrollIntoView({ behavior: "smooth", block: "start" }), []);
  // an old link to the Bag tab lands on the clothes
  const landed = useRef(false);
  useEffect(() => {
    if (landed.current || !trip || !TO_BAG.has(loc.hash.slice(1))) return;
    landed.current = true;
    setTimeout(toBag, 300);
  }, [trip, loc.hash, toBag]);

  function profileChanged() {
    refreshUser();
    reBag();
  }

  const stops = useMemo(() => (trip ? [...trip.stops].sort((a, b) => a.position - b.position) : []), [trip]);
  const t0 = stops.length ? stops.reduce((m, s) => (s.start_date < m ? s.start_date : m), stops[0].start_date) : null;

  if (err && !trip) return <main className="page"><div className="wrap"><p className="err">{err}</p><Link to="/trips">Back to my trips</Link></div></main>;
  if (!trip) return <main className="page"><p className="loading"><span className="spin" /> Loading trip</p></main>;

  async function toggleSave() {
    if (!trip) return;
    const on = !trip.saved;
    // a trip still called "New trip" gets the name of its places when it is saved
    const st = [...trip.stops].sort((a, b) => a.position - b.position);
    const name = on && trip.name === "New trip" && st.length ? (st.length > 1 ? `${st[0].name} to ${st[st.length - 1].name}` : st[0].name) : undefined;
    setTrip(await api.patchTrip(trip.id, { saved: on, ...(name ? { name } : {}) }));
    toast(on ? (user?.is_guest ? "Saved in Trips. Create a free account to keep it on every device." : "Saved in Trips.") : "Removed from Saved.");
  }

  async function rename(name: string) {
    if (!trip || !name.trim() || name === trip.name) return;
    setTrip(await api.patchTrip(trip.id, { name: name.trim() }));
  }

  const tEnd = stops.length ? stops.reduce((m, s) => (s.end_date > m ? s.end_date : m), stops[0].end_date) : null;
  const totalDays = t0 && tEnd ? daysBetween(t0, tEnd) + 1 : 0;
  const source = trip.source_itinerary ? itineraries?.find((it) => it.slug === trip.source_itinerary) : undefined;
  async function setStart(v: string) {
    if (!v) return;
    try { setTrip(await api.setDates(id, { start_date: v })); setDateOpen(false); toast("Dates updated."); reBag(); keep(); }
    catch (e) { toast((e as Error).message); }
  }
  const sel = stageIdx < 0 ? -1 : Math.min(stageIdx, Math.max(0, stops.length - 1));

  const sheets = (
    <>
      <button type="button" className="x-fab" onClick={() => setAskOpen(true)}>
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z" /></svg>
        <span>Ask</span>
      </button>
      <Sheet open={askOpen} onClose={() => setAskOpen(false)} title="Tell us, or ask">
        <TailorChat tripId={id} tier={tier} onChanged={profileChanged} initial={askText} key={askText} />
      </Sheet>
    </>
  );
  const metaTitle = (
    <>
              <p className="x-meta">
                {/* the one place to say when you leave (flow audit, Manu 2026-11-16); a guess until then */}
                {t0 && tEnd ? <><button type="button" className="x-when" aria-expanded={dateOpen} onClick={() => setDateOpen(!dateOpen)}
                  title={trip.estimate ? "A guess: set your date" : "Change the date"}><b>{trip.estimate ? "≈ " : ""}{dayMonth(t0)} – {dayMonth(tEnd)}</b></button>
                  <span>{totalDays} days</span><span>{stops.length} {stops.length === 1 ? "place" : "places"}</span></> : <span>No places yet</span>}
              </p>
              {dateOpen && t0 && (
                <p className="x-when-set"><label htmlFor="x-leave">Leaving</label>
                  <input id="x-leave" type="date" defaultValue={trip.estimate?.start ? "" : t0} onChange={(e) => setStart(e.target.value)} /></p>
              )}
              <h1><textarea key={trip.name} className="x-title" rows={1} ref={(el) => { if (el) { el.style.height = "auto"; el.style.height = `${el.scrollHeight}px`; } }} onInput={(e) => { const el = e.currentTarget; el.style.height = "auto"; el.style.height = `${el.scrollHeight}px`; }} defaultValue={trip.name} aria-label="Trip name" onBlur={(e) => rename(e.target.value.replace(/\s+/g, " ").trim())}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); (e.target as HTMLTextAreaElement).blur(); } }} /></h1>
    </>
  );
  const actions = (
            <div className="x-head-a">
              {/* goes into Trips on the first change, or when you press Save */}
              <button type="button" className={`mf-btn sm x-save${trip.saved ? " on" : ""}`} aria-pressed={!!trip.saved} onClick={toggleSave}>
                {trip.saved ? <><Check /> Saved</> : "Save"}
              </button>
              <div className="x-menu-w">
                <button type="button" className="x-round" aria-label="More" aria-expanded={menu} onClick={() => setMenu(!menu)}>
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" /></svg>
                </button>
                {menu && (
                  <div className="x-menu" role="menu">
                    <button type="button" role="menuitem" onClick={async () => { setMenu(false); const c = await api.duplicateTrip(id); nav(`/trips/${c.id}`); }}>Duplicate</button>
                    <button type="button" role="menuitem" className="danger" onClick={async () => { setMenu(false); if (window.confirm("Delete this trip?")) { await api.deleteTrip(id); nav("/trips"); } }}>Delete trip</button>
                  </div>
                )}
              </div>
            </div>
  );
  const below = (
    <>
          {trip.source_itinerary && (
            <p className="x-from"><Link to={`/ideas/${trip.source_itinerary}`}>Day by day{source ? `: ${source.title}` : ""} →</Link></p>
          )}
    </>
  );
  // the route on the map at the top, an empty trip too (you add its stops there), the clothes below
  return (
    <main className="x-trip x-trip-st ip-one">
      <div className="ip-top">
        <TripStudio trip={trip} plans={plans} strategy={strategy} tier={tier} sel={stageIdx < 0 ? null : sel}
          setSel={(i) => setStageIdx(i ?? -1)} onChanged={edited} onPlans={picked}
          head={<><div className="mf-head-r">{metaTitle}{actions}</div>{below}</>} tabs={null}
          onBag={toBag} onAsk={(t) => { setAskText(t ?? ""); setAskOpen(true); }}
          firstAdd={(loc.state as { add?: string } | null)?.add} />
      </div>
      {stops.length > 0 && <TripBag tripId={id} ver={ver} tier={tier} setTier={setTier} onPlans={bagBack}
        title={<>What to wear{totalDays ? <span>{totalDays} days from {t0 ? dayMonth(t0) : ""}</span> : null}</>} />}
      {sheets}
    </main>
  );
}

const Check = () => <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10" /></svg>;
