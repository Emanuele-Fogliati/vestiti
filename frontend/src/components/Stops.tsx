import { useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { activityText, addDays, countryName, dayMonth, daysBetween, minus, nights, SOURCE_LABEL } from "../lib/format";
import { terrainFor, type Terrain } from "../lib/terrain";
import type { Activity, Place, Stage, Stop, Visit } from "../lib/types";
import { ActivityEditor } from "./ActivityEditor";
import { Illustration } from "./Illustration";
import { PlaceQuestion } from "./PlaceQuestion";
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

/** The places a stop's days take you to, day by day: a picture for each one the library has
 * drawn (once: Machu Picchu is not shown twice), a name for the others. */
export function Visits({ stop, dayFrom, terrain }: { stop: Stop; dayFrom: number; terrain: Terrain }) {
  const vs = stop.visits ?? [];
  if (!vs.length) return null;
  const multi = nights(stop.start_date, stop.end_date) > 1;
  const groups: { day: number | null; items: Visit[] }[] = [];
  for (const v of vs) {
    const day = multi && v.date ? dayFrom + daysBetween(stop.start_date, v.date) : null;
    const g = groups[groups.length - 1];
    if (g && g.day === day) g.items.push(v); else groups.push({ day, items: [v] });
  }
  const shown = new Set(stop.art ? [stop.art.id] : []);
  return (
    <div className="visits" aria-label={`Places you visit from ${stop.name}`}>
      {groups.map((g, gi) => (
        <div className="vday" key={gi}>
          {g.day !== null && <span className="vd">Day {g.day}</span>}
          {g.items.map((v, i) => {
            const pic = v.art && !shown.has(v.art.id);
            if (v.art) shown.add(v.art.id);
            return pic ? (
              <div className="visit" key={i}><Illustration terrain={terrain} art={v.art} label={v.name} /><span>{v.name}</span></div>
            ) : <span className="vchip" key={i} title={v.art ? v.art.label : undefined}>{v.name}</span>;
          })}
        </div>
      ))}
    </div>
  );
}

export function StopCard({ stop, stage, index, count, selected, dayFrom, onSelect, onEdit, onDelete, onMove, onConfirm }: {
  stop: Stop; stage?: Stage; index: number; count: number; selected: boolean; dayFrom: number;
  onSelect: () => void; onEdit: () => void; onDelete: () => void; onMove: (dir: -1 | 1) => void;
  /** "Yes, this is the place" for a stop the server is not sure about. */
  onConfirm?: () => void;
}) {
  const n = nights(stop.start_date, stop.end_date);
  const terrain = terrainFor(stop, index);
  const est = stop.days_estimated;
  return (
    <li className={`stop${selected ? " sel" : ""}`} tabIndex={0} onClick={onSelect}
      onKeyDown={(e) => { if (e.key === "Enter" && e.target === e.currentTarget) onSelect(); }}
      aria-label={`${stop.name}, select to see its layers`}>
      <div className="days" title={est ? "You did not say how long: these days are a guess" : undefined}>{n > 1 ? "Days" : "Day"} <b>{n > 1 ? `${dayFrom}–${dayFrom + n - 1}` : dayFrom}</b>
        <span>{dayMonth(stop.start_date)}{n > 1 ? ` – ${dayMonth(stop.end_date)}` : ""}</span>
        {est && <span className="est">≈ {n} {n === 1 ? "day" : "days"}, a guess</span>}</div>
      <Illustration terrain={terrain} art={stop.art} />
      <div className="info">
        <h3>{stop.name}</h3>
        {stop.place_status === "check" && onConfirm && (
          <PlaceQuestion place={stop} issues={stop.place_note ? [stop.place_note] : []} onYes={onConfirm} onSearch={onEdit} />
        )}
        <div className="acts">{stop.activities.map((a, i) => <span className="tag" key={i}>{activityText(a)}</span>)}
          {stop.country_code && <span className="tag" title="Country">{countryName(stop.country_code)}</span>}
          <span className="tag">{Math.round(stop.elevation_m)} m</span></div>
        {stop.notes && <p className="act">{stop.notes}</p>}
        <Visits stop={stop} dayFrom={dayFrom} terrain={terrain} />
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

export function StopForm({ tripId, stop, defaultStart, onDone, onCancel, countries }: {
  tripId: string; stop?: Stop; defaultStart: string; onDone: () => void; onCancel: () => void;
  /** The trip's countries: the place search lists places there first. */
  countries?: string[];
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
  const [visits, setVisits] = useState((stop?.visits ?? []).map((v) => v.name).join(", "));
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
      visits: visitsFrom(visits, stop?.visits ?? []),
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
        <PlaceSearch value={place} autoFocus={!stop} countries={countries} onPick={(p) => { setPlace(p); setElev(Math.round(p.elevation_m ?? 0)); }} /></div>
      <div className="grid3">
        <div className="field"><label>From</label><input type="date" value={start} onChange={(e) => { setStart(e.target.value); if (e.target.value > end) setEnd(e.target.value); }} /></div>
        <div className="field"><label>To</label><input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} /></div>
        <div className="field"><label>Town elevation (m)</label><input type="number" value={elev} onChange={(e) => setElev(e.target.value === "" ? "" : Number(e.target.value))} /></div>
      </div>
      <ActivityEditor value={acts} onChange={setActs} />
      <div className="field"><label>Places you visit from here (optional, comma-separated)</label><input type="text" value={visits} onChange={(e) => setVisits(e.target.value)} placeholder="e.g. Moray, Maras, Chinchero" /></div>
      <div className="field"><label>Notes (optional)</label><input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Laguna de los Tres, 20 km" /></div>
      {err && <p className="err">{err}</p>}
      <div className="row">
        <button className="btn primary" type="submit" disabled={busy}>{busy ? <span className="spin" /> : stop ? "Save stop" : "Add stop"}</button>
        <button className="btn" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** "Moray, Maras" -> visits; names that were already there keep their day. */
function visitsFrom(text: string, before: Visit[]): { name: string; date: string | null }[] {
  return text.split(",").map((x) => x.trim()).filter(Boolean).slice(0, 30).map((name) => ({
    name, date: before.find((v) => v.name.toLowerCase() === name.toLowerCase())?.date ?? null,
  }));
}
