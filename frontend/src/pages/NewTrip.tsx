import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ActivityEditor } from "../components/ActivityEditor";
import { PlaceSearch } from "../components/PlaceSearch";
import { api, type StopInput } from "../lib/api";
import { useApp } from "../lib/app-context";
import { activityText } from "../lib/format";
import type { DraftStop } from "../lib/types";

export default function NewTrip() {
  const { config, ensureUser, toast } = useApp();
  const loc = useLocation();
  const nav = useNavigate();
  const initial = (loc.state as { text?: string } | null)?.text ?? "";
  const [text, setText] = useState(initial);
  const [name, setName] = useState("");
  const [draft, setDraft] = useState<DraftStop[] | null>(null);
  const [questions, setQuestions] = useState<string[]>([]);
  const [parser, setParser] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<number | null>(null);

  async function parse(t = text) {
    if (t.trim().length < 3) return;
    setBusy(true); setErr(null);
    try {
      await ensureUser();
      const r = await api.parseItinerary(t);
      setDraft(r.stops);
      setQuestions(r.questions);
      setParser(r.parser);
      if (r.trip_name && !name) setName(r.trip_name);
      if (!r.stops.length) setErr("I couldn't find any stops. Try 'Rome 3 days, then 4 days hiking in Chamonix'.");
    } catch (e) {
      setErr((e as Error).message);
    } finally { setBusy(false); }
  }

  useEffect(() => { if (initial) parse(initial); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function create(withStops: boolean) {
    setBusy(true); setErr(null);
    try {
      await ensureUser();
      const stops: StopInput[] = withStops && draft ? draft.filter((s) => s.place).map((s) => ({
        name: s.place!.name, country_code: s.place!.country_code ?? null, latitude: s.place!.latitude,
        longitude: s.place!.longitude, elevation_m: s.place!.elevation_m ?? 0, start_date: s.start_date,
        end_date: s.end_date, activities: s.activities, notes: null,
      })) : [];
      const t = await api.createTrip(name.trim() || (stops.map((s) => s.name).slice(0, 3).join(" · ") || "My trip"), stops);
      const dropped = withStops && draft ? draft.length - stops.length : 0;
      if (dropped) toast(`${dropped} stop(s) without a map match were left out. Add them on the trip page.`);
      nav(`/trips/${t.id}`);
    } catch (e) {
      setErr((e as Error).message);
    } finally { setBusy(false); }
  }

  const set = (i: number, patch: Partial<DraftStop>) => setDraft((d) => d && d.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const ai = config?.ai;

  return (
    <main className="page">
      <div className="wrap">
        <div className="page-head">
          <div><p className="kicker">New trip</p><h1>Describe your trip</h1></div>
          <span className="tag">{ai?.available ? `AI: ${ai.model.split("/").pop()} (local)` : "AI offline: rule-based reader"}</span>
        </div>
        <div className="cols">
          <div className="stack">
            <div className="field"><label htmlFor="desc">Stops, dates, activities. Any language.</label>
              <textarea id="desc" rows={5} value={text} onChange={(e) => setText(e.target.value)}
                placeholder="From 12 June 2027: 3 days in Reykjavik, then 4 days hard trekking in Landmannalaugar up to 1100 m, then 2 days in Rome" />
            </div>
            <div className="row">
              <button className="btn primary" type="button" disabled={busy} onClick={() => parse()}>{busy ? <span className="spin" /> : "Read my trip"}</button>
              <button className="btn" type="button" disabled={busy} onClick={() => create(false)}>Skip, add stops by hand</button>
            </div>
            {err && <p className="err">{err}</p>}

            {draft && draft.length > 0 && (
              <div className="draft">
                <div className="row"><h2 style={{ fontSize: 22 }}>Check the stops</h2><span className="spacer" />
                  <span className="ai-src">{parser === "llm" ? "read by the local AI model" : "read by the rule-based parser"}</span></div>
                {draft.map((s, i) => (
                  <div key={i} className="stack" style={{ gap: 8 }}>
                    <div className="drow">
                      <div>
                        <PlaceSearch value={s.place} onPick={(p) => set(i, { place: p })} />
                        {!s.place && <p className="err small">No map match for "{s.name}". Search for it.</p>}
                      </div>
                      <input type="date" value={s.start_date} aria-label="Start date" onChange={(e) => set(i, { start_date: e.target.value, end_date: e.target.value > s.end_date ? e.target.value : s.end_date })} />
                      <input type="date" value={s.end_date} min={s.start_date} aria-label="End date" onChange={(e) => set(i, { end_date: e.target.value })} />
                      <button type="button" className="link small" style={{ textAlign: "left" }} onClick={() => setEditing(editing === i ? null : i)}>
                        {s.activities.map(activityText).join(", ")} ✎
                      </button>
                      <button type="button" className="btn sm ghost" aria-label="Remove stop" onClick={() => setDraft(draft.filter((_, j) => j !== i))}>✕</button>
                    </div>
                    {editing === i && <div className="stopform"><ActivityEditor value={s.activities} onChange={(a) => set(i, { activities: a })} /></div>}
                  </div>
                ))}
                {questions.length > 0 && (
                  <div className="banner info"><b>Worth checking</b><ul>{questions.map((q, i) => <li key={i}>{q}</li>)}</ul></div>
                )}
                <div className="field"><label htmlFor="tname">Trip name</label>
                  <input id="tname" type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Patagonia, May 2027" /></div>
                <button className="btn primary" type="button" disabled={busy} onClick={() => create(true)}>Create trip and dress it</button>
              </div>
            )}
          </div>
          <aside className="panel stack">
            <h3 style={{ fontSize: 18 }}>Tips</h3>
            <ul className="stagenotes">
              <li>Give a start date ("from 12 June 2027") and days per stop.</li>
              <li>Say how hard a hike is and how high it goes. That changes the plan more than anything.</li>
              <li>Not decided? "Maybe hiking, don't know yet" plans for both.</li>
              <li>You can change, add or remove stops later. The plan updates.</li>
            </ul>
          </aside>
        </div>
      </div>
    </main>
  );
}
