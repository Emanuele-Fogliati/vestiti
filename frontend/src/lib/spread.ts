import { addDays, nights } from "./format";

/** Days per stop when the traveller did not say how long (same rule as the API,
 * backend/app/services/dates.py): known days stay, the others share what is left of the
 * total as evenly as possible (earlier stops get the extra day), at least one day each. */
export function spread(known: (number | null)[], total: number | null, perPlace = 2): number[] {
  const free = known.flatMap((k, i) => (k === null ? [i] : []));
  const out = known.map((k) => k ?? 0);
  if (!free.length) return out;
  const fixed = known.reduce<number>((a, k) => a + (k ?? 0), 0);
  const left = total === null ? perPlace * free.length : Math.max(total - fixed, free.length);
  const base = Math.floor(left / free.length), extra = left % free.length;
  free.forEach((i, j) => { out[i] = base + (j < extra ? 1 : 0); });
  return out;
}

/** Back-to-back stops from `start`. */
export function layOut(days: number[], start: string): [string, string][] {
  let cur = start;
  return days.map((d) => {
    const end = addDays(cur, Math.max(d, 1) - 1);
    const r: [string, string] = [cur, end];
    cur = addDays(end, 1);
    return r;
  });
}

type Dated = { start_date: string; end_date: string; days_estimated?: boolean; visits?: { date?: string | null }[] };

/** Move a visit with its stop: it keeps its day within the stop, never past the end. */
function moveVisits<T extends Dated>(s: T, start: string, end: string): T["visits"] {
  return s.visits?.map((v) => {
    if (!v.date) return v;
    let d = addDays(start, nights(s.start_date, v.date) - 1);
    if (d > end) d = end;
    if (d < start) d = start;
    return { ...v, date: d };
  });
}

/** The draft or trip with a new start and/or total length: a start moves every stop, a total
 * spreads the guessed stops over it. Stops whose days were chosen keep them. */
export function redate<T extends Dated>(stops: T[], opts: { start?: string; total?: number }): T[] {
  if (!stops.length) return stops;
  const first = stops.reduce((m, s) => (s.start_date < m ? s.start_date : m), stops[0].start_date);
  const start = opts.start || first;
  if (opts.total) {
    const known = stops.map((s) => (s.days_estimated ? null : nights(s.start_date, s.end_date)));
    const dates = layOut(spread(known, opts.total), start);
    return stops.map((s, i) => ({ ...s, start_date: dates[i][0], end_date: dates[i][1], visits: moveVisits(s, dates[i][0], dates[i][1]) }));
  }
  const shift = nights(first, start) - 1;
  return stops.map((s) => {
    const a = addDays(s.start_date, shift), b = addDays(s.end_date, shift);
    return { ...s, start_date: a, end_date: b, visits: moveVisits(s, a, b) };
  });
}
