import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { dayMonth, daysBetween, minus } from "../lib/format";
import type { Board, BoardLeg, Stop } from "../lib/types";
import { Illustration } from "./Illustration";

const ICON: Record<string, string> = {
  flight: "M21 15.5l-8-4.5V5.5a1.5 1.5 0 0 0-3 0V11l-8 4.5V17l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-4.5l8 2.5z",
  bus: "M6 3h12a2 2 0 0 1 2 2v12h-1v2.5h-3V17H8v2.5H5V17H4V5a2 2 0 0 1 2-2z M6 6v5h12V6z",
  car: "M5 11l2-5h10l2 5h1v6h-2v2h-3v-2H9v2H6v-2H4v-6z M7.5 11h9l-1.2-3H8.7z",
  boat: "M3 16l2 4h14l2-4H3zM6 15V9h5V4l7 11H6z",
  train: "M7 3h10a3 3 0 0 1 3 3v9a3 3 0 0 1-2 2.8l1.5 2.2h-2.4L16 18H8l-1.1 2H4.5L6 17.8A3 3 0 0 1 4 15V6a3 3 0 0 1 3-3zm-1 4v4h12V7z",
};

function legText(l: BoardLeg): string {
  const h = l.hours ? (l.hours < 1 ? `${Math.round(l.hours * 60)} min` : `${Math.round(l.hours * 10) / 10} h`) : "";
  const how = l.mode === "flight" ? "Flight" : l.mode === "local" ? "Short hop" : l.mode === "boat" ? "Boat" : l.mode === "train" ? "Train" : "By road";
  return [how, `to ${l.to_name}`, h].filter(Boolean).join(" · ");
}

/** The trip as a timeline (design R16): each stop with its drawing, the way between stops, and,
 *  when you open a stop, its days with the drawing of what you do. Opening a stop flies the map
 *  to it. No clothes here: packing is the next step. */
export function TripTimeline({ tripId, stops, open, onOpen, version }: {
  tripId: string; stops: Stop[]; open: number | null; onOpen: (i: number | null) => void; version: number;
}) {
  const [board, setBoard] = useState<Board | null>(null);
  useEffect(() => { api.board(tripId).then(setBoard).catch(() => setBoard(null)); }, [tripId, version]);
  const t0 = stops.length ? stops.reduce((m, s) => (s.start_date < m ? s.start_date : m), stops[0].start_date) : null;
  const dayNo = (d: string) => (t0 ? daysBetween(t0, d) + 1 : 0);

  return (
    <ol className="tl">
      {stops.map((s, i) => {
        const b = board?.stops.find((x) => x.id === s.id);
        const leg = i > 0 ? b?.arrival : null;
        const isOpen = open === i;
        const a = dayNo(s.start_date), z = dayNo(s.end_date);
        return (
          <li key={s.id} className={`tl-stop${isOpen ? " open" : ""}`}>
            {leg && (
              <div className="tl-leg">
                <span className="tl-leg-ic"><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d={ICON[leg.mode] ?? ICON.bus} fill="currentColor" fillRule="evenodd" /></svg></span>
                <span>Day {a} · {legText(leg)}</span>
              </div>
            )}
            <button type="button" className="tl-head" aria-expanded={isOpen} onClick={() => onOpen(isOpen ? null : i)}>
              <span className="tl-av">{s.art ? <Illustration art={s.art} /> : <i>{i + 1}</i>}</span>
              <span className="tl-name"><b>{s.name}</b><small>{a === z ? `Day ${a}` : `Days ${a}–${z}`} · {dayMonth(s.start_date)}{s.end_date !== s.start_date ? ` – ${dayMonth(s.end_date)}` : ""}</small></span>
            </button>
            {isOpen && (
              <div className="tl-days">
                {!b && <p className="tl-wait"><span className="spin" /></p>}
                {b?.plan.days.map((d) => {
                  const pic = d.things.find((t) => t.art)?.art ?? s.art;
                  const what = d.things.length ? d.things.map((t) => t.name).join(" · ") : d.title;
                  return (
                    <div key={d.date} className="tl-day">
                      <span className="tl-pic">{pic ? <Illustration art={pic} /> : null}</span>
                      <span className="tl-dt">
                        <small>Day {dayNo(d.date)} · {dayMonth(d.date)} · {minus(d.tmin)}–{minus(d.tmax)}°{d.rain_chance >= 40 ? ` · ${d.rain_chance}% rain` : ""}</small>
                        <b>{what || "Free day"}</b>
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
