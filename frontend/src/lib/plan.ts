/* The route being started, before it is a trip: dates follow the days, a stop with its own
   date starts then. Pure functions (Manu, 2026-11-12). */
import { addDays, MONTHS } from "./format";
import type { PlanStep } from "./types";

export interface Dated { start: string; end: string; gap: number }

/** Each step's days on the calendar from `start`; a step with its own date waits for it. */
export function dated(steps: PlanStep[], start: string | null): (Dated | null)[] {
  let cur = start;
  // no start but a later stop has a date: count back from it
  if (!cur) {
    const i = steps.findIndex((s) => s.start_date);
    if (i >= 0) cur = addDays(steps[i].start_date!, -steps.slice(0, i).reduce((n, s) => n + s.days, 0));
  }
  return steps.map((s) => {
    if (!cur) return null;
    let gap = 0;
    if (s.start_date && s.start_date > cur) {
      gap = Math.round((Date.parse(s.start_date) - Date.parse(cur)) / 86400000);
      cur = s.start_date;
    }
    const d = { start: cur, end: addDays(cur, s.days - 1), gap };
    cur = addDays(d.end, 1);
    return d;
  });
}

export const totalDays = (steps: PlanStep[]) => steps.reduce((n, s) => n + s.days, 0);

export function short(d: string): string {
  const x = new Date(d + "T12:00:00Z");
  return `${x.getUTCDate()} ${MONTHS[x.getUTCMonth()]}`;
}

export function span(d: Dated): string {
  return d.start === d.end ? short(d.start) : `${short(d.start)} – ${short(d.end)}`;
}

/** Changing a step's days: later steps with their own dates keep them (and the days between
 * them shrink or grow), the rest move. */
export function setDays(steps: PlanStep[], i: number, days: number): PlanStep[] {
  return steps.map((s, j) => (j === i ? { ...s, days: Math.max(1, Math.min(60, days)) } : s));
}

export function move(steps: PlanStep[], i: number, by: -1 | 1): PlanStep[] {
  const j = i + by;
  if (j < 0 || j >= steps.length) return steps;
  const out = [...steps];
  [out[i], out[j]] = [out[j], out[i]];
  // a date stays with its place only if it still comes after the stop before
  return out.map((s) => ({ ...s, start_date: s.fixed_dates ? s.start_date : null }));
}

/** The first day of a month, this year or next, never in the past. */
export function firstOf(month: number, todayIso: string): string {
  const y = Number(todayIso.slice(0, 4));
  const d = `${y}-${String(month).padStart(2, "0")}-01`;
  return d >= todayIso.slice(0, 7) + "-01" && d > todayIso ? d : `${y + 1}-${String(month).padStart(2, "0")}-01`;
}

export const LENGTHS: [string, number][] = [["A weekend", 3], ["1 week", 7], ["10 days", 10], ["2 weeks", 14], ["3 weeks", 21], ["4 weeks", 28]];
