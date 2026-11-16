import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useItineraries } from "../components/ItineraryCards";
import { Kit } from "../components/Kit";
import { FitCard } from "../components/FitCard";
import { PlanChange } from "../components/PlanChange";
import { TailorChat } from "../components/TailorChat";
import { TripStudio } from "../components/TripStudio";
import { Sheet } from "../components/Sheet";
import { Coldest, WeatherTab } from "../components/WeatherTab";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { dayMonth, daysBetween } from "../lib/format";
import type { Plans, QuizResult, Strategy, Tier, Trip } from "../lib/types";

// two tabs (flow audit, Manu 2026-11-16): the places, and the bag. The weather lives in the bag,
// as the reason for it; the map already shows each stop's temperatures.
type Tab = "trip" | "bag";
const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "trip", label: "Plan", icon: "M3 18l5-9 4 6 3-4 6 7" },
  { id: "bag", label: "Bag", icon: "M4 9a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2zM9 7V5a3 3 0 0 1 6 0v2" },
];
// old section anchors still land in the right tab
const HASH: Record<string, Tab> = { trip: "trip", days: "trip", flights: "trip", map: "trip", weather: "bag", layers: "bag", bag: "bag", kit: "bag", total: "bag", ask: "trip" };

function TabIcon({ d }: { d: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>;
}

export default function TripPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const loc = useLocation();
  const { toast, user, refreshUser } = useApp();
  const [quizResult, setQuizResult] = useState<QuizResult | null>(null);
  const [trip, setTrip] = useState<Trip | null>(null);
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [plans, setPlans] = useState<Plans | null>(null);
  const [tier, setTier] = useState<Tier>("medium");
  const [stageIdx, setStageIdx] = useState(-1); // -1: the whole route, no stop open
  const [err, setErr] = useState<string | null>(null);
  const [planning, setPlanning] = useState(false);
  const [tab, setTab] = useState<Tab>(HASH[loc.hash.slice(1)] ?? "trip");
  const [, setVer] = useState(0);
  const [askOpen, setAskOpen] = useState(loc.hash === "#ask");
  const [askText, setAskText] = useState("");
  const [dateOpen, setDateOpen] = useState(false);
  const [menu, setMenu] = useState(false);
  const tabsRef = useRef<HTMLElement>(null);
  const pillRef = useRef<HTMLSpanElement>(null);
  const itineraries = useItineraries();

  const loadPlans = useCallback(async (t: Tier) => {
    setPlanning(true);
    try {
      const [s, p] = await Promise.all([api.strategy(id, t), api.plans(id)]);
      setStrategy(s);
      setPlans(p);
    } catch (e) { setErr((e as Error).message); } finally { setPlanning(false); }
  }, [id]);

  const loadAll = useCallback(async () => {
    try {
      const t = await api.trip(id);
      setTrip(t);
      setVer((v) => v + 1);
      if (t.stops.length) await loadPlans(tier);
      else { setStrategy(null); setPlans(null); }
    } catch (e) { setErr((e as Error).message); }
  }, [id, tier, loadPlans]);

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
  const picked = useCallback(() => { loadPlans(tier); keep(); }, [loadPlans, tier, keep]);

  useEffect(() => {
    const t = HASH[loc.hash.slice(1)];
    if (t) setTab(t);
  }, [loc.hash]);

  // the yellow pill slides under the chosen tab
  const placePill = useCallback(() => {
    const bar = tabsRef.current, pill = pillRef.current;
    const b = bar?.querySelector<HTMLButtonElement>(`[data-tab="${tab}"]`);
    if (!b || !pill) return;
    pill.style.width = `${b.offsetWidth}px`;
    pill.style.transform = `translateX(${b.offsetLeft}px)`;
  }, [tab]);
  useEffect(() => {
    placePill();
    addEventListener("resize", placePill);
    document.fonts?.ready.then(placePill);
    return () => removeEventListener("resize", placePill);
  }, [placePill, trip]);

  function go(t: Tab) {
    setTab(t);
    nav(`#${t}`, { replace: true, preventScrollReset: true });
    const bar = tabsRef.current;
    if (bar && innerWidth > 760) {
      const top = bar.getBoundingClientRect().top + scrollY - 1;
      if (scrollY > top) scrollTo({ top });
    } else if (bar) {
      const head = document.querySelector(".x-head");
      const top = head ? head.getBoundingClientRect().bottom + scrollY - 8 : 0;
      if (scrollY > top) scrollTo({ top });
    }
  }

  async function quizDone(r: QuizResult) {
    setQuizResult(r.changes.length ? r : null);
    await refreshUser();
    if (trip?.stops.length) loadPlans(tier);
  }

  function profileChanged() {
    refreshUser();
    loadPlans(tier);
  }

  function changeTier(t: Tier) {
    setTier(t);
    if (trip?.stops.length) api.strategy(id, t).then(setStrategy).catch(() => undefined);
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
  const estimateWeather = strategy?.stages.some((s) => s.weather_sources.includes("estimate"));
  async function setStart(v: string) {
    if (!v) return;
    try { setTrip(await api.setDates(id, { start_date: v })); setDateOpen(false); toast("Dates updated."); loadPlans(tier); keep(); }
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
                {planning && <span className="spin" aria-label="Updating" />}
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
          {quizResult && (
            <div className="x-alert x-quizres">
              <div className="x-row"><b>{quizResult.plan.pieces.length || quizResult.plan.status ? "Your answers changed the bag" : "Saved. Your bag already fit you"}</b>
                <button type="button" className="x-close" aria-label="Close" onClick={() => setQuizResult(null)}>✕</button></div>
              <PlanChange changes={quizResult.changes} plan={quizResult.plan} />
            </div>
          )}
    </>
  );
  const tabBar = (
      <nav className="x-tabs" aria-label="Trip" ref={tabsRef}>
        <div className="wrap">
          <div className="x-tabs-in" role="tablist">
            <span className="x-pill" ref={pillRef} aria-hidden="true" />
            {TABS.map((t) => (
              <button key={t.id} type="button" role="tab" data-tab={t.id} aria-selected={tab === t.id} aria-controls={`p-${t.id}`} onClick={() => go(t.id)}>
                <TabIcon d={t.icon} />{t.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

  );

  // the bag (flow audit, Manu 2026-11-16): the coldest hour it is sized for, two questions the
  // first time, the suitcase, the list. The weather day by day is folded under the coldest hour.
  const bagBody = (
    <div className="x-panel mf-tab" id="p-bag" role="tabpanel">
      {plans && !plans.empty ? <>
        {user && !user.profile_done_at && <FitCard tripId={id} tier={tier} onDone={quizDone} />}
        {strategy && !strategy.empty && (
          <div className="x-cold-top">
            <Coldest strategy={strategy} />
            <details className="x-wx">
              <summary>Weather, day by day</summary>
              {estimateWeather && <p className="x-alert warn">The weather service could not be reached: some places use a rough estimate. Reload later.</p>}
              <WeatherTab strategy={strategy} />
            </details>
          </div>
        )}
        <Kit tripId={id} plans={plans} tier={tier} setTier={changeTier} onChanged={picked} />
      </> : <Empty planning={planning} onAdd={() => go("trip")} />}
    </div>
  );

  // with stops, every tab is the map-first page: the header and the tabs sit in its panel,
  // Plan shows the map, Weather and Bag fill the big panel beside it
  // every trip is the map-first page, an empty one too: you add its stops on the map (Manu 2026-11-16)
  return (
    <main className="x-trip x-trip-st">
      <TripStudio content={tab === "bag" ? bagBody : undefined} trip={trip} plans={plans} strategy={strategy} tier={tier} sel={stageIdx < 0 ? null : sel}
        setSel={(i) => setStageIdx(i ?? -1)} onChanged={edited} onPlans={picked}
        head={<><div className="mf-head-r">{metaTitle}{actions}</div>{below}</>} tabs={tabBar}
        onBag={() => go("bag")} onAsk={(t) => { setAskText(t ?? ""); setAskOpen(true); }}
        firstAdd={(loc.state as { add?: string } | null)?.add} />
      {sheets}
    </main>
  );

}

function Empty({ planning, onAdd }: { planning: boolean; onAdd: () => void }) {
  return (
    <div className="x-empty">
      {planning ? <span className="spin" /> : <><b>Add a place first.</b><button type="button" className="x-btn y" onClick={onAdd}>Go to Trip</button></>}
    </div>
  );
}

const Check = () => <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10" /></svg>;
