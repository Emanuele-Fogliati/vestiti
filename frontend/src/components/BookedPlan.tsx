/* A trip already booked, told in detail (Manu, 2026-11-14): every day hour by hour. The moves
   come from the text (flight, car, borders, the bed), the things to do from our guides; then the
   AI can rewrite each base for what the traveller wants ("we walk slowly", "no boats"), checked
   so that it never loses or moves a flight. Every row can be changed by hand. */
import { useState } from "react";
import { api, ApiError } from "../lib/api";
import { short } from "../lib/plan";
import type { BookedDay, DayPlan, DayRow, PlanStep, WeatherRule } from "../lib/types";

const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const weekday = (iso: string) => WD[new Date(iso + "T12:00:00Z").getUTCDay()];
const EFFORT: { v: DayRow["effort"]; l: string }[] = [
  { v: null, l: "–" }, { v: "zero", l: "No effort" }, { v: "low", l: "Easy" }, { v: "medium", l: "Medium" }, { v: "high", l: "Hard" },
];
const prioName = (p: number) => (p === 1 ? "Don't miss" : `Priority ${p}`);

interface Props {
  text: string; steps: PlanStep[]; timeline: BookedDay[]; groups: number;
  days: DayPlan[]; weather: WeatherRule[]; onDays: (d: DayPlan[]) => void; onWeather: (w: WeatherRule[]) => void;
}

function Row({ row, onChange, onDrop }: { row: DayRow; onChange: (r: DayRow) => void; onDrop: () => void }) {
  return (
    <li className={`hr${row.fixed ? " hr-fixed" : ""}${row.optional ? " hr-opt" : ""}`}>
      <input className="hr-at" value={row.at ?? ""} placeholder="--:--" aria-label="Time"
        onChange={(e) => onChange({ ...row, at: e.target.value || null })} />
      <div className="hr-main">
        <span className="hr-what" contentEditable suppressContentEditableWarning role="textbox" aria-label="What"
          onBlur={(e) => { const v = e.currentTarget.textContent?.trim() ?? ""; if (v !== row.what) onChange({ ...row, what: v }); }}>
          {row.what}
        </span>
        {row.note && <span className="hr-note">{row.note}</span>}
      </div>
      {!row.fixed && <div className="hr-tags">
      <select className={`hr-eff eff-${row.effort ?? "none"}`} value={row.effort ?? ""} aria-label="Effort"
        onChange={(e) => onChange({ ...row, effort: (e.target.value || null) as DayRow["effort"] })}>
        {EFFORT.map((x) => <option key={x.l} value={x.v ?? ""}>{x.l}</option>)}
      </select>
      <button type="button" className={`hr-optb${row.optional ? " on" : ""}`} aria-pressed={row.optional}
        title="Optional: do it if there is time" onClick={() => onChange({ ...row, optional: !row.optional })}>Optional</button>
      </div>}
      <button type="button" className="hr-x" aria-label="Remove this row" onClick={onDrop}>×</button>
    </li>
  );
}

export default function BookedPlan({ text, steps, timeline, groups, days, weather, onDays, onWeather }: Props) {
  const [wishes, setWishes] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const byDate = new Map(days.map((d) => [d.date, d]));

  function setDay(date: string, f: (d: DayPlan) => DayPlan) {
    onDays(days.map((d) => (d.date === date ? f(d) : d)));
  }

  async function write() {
    setNote("");
    let cur = days, rules: WeatherRule[] = [], models = new Set<string>(), fell = 0;
    for (let g = 0; g < groups; g++) {
      setBusy(g);
      try {
        const r = await api.planDays(text, g, wishes);
        const got = new Map(r.days.map((d) => [d.date, d]));
        cur = cur.map((d) => got.get(d.date) ?? d);
        onDays(cur);
        rules = rules.concat(r.weather);
        if (r.source === "llm" && r.model) models.add(r.model); else fell++;
      } catch (e) {
        setNote(e instanceof ApiError ? e.message : String(e));
        break;
      }
    }
    if (rules.length) onWeather(rules);
    setBusy(null);
    setNote((n) => n || (models.size
      ? `Written by ${[...models].join(", ")}${fell ? `; ${fell} part${fell > 1 ? "s" : ""} kept from our guides (the AI did not answer)` : ""}. Flights, drives and beds were checked against your text.`
      : "The AI is not available right now: this is still the plan from your text and our guides."));
  }

  return (
    <>
      <div className="mine">
        <label htmlFor="wishes"><b>Make it yours</b> <span>What do you want from these days? Pace, fitness, what you love or skip.</span></label>
        <textarea id="wishes" rows={2} value={wishes} maxLength={1500} onChange={(e) => setWishes(e.target.value)}
          placeholder="We walk slowly, one easy day after each big hike, no boats, we love wildlife" />
        <div className="mine-go">
          <button type="button" className="btn btn-primary" onClick={write} disabled={busy !== null}>
            {busy !== null ? `Writing part ${busy + 1} of ${groups}…` : "Write my days with AI"}
          </button>
          {note && <span className="small muted">{note}</span>}
        </div>
      </div>

      <ol className="dayrows booked">
        {timeline.map((t, k) => {
          const s = t.stop != null ? steps[t.stop] : null;
          const d = byDate.get(t.date);
          const newStop = s && t.stop_day === 1;
          return [
            newStop && (
              <li key={`h${k}`} className="dayband">
                <b>{s!.name}</b>
                <span>{s!.transit ? `between flights, ${s!.transit}` : `${s!.days} ${s!.days === 1 ? "night" : "nights"}`}
                  {s!.lodging ? ` · ${s!.lodging}` : ""}</span>
              </li>
            ),
            <li key={t.date} className="dayrow">
              <div className="dayrow-n"><b>Day {t.n}</b><span>{weekday(t.date)} {short(t.date)}</span></div>
              <div className="dayrow-body">
                {d && (
                  <>
                    <p className="dayrow-t">
                      <input className="day-title" value={d.title} aria-label="Day title"
                        onChange={(e) => setDay(d.date, (x) => ({ ...x, title: e.target.value }))} />
                      {d.priority != null && <span className={`prio prio-${Math.min(d.priority, 3)}`}>{prioName(d.priority)}</span>}
                      {weather.some((w) => w.drop === d.date) && <span className="prio prio-drop">First to drop if it rains</span>}
                    </p>
                    <ul className="hrs">
                      {d.rows.map((r, i) => (
                        <Row key={i} row={r}
                          onChange={(nr) => setDay(d.date, (x) => ({ ...x, rows: x.rows.map((y, j) => (j === i ? nr : y)) }))}
                          onDrop={() => setDay(d.date, (x) => ({ ...x, rows: x.rows.filter((_, j) => j !== i) }))} />
                      ))}
                    </ul>
                    <button type="button" className="link hr-add"
                      onClick={() => setDay(d.date, (x) => ({ ...x, rows: [...x.rows, { at: null, what: "", effort: null, optional: false, fixed: false }] }))}>
                      + Add a row
                    </button>
                  </>
                )}
                {t.sleep && "in_the_air" in t.sleep && <p className="sleep">Night on the plane</p>}
              </div>
            </li>,
          ];
        })}
      </ol>

      {weather.length > 0 && (
        <div className="wx-rules">
          <h3>If the weather turns</h3>
          <ul>
            {weather.map((w, i) => (
              <li key={i}>{w.area && <b>{w.area}: </b>}{w.how} <span className="muted">({weekday(w.drop)} {short(w.drop)})</span></li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
