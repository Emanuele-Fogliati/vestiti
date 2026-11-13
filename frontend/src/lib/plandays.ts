import { legText, legWeight, type Leg } from "./travel";
import type { PlanDay, PlanStep } from "./types";

/** The days of a step as long as the traveller made it: the proposed days first; a day added
 * takes the next thing to do from there (from the guide when one is written, else what trips
 * do), then stays free; a day taken off drops the last. */
export function daysOf(s: PlanStep): PlanDay[] {
  const plan = (s.plan ?? []).filter((d) => d.day <= s.days);
  // a trek cut short by the days left is not a trek: keep only what fits
  const out: PlanDay[] = plan.map((d) => (d.days && d.day + d.days - 1 > s.days ? { ...d, days: s.days - d.day + 1 } : d));
  const things = [...(s.more_things ?? [])];
  const also = things.length ? [] : [...(s.also ?? [])];
  for (let d = out.length + 1; d <= s.days; d++) {
    const t = things.shift();
    const next = also.shift();
    if (t) out.push({ day: d, kind: "day", sights: [t.name], items: [t] });
    else out.push(next ? { day: d, kind: "day", sights: [next] } : { day: d, kind: "free", sights: [] });
  }
  return out;
}

/** One line for a day: "Arrive · Raqchi on the way", "Machu Picchu · Huayna Picchu", "Free day".
 * The arrival day says how you get there: a long road makes it a travel day. */
export function dayText(d: PlanDay, first: boolean, travel?: { from: string; leg: Leg }): string {
  const list = d.items?.length ? d.items.map((t) => t.name).join(" · ") : d.sights.join(" · ");
  if (d.kind === "arrive") {
    const how = travel && legText(travel.leg);
    if (!first && travel && how) {
      const go = `From ${travel.from}: ${how.charAt(0).toLowerCase()}${how.slice(1)}`;
      const w = legWeight(travel.leg);
      if (w === "full") return list ? `${go}. Travel day · if you arrive early: ${list}` : `${go}. Travel day`;
      if (d.items?.length) return `${go} · then ${list}`;
      return list ? `${go} · on the way: ${list}` : `${go} · settle in`;
    }
    if (d.items?.length) return `${first ? "Start" : "Arrive"} · then ${list}`;
    return list ? `${first ? "Start" : "Arrive"} · on the way: ${list}` : first ? "Start" : "Arrive, settle in";
  }
  if (d.kind === "more") return `${d.of ?? "Trip out"}, continued`;
  if (d.kind === "free") return "Free day: at your pace, or a spare day for the weather";
  return d.days && d.days > 1 ? `${list} (${d.days} days)` : list;
}

/** The trip day each step starts on (1 for the first): the days before it, and the free days
 * waiting for a later fixed date. Days are counted across the whole trip, never per stop. */
export function firstDays(steps: { days: number }[], gaps: number[] = []): number[] {
  let n = 1;
  return steps.map((s, i) => {
    n += gaps[i] ?? 0;
    const at = n;
    n += s.days;
    return at;
  });
}
