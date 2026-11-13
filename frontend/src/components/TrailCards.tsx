import { Link } from "react-router-dom";
import type { TrailCard as Card, TrailDifficulty } from "../lib/types";
import { Illustration } from "./Illustration";

export const DIFFICULTY: Record<TrailDifficulty, string> = { easy: "Easy", moderate: "Moderate", hard: "Hard", technical: "Technical" };
const fmt = (n: number) => n.toLocaleString("en-US");

export function hoursText(h: [number, number], days: number): string {
  if (days > 1) return `${days} days`;
  const [lo, hi] = h;
  return hi > lo ? `${lo}–${hi} h` : `${lo} h`;
}

/** The numbers that decide a walk, in one line: km, climb, time, top. */
export function TrailFacts({ t }: { t: Card }) {
  return (
    <dl className="tfacts">
      {t.km != null && <div><dt>Distance</dt><dd>{fmt(Math.round(t.km))} km</dd></div>}
      {t.gain_m != null && <div><dt>Climb</dt><dd>+{fmt(Math.round(t.gain_m))} m</dd></div>}
      <div><dt>Time</dt><dd>{hoursText(t.hours, t.days)}</dd></div>
      {t.max_m != null && <div><dt>Highest</dt><dd>{fmt(t.max_m)} m</dd></div>}
    </dl>
  );
}

/** Trails as cards: the drawing, the numbers, how hard and when. `query` keeps the trip context
 *  (?trip=..&stop=..) so the trail page can add the walk to that stop. */
export function TrailCards({ trails, query = "" }: { trails: Card[]; query?: string }) {
  return (
    <ul className="tcards">
      {trails.map((t) => (
        <li key={t.id} className={`tcard${t.in_season === false ? " off" : ""}`}>
          <Link to={`/trails/${t.id}${query}`}>
            {t.art && <Illustration art={t.art} label={t.name} />}
            <div className="tcard-body">
              <div className="tags">
                <span className={`tag diff-${t.difficulty}`}>{DIFFICULTY[t.difficulty]}</span>
                {t.kind === "multiday" && <span className="tag">{t.days} days</span>}
                {t.glacier && <span className="tag">Glacier</span>}
                {t.in_season === false && <span className="tag warn">Not in season then</span>}
              </div>
              <h3>{t.name}</h3>
              <p className="small muted">From {t.base} · best {t.months_text}</p>
              <TrailFacts t={t} />
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
