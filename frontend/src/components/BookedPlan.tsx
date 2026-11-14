/* A trip already booked, told in detail (Manu, 2026-11-14): every day with its moves (flight,
   car, taxi: times, layovers, borders, the car picked up and returned), what to do there, and
   the bed you sleep in. Read by services/booked.py; the stops below it are the bases. */
import { daysOf } from "../lib/plandays";
import { short } from "../lib/plan";
import type { BookedDay, BookedLeg, PlanStep } from "../lib/types";
import HourByHour from "./HourByHour";

const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const weekday = (iso: string) => WD[new Date(iso + "T12:00:00Z").getUTCDay()];
const MODE: Record<string, string> = { flight: "Flight", car: "Car", transfer: "Transfer" };
const modeName = (m: string) => MODE[m] ?? m.charAt(0).toUpperCase() + m.slice(1);

function Leg({ leg }: { leg: BookedLeg }) {
  const at = (name: string | null, ap: string | null) => (name && ap && ap !== name ? `${name} (${ap})` : ap ?? name ?? "");
  const next = leg.arr_date && leg.date && leg.arr_date !== leg.date ? ` ${weekday(leg.arr_date)} ${short(leg.arr_date)}` : "";
  const meta = [
    leg.via.length ? `via ${leg.via.join(", ")}` : "",
    ...leg.stops.map((s) => `stop at ${s.name}${s.when ? `, ${s.when}` : ""}`),
    ...leg.notes,
  ].filter(Boolean);
  return (
    <li className={`leg leg-${leg.mode === "flight" ? "flight" : leg.mode === "car" ? "car" : "other"}`}>
      <span className="leg-mode">{modeName(leg.mode)}</span>
      <div className="leg-main">
        <span className="leg-route">
          {leg.dep && <time>{leg.dep}</time>} {at(leg.from, leg.from_airport)} → {at(leg.to, leg.to_airport)}
          {(leg.arr || leg.arr_part) && <span className="leg-arr"> · arrive {leg.arr ?? `in the ${leg.arr_part}`}{next}</span>}
        </span>
        {meta.length > 0 && <span className="leg-meta">{meta.join(" · ")}</span>}
      </div>
    </li>
  );
}

export default function BookedPlan({ steps, timeline }: { steps: PlanStep[]; timeline: BookedDay[] }) {
  const plans = steps.map((s) => daysOf(s));
  return (
    <ol className="dayrows booked">
      {timeline.map((d, k) => {
        const s = d.stop != null ? steps[d.stop] : null;
        const pd = s && d.stop_day ? plans[d.stop!][d.stop_day - 1] : null;
        const items = pd?.items ?? [];
        const what = items.length ? items.map((t) => t.name).join(" · ")
          : pd && pd.kind !== "arrive" ? (pd.kind === "free" ? "Free day: at your pace, or a spare day for the weather" : pd.sights.join(" · ")) : "";
        const newStop = s && d.stop_day === 1;
        const sleep = d.sleep;
        return [
          newStop && (
            <li key={`h${k}`} className="dayband">
              <b>{s!.name}</b>
              <span>{s!.transit ? `between flights, ${s!.transit}` : `${s!.days} ${s!.days === 1 ? "night" : "nights"}`}
                {s!.lodging ? ` · ${s!.lodging}` : ""}</span>
            </li>
          ),
          <li key={d.date} className={`dayrow${pd?.kind === "free" ? " sd-free" : ""}`}>
            <div className="dayrow-n"><b>Day {d.n}</b><span>{weekday(d.date)} {short(d.date)}</span></div>
            <div className="dayrow-body">
              {d.legs.length > 0 && <ul className="legs">{d.legs.map((l, i) => <Leg key={i} leg={l} />)}</ul>}
              {what && <p className="dayrow-t">{what}</p>}
              {items.map((t) => (
                <HourByHour key={t.id} steps={t.steps} extras={t.extras} book={t.book}
                  label={items.length > 1 ? `${t.name}: hour by hour` : "Hour by hour"} />
              ))}
              {sleep && ("in_the_air" in sleep
                ? <p className="sleep">Night on the plane</p>
                : <p className="sleep">Sleep · {sleep.name ?? sleep.town}{sleep.address ? `, ${sleep.address}` : ""}</p>)}
            </div>
          </li>,
        ];
      })}
    </ol>
  );
}
