import type { PlanDay, PlanStep } from "./types";

/** The days of a step as long as the traveller made it: the proposed days first; a day added
 * takes the next thing trips do from there, then stays free; a day taken off drops the last. */
export function daysOf(s: PlanStep): PlanDay[] {
  const plan = (s.plan ?? []).filter((d) => d.day <= s.days);
  // a trek cut short by the days left is not a trek: keep only what fits
  const out: PlanDay[] = plan.map((d) => (d.days && d.day + d.days - 1 > s.days ? { ...d, days: s.days - d.day + 1 } : d));
  const also = [...(s.also ?? [])];
  for (let d = out.length + 1; d <= s.days; d++) {
    const next = also.shift();
    out.push(next ? { day: d, kind: "day", sights: [next] } : { day: d, kind: "free", sights: [] });
  }
  return out;
}

/** One line for a day: "Arrive · Raqchi on the way", "Machu Picchu · Huayna Picchu", "Free day". */
export function dayText(d: PlanDay, first: boolean): string {
  const list = d.sights.join(" · ");
  if (d.kind === "arrive") return list ? `${first ? "Start" : "Arrive"} · on the way: ${list}` : first ? "Start" : "Arrive, settle in";
  if (d.kind === "more") return `${d.of ?? "Trip out"}, continued`;
  if (d.kind === "free") return "Free day: at your pace, or a spare day for the weather";
  return d.days && d.days > 1 ? `${list} (${d.days} days)` : list;
}
