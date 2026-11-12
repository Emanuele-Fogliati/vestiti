/* Multi-city flights: every flight of the day per leg, and the checks between the picks
   (Manu, 2026-11-12: "un'ora prima, un'ora dopo", and many legs at once). Pure functions. */
import type { FlightLeg, FlightOffer } from "./types";

/** Duffel times are local to the airport, without an offset: "2026-12-03T08:15:00". */
export const hhmm = (iso: string | null | undefined) => (iso ? iso.slice(11, 16) : "—");
export const dayOf = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : "");
/** Minutes after midnight of the departure, for the day strip. */
export const minuteOfDay = (iso: string | null | undefined) =>
  iso ? Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16)) : 0;

export function duration(min: number | null): string {
  if (min == null) return "";
  const h = Math.floor(min / 60), m = min % 60;
  return h ? `${h} h${m ? ` ${String(m).padStart(2, "0")}` : ""}` : `${m} min`;
}

export function shiftDay(day: string, n: number): string {
  const d = new Date(day + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export function daysApart(a: string, b: string): number {
  return Math.round((new Date(b + "T12:00:00Z").getTime() - new Date(a + "T12:00:00Z").getTime()) / 86400000);
}

export interface FlightFilter { direct: boolean; sort: "time" | "price"; from?: number; to?: number }

/** The offers to show: direct only if asked, inside the hours asked, in time or price order. */
export function visible(offers: FlightOffer[], f: FlightFilter): FlightOffer[] {
  const out = offers.filter((o) => {
    const s = o.slices[0];
    if (!s) return false;
    if (f.direct && s.stops > 0) return false;
    const m = minuteOfDay(s.departs);
    if (f.from != null && m < f.from * 60) return false;
    if (f.to != null && m > f.to * 60) return false;
    return true;
  });
  return out.sort(f.sort === "price"
    ? (a, b) => a.price - b.price
    : (a, b) => (a.slices[0].departs ?? "").localeCompare(b.slices[0].departs ?? "") || a.price - b.price);
}

export function cheapest(offers: FlightOffer[]): FlightOffer | null {
  return offers.reduce<FlightOffer | null>((m, o) => (!m || o.price < m.price ? o : m), null);
}

/** The fastest of the day, by total time. */
export function fastest(offers: FlightOffer[]): FlightOffer | null {
  return offers.reduce<FlightOffer | null>((m, o) => {
    const t = o.slices[0]?.minutes ?? Infinity, mt = m?.slices[0]?.minutes ?? Infinity;
    return !m || t < mt ? o : m;
  }, null);
}

export interface Check { level: "bad" | "warn" | "ok"; text: string }

const MIN_SEPARATE_H = 3;

/** What the picks mean for the days and for each other. Legs and picks in trip order. */
export function checks(legs: FlightLeg[], picks: (FlightOffer | null)[]): Check[][] {
  return legs.map((leg, i) => {
    const out: Check[] = [];
    const p = picks[i]?.slices[0];
    if (!p) return out;
    const dep = dayOf(p.departs), arr = dayOf(p.arrives);
    const off = dep ? daysApart(leg.date, dep) : 0;
    if (off !== 0) {
      const where = leg.stop_id ? `${leg.to_name} starts on ${nice(leg.date)}` : `your flight home is planned for ${nice(leg.date)}`;
      out.push({ level: "warn", text: `This flight is ${Math.abs(off)} day${Math.abs(off) > 1 ? "s" : ""} ${off < 0 ? "earlier" : "later"}: ${where}. Move the days on the board, or pick a flight on that day.` });
    }
    if (dep && arr && arr > dep) out.push({ level: "warn", text: `Lands the next day, ${nice(arr)}.` });
    const next = picks[i + 1]?.slices[0];
    if (next?.departs && p.arrives) {
      if (next.departs < p.arrives && next.origin === p.destination) {
        out.push({ level: "bad", text: `The next flight leaves before this one lands.` });
      } else if (next.origin === p.destination) {
        const gap = (Date.parse(next.departs + "Z") - Date.parse(p.arrives + "Z")) / 3600000;
        if (gap < MIN_SEPARATE_H) {
          out.push({ level: "bad", text: `Only ${gap < 1 ? `${Math.round(gap * 60)} min` : `${gap.toFixed(1).replace(/\.0$/, "")} h`} before the next flight, on a separate ticket: if this one is late, nobody waits for you. Leave at least ${MIN_SEPARATE_H} h, or buy them as one ticket.` });
        }
      } else if (dayOf(next.departs) === arr) {
        out.push({ level: "warn", text: `The next flight leaves from ${next.origin}, not ${p.destination}, the same day: check how you get there.` });
      }
    }
    return out;
  });
}

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export function nice(day: string): string {
  const d = new Date(day + "T12:00:00Z");
  return `${DOW[d.getUTCDay()]} ${d.getUTCDate()} ${MON[d.getUTCMonth()]}`;
}

/** The sum of the picks when they are all in one currency. */
export function total(picks: (FlightOffer | null)[]): { amount: number; currency: string; count: number } | null {
  const ps = picks.filter((p): p is FlightOffer => !!p);
  if (!ps.length || new Set(ps.map((p) => p.currency)).size > 1) return null;
  return { amount: ps.reduce((s, p) => s + p.price, 0), currency: ps[0].currency, count: ps.length };
}

/** One line for the board: "AR 1874 08:15 → 11:30". */
export function pickNote(o: FlightOffer): string {
  const s = o.slices[0];
  const fl = s.segments.map((g) => g.flight).filter(Boolean).join(" + ");
  return `${fl} ${hhmm(s.departs)} → ${hhmm(s.arrives)}${dayOf(s.arrives) > dayOf(s.departs) ? " (+1)" : ""}`.trim().slice(0, 200);
}

export function money(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);
  } catch {
    return `${Math.round(amount)} ${currency}`;
  }
}
