/** The trip board's rules, run in the browser before asking the server (which checks again):
 * stops lie back to back on the days, free days between them stay where they are, and a change
 * may never move a fixed stop, a booked arrival or a booked flight home. When it would, we look
 * for the day elsewhere: "Take the day from El Calafate". */
import { addDays, daysBetween } from "./format";
import type { Activity, BoardStop, StopStatus } from "./types";

export interface Block {
  id: string;
  name: string;
  days: number;
  status: StopStatus;
  gap: number; // free days before it
  fixedNote?: string | null;
  arrivalBooked?: boolean;
}

export interface Placed extends Block { start: string; end: string }

export function blocksOf(stops: BoardStop[], start: string | null): Block[] {
  let cur = start;
  return stops.map((s) => {
    const gap = cur ? Math.max(0, daysBetween(cur, s.start_date)) : 0;
    cur = addDays(s.end_date, 1);
    return { id: s.id, name: s.name, days: s.days, status: s.status, gap, fixedNote: s.fixed_note,
      arrivalBooked: s.arrival.booked };
  });
}

export function place(blocks: Block[], start: string): Placed[] {
  let cur = start;
  return blocks.map((b) => {
    const s = addDays(cur, b.gap);
    const e = addDays(s, b.days - 1);
    cur = addDays(e, 1);
    return { ...b, start: s, end: e };
  });
}

/** Why the change can't be made, or null. */
export function blocked(before: Block[], after: Block[], start: string, returnBooked: boolean): string | null {
  const a = place(before, start), b = place(after, start);
  for (const x of a) {
    const y = b.find((z) => z.id === x.id);
    if (!y) continue;
    if (x.status === "fixed" && y.status === "fixed" && (x.start !== y.start || x.end !== y.end))
      return `${x.name} is fixed (${x.fixedNote || "booked"}): this change would move it.`;
    if (x.arrivalBooked && x.start !== y.start)
      return `Your booked way to ${x.name} is on that day: this change would move it.`;
  }
  if (returnBooked && a.length && b.length && a[a.length - 1].end !== b[b.length - 1].end)
    return "Your flight home is booked: this change would move the end of the trip.";
  return null;
}

export interface Fix { label: string; blocks: Block[] }

/** Ways to make a change that adds days fit: take them back from another stop that can move,
 * nearest first, or from the free days before the stop that would be pushed. */
export function fixes(before: Block[], after: Block[], start: string, returnBooked: boolean, changed: number): Fix[] {
  const extra = after.reduce((n, b) => n + b.days + b.gap, 0) - before.reduce((n, b) => n + b.days + b.gap, 0);
  if (extra <= 0) return [];
  const order = after.map((_, i) => i).filter((i) => i !== changed)
    .sort((i, j) => Math.abs(i - changed) - Math.abs(j - changed) || i - j);
  const out: Fix[] = [];
  for (const i of order) {
    const b = after[i];
    if (b.gap >= extra) {
      const t = after.map((x, k) => (k === i ? { ...x, gap: x.gap - extra } : x));
      if (!blocked(before, t, start, returnBooked)) out.push({ label: `Use the free days before ${b.name}`, blocks: t });
    }
    if (b.status !== "fixed" && b.days - extra >= 1) {
      const t = after.map((x, k) => (k === i ? { ...x, days: x.days - extra } : x));
      if (!blocked(before, t, start, returnBooked))
        out.push({ label: `Take ${extra === 1 ? "the day" : `${extra} days`} from ${b.name}`, blocks: t });
    }
    if (out.length >= 2) break;
  }
  return out;
}

export function resize(blocks: Block[], i: number, delta: number): Block[] {
  return blocks.map((b, k) => (k === i ? { ...b, days: Math.max(1, b.days + delta) } : b));
}

/** Swap with the neighbour; free days stay where they were on the board. */
export function move(blocks: Block[], i: number, dir: -1 | 1): Block[] {
  const j = i + dir;
  if (j < 0 || j >= blocks.length) return blocks;
  const out = blocks.map((b) => ({ ...b }));
  const gi = out[i].gap, gj = out[j].gap;
  [out[i], out[j]] = [out[j], out[i]];
  out[i].gap = gi;
  out[j].gap = gj;
  return out;
}

/** Remove a stop: its days close up, unless something booked comes after it; then they stay
 * as free days. */
export function remove(blocks: Block[], i: number, start: string, returnBooked: boolean): Block[] {
  const closed = blocks.filter((_, k) => k !== i);
  if (!blocked(blocks, closed, start, returnBooked)) return closed;
  return closed.map((b, k) => (k === i ? { ...b, gap: b.gap + blocks[i].days + blocks[i].gap } : b));
}

const DIFF = ["easy", "moderate", "hard", "technical"];

/** What the planned things to do mean for the clothes: one activity per type, the hardest
 * hike and the highest point. */
export function activitiesFrom(acts: (Activity | null | undefined)[]): Activity[] {
  const by = new Map<string, Activity>();
  for (const a of acts) {
    if (!a) continue;
    const k = a.type;
    const cur = by.get(k);
    if (!cur) { by.set(k, { ...a }); continue; }
    if (a.difficulty && DIFF.indexOf(a.difficulty) > DIFF.indexOf(cur.difficulty ?? "")) cur.difficulty = a.difficulty;
    if ((a.max_altitude_m ?? 0) > (cur.max_altitude_m ?? 0)) cur.max_altitude_m = a.max_altitude_m;
    if (a.glacier) cur.glacier = true;
  }
  return [...by.values()];
}

export function sameActivities(a: Activity[], b: Activity[]): boolean {
  const key = (x: Activity) => `${x.type}|${x.difficulty ?? ""}|${Math.round(x.max_altitude_m ?? 0)}|${x.glacier ? 1 : 0}`;
  const ka = a.map(key).sort().join(";"), kb = b.map(key).sort().join(";");
  return ka === kb;
}
