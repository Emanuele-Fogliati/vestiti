import { useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { activityText, addDays, dayMonth, minus, nights, SOURCE_LABEL } from "../lib/format";
import { terrainFor } from "../lib/terrain";
import type { Activity, Place, Stage, Stop } from "../lib/types";
import { ActivityEditor } from "./ActivityEditor";
import { Illustration } from "./Illustration";
import { PlaceSearch } from "./PlaceSearch";

function Conditions({ stage }: { stage?: Stage }) {
  if (!stage) return null;
  const ds = stage.days;
  const mn = Math.min(...ds.map((d) => d.tmin)), mx = Math.max(...ds.map((d) => d.tmax));
  const wl = Math.min(...ds.map((d) => d.wind_kmh)), wh = Math.max(...ds.map((d) => d.wind_kmh));
  const rest = stage.modes.rest.condition;
  const rain = Math.max(...ds.map((d) => d.precip_prob));
  return (
    <dl className="cond">
      <div><dt>Temp</dt><dd>{minus(Math.round(mn))} / {Math.round(mx)} °C</dd></div>
      <div><dt>Wind</dt><dd>{wl === wh ? wl : `${wl}–${wh}`} km/h</dd></div>
      <div><dt>Feels like</dt><dd className="hot">{minus(Math.round(rest.feels_like_c))} °C</dd></div>
      <div><dt>Rain</dt><dd>{Math.round(rain)}%</dd></div>
      {stage.max_altitude_m > stage.elevation_m + 50 && <div><dt>Up to</dt><dd>{Math.round(stage.max_altitude_m).toLocaleString("en-US")} m</dd></div>}
      <div><dt>Data</dt><dd>{stage.weather_sources.map((s) => SOURCE_LABEL[s] ?? s).join(" + ")}</dd></div>
    </dl>
  );
}

export function StopCard({ stop, stage, index, count, selected, dayFrom, onSelect, onEdit, onDelete, onMove }: {
  stop: Stop; stage?: Stage; index: number; count: number; selected: boolean; dayFrom: number;
  onSelect: () => void; onEdit: () => void; onDelete: () => void; onMove: (dir: -1 | 1) => void;
}) {
  const n = nights(stop.start_date, stop.end_date);
  return (
    <li className={`stop${selected ? " sel" : ""}`} tabIndex={0} onClick={onSelect}
      onKeyDown={(e) => { if (e.key === "Enter" && e.target === e.currentTarget) onSelect(); }}
      aria-label={`${stop.name}, select to see its layers`}>
      <div className="days">{n > 1 ? "Days" : "Day"} <b>{n > 1 ? `${dayFrom}–${dayFrom + n - 1}` : dayFrom}</b>
        <span>{dayMonth(stop.start_date)}{n > 1 ? ` – ${dayMonth(stop.end_date)}` : ""}</span></div>
      <Illustration terrain={terrainFor(stop, index)} art={stop.art} place={stop} />
      <div className="info">
        <h3>{stop.name}</h3>
        <div className="acts">{stop.activities.map((a, i) => <span className="tag" key={i}>{activityText(a)}</span>)}
          <span className="tag">{Math.round(stop.elevation_m)} m</span></div>
        {stop.notes && <p className="act">{stop.notes}</p>}
        <Conditions stage={stage} />
        {stage && (
          <div className="wx" aria-label="Daily weather">
            {stage.days.map((d) => (
              <div className="d" key={d.date} title={SOURCE_LABEL[d.source]}>
                <b>{dayMonth(d.date)}</b>{minus(Math.round(d.tmin))}/{Math.round(d.tmax)}°
                <div className={d.precip_prob >= 50 ? "r" : ""}>{Math.round(d.precip_prob)}% · {d.precip_mm}mm</div>
                <div>{d.wind_kmh} km/h</div>
              </div>
            ))}
          </div>
        )}
        <div className="tools" onClick={(e) => e.stopPropagation()}>
          <button type="button" className="btn sm" onClick={onEdit}>Edit</button>
          <button type="button" className="btn sm" disabled={index === 0} onClick={() => onMove(-1)} aria-label="Move up">↑</button>
          <button type="button" className="btn sm" disabled={index === count - 1} onClick={() => onMove(1)} aria-label="Move down">↓</button>
          <button type="button" className="btn sm danger" onClick={onDelete}>Remove</button>
        </div>
      </div>
    </li>
  );
}

export function StopForm({ tripId, stop, defaultStart, onDone, onCancel }: {
  tripId: string; stop?: Stop; defaultStart: string; onDone: () => void; onCancel: () => void;
}) {
  const { toast } = useApp();
  const [place, setPlace] = useState<Place | null>(stop ? {
    name: stop.name, country_code: stop.country_code, latitude: stop.latitude, longitude: stop.longitude,
    elevation_m: stop.elevation_m,
  } : null);
  const [start, setStart] = useState(stop?.start_date ?? defaultStart);
  const [end, setEnd] = useState(stop?.end_date ?? addDays(defaultStart, 2));
  const [acts, setActs] = useState<Activity[]>(stop?.activities?.length ? stop.activities : [{ type: "city" }]);
  const [notes, setNotes] = useState(stop?.notes ?? "");
  const [elev, setElev] = useState<number | "">(stop?.elevation_m ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!place) { setErr("Pick a place from the list."); return; }
    if (end < start) { setErr("The end date is before the start date."); return; }
    setBusy(true); setErr(null);
    const body = {
      name: place.name, country_code: place.country_code ?? null, latitude: place.latitude,
      longitude: place.longitude, elevation_m: elev === "" ? place.elevation_m ?? 0 : Number(elev),
      start_date: start, end_date: end, activities: acts, notes: notes || null,
    };
    try {
      if (stop) await api.patchStop(tripId, stop.id, body);
      else await api.addStop(tripId, body);
      toast(stop ? "Stop updated. The plan is recalculated." : "Stop added. Fetching its weather.");
      onDone();
    } catch (e2) { setErr((e2 as Error).message); } finally { setBusy(false); }
  }

  return (
    <form className="stopform form" onSubmit={submit}>
      <h3 style={{ fontSize: 18 }}>{stop ? `Edit ${stop.name}` : "Add a stop"}</h3>
      <div className="field"><label>Place</label>
        <PlaceSearch value={place} autoFocus={!stop} onPick={(p) => { setPlace(p); setElev(Math.round(p.elevation_m ?? 0)); }} /></div>
      <div className="grid3">
        <div className="field"><label>From</label><input type="date" value={start} onChange={(e) => { setStart(e.target.value); if (e.target.value > end) setEnd(e.target.value); }} /></div>
        <div className="field"><label>To</label><input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} /></div>
        <div className="field"><label>Town elevation (m)</label><input type="number" value={elev} onChange={(e) => setElev(e.target.value === "" ? "" : Number(e.target.value))} /></div>
      </div>
      <ActivityEditor value={acts} onChange={setActs} />
      <div className="field"><label>Notes (optional)</label><input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Laguna de los Tres, 20 km" /></div>
      {err && <p className="err">{err}</p>}
      <div className="row">
        <button className="btn primary" type="submit" disabled={busy}>{busy ? <span className="spin" /> : stop ? "Save stop" : "Add stop"}</button>
        <button className="btn" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
