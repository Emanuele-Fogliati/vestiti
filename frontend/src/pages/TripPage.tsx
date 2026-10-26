import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ElevationProfile } from "../components/ElevationProfile";
import { TripMap } from "../components/Maps";
import { useItineraries } from "../components/ItineraryCards";
import { Kit } from "../components/Kit";
import { LayerStrategy } from "../components/LayerStrategy";
import { EstimateForm } from "../components/Estimate";
import { PlanChange } from "../components/PlanChange";
import { ProfileQuiz } from "../components/ProfileQuiz";
import { TailorChat } from "../components/TailorChat";
import { StopCard, StopForm } from "../components/Stops";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { addDays, dayMonth, daysBetween, minus, money, today } from "../lib/format";
import type { Plans, QuizResult, Strategy, Tier, Trip, User } from "../lib/types";

const COLD_TXT: [number, string][] = [[0.3, "always cold"], [0.15, "a bit cold"], [0, "average with cold"], [-0.3, "rarely cold"]];
const PACE_TXT = { relaxed: "slow pace", average: "average pace", brisk: "fast pace" };
const EVE_TXT = { early: "inside after dinner", sometimes: "out some evenings", late: "out late" };

function profileText(u: User): string {
  const cold = COLD_TXT.reduce((b, c) => (Math.abs(c[0] - u.thermal_offset) < Math.abs(b[0] - u.thermal_offset) ? c : b))[1];
  return [cold, PACE_TXT[u.pace] ?? "average pace", EVE_TXT[u.evenings] ?? "out some evenings"].join(" · ");
}

export default function TripPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const { toast, user, refreshUser } = useApp();
  const [quizOpen, setQuizOpen] = useState(false);
  const [quizResult, setQuizResult] = useState<QuizResult | null>(null);
  const [trip, setTrip] = useState<Trip | null>(null);
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [plans, setPlans] = useState<Plans | null>(null);
  const [tier, setTier] = useState<Tier>("medium");
  const [stageIdx, setStageIdx] = useState(0);
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [planning, setPlanning] = useState(false);
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
      if (t.stops.length) await loadPlans(tier);
      else { setStrategy(null); setPlans(null); }
    } catch (e) { setErr((e as Error).message); }
  }, [id, tier, loadPlans]);

  useEffect(() => { loadAll(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  // the quiz comes before the plan, once per traveller (answered or skipped)
  useEffect(() => {
    if (trip && trip.stops.length && user && !user.profile_done_at) setQuizOpen(true);
  }, [trip, user]);

  async function quizDone(r: QuizResult) {
    setQuizOpen(false);
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

  async function rename(name: string) {
    if (!trip || !name.trim() || name === trip.name) return;
    setTrip(await api.patchTrip(trip.id, { name: name.trim() }));
  }

  async function removeStop(stopId: string) {
    if (!window.confirm("Remove this stop? Its weather and layers go with it.")) return;
    await api.deleteStop(id, stopId);
    toast("Stop removed.");
    setStageIdx(0);
    loadAll();
  }

  async function move(i: number, dir: -1 | 1) {
    const ids = stops.map((s) => s.id);
    const j = i + dir;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    setTrip(await api.reorder(id, ids));
    loadPlans(tier);
  }

  const last = stops[stops.length - 1];
  const nextStart = last ? addDays(last.end_date, 1) : addDays(today(), 30);
  const totalDays = stops.length && t0 ? daysBetween(t0, stops.reduce((m, s) => (s.end_date > m ? s.end_date : m), stops[0].end_date)) + 1 : 0;
  const coldest = strategy?.stages?.length ? Math.min(...strategy.stages.map((s) => s.modes.rest.condition.feels_like_c)) : null;
  const tp = plans && !plans.empty ? plans.tiers[tier] : null;

  const source = trip.source_itinerary ? itineraries?.find((it) => it.slug === trip.source_itinerary) : undefined;
  // your own trip to a country we have a recommended route for: point to it
  const countries = new Set(stops.map((s) => s.country_code).filter(Boolean));
  const related = !trip.source_itinerary ? itineraries?.find((it) => it.countries.some((c) => countries.has(c))) : undefined;

  const sources = new Set(strategy?.stages.flatMap((s) => s.weather_sources) ?? []);
  const weatherHeadline = !sources.size ? "weather loading" : sources.has("estimate") ? "estimated weather"
    : sources.has("forecast") ? "real forecast" : "climate averages";

  return (
    <main>
      <nav className="secnav" aria-label="Trip sections">
        <div className="wrap">
          <span className="tname">{trip.name}</span>
          <a href="#trip">Trip</a><a href="#layers">Layers</a><a href="#kit">Kit</a><a href="#total">Total</a><a href="#ask">Chat</a>
          {planning && <span className="spin" aria-label="Updating plan" />}
        </div>
      </nav>
      <section className="thero">
        <div className="wrap">
          <p className="kicker">{t0 ? `${trip.estimate ? "≈ " : ""}${dayMonth(t0)} · ${totalDays} days · ${stops.length} stops${trip.estimate ? " · estimate" : ""}` : "No stops yet"}</p>
          <h1><textarea className="titleedit" rows={1} defaultValue={trip.name} aria-label="Trip name" onBlur={(e) => rename(e.target.value.replace(/\s+/g, " ").trim())}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); (e.target as HTMLTextAreaElement).blur(); } }} /></h1>
          <div className="facts">
            <div className="fact"><b>{coldest !== null ? `${minus(Math.round(coldest))} °C` : "—"}</b><span>Coldest feels-like</span></div>
            <div className="fact"><b>{totalDays || "—"}</b><span>Days</span></div>
            <div className="fact"><b>{tp ? `${tp.totals.items_owned} of ${tp.items.length}` : "—"}</b><span>Pieces you own</span></div>
            <div className="fact"><b>{tp ? money(tp.totals.total) : "—"}</b><span>{tier} kit total</span></div>
          </div>
          {user && (
            <div className="tailored">
              <span className="kicker">Tailored to you</span>
              <span>{user.profile_done_at ? profileText(user) : "not yet: answer 4 quick questions"}</span>
              <button type="button" className="link small" onClick={() => setQuizOpen(true)}>{user.profile_done_at ? "Change" : "Start"}</button>
              <a className="link small" href="#ask">or tell us in the chat</a>
            </div>
          )}
          {quizResult && (
            <div className="banner ok quizres">
              <div className="row"><b>{quizResult.plan.pieces.length || quizResult.plan.status ? "Your answers changed the kit" : "Saved. Your kit already fit you"}</b><span className="spacer" />
                <button type="button" className="btn sm ghost" aria-label="Close" onClick={() => setQuizResult(null)}>✕</button></div>
              <PlanChange changes={quizResult.changes} plan={quizResult.plan} />
            </div>
          )}
          {trip.source_itinerary && (
            <p className="from-rec small">
              <span className="label">From a recommended trip</span>
              <span>It's yours now: change stops, days and activities, the kit follows.</span>
              <Link to={`/ideas/${trip.source_itinerary}`}>Day-by-day guide and tours{source ? `: ${source.title}` : ""} →</Link>
            </p>
          )}
          {related && (
            <p className="from-rec small">
              <span className="label">Ideas for this trip</span>
              <Link to={`/ideas/${related.slug}`}>See our recommended route: {related.title} →</Link>
            </p>
          )}
          {user?.is_guest && tp && (
            <div className="banner info save-nudge">
              <span><b>Keep this trip.</b> You're a guest: it lives only in this browser. A free account keeps it on any device.</span>
              <span className="row">
                <Link className="btn sm primary" to="/register" state={{ from: `/trips/${id}` }}>Create free account</Link>
                <Link className="btn sm" to="/login" state={{ from: `/trips/${id}` }}>Sign in</Link>
              </span>
            </div>
          )}
          <div className="row" style={{ marginTop: 18 }}>
            <button type="button" className="btn sm" onClick={async () => { const c = await api.duplicateTrip(id); nav(`/trips/${c.id}`); }}>Duplicate</button>
            <button type="button" className="btn sm danger" onClick={async () => { if (window.confirm("Delete this trip?")) { await api.deleteTrip(id); nav("/trips"); } }}>Delete trip</button>
          </div>
        </div>
      </section>

      <section className="band alt" id="trip">
        <div className="wrap">
          <header className="sh"><p className="sh-k">The trip</p><h2>{stops.length ? `${stops.length} ${stops.length === 1 ? "stop" : "stops"}, ${weatherHeadline}` : "Add your first stop"}</h2>
            {sources.has("estimate") && (
              <div className="banner warn" style={{ margin: "12px 0" }}>
                The weather service could not be reached, so some stops use a <b>rough estimate</b> from latitude and season.
                Reload later for real data before you trust the kit.
              </div>
            )}
            {trip.estimate && t0 && (
              <div style={{ margin: "12px 0" }}>
                <EstimateForm start={trip.estimate.start} days={trip.estimate.days} firstDay={t0} totalDays={totalDays}
                  onApply={async (v) => { setTrip(await api.setDates(id, { start_date: v.start, total_days: v.total })); toast("Dates updated. The plan is recalculated."); loadPlans(tier); }}
                  onKeep={async () => { setTrip(await api.setDates(id, { confirm: true })); }} />
              </div>
            )}
            <p>Each stop sets its own conditions. One kit has to cover all of them, so we size it to the hardest hour of the whole trip. Edit, add or remove stops any time: the plan follows.</p></header>
          <TripMap stops={stops} />
          <ElevationProfile stops={stops} selected={stageIdx} onSelect={(i) => { setStageIdx(i); document.getElementById("layers")?.scrollIntoView({ behavior: "smooth" }); }} />
          <ol className="stops">
            {stops.map((s, i) => editing === s.id ? (
              <li key={s.id} style={{ padding: "16px 0" }}><StopForm tripId={id} stop={s} defaultStart={s.start_date}
                onDone={() => { setEditing(null); loadAll(); }} onCancel={() => setEditing(null)} /></li>
            ) : (
              <StopCard key={s.id} stop={s} index={i} count={stops.length} stage={strategy?.stages.find((x) => x.stop_id === s.id)}
                selected={i === stageIdx} dayFrom={t0 ? daysBetween(t0, s.start_date) + 1 : 1}
                onSelect={() => setStageIdx(i)} onEdit={() => setEditing(s.id)} onDelete={() => removeStop(s.id)} onMove={(d) => move(i, d)} />
            ))}
          </ol>
          <div className="addstop">
            {editing === "new" ? (
              <StopForm tripId={id} defaultStart={nextStart} onDone={() => { setEditing(null); loadAll(); }} onCancel={() => setEditing(null)} />
            ) : <button type="button" className="btn primary" onClick={() => setEditing("new")}>+ Add a stop</button>}
          </div>
          {strategy && strategy.questions.length > 0 && (
            <div style={{ marginTop: 28 }}>
              <h3 className="subh" style={{ marginTop: 0 }}>A few questions that change the plan</h3>
              <ul className="qs">{strategy.questions.map((q, i) => (
                <li key={i}>{q.question}
                  {q.stop_id && <div className="opts"><button type="button" className="btn sm" onClick={() => setEditing(q.stop_id!)}>Edit that stop</button></div>}
                </li>
              ))}</ul>
            </div>
          )}
        </div>
      </section>

      <section className="band" id="layers">
        <div className="wrap">
          <header className="sh"><p className="sh-k">Layer strategy</p><h2>What to wear at each stop</h2>
            <p>Pick a stop and whether you're moving or resting. We stack the layers that stop needs for its coldest feels-like moment, check the warmth against what your body loses, and tell you what to change if it falls short.</p></header>
          {strategy && !strategy.empty ? (
            <LayerStrategy tripId={id} strategy={strategy} tier={tier} stageIdx={Math.min(stageIdx, strategy.stages.length - 1)} setStageIdx={setStageIdx} onChanged={() => loadPlans(tier)} />
          ) : <div className="empty">{planning ? <span className="spin" /> : "Add a stop to see the layer strategy."}</div>}
        </div>
      </section>

      <section className="band alt" id="kit" style={{ paddingBottom: 0 }}>
        <div className="wrap"><header className="sh"><p className="sh-k">The kit</p><h2>{tp ? `${tp.items.length} pieces, three budgets` : "The kit"}</h2>
          <p>Every piece is checked against the layer spec and rated for this trip. PASS meets it, CHECK misses something (read why). Switch budget, swap any piece, use what you own, or rent.</p></header></div>
        {plans && !plans.empty ? <Kit tripId={id} plans={plans} tier={tier} setTier={changeTier} onChanged={() => loadPlans(tier)} />
          : <div className="wrap" style={{ paddingBottom: 72 }}><div className="empty">{planning ? <span className="spin" /> : "Add a stop to see the kit."}</div></div>}
      </section>

      <section className="band alt" id="ask">
        <div className="wrap">
          <header className="sh"><p className="sh-k">Chat</p><h2>Tell us about you, or ask</h2>
            <p>"I'm always cold", "I have an old Decathlon fleece", "I walk slowly": the kit is recomputed for you and you see exactly what changed. Questions about the plan are answered from its numbers.</p></header>
          <TailorChat tripId={id} tier={tier} onChanged={profileChanged} />
        </div>
      </section>
      {quizOpen && <ProfileQuiz tripId={id} tier={tier} onDone={quizDone} />}
    </main>
  );
}
